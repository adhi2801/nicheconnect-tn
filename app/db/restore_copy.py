"""The monthly restore test's scratch copy, on AWS (item 90): restore, wait, delete.

Only the RDS calls live here; what is checked on the copy, and the run that
ties it together, is `app/db/restore_check.py`.

The copy is made by point-in-time restore from this environment's own
database into its private subnets and its database security group, never
public, with no deletion protection and no backups of its own, so it is cheap
and nothing stops its deletion. It is encrypted because the source is: RDS
restores an encrypted instance only as an encrypted one, and the check reads
that back rather than trusting it.

Every copy is named `<source>-restore-check-<time>`, and this file refuses to
delete anything else: the task's IAM role (infra/modules/app/restore_check.tf)
grants deletion only on that pattern, and this is the same rule written a
second time, so a bug here can never reach production's own database.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from app.core.deadline import Deadline

MARK = "-restore-check-"
# Polling the copy's state: RDS takes minutes, so once every 30 seconds.
POLL_SECONDS = 30.0
# States from which a restore never becomes available on its own.
DEAD_STATES = frozenset(
    {
        "failed",
        "incompatible-network",
        "incompatible-parameters",
        "incompatible-restore",
        "inaccessible-encryption-credentials",
        "storage-full",
    }
)
# What a delete may answer without it being a fault: already gone, or
# already being deleted (a sweep and a `finally` may both ask).
GONE = frozenset(
    {"DBInstanceNotFound", "DBInstanceNotFoundFault", "InvalidDBInstanceState"}
)
# The earliest moment is kept an hour inside the window, so a restore asked
# for near its edge is never refused because the edge moved meanwhile.
WINDOW_MARGIN = timedelta(hours=1)
TAGS = [{"Key": "purpose", "Value": "restore-check"}]


class CopyFailed(RuntimeError):
    """The restore stopped in a state it never leaves (the state is the message)."""


class CopyNotReady(TimeoutError):
    """The copy was not available before the run's time limit."""


@dataclass(frozen=True)
class Copy:
    """The facts about a copy the run checks or connects with."""

    identifier: str
    host: str
    port: int
    public: bool
    encrypted: bool
    deletion_protection: bool
    backups_kept_days: int


class RestoreCopies:
    """Scratch copies of one source database, made and removed through RDS."""

    def __init__(
        self, rds: Any, *, source: str, subnet_group: str, security_group: str
    ) -> None:
        self._rds = rds
        self.source = source
        self._subnet_group = subnet_group
        self._security_group = security_group

    @property
    def prefix(self) -> str:
        return f"{self.source}{MARK}"

    def name(self, at: datetime) -> str:
        """The copy's identifier for a run started at `at` (UTC)."""
        return f"{self.prefix}{at:%Y%m%d-%H%M}"

    def window(self) -> tuple[datetime, datetime]:
        """The earliest and the latest moment the source can be restored to.

        RDS names the latest; the earliest is the retention period back from
        it, or the instance's birth if younger, kept an hour inside.
        """
        source = self._describe(self.source)
        latest: datetime = source["LatestRestorableTime"]
        earliest = max(
            latest - timedelta(days=int(source["BackupRetentionPeriod"])),
            source["InstanceCreateTime"],
        )
        return min(earliest + WINDOW_MARGIN, latest), latest

    def start(self, identifier: str, restore_time: datetime | None) -> None:
        """Ask RDS for the copy: the latest restorable moment when `restore_time` is None."""
        self._own(identifier)
        moment: dict[str, Any] = (
            {"UseLatestRestorableTime": True}
            if restore_time is None
            else {"RestoreTime": restore_time}
        )
        self._rds.restore_db_instance_to_point_in_time(
            SourceDBInstanceIdentifier=self.source,
            TargetDBInstanceIdentifier=identifier,
            DBSubnetGroupName=self._subnet_group,
            VpcSecurityGroupIds=[self._security_group],
            PubliclyAccessible=False,
            DeletionProtection=False,
            MultiAZ=False,
            BackupRetentionPeriod=0,
            CopyTagsToSnapshot=False,
            Tags=TAGS,
            **moment,
        )

    def wait(
        self,
        identifier: str,
        deadline: Deadline,
        sleep: Callable[[float], None],
    ) -> Copy:
        """The copy once RDS says it is available.

        Raises CopyFailed on a state RDS never leaves, and CopyNotReady once
        the deadline passes.
        """
        while True:
            instance = self._describe(identifier)
            state = instance["DBInstanceStatus"]
            if state == "available":
                return Copy(
                    identifier=identifier,
                    host=instance["Endpoint"]["Address"],
                    port=int(instance["Endpoint"]["Port"]),
                    public=bool(instance["PubliclyAccessible"]),
                    encrypted=bool(instance["StorageEncrypted"]),
                    deletion_protection=bool(instance["DeletionProtection"]),
                    backups_kept_days=int(instance["BackupRetentionPeriod"]),
                )
            if state in DEAD_STATES:
                raise CopyFailed(state)
            if deadline.expired():
                raise CopyNotReady(identifier)
            sleep(deadline.capped(POLL_SECONDS))

    def delete(self, identifier: str) -> None:
        """Delete a copy, with no final snapshot; one already gone is fine."""
        self._own(identifier)
        try:
            self._rds.delete_db_instance(
                DBInstanceIdentifier=identifier,
                SkipFinalSnapshot=True,
                DeleteAutomatedBackups=True,
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in GONE:
                raise

    def sweep(self) -> list[str]:
        """Delete every copy an earlier run left behind; their identifiers."""
        left = [
            instance["DBInstanceIdentifier"]
            for instance in self._instances()
            if instance["DBInstanceIdentifier"].startswith(self.prefix)
            and instance["DBInstanceStatus"] != "deleting"
        ]
        for identifier in left:
            self.delete(identifier)
        return left

    def _own(self, identifier: str) -> None:
        if not identifier.startswith(self.prefix):
            raise ValueError(f"not a restore-check copy of {self.source}: {identifier}")

    def _describe(self, identifier: str) -> dict[str, Any]:
        found: dict[str, Any] = self._rds.describe_db_instances(
            DBInstanceIdentifier=identifier
        )["DBInstances"][0]
        return found

    def _instances(self) -> Iterator[dict[str, Any]]:
        for page in self._rds.get_paginator("describe_db_instances").paginate():
            yield from page["DBInstances"]
