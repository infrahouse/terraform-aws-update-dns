data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

data "aws_iam_policy" "AWSLambdaBasicExecutionRole" {
  name = "AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
    ]
    resources = [
      aws_cloudwatch_log_group.update_dns.arn
    ]
  }
  statement {
    effect = "Allow"
    actions = [
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:*:log-stream:*"
    ]
  }
}

data "aws_iam_policy_document" "lambda-permissions" {
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

resource "aws_iam_policy" "lambda_logging" {
  name_prefix = "lambda_logging"
  description = "IAM policy for logging from a lambda"
  policy      = data.aws_iam_policy_document.lambda_logging.json
  tags        = local.default_module_tags
}

resource "aws_iam_policy" "lambda_permissions" {
  name_prefix = "lambda_permissions"
  description = "IAM policy for a lambda permissions"
  policy      = data.aws_iam_policy_document.lambda-permissions.json
  tags        = local.default_module_tags
}

resource "aws_iam_role" "iam_for_lambda" {
  name_prefix        = "iam_for_lambda"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = local.default_module_tags
}

resource "aws_iam_role_policy_attachment" "AWSLambdaBasicExecutionRole" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = data.aws_iam_policy.AWSLambdaBasicExecutionRole.arn
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.lambda_logging.arn
}

resource "aws_iam_role_policy_attachment" "lambda_permissions" {
  policy_arn = aws_iam_policy.lambda_permissions.arn
  role       = aws_iam_role.iam_for_lambda.name
}

resource "aws_lambda_function" "update_dns" {
  s3_bucket     = aws_s3_bucket.lambda_tmp.bucket
  s3_key        = aws_s3_object.lambda_package.key
  function_name = "update_dns_${var.asg_name}"
  role          = aws_iam_role.iam_for_lambda.arn
  handler       = "main.lambda_handler"

  runtime = "python3.12"
  timeout = 60
  environment {
    variables = {
      "ROUTE53_ZONE_ID" : var.route53_zone_id,
      "ROUTE53_ZONE_NAME" : data.aws_route53_zone.asg_zone.name,
      "ROUTE53_HOSTNAME" : var.route53_hostname,
      "ROUTE53_TTL" : var.route53_ttl,
      "ROUTE53_PUBLIC_IP" : var.route53_public_ip
      "ASG_NAME" : var.asg_name,
      "LOCK_TABLE_NAME" : aws_dynamodb_table.update_dns_lock.name
      "LIFECYCLE_HOOK_LAUNCHING" : local.lifecycle_hook_launching
      "LIFECYCLE_HOOK_TERMINATING" : local.lifecycle_hook_terminating
      "COMPLETE_LAUNCHING_LIFECYCLE_HOOK" : var.complete_launching_lifecycle_hook
      "COMPLETE_TERMINATING_LIFECYCLE_HOOK" : var.complete_terminating_lifecycle_hook
    }
  }
  tags = merge(
    local.default_module_tags,
    {
      module_version : local.module_version
    }
  )
  depends_on = [
    data.archive_file.lambda,
    aws_s3_object.lambda_package,
  ]
}

resource "aws_lambda_function_event_invoke_config" "update_dns" {
  function_name          = aws_lambda_function.update_dns.function_name
  maximum_retry_attempts = 0
}

resource "aws_lambda_permission" "allow_cloudwatch_asg_lifecycle_hook" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.update_dns.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scale.arn
}
