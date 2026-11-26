"""The restore test's rights in OpenTofu cannot quietly widen (item 90, D-205).

The task that restores and deletes databases is the one place in infra/ that
may remove a database. Read from the .tf files themselves: deleting is
granted once, to that task's role, on scratch copies named
"<name>-restore-check-*" only; no wildcard RDS action exists anywhere; the
restore is from this environment's own database; and the three settings
reach that task alone.
"""

import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1] / "infra" / "modules" / "app"
RESTORE_CHECK = (INFRA / "restore_check.tf").read_text(encoding="utf-8")
COPIES = (
    '"arn:aws:rds:${data.aws_region.current.region}:'
    '${data.aws_caller_identity.current.account_id}:db:${local.name}-restore-check-*"'
)


def statement(sid: str) -> str:
    """The text of one IAM statement, from its Sid to the next closing brace."""
    found = re.search(rf'Sid\s+= "{sid}"', RESTORE_CHECK)
    assert found is not None, sid
    start = found.start()
    return RESTORE_CHECK[start : RESTORE_CHECK.index("},", start)]


def every_tf() -> dict[str, str]:
    found = {
        path.name: path.read_text(encoding="utf-8")
        for path in INFRA.parent.parent.rglob("*.tf")
    }
    assert len(found) >= 10
    return found


def test_the_copies_are_only_those_named_restore_check():
    assert f"restore_check_copies = {COPIES}" in RESTORE_CHECK


def test_deleting_is_granted_on_the_copies_only():
    delete = statement("DeleteOnlyRestoreCheckCopies")

    assert 'Action   = ["rds:DeleteDBInstance"]' in delete
    assert "Resource = [local.restore_check_copies]" in delete


def test_no_other_file_or_statement_may_delete_a_database_or_use_a_wildcard():
    for name, text in every_tf().items():
        deletes = len(re.findall(r'"rds:Delete', text))
        assert deletes == (1 if name == "restore_check.tf" else 0), name
        assert not re.search(r'"rds:\*"|"rds:[A-Za-z]*\*"|"\*:\*"', text), name


def test_restoring_is_from_this_environment_s_database_only():
    restore = statement("RestoreFromThisEnvironmentOnly")
    resources = restore[restore.index("Resource") :]

    assert re.findall(r"^\s+(\S+),$", resources, re.MULTILINE) == [
        "aws_db_instance.main.arn",
        "local.restore_check_copies",
        "aws_db_subnet_group.main.arn",
    ]


def test_only_describe_reaches_every_database():
    describe = statement("DescribeDatabases")

    assert 'Action   = ["rds:DescribeDBInstances"]' in describe
    assert RESTORE_CHECK.count('Resource = ["*"]') == 1


def test_the_task_runs_under_its_own_role_and_the_api_never_holds_these_rights():
    assert "task_role_arn            = aws_iam_role.restore_check.arn" in RESTORE_CHECK
    assert "rds:" not in (INFRA / "compute.tf").read_text(encoding="utf-8")


def test_its_three_settings_reach_this_task_only():
    for name, text in every_tf().items():
        if name != "restore_check.tf":
            assert "RESTORE_CHECK_" not in text, name
    for setting in ("SOURCE_DB", "SUBNET_GROUP", "SECURITY_GROUP"):
        assert f'name = "RESTORE_CHECK_{setting}"' in RESTORE_CHECK


def test_it_runs_monthly_and_its_results_are_kept_400_days():
    assert 'schedule_expression          = "cron(30 2 1 * ? *)"' in RESTORE_CHECK
    assert 'schedule_expression_timezone = "Asia/Kolkata"' in RESTORE_CHECK
    assert "retention_in_days = 400" in RESTORE_CHECK
    assert (
        'command                = ["python", "-m", "app.db.restore_check"]'
        in RESTORE_CHECK
    )
