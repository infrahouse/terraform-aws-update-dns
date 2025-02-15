output "lambda_name" {
  description = "Lambda function name that manages DNS records"
  value       = aws_lambda_function.update_dns.function_name
}

output "lifecycle_name_launching" {
  description = "User must create a launching lifecycle hook with this name."
  value       = local.lifecycle_hook_launching
}

output "lifecycle_name_terminating" {
  description = "User must create a terminating lifecycle hook with this name."
  value       = local.lifecycle_hook_terminating
}
