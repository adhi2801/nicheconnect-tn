"""The data export, built in the background and downloaded once (D-111), through the API.

Asking with a code; the job building it and telling the owner; the one
download, with a code for that export, destroying the stored copy; an
unclaimed one destroyed after 24 hours; a failure; and nobody else's export
ever reachable. What the file holds is tests/modules/me/test_export_api.py.
"""

import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.core.storage import memory_store
from app.modules.me import data_export_service, export_service
from app.modules.me.data_export_service import RECENT_EXPORTS
from app.modules.me.export_models import EXPORT_KEPT_FOR, DataExport, object_key
from app.modules.notifications.models import Notification
from tests.deal_flow import User, creator_user
from tests.step_up import (
    EXPORT_URL,
    STEP_UP_URL,
    ask_for_code,
    ask_for_export,
    build_exports,
    download_ready_export,
    with_code,
)


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.commit()
    return user


@pytest.fixture(autouse=True)
def empty_store():
    memory_store().clear()
    yield
    memory_store().clear()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def told(db, user: User, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


def read(client, user: User, export_id: str):
    return client.get(f"{EXPORT_URL}/{export_id}", headers=user.headers)


def stamp(moment) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def ready_export(client, user: User) -> str:
    export_id = ask_for_export(client, user.headers)
    build_exports()
    return export_id


# --- asking ----------------------------------------------------------------------------


def test_asking_answers_at_once_and_the_export_is_prepared(client, clock, creator):
    response = client.post(
        EXPORT_URL, headers=with_code(client, creator.headers, "download_export")
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "preparing"
    assert body["requested_at"] == stamp(clock.now)
    assert (body["ready_at"], body["expires_at"], body["size_bytes"]) == (
        None,
        None,
        None,
    )
    assert read(client, creator, body["id"]).json() == body


def test_asking_needs_a_code(client, creator):
    response = client.post(EXPORT_URL, headers=creator.headers)

    assert_problem(response, 401, "step_up_required")


def test_one_is_prepared_at_a_time_and_a_refusal_spends_no_code(client, creator):
    ask_for_export(client, creator.headers)
    code = ask_for_code(client, creator.headers, "download_export")

    refused = client.post(EXPORT_URL, headers={**creator.headers, "Step-Up-Code": code})
    build_exports()
    accepted = client.post(EXPORT_URL, headers={**creator.headers, "Step-Up-Code": code})

    assert_problem(refused, 409, "export_already_preparing")
    assert accepted.status_code == 202, accepted.text


def test_signed_out_nobody_may_ask_read_list_or_download(client, creator):
    export_id = ready_export(client, creator)

    assert client.post(EXPORT_URL).status_code == 401
    assert client.get(EXPORT_URL).status_code == 401
    assert client.get(f"{EXPORT_URL}/{export_id}").status_code == 401
    assert client.post(f"{EXPORT_URL}/{export_id}/download").status_code == 401


# --- the job ---------------------------------------------------------------------------


def test_the_job_builds_it_stores_it_and_tells_the_owner(client, db, clock, creator):
    export_id = ask_for_export(client, creator.headers)

    run = build_exports()

    assert (run.built, run.failed) == (1, 0)
    body = read(client, creator, export_id).json()
    assert body["status"] == "ready"
    assert body["expires_at"] == stamp(clock.now + EXPORT_KEPT_FOR)
    stored = memory_store().read(object_key_for(export_id), max_bytes=10**8)
    assert body["size_bytes"] == len(stored)
    assert json.loads(stored)["account_id"] == str(creator.account_id)
    [notice] = told(db, creator, "data_export_ready")
    assert notice.details == {
        "export_id": export_id,
        "expires_at": (clock.now + EXPORT_KEPT_FOR).isoformat(),
    }


def object_key_for(export_id: str) -> str:
    import uuid

    return object_key(uuid.UUID(export_id))


def test_running_the_job_again_builds_nothing_twice(client, db, creator):
    ask_for_export(client, creator.headers)

    first, second = build_exports(), build_exports()

    assert (first.built, second.built) == (1, 0)
    assert len(told(db, creator, "data_export_ready")) == 1


def test_a_build_that_fails_is_marked_and_another_may_be_asked(
    client, db, creator, monkeypatch
):
    export_id = ask_for_export(client, creator.headers)

    def broken(*args, **kwargs):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(export_service, "build_export", broken)
    run = build_exports()
    monkeypatch.undo()

    assert (run.built, run.failed) == (0, 1)
    assert read(client, creator, export_id).json()["status"] == "failed"
    assert memory_store().keys() == set()
    assert told(db, creator, "data_export_ready") == []
    limiter.reset()
    assert (
        client.post(
            EXPORT_URL, headers=with_code(client, creator.headers, "download_export")
        ).status_code
        == 202
    )


def test_a_file_over_the_size_cap_fails_and_is_never_stored(
    client, db, creator, monkeypatch
):
    export_id = ask_for_export(client, creator.headers)
    monkeypatch.setattr(data_export_service, "MAX_EXPORT_BYTES", 10)

    run = build_exports()

    assert (run.built, run.failed) == (0, 1)
    assert read(client, creator, export_id).json()["status"] == "failed"
    assert memory_store().keys() == set()


def test_a_failed_export_cannot_be_downloaded(client, creator, monkeypatch):
    export_id = ask_for_export(client, creator.headers)
    monkeypatch.setattr(data_export_service, "MAX_EXPORT_BYTES", 10)
    build_exports()

    asked = client.post(
        STEP_UP_URL,
        json={"action": "download_export", "export_id": export_id},
        headers=creator.headers,
    )

    assert_problem(asked, 409, "export_failed")


# --- downloading -----------------------------------------------------------------------


def test_downloading_gives_the_file_once_and_destroys_it(client, db, creator):
    export_id = ready_export(client, creator)
    stored = memory_store().read(object_key_for(export_id), max_bytes=10**8)

    response = download_ready_export(client, creator.headers, export_id)

    assert response.status_code == 200, response.text
    assert response.content == stored
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert memory_store().keys() == set()
    assert read(client, creator, export_id).json()["status"] == "downloaded"
    assert len(told(db, creator, "data_exported")) == 1


def test_a_second_download_is_refused_before_any_code_is_sent(client, creator):
    export_id = ready_export(client, creator)
    assert download_ready_export(client, creator.headers, export_id).status_code == 200

    asked = client.post(
        STEP_UP_URL,
        json={"action": "download_export", "export_id": export_id},
        headers=creator.headers,
    )

    assert_problem(asked, 409, "export_already_downloaded")


def test_a_download_needs_a_code_for_that_export(client, creator):
    export_id = ready_export(client, creator)
    for_asking = ask_for_code(client, creator.headers, "download_export")

    no_code = client.post(f"{EXPORT_URL}/{export_id}/download", headers=creator.headers)
    wrong_code = client.post(
        f"{EXPORT_URL}/{export_id}/download",
        headers={**creator.headers, "Step-Up-Code": for_asking},
    )

    assert_problem(no_code, 401, "step_up_required")
    assert_problem(wrong_code, 400, "step_up_code_invalid")
    assert read(client, creator, export_id).json()["status"] == "ready"


def test_a_code_for_one_export_cannot_download_another(client, creator):
    first = ready_export(client, creator)
    limiter.reset()
    second = ready_export(client, creator)
    for_first = ask_for_code(client, creator.headers, "download_export", export_id=first)

    refused = client.post(
        f"{EXPORT_URL}/{second}/download",
        headers={**creator.headers, "Step-Up-Code": for_first},
    )
    accepted = client.post(
        f"{EXPORT_URL}/{first}/download",
        headers={**creator.headers, "Step-Up-Code": for_first},
    )

    assert_problem(refused, 400, "step_up_code_invalid")
    assert accepted.status_code == 200, accepted.text


def test_one_still_being_prepared_cannot_be_downloaded(client, creator):
    export_id = ask_for_export(client, creator.headers)

    asked = client.post(
        STEP_UP_URL,
        json={"action": "download_export", "export_id": export_id},
        headers=creator.headers,
    )

    assert_problem(asked, 409, "export_not_ready")


# --- the 24 hours ----------------------------------------------------------------------


def test_it_can_be_downloaded_until_its_last_second(client, clock, creator):
    export_id = ready_export(client, creator)
    clock.advance(EXPORT_KEPT_FOR - timedelta(seconds=1))

    assert download_ready_export(client, creator.headers, export_id).status_code == 200


def test_after_24_hours_it_is_destroyed_and_cannot_be_had(client, db, clock, creator):
    export_id = ready_export(client, creator)
    clock.advance(EXPORT_KEPT_FOR)

    run = build_exports()
    asked = client.post(
        STEP_UP_URL,
        json={"action": "download_export", "export_id": export_id},
        headers=creator.headers,
    )

    assert run.expired == 1
    assert memory_store().keys() == set()
    assert read(client, creator, export_id).json()["status"] == "expired"
    assert_problem(asked, 409, "export_expired")
    row = db.scalars(
        select(DataExport)
        .where(DataExport.account_id == creator.account_id)
        .execution_options(populate_existing=True)
    ).one()
    assert row.file_deleted_at == clock.now
    assert build_exports().expired == 0


# --- nobody else's ---------------------------------------------------------------------


def test_nobody_else_can_see_ask_for_or_download_it(client, db, clock, creator):
    export_id = ready_export(client, creator)
    someone = creator_user(db, clock)
    db.commit()

    seen = read(client, someone, export_id)
    asked = client.post(
        STEP_UP_URL,
        json={"action": "download_export", "export_id": export_id},
        headers=someone.headers,
    )
    taken = client.post(
        f"{EXPORT_URL}/{export_id}/download",
        headers={**someone.headers, "Step-Up-Code": "123456"},
    )

    assert_problem(seen, 404, "export_not_found")
    assert_problem(asked, 404, "export_not_found")
    assert_problem(taken, 404, "export_not_found")
    assert client.get(EXPORT_URL, headers=someone.headers).json()["items"] == []
    assert memory_store().keys() == {object_key_for(export_id)}


def test_the_list_holds_the_newest_five(client, clock, creator):
    made = []
    for _ in range(RECENT_EXPORTS + 1):
        # Past the phone's own cap on codes, and the limiter's (real time).
        clock.advance(timedelta(minutes=10))
        limiter.reset()
        made.append(ready_export(client, creator))

    items = client.get(EXPORT_URL, headers=creator.headers).json()["items"]

    assert [item["id"] for item in items] == list(reversed(made))[:RECENT_EXPORTS]


def test_the_file_lists_the_exports_asked_for(client, creator):
    export_id = ready_export(client, creator)

    body = download_ready_export(client, creator.headers, export_id).json()

    [row] = body["data"]["data_exports"]
    assert row["id"] == export_id
    assert set(row) == set(export_service.DATA_EXPORT_FIELDS)
