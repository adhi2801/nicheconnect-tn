"""The monthly restore test's AWS side and its run (item 90, D-205), against moto's RDS.

Nothing reaches AWS: moto stands in for RDS, and records what each restore
asked for (moto drops a False or a 0, so the request is read as sent). The
database checks are replaced here by a stand-in: they are proven against real
PostgreSQL in `tests/test_restore_check.py`. What is proven here: the copy is
asked for private, unprotected, without backups, in the database's own subnet
group and security group; it is deleted when the checks fail, when they
crash and when it never becomes available; a leftover is swept first, and
nothing that is not a copy is ever deleted; a slow restore or too much lost
is a failure; and Sentry hears only the monitor's slug and status.
"""

import random
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import boto3
import pytest
import sentry_sdk
from moto import mock_aws
from sentry_sdk.crons import MonitorStatus
from sqlalchemy.exc import OperationalError

from app.core.deadline import Deadline
from app.db import restore_check
from app.db.restore_check import (
    MONITOR_SLUG,
    Outcome,
    copies_from,
    heartbeat,
    main,
    record,
    restore_moment,
    run,
)
from app.db.restore_copy import Copy, CopyFailed, CopyNotReady, RestoreCopies
from tests.core.test_config import load
from tests.core.test_error_tracking import DSN, Collect

SOURCE = "nicheconnect-production"
SECURITY_GROUP = "sg-0123456789abcdef0"
PRODUCTION_URL = (
    "postgresql+psycopg://nicheconnect_app:secret@prod.internal:5432/nicheconnect"
)
NOVEMBER = datetime(2026, 11, 30, 21, 0, tzinfo=UTC)  # 02:30 on 1 December in Tamil Nadu


class Clock:
    """A monotonic clock that only moves when the run sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class Recording:
    """moto's RDS client, with every restore request kept as it was sent, the
    copy's state overridable, and the latest restorable moment held still.

    moto drops a False or a 0 from a restore request and copies the source's
    value instead; AWS honours them, so the copy's backups are read back as
    asked."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.latest = datetime.now(UTC).replace(microsecond=0)
        self.restores: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.state: str | None = None

    def restore_db_instance_to_point_in_time(self, **params: Any) -> Any:
        self.restores.append(params)
        return self._client.restore_db_instance_to_point_in_time(**params)

    def delete_db_instance(self, **params: Any) -> Any:
        self.deleted.append(params["DBInstanceIdentifier"])
        return self._client.delete_db_instance(**params)

    def describe_db_instances(self, **params: Any) -> Any:
        found = self._client.describe_db_instances(**params)
        asked = {r["TargetDBInstanceIdentifier"]: r for r in self.restores}
        for instance in found["DBInstances"]:
            instance["LatestRestorableTime"] = self.latest
            if instance["DBInstanceIdentifier"] in asked:
                restore = asked[instance["DBInstanceIdentifier"]]
                instance["BackupRetentionPeriod"] = restore.get(
                    "BackupRetentionPeriod", 14
                )
                instance["DeletionProtection"] = restore.get("DeletionProtection", False)
            if (
                self.state is not None
                and "-restore-check-" in instance["DBInstanceIdentifier"]
            ):
                instance["DBInstanceStatus"] = self.state
        return found

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


@pytest.fixture
def rds() -> Iterator[Recording]:
    with mock_aws():
        ec2 = boto3.client("ec2", region_name="ap-south-1")
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
        subnets = [
            ec2.create_subnet(
                VpcId=vpc, CidrBlock=f"10.0.{i}.0/24", AvailabilityZone=zone
            )["Subnet"]["SubnetId"]
            for i, zone in enumerate(["ap-south-1a", "ap-south-1b"])
        ]
        client = boto3.client("rds", region_name="ap-south-1")
        client.create_db_subnet_group(
            DBSubnetGroupName=SOURCE,
            DBSubnetGroupDescription="private",
            SubnetIds=subnets,
        )
        client.create_db_instance(
            DBInstanceIdentifier=SOURCE,
            Engine="postgres",
            DBInstanceClass="db.t4g.small",
            AllocatedStorage=20,
            MasterUsername="nicheconnect",
            MasterUserPassword="not-a-real-password-1",
            StorageEncrypted=True,
            BackupRetentionPeriod=14,
            DBSubnetGroupName=SOURCE,
            PubliclyAccessible=False,
        )
        yield Recording(client)


@pytest.fixture
def copies(rds) -> RestoreCopies:
    return RestoreCopies(
        rds, source=SOURCE, subnet_group=SOURCE, security_group=SECURITY_GROUP
    )


def identifiers(rds: Recording) -> set[str]:
    return {
        instance["DBInstanceIdentifier"]
        for instance in rds.describe_db_instances()["DBInstances"]
        if instance["DBInstanceStatus"] != "deleting"
    }


def checks_find(monkeypatch, found: list[str] | Exception) -> list[dict[str, Any]]:
    """The database checks replaced: what they were asked, and what they answer."""
    asked: list[dict[str, Any]] = []

    def stand_in(production_url: str, copy_url: str, **kwargs: Any) -> list[str]:
        asked.append({"production_url": production_url, "copy_url": copy_url, **kwargs})
        if isinstance(found, Exception):
            raise found
        return list(found)

    monkeypatch.setattr(restore_check, "database_problems", stand_in)
    return asked


def times(*moments: datetime):
    """`now` answering each moment in turn, then the last for ever."""
    queue = list(moments)

    def now() -> datetime:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return now


def a_run(
    copies: RestoreCopies, clock: Clock | None = None, *, now=None, rng=None
) -> Outcome:
    clock = clock or Clock()
    latest = copies.window()[1]
    return run(
        copies,
        production_url=PRODUCTION_URL,
        heads={"578a45512fe0"},
        now=now or times(latest + timedelta(minutes=2), latest + timedelta(minutes=40)),
        sleep=clock.sleep,
        rng=rng or random.Random(7),
        clock=clock,
    )


# --- the copy --------------------------------------------------------------------------


def test_the_copy_is_asked_for_private_unprotected_without_backups_and_tagged(
    copies, rds
):
    copies.start(copies.name(NOVEMBER), None)

    (asked,) = rds.restores
    assert asked == {
        "SourceDBInstanceIdentifier": SOURCE,
        "TargetDBInstanceIdentifier": f"{SOURCE}-restore-check-20261130-2100",
        "DBSubnetGroupName": SOURCE,
        "VpcSecurityGroupIds": [SECURITY_GROUP],
        "PubliclyAccessible": False,
        "DeletionProtection": False,
        "MultiAZ": False,
        "BackupRetentionPeriod": 0,
        "CopyTagsToSnapshot": False,
        "Tags": [{"Key": "purpose", "Value": "restore-check"}],
        "UseLatestRestorableTime": True,
    }


def test_a_chosen_moment_is_asked_for_instead_of_the_latest(copies, rds):
    moment = datetime(2026, 11, 20, 4, 5, 6, tzinfo=UTC)
    copies.start(copies.name(NOVEMBER), moment)

    (asked,) = rds.restores
    assert asked["RestoreTime"] == moment
    assert "UseLatestRestorableTime" not in asked


def test_the_copy_comes_back_private_and_encrypted(copies):
    identifier = copies.name(NOVEMBER)
    copies.start(identifier, None)
    clock = Clock()

    copy = copies.wait(identifier, Deadline(60, clock), clock.sleep)

    assert (copy.identifier, copy.public, copy.encrypted, copy.deletion_protection) == (
        identifier,
        False,
        True,
        False,
    )
    assert copy.host and copy.port


def test_the_window_runs_from_the_retention_period_to_the_latest_moment(copies):
    earliest, latest = copies.window()

    assert earliest <= latest
    assert latest - earliest <= timedelta(days=14)


def test_a_restore_that_dies_is_reported_with_its_state(copies, rds):
    identifier = copies.name(NOVEMBER)
    copies.start(identifier, None)
    rds.state = "incompatible-restore"
    clock = Clock()

    with pytest.raises(CopyFailed, match="incompatible-restore"):
        copies.wait(identifier, Deadline(600, clock), clock.sleep)


def test_a_copy_still_making_at_the_deadline_is_not_waited_for(copies, rds):
    identifier = copies.name(NOVEMBER)
    copies.start(identifier, None)
    rds.state = "creating"
    clock = Clock()

    with pytest.raises(CopyNotReady):
        copies.wait(identifier, Deadline(95, clock), clock.sleep)

    assert clock.slept == [30.0, 30.0, 30.0, 5.0]


@pytest.mark.parametrize(
    "identifier", [SOURCE, "nicheconnect-staging-restore-check-20261201-0230", "anything"]
)
def test_nothing_but_this_source_s_copies_can_be_deleted(copies, rds, identifier):
    with pytest.raises(ValueError, match="not a restore-check copy"):
        copies.delete(identifier)

    assert rds.deleted == []
    assert SOURCE in identifiers(rds)


def test_deleting_a_copy_already_gone_is_fine(copies, rds):
    copies.delete(copies.name(NOVEMBER))

    assert rds.deleted == [f"{SOURCE}-restore-check-20261130-2100"]


def test_leftovers_are_swept_and_nothing_else(copies, rds):
    left = f"{SOURCE}-restore-check-20261031-2100"
    other = "nicheconnect-staging-restore-check-20261031-2100"
    rds.restore_db_instance_to_point_in_time(
        SourceDBInstanceIdentifier=SOURCE,
        TargetDBInstanceIdentifier=left,
        UseLatestRestorableTime=True,
    )
    rds.restore_db_instance_to_point_in_time(
        SourceDBInstanceIdentifier=SOURCE,
        TargetDBInstanceIdentifier=other,
        UseLatestRestorableTime=True,
    )

    assert copies.sweep() == [left]
    assert identifiers(rds) == {SOURCE, other}


# --- the run --------------------------------------------------------------------------------


def test_a_good_run_checks_the_copy_records_its_times_and_deletes_it(
    copies, rds, monkeypatch
):
    asked = checks_find(monkeypatch, [])
    latest = copies.window()[1]

    outcome = a_run(copies)

    assert outcome.ok
    assert outcome.latest
    assert outcome.rpo == timedelta(minutes=2)
    assert outcome.rto == timedelta(minutes=38)
    (checked,) = asked
    assert checked["production_url"] == PRODUCTION_URL
    assert "@prod.internal" not in checked["copy_url"]
    assert checked["copy_url"].startswith("postgresql+psycopg://nicheconnect_app:secret@")
    assert checked["cutoff"] == latest - timedelta(minutes=10)
    assert checked["heads"] == {"578a45512fe0"}
    assert identifiers(rds) == {SOURCE}


def test_a_failed_check_fails_the_run_and_the_copy_is_still_deleted(
    copies, rds, monkeypatch
):
    checks_find(monkeypatch, ["sealed: admin_action differs from production"])

    outcome = a_run(copies)

    assert outcome.problems == ["sealed: admin_action differs from production"]
    assert identifiers(rds) == {SOURCE}


def test_a_check_that_cannot_reach_the_copy_fails_the_run_and_deletes_it(
    copies, rds, monkeypatch
):
    checks_find(monkeypatch, OperationalError("SELECT 1", {}, Exception("refused")))

    outcome = a_run(copies)

    assert outcome.problems == ["database: OperationalError"]
    assert outcome.rto is None
    assert identifiers(rds) == {SOURCE}


def test_a_copy_never_ready_stops_at_ninety_minutes_and_is_deleted(
    copies, rds, monkeypatch
):
    asked = checks_find(monkeypatch, [])
    rds.state = "creating"
    clock = Clock()

    outcome = a_run(copies, clock)

    assert outcome.problems == ["restore: not done within 90 minutes"]
    assert clock.now == 90 * 60
    assert asked == []
    rds.state = None
    assert identifiers(rds) == {SOURCE}


def test_a_restore_that_dies_fails_the_run_and_is_deleted(copies, rds, monkeypatch):
    checks_find(monkeypatch, [])
    rds.state = "failed"

    outcome = a_run(copies)

    assert outcome.problems == ["restore: stopped in state failed"]
    assert rds.deleted == [rds.restores[0]["TargetDBInstanceIdentifier"]]


def test_a_leftover_is_swept_before_the_run_restores(copies, rds, monkeypatch):
    checks_find(monkeypatch, [])
    rds.restore_db_instance_to_point_in_time(
        SourceDBInstanceIdentifier=SOURCE,
        TargetDBInstanceIdentifier=f"{SOURCE}-restore-check-20261031-2100",
        UseLatestRestorableTime=True,
    )

    outcome = a_run(copies)

    assert outcome.ok
    assert outcome.swept == 1
    assert identifiers(rds) == {SOURCE}


def test_a_restore_over_an_hour_fails_the_run(copies, monkeypatch):
    checks_find(monkeypatch, [])
    latest = copies.window()[1]
    asked = latest + timedelta(minutes=1)

    outcome = a_run(copies, now=times(asked, asked + timedelta(minutes=61)))

    assert outcome.problems == ["target: restore took 3660 s, over 3600"]


def test_over_five_minutes_lost_fails_the_run(copies, monkeypatch):
    checks_find(monkeypatch, [])
    latest = copies.window()[1]
    asked = latest + timedelta(minutes=6)

    outcome = a_run(copies, now=times(asked, asked + timedelta(minutes=30)))

    assert outcome.problems == ["target: 360 s would be lost, over 300"]


def test_every_third_month_a_random_second_in_the_window_is_restored(
    copies, rds, monkeypatch
):
    asked = checks_find(monkeypatch, [])
    # 02:30 on 1 December in Tamil Nadu is still November in UTC: December counts.
    at = datetime(2026, 11, 30, 21, 0, tzinfo=UTC)
    rds.latest = at - timedelta(minutes=1)
    earliest, latest = copies.window()

    outcome = a_run(copies, now=times(at, at + timedelta(minutes=30)))

    assert not outcome.latest
    assert earliest <= outcome.restore_time <= latest
    assert rds.restores[0]["RestoreTime"] == outcome.restore_time
    assert asked[0]["cutoff"] == outcome.restore_time - timedelta(minutes=10)


def test_the_last_day_of_november_in_tamil_nadu_restores_the_latest(
    copies, rds, monkeypatch
):
    checks_find(monkeypatch, [])
    at = datetime(2026, 11, 30, 18, 0, tzinfo=UTC)  # 23:30 on 30 November in Tamil Nadu
    rds.latest = at - timedelta(minutes=1)

    outcome = a_run(copies, now=times(at, at + timedelta(minutes=30)))

    assert outcome.latest
    assert "RestoreTime" not in rds.restores[0]


def test_the_random_moment_reaches_both_ends_of_the_window():
    earliest = datetime(2026, 11, 16, tzinfo=UTC)
    latest = earliest + timedelta(days=14)

    class Edge(random.Random):
        def __init__(self, pick_last: bool) -> None:
            super().__init__()
            self.pick_last = pick_last

        def randint(self, a: int, b: int) -> int:
            return b if self.pick_last else a

    assert restore_moment(date(2026, 12, 1), earliest, latest, Edge(False)) == earliest
    assert restore_moment(date(2026, 12, 1), earliest, latest, Edge(True)) == latest


@pytest.mark.parametrize(
    ("month", "random_moment"),
    [(1, False), (2, False), (3, True), (11, False), (12, True)],
)
def test_only_every_third_month_restores_a_random_moment(month, random_moment):
    earliest = datetime(2026, 11, 16, tzinfo=UTC)
    chosen = restore_moment(
        date(2026, month, 1), earliest, earliest + timedelta(days=14), random.Random(1)
    )

    assert (chosen is not None) is random_moment


# --- what it writes, and what Sentry hears --------------------------------------------------------


def outcome(**overrides: Any) -> Outcome:
    fields: dict[str, Any] = {
        "problems": [],
        "restore_time": datetime(2026, 11, 30, 20, 55, 0, 123, tzinfo=UTC),
        "latest": True,
        "rto": timedelta(minutes=38, seconds=0.4),
        "rpo": timedelta(minutes=2),
        "swept": 0,
    }
    fields.update(overrides)
    return Outcome(**fields)


def test_the_result_is_one_line_of_numbers(caplog):
    caplog.set_level("INFO", logger="app.db.restore_check")

    record(outcome())

    (line,) = caplog.messages
    assert line == (
        'restore_check.result {"copies_swept": 0, "latest": true, "ok": true, "problems": [],'
        ' "restore_time": "2026-11-30T20:55:00+00:00", "rpo_seconds": 120,'
        ' "rpo_target_seconds": 300, "rto_seconds": 2280, "rto_target_seconds": 3600}'
    )


def test_a_failure_is_also_an_error_line(caplog):
    caplog.set_level("INFO", logger="app.db.restore_check")

    record(outcome(problems=["dbos: schema missing"], rto=None))

    assert [r.levelname for r in caplog.records] == ["INFO", "ERROR"]
    assert '"rto_seconds": null' in caplog.messages[0]


@pytest.fixture
def sent() -> Iterator[Collect]:
    transport = Collect()
    assert restore_check.init_error_tracking(
        load(sentry_dsn=DSN, app_release="abc1234", environment="production"),
        transport=transport,
    )
    try:
        yield transport
    finally:
        sentry_sdk.init(dsn=None)


def check_ins(sent: Collect) -> list[dict[str, Any]]:
    sentry_sdk.flush()
    return [
        item.payload.json
        for envelope in sent.envelopes
        for item in envelope.items
        if item.type == "check_in"
    ]


def test_sentry_hears_the_monitor_s_slug_status_and_duration_only(sent):
    started = heartbeat(MonitorStatus.IN_PROGRESS)
    heartbeat(MonitorStatus.ERROR, check_in_id=started, duration=12.5)

    first, last = check_ins(sent)
    assert first["monitor_slug"] == last["monitor_slug"] == MONITOR_SLUG
    assert (first["status"], last["status"]) == ("in_progress", "error")
    assert first["check_in_id"] == last["check_in_id"] == started
    assert last["duration"] == 12.5
    assert first["monitor_config"]["schedule"] == {
        "type": "crontab",
        "value": "30 2 1 * *",
    }
    assert first["monitor_config"]["timezone"] == "Asia/Kolkata"
    assert set(last) <= {
        "type",
        "monitor_slug",
        "check_in_id",
        "status",
        "duration",
        "environment",
        "release",
        "monitor_config",
        "contexts",
        "event_id",
        "timestamp",
        "platform",
        "sdk",
        "server_name",
    }
    assert "user" not in last and "request" not in last


# --- the entry point --------------------------------------------------------------------------


def given(monkeypatch, rds: Recording) -> None:
    """main's copies on the recording client, which reads a copy back as AWS makes it."""
    monkeypatch.setattr(
        restore_check,
        "copies_from",
        lambda config: RestoreCopies(
            rds,
            source=config.restore_check_source_db,
            subnet_group=config.restore_check_subnet_group,
            security_group=config.restore_check_security_group,
        ),
    )


def statuses(monkeypatch) -> list[str]:
    said: list[str] = []
    monkeypatch.setattr(
        restore_check, "heartbeat", lambda status, **_: said.append(status) or "check-in"
    )
    return said


def test_unconfigured_it_does_nothing_and_says_so(monkeypatch, caplog):
    said = statuses(monkeypatch)

    assert main(load()) == 1
    assert said == ["in_progress", "error"]
    assert "restore_check.crashed" in caplog.messages


def test_configured_it_runs_and_checks_in_ok(rds, monkeypatch):
    said = statuses(monkeypatch)
    given(monkeypatch, rds)
    checks_find(monkeypatch, [])
    config = load(
        restore_check_source_db=SOURCE,
        restore_check_subnet_group=SOURCE,
        restore_check_security_group=SECURITY_GROUP,
    )

    assert main(config) == 0
    assert said == ["in_progress", "ok"]


def test_a_failed_run_exits_1_and_checks_in_error(rds, monkeypatch):
    said = statuses(monkeypatch)
    given(monkeypatch, rds)
    checks_find(monkeypatch, ["dbos: schema missing"])
    config = load(
        restore_check_source_db=SOURCE,
        restore_check_subnet_group=SOURCE,
        restore_check_security_group=SECURITY_GROUP,
    )

    assert main(config) == 1
    assert said == ["in_progress", "error"]


def test_the_task_s_copies_come_from_its_three_settings():
    with mock_aws():
        copies = copies_from(
            load(
                restore_check_source_db=SOURCE,
                restore_check_subnet_group="nicheconnect-production",
                restore_check_security_group=SECURITY_GROUP,
            )
        )

    assert copies.prefix == f"{SOURCE}-restore-check-"


@pytest.mark.parametrize(
    "missing",
    [
        "restore_check_source_db",
        "restore_check_subnet_group",
        "restore_check_security_group",
    ],
)
def test_any_setting_missing_refuses_to_run(missing):
    values = {
        "restore_check_source_db": SOURCE,
        "restore_check_subnet_group": SOURCE,
        "restore_check_security_group": SECURITY_GROUP,
    }
    values[missing] = ""

    with pytest.raises(restore_check.NotConfigured):
        copies_from(load(**values))


def test_a_copy_s_url_keeps_the_login_and_changes_only_the_address():
    copy = Copy("x-restore-check-1", "copy.internal", 6543, False, True, False, 0)

    assert restore_check.copy_url(PRODUCTION_URL, copy) == (
        "postgresql+psycopg://nicheconnect_app:secret@copy.internal:6543/nicheconnect"
    )
