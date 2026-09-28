"""A deal's proof in a daily checkpoint, over HTTP (D-060)."""

import base64
import hashlib
import json
import shlex
import shutil
import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

import certifi
import pytest
from sqlalchemy import delete, text

from app.core.clock import india_date
from app.modules.deal_memo import anchor_service, merkle, record_service
from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.record_router import READ_LIMIT
from app.modules.deal_memo.timestamp_authority import Stamp
from tests.deal_flow import MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.factories import FIXED_NOW

# Deals below are recorded at FIXED_NOW, so the next day's checkpoint holds them.
DAY_AFTER = india_date(FIXED_NOW) + timedelta(days=1)


@pytest.fixture(autouse=True)
def empty_record(db):
    """A checkpoint covers every deal, so each test starts from none; the
    triggers are set aside only for this delete, inside the test's own
    rolled-back transaction."""
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(delete(DealRecordTimestamp))
    db.execute(delete(DealRecordCheckpoint))
    db.execute(delete(DealRecordEntry))
    db.execute(text("SET LOCAL session_replication_role = origin"))


class FakeAuthority:
    def __init__(self, name: str):
        self.name = name

    def stamp(self, fingerprint: bytes) -> Stamp:
        return Stamp(
            token=b"signed-" + self.name.encode() + fingerprint, signed_at=FIXED_NOW
        )


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def proof_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/record/proof"


def stamped_checkpoint(db, day=DAY_AFTER):
    checkpoint = anchor_service.create_checkpoint(db, day)
    anchor_service.stamp_checkpoint(
        db, checkpoint, [FakeAuthority("digicert"), FakeAuthority("sectigo")]
    )
    return checkpoint


# --- what the proof says -----------------------------------------------------------


def test_the_proof_leads_from_the_deals_seal_to_the_stamped_root(
    client, db, brand, creator
):
    memos = [accepted_memo(client, brand, creator) for _ in range(3)]
    checkpoint = stamped_checkpoint(db)

    for memo_id in memos:
        response = client.get(proof_url(memo_id), headers=brand.headers)
        assert response.status_code == 200, response.text
        proof = response.json()
        rebuilt = merkle.root_from_path(
            proof["leaf_index"],
            proof["leaf_count"],
            uuid.UUID(memo_id).bytes + bytes.fromhex(proof["seal"]),
            [bytes.fromhex(h) for h in proof["audit_path"]],
        )
        assert rebuilt.hex() == proof["merkle_root"] == checkpoint.merkle_root.hex()
        assert proof["leaf_count"] == 3
        assert proof["checkpoint_date"] == DAY_AFTER.isoformat()


def test_the_seal_is_the_one_the_record_shows(client, brand, creator, db):
    memo_id = accepted_memo(client, brand, creator)
    stamped_checkpoint(db)

    proof = client.get(proof_url(memo_id), headers=creator.headers).json()
    record = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers).json()

    assert proof["seal"] == record["latest_seal"]


def test_the_timestamps_come_back_exactly_as_issued(client, brand, creator, db):
    memo_id = accepted_memo(client, brand, creator)
    checkpoint = stamped_checkpoint(db)

    proof = client.get(proof_url(memo_id), headers=brand.headers).json()

    assert proof["stamped"] is True
    assert [t["authority"] for t in proof["timestamps"]] == ["digicert", "sectigo"]
    for stamp in proof["timestamps"]:
        token = base64.b64decode(stamp["token_base64"])
        assert token == b"signed-" + stamp["authority"].encode() + checkpoint.merkle_root


def test_an_unstamped_checkpoint_is_shown_as_a_gap(client, brand, creator, db):
    memo_id = accepted_memo(client, brand, creator)
    anchor_service.create_checkpoint(db, DAY_AFTER)

    proof = client.get(proof_url(memo_id), headers=brand.headers).json()

    assert proof["stamped"] is False
    assert proof["timestamps"] == []


def test_without_a_date_the_newest_covering_checkpoint_is_used(
    client, brand, creator, db
):
    memo_id = accepted_memo(client, brand, creator)
    stamped_checkpoint(db, DAY_AFTER)
    stamped_checkpoint(db, DAY_AFTER + timedelta(days=1))

    latest = client.get(proof_url(memo_id), headers=brand.headers).json()
    chosen = client.get(
        proof_url(memo_id), params={"date": DAY_AFTER.isoformat()}, headers=brand.headers
    ).json()

    assert latest["checkpoint_date"] == (DAY_AFTER + timedelta(days=1)).isoformat()
    assert chosen["checkpoint_date"] == DAY_AFTER.isoformat()


# --- when there is no proof ----------------------------------------------------------


def test_no_checkpoint_yet_is_not_found(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    response = client.get(proof_url(memo_id), headers=brand.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "checkpoint_not_found"


def test_a_checkpoint_from_before_the_deal_does_not_cover_it(client, brand, creator, db):
    memo_id = accepted_memo(client, brand, creator)
    before = india_date(FIXED_NOW)  # midnight at the start of the deal's own day
    stamped_checkpoint(db, before)

    response = client.get(
        proof_url(memo_id), params={"date": before.isoformat()}, headers=brand.headers
    )

    assert response.status_code == 404
    assert response.json()["code"] == "checkpoint_not_found"


def test_a_backdated_entry_is_answered_plainly_not_as_a_crash(client, brand, creator, db):
    memo_id = accepted_memo(client, brand, creator)
    stamped_checkpoint(db)
    memo = db.get(DealMemo, uuid.UUID(memo_id))
    # An entry slipped in after the day was stamped, dated before its cut-off.
    record_service.append(
        db, memo, kind="memo_cancelled", actor_role="brand", now=FIXED_NOW
    )

    response = client.get(proof_url(memo_id), headers=brand.headers)

    assert response.status_code == 409
    assert response.json()["code"] == "record_does_not_match_checkpoint"


# --- who may ask -------------------------------------------------------------------------


def test_anyone_else_gets_not_found(client, db, clock, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    stamped_checkpoint(db)

    for stranger in (brand_user(db, clock), creator_user(db, clock)):
        response = client.get(proof_url(memo_id), headers=stranger.headers)
        assert response.status_code == 404
        assert response.json()["code"] == "memo_not_found"


def test_it_is_not_public(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    assert client.get(proof_url(memo_id)).status_code == 401


def test_a_bad_date_is_rejected(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    response = client.get(
        proof_url(memo_id), params={"date": "yesterday"}, headers=brand.headers
    )

    assert response.status_code == 422


def test_it_is_rate_limited(client, brand, creator, db):
    memo_id = accepted_memo(client, brand, creator)
    stamped_checkpoint(db)
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(proof_url(memo_id), headers=brand.headers).status_code == 200

    assert client.get(proof_url(memo_id), headers=brand.headers).status_code == 429


# --- the guide, run as written --------------------------------------------------------

GUIDE = Path(__file__).parents[3] / "docs" / "DEAL_RECORD_VERIFY.md"
FIXTURES = Path(__file__).parent / "fixtures"


def guide_section_7() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    return text[text.index("## 7.") :]


def test_the_guides_proof_script_works(
    client, brand, creator, db, tmp_path, monkeypatch, capsys
):
    memo_id = accepted_memo(client, brand, creator)
    accepted_memo(client, brand, creator)  # a second deal, so there is a real path
    checkpoint = stamped_checkpoint(db)
    proof = client.get(proof_url(memo_id), headers=brand.headers).json()
    (tmp_path / "proof.json").write_text(json.dumps(proof), encoding="utf-8")
    script = next(
        block.split("\n", 1)[1]
        for block in guide_section_7().split("```")
        if block.startswith("python") and "proof.json" in block
    )
    monkeypatch.chdir(tmp_path)

    exec(compile(script, "DEAL_RECORD_VERIFY.md", "exec"), {})  # noqa: S102

    assert capsys.readouterr().out.strip().endswith(checkpoint.merkle_root.hex())
    assert (tmp_path / "root.bin").read_bytes() == checkpoint.merkle_root
    assert (tmp_path / "digicert.tsr").exists()


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl command")
def test_the_guides_openssl_commands_verify_real_tokens(tmp_path):
    """The two commands exactly as the guide prints them, on genuine DigiCert
    and Sectigo tokens, with the fingerprint they signed as root.bin."""
    for name in ("digicert", "sectigo"):
        shutil.copy(FIXTURES / f"{name}_probe.tsr", tmp_path / f"{name}.tsr")
    (tmp_path / "root.bin").write_bytes(hashlib.sha256(b"probe").digest())
    shutil.copy(certifi.where(), tmp_path / "cacert.pem")
    commands = [
        line.strip()
        for line in guide_section_7().splitlines()
        if line.strip().startswith("openssl ts -verify")
    ]
    assert len(commands) == 2

    for command in commands:
        result = subprocess.run(  # noqa: S603
            shlex.split(command),
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert "Verification: OK" in result.stdout, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl command")
def test_openssl_refuses_a_token_against_the_wrong_fingerprint(tmp_path):
    shutil.copy(FIXTURES / "digicert_probe.tsr", tmp_path / "digicert.tsr")
    (tmp_path / "root.bin").write_bytes(hashlib.sha256(b"not what was signed").digest())
    shutil.copy(certifi.where(), tmp_path / "cacert.pem")

    result = subprocess.run(  # noqa: S603
        shlex.split(
            "openssl ts -verify -in digicert.tsr -data root.bin -CAfile cacert.pem"
        ),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "Verification: OK" not in result.stdout
