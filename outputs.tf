output "lambda_name" {
  description = "Lambda function name that manages DNS records"
  value = aws_lambda_function.update_dns.function_name
}
