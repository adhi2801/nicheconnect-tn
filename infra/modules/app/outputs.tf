output "api_url" {
  value       = "https://${var.domain_name}"
  description = "Where the API answers once the DNS records below are in place"
}

output "load_balancer_dns_name" {
  value       = aws_lb.api.dns_name
  description = "Point the domain at this with a CNAME record"
}

output "certificate_validation_records" {
  value = [
    for o in aws_acm_certificate.api.domain_validation_options : {
      name  = o.resource_record_name
      type  = o.resource_record_type
      value = o.resource_record_value
    }
  ]
  description = "Add these at the domain's DNS so the TLS certificate can be issued"
}

output "image_repositories" {
  value = { for kind, repo in aws_ecr_repository.image : kind => repo.repository_url }
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "migrate_task_definition" {
  value       = aws_ecs_task_definition.migrate.arn
  description = "Run this once before each deploy: alembic upgrade head"
}

output "task_network" {
  value       = local.network
  description = "Subnets and security group for running the migrate task"
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.bucket
}

output "msg91_secret_name" {
  value       = aws_secretsmanager_secret.msg91.name
  description = "Paste the MSG91 auth key here, then set otp_sender = msg91"
}

output "anthropic_secret_name" {
  value       = aws_secretsmanager_secret.anthropic.name
  description = "Paste the Claude API key here, then set proof_reading_enabled = true (D-070)"
}
