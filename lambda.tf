data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    actions = ["autoscaling:CompleteLifecycleAction"]
    resources = [
      local.asg_arn
    ]
  }
  statement {
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeTags"
    ]
    resources = ["*"]
  }
  statement {
    actions = [
      "ec2:CreateTags",
    ]
    resources = [
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*"
    ]
  }
  statement {
    actions = [
      "route53:ChangeResourceRecordSets",
      "route53:ListResourceRecordSets",
      "route53:GetHostedZone",
    ]
    resources = [
      "arn:aws:route53:::hostedzone/${var.route53_zone_id}"
    ]
  }
  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = [
      aws_dynamodb_table.update_dns_lock.arn
    ]
  }
}

resource "aws_iam_policy" "lambda_permissions" {
  name_prefix = "lambda_permissions"
  description = "IAM policy for lambda permissions (ASG, EC2, Route53, DynamoDB)"
  policy      = data.aws_iam_policy_document.lambda_permissions.json
  tags        = local.default_module_tags
}

module "update_dns_lambda" {
  source  = "registry.infrahouse.com/infrahouse/lambda-monitored/aws"
  version = "1.0.3"

  function_name                 = "update-dns-${var.asg_name}"
  lambda_source_dir             = "${path.module}/update_dns"
  requirements_file             = "${path.module}/update_dns/requirements.txt"
  python_version                = "python3.12"
  architecture                  = "x86_64"
  timeout                       = 60
  handler                       = "main.lambda_handler"
  cloudwatch_log_retention_days = var.log_retention_in_days

  alarm_emails   = var.alarm_emails
  alert_strategy = var.alert_strategy

  environment_variables = {
    ROUTE53_ZONE_ID                     = var.route53_zone_id
    ROUTE53_ZONE_NAME                   = data.aws_route53_zone.asg_zone.name
    ROUTE53_HOSTNAME                    = var.route53_hostname
    ROUTE53_TTL                         = tostring(var.route53_ttl)
    ROUTE53_PUBLIC_IP                   = tostring(var.route53_public_ip)
    ASG_NAME                            = var.asg_name
    LOCK_TABLE_NAME                     = aws_dynamodb_table.update_dns_lock.name
    LIFECYCLE_HOOK_LAUNCHING            = local.lifecycle_hook_launching
    LIFECYCLE_HOOK_TERMINATING          = local.lifecycle_hook_terminating
    COMPLETE_LAUNCHING_LIFECYCLE_HOOK   = tostring(var.complete_launching_lifecycle_hook)
    COMPLETE_TERMINATING_LIFECYCLE_HOOK = tostring(var.complete_terminating_lifecycle_hook)
  }

  tags = merge(
    local.default_module_tags,
    {
      module_version = local.module_version
    }
  )
}

resource "aws_iam_role_policy_attachment" "lambda_permissions" {
  role       = module.update_dns_lambda.lambda_role_name
  policy_arn = aws_iam_policy.lambda_permissions.arn
}

resource "aws_lambda_function_event_invoke_config" "update_dns" {
  function_name          = module.update_dns_lambda.lambda_function_name
  maximum_retry_attempts = 0
}

resource "aws_lambda_permission" "allow_cloudwatch_asg_lifecycle_hook" {
  action        = "lambda:InvokeFunction"
  function_name = module.update_dns_lambda.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scale.arn
}
