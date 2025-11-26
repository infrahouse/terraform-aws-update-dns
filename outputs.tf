output "lambda_name" {
  description = "Lambda function name that manages DNS records"
  value       = module.update_dns_lambda.lambda_function_name
}

output "lambda_arn" {
  description = "ARN of the Lambda function that manages DNS records"
  value       = module.update_dns_lambda.lambda_function_arn
}

output "lambda_role_name" {
  description = "IAM role name for the Lambda function"
  value       = module.update_dns_lambda.lambda_role_name
}

output "cloudwatch_alarm_arns" {
  description = "Map of CloudWatch alarm ARNs monitoring the Lambda function"
  value = {
    error    = module.update_dns_lambda.error_alarm_arn
    throttle = module.update_dns_lambda.throttle_alarm_arn
    duration = module.update_dns_lambda.duration_alarm_arn
  }
}

output "sns_topic_arn" {
  description = "ARN of SNS topic for Lambda monitoring alerts"
  value       = module.update_dns_lambda.sns_topic_arn
}

output "lifecycle_name_launching" {
  description = "User must create a launching lifecycle hook with this name."
  value       = local.lifecycle_hook_launching
}

output "lifecycle_name_terminating" {
  description = "User must create a terminating lifecycle hook with this name."
  value       = local.lifecycle_hook_terminating
}

output "route53_hostname_prefixes" {
  description = "List of DNS hostname prefixes configured for the module"
  value       = var.route53_hostname_prefixes
}
