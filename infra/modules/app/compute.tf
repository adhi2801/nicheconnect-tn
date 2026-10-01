# The app, the migration step and the embeddings refresh, on ECS Fargate
# (D-062, D-063).
#
# Two roles, kept apart on purpose:
#   execution role  what AWS needs to START a container: pull its image, read
#                   its secrets, write its logs
#   task role       what the running APP may do: read and write its own
#                   uploads bucket, and nothing else

data "aws_region" "current" {}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "app" {
  for_each          = toset(["api", "migrate", "embeddings"])
  name              = "/nicheconnect/${var.environment}/${each.key}"
  retention_in_days = var.log_retention_days
}

# --- roles --------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "read-app-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.app.arn, aws_secretsmanager_secret.msg91.arn]
    }]
  })
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "task_uploads" {
  name = "own-uploads-bucket"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Proof files only (D-065): sign uploads and view links, check, read,
        # write the clean copy, delete. Nothing outside that prefix.
        Sid      = "ProofFiles"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.uploads.arn}/proof-files/*"]
      },
      {
        # Without this S3 answers a missing file with 403, not 404, and the
        # app could not tell "never uploaded" from "not allowed": a creator
        # who abandoned an upload would get a server error, and the cleaner
        # could not mark a vanished file as missing. No prefix condition:
        # the check behind a 404 is not documented to carry one, and the
        # bucket holds nothing but these random keys.
        Sid      = "TellMissingFromForbidden"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.uploads.arn]
      },
    ]
  })
}

# --- what every container is told ------------------------------------------------------

locals {
  image = {
    for kind, repo in aws_ecr_repository.image : kind => "${repo.repository_url}:${var.image_tag}"
  }

  environment = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "CORS_ALLOWED_ORIGINS", value = var.cors_allowed_origins },
    # The load balancer sits inside the VPC, so the VPC's range is the only
    # proxy whose X-Forwarded-For is believed (D-003, client_ip.py).
    { name = "TRUSTED_PROXIES", value = var.vpc_cidr },
    { name = "OTP_SENDER", value = var.otp_sender },
    { name = "MSG91_WHATSAPP_NUMBER", value = var.msg91_whatsapp_number },
    { name = "MSG91_OTP_TEMPLATE", value = var.msg91_otp_template },
    { name = "UPLOADS_BUCKET", value = aws_s3_bucket.uploads.bucket },
  ]

  secrets = concat(
    [
      for key in ["DATABASE_URL", "REDIS_URL", "RATE_LIMIT_STORAGE_URI", "SECRET_KEY", "OTP_HASH_KEY"] :
      { name = key, valueFrom = "${aws_secretsmanager_secret.app.arn}:${key}::" }
    ],
    [{ name = "MSG91_AUTH_KEY", valueFrom = aws_secretsmanager_secret.msg91.arn }],
  )

  network = {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true # outbound only; see network.tf
  }
}

# --- the API ------------------------------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # The only writable place: temporary files, if any library needs them.
  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([{
    name                   = "api"
    image                  = local.image["api"]
    essential              = true
    readonlyRootFilesystem = true # the app writes nothing to its own disk
    portMappings           = [{ containerPort = 8000, protocol = "tcp" }]
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
    # Every instance runs the job runner; DBOS shares the work (D-060).
    environment = concat(local.environment, [{ name = "RUN_JOBS", value = "true" }])
    secrets     = local.secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["api"].name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.network.subnets
    security_groups  = local.network.security_groups
    assign_public_ip = local.network.assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # A deploy whose containers do not become healthy rolls itself back.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60
  enable_execute_command             = false

  depends_on = [aws_lb_listener.https]
}

# --- migrations: one task, run before each deploy -----------------------------------------

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name        = "migrate"
    image       = local.image["api"]
    essential   = true
    command     = ["alembic", "upgrade", "head"]
    environment = local.environment
    secrets     = local.secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["migrate"].name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = "migrate"
      }
    }
  }])
}

# --- the embeddings refresh, daily ----------------------------------------------------------

resource "aws_ecs_task_definition" "embeddings" {
  family                   = "${local.name}-embeddings"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.embeddings_cpu
  memory                   = var.embeddings_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name        = "embeddings"
    image       = local.image["embeddings"]
    essential   = true
    environment = local.environment
    secrets     = local.secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["embeddings"].name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = "embeddings"
      }
    }
  }])
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler_run_embeddings" {
  name = "run-embeddings-task"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = [aws_ecs_task_definition.embeddings.arn_without_revision, "${aws_ecs_task_definition.embeddings.arn_without_revision}:*"]
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
      },
    ]
  })
}

resource "aws_scheduler_schedule" "embeddings" {
  name                         = "${local.name}-embeddings"
  description                  = "Bring every embedding up to date with its text (D-052)"
  schedule_expression          = "cron(0 1 * * ? *)"
  schedule_expression_timezone = "Asia/Kolkata" # 01:00 in Tamil Nadu
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.embeddings.arn
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
