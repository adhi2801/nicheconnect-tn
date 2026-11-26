# The monthly restore test (item 90, D-205; app/db/restore_check.py): on the
# 1st of each month at 02:30 in Tamil Nadu, just after the backup window,
# restore this environment's database into a scratch copy, check it as the
# app's own login, record the recovery time and loss against D-168, and
# delete the copy.
#
# Its own task role, because it alone may make and delete databases, and
# only these: restore from this environment's database, read any database's
# description, delete only a copy named "<name>-restore-check-*". The API's
# task role holds none of this, so the internet-facing process can never
# delete a database.

data "aws_caller_identity" "current" {}

locals {
  # Every scratch copy, and nothing else (app/db/restore_copy.py names them).
  restore_check_copies = "arn:aws:rds:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:db:${local.name}-restore-check-*"
}

resource "aws_cloudwatch_log_group" "restore_check" {
  # The result line of every run, kept past a year so each month can be
  # read against the last (D-168's targets, written down monthly).
  name              = "/nicheconnect/${var.environment}/restore-check"
  retention_in_days = 400
}

resource "aws_iam_role" "restore_check" {
  name               = "${local.name}-restore-check"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "restore_check" {
  name = "restore-check-copies"
  role = aws_iam_role.restore_check.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # A copy of this environment's database, and of no other, tagged
        # as it is made.
        Sid    = "RestoreFromThisEnvironmentOnly"
        Effect = "Allow"
        Action = ["rds:RestoreDBInstanceToPointInTime", "rds:AddTagsToResource"]
        Resource = [
          aws_db_instance.main.arn,
          local.restore_check_copies,
          aws_db_subnet_group.main.arn,
        ]
      },
      {
        # Reading the source's window and the copy's state, and listing
        # what an earlier run left behind. Describe has no write effect.
        Sid      = "DescribeDatabases"
        Effect   = "Allow"
        Action   = ["rds:DescribeDBInstances"]
        Resource = ["*"]
      },
      {
        # The one right that removes anything: a scratch copy, never the
        # source (tests/test_restore_check_infra.py fails if this widens).
        Sid      = "DeleteOnlyRestoreCheckCopies"
        Effect   = "Allow"
        Action   = ["rds:DeleteDBInstance"]
        Resource = [local.restore_check_copies]
      },
    ]
  })
}

resource "aws_ecs_task_definition" "restore_check" {
  family                   = "${local.name}-restore-check"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.restore_check.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([{
    name                   = "restore-check"
    image                  = local.image["api"]
    essential              = true
    readonlyRootFilesystem = true
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
    command                = ["python", "-m", "app.db.restore_check"]
    # Its three settings reach this task only. It connects with the app's
    # own login (DATABASE_URL), to production and to the copy, which
    # carries the same login.
    environment = concat(local.environment, [
      { name = "RESTORE_CHECK_SOURCE_DB", value = aws_db_instance.main.identifier },
      { name = "RESTORE_CHECK_SUBNET_GROUP", value = aws_db_subnet_group.main.name },
      { name = "RESTORE_CHECK_SECURITY_GROUP", value = aws_security_group.database.id },
    ])
    secrets = local.secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.restore_check.name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = "restore-check"
      }
    }
  }])
}

resource "aws_iam_role_policy" "scheduler_run_restore_check" {
  name = "run-restore-check-task"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = [aws_ecs_task_definition.restore_check.arn_without_revision, "${aws_ecs_task_definition.restore_check.arn_without_revision}:*"]
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.execution.arn, aws_iam_role.restore_check.arn]
      },
    ]
  })
}

resource "aws_scheduler_schedule" "restore_check" {
  name                         = "${local.name}-restore-check"
  description                  = "Restore the database into a scratch copy, check it, delete it (item 90)"
  schedule_expression          = "cron(30 2 1 * ? *)"
  schedule_expression_timezone = "Asia/Kolkata" # 02:30 on the 1st, in Tamil Nadu
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.restore_check.arn
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = local.network.subnets
        security_groups  = local.network.security_groups
        assign_public_ip = local.network.assign_public_ip
      }
    }
    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
