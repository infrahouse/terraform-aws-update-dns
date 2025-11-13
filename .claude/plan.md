# Migration Plan: terraform-aws-update-dns → terraform-aws-lambda-monitored

Overview

This plan outlines migrating from a custom Lambda implementation to using the terraform-aws-lambda-monitored module, 
which provides built-in monitoring and simplified Lambda deployment.

  ---
## Current vs. Target Architecture

What Changes:
- Lambda deployment: Custom S3 bucket + packaging → Module-managed deployment
- Monitoring: Basic CloudWatch Logs → Logs + Alarms (errors, throttles, duration)
- IAM: Manual role + policies → Module-managed role + custom policy attachments
- Packaging: Custom bash script + null_resource → Module-handled multi-arch packaging

What Stays:
- EventBridge/CloudWatch Event rules (ASG lifecycle hooks)
- DynamoDB lock table
- ASG lifecycle hook resources
- Lambda function code (update_dns/main.py)
- All business logic and environment variables

  ---
## Migration Steps

### Phase 1: Add New Module & Configuration ✅ COMPLETED

1.1 Add new variable for monitoring ✅
- ✅ Add alarm_emails variable (required by new module)
- ✅ Add alert_strategy variable (optional: "immediate" vs "threshold")

1.2 Replace Lambda resource with module
module "update_dns_lambda" {
source  = "infrahouse/lambda-monitored/aws"

    function_name               = "update_dns_${var.asg_name}"
    lambda_source_dir          = "${path.module}/update_dns"
    requirements_file          = "${path.module}/update_dns/requirements.txt"
    python_version             = "python3.12"
    architecture               = "x86_64"
    
    alarm_emails               = var.alarm_emails
    cloudwatch_log_retention_days = var.log_retention_in_days
    
    timeout                    = 60
    handler                    = "main.lambda_handler"

    environment = {
      ROUTE53_ZONE_ID                     = var.route53_zone_id
      ROUTE53_ZONE_NAME                   = data.aws_route53_zone.asg_zone.name
      ROUTE53_HOSTNAME                    = var.route53_hostname
      ROUTE53_TTL                         = var.route53_ttl
      ROUTE53_PUBLIC_IP                   = var.route53_public_ip
      ASG_NAME                            = var.asg_name
      LOCK_TABLE_NAME                     = aws_dynamodb_table.lock.name
      LIFECYCLE_HOOK_LAUNCHING            = local.lifecycle_name_launching
      LIFECYCLE_HOOK_TERMINATING          = local.lifecycle_name_terminating
      COMPLETE_LAUNCHING_LIFECYCLE_HOOK   = var.complete_launching_lifecycle_hook
      COMPLETE_TERMINATING_LIFECYCLE_HOOK = var.complete_terminating_lifecycle_hook
    }
}

### Phase 1.1: Update the module unit tests ✅ COMPLETED

- ✅ Update tests/test_module.py for continuous testing during the module development
- ✅ Use pytest-infrahouse's fixture subzone
- ✅ Replace test_zone with route53_zone_id variable
- ✅ Remove data source lookup for Route53 zone

### Phase 2: Update IAM Configuration ✅ COMPLETED

2.1 Attach custom policies to module-created role ✅
The module creates a basic IAM role, but we need to attach our custom permissions:

resource "aws_iam_role_policy" "lambda_permissions" {
name   = "lambda_permissions"
role   = module.update_dns_lambda.lambda_role_name  # Use module output
policy = jsonencode({...})  # Keep existing policy
}

2.2 Remove standalone IAM role resource ✅
- ✅ Delete aws_iam_role.iam_for_lambda
- ✅ Remove aws_iam_role_policy_attachment.lambda_logs
- ✅ Keep custom policy attachments (updated to use module role)

### Phase 3: Clean Up Removed Resources ✅ COMPLETED

3.1 Remove custom Lambda deployment ✅
Delete these resources:
- ✅ aws_lambda_function.update_dns (lambda.tf) - replaced with module
- ✅ aws_lambda_function_event_invoke_config.update_dns (lambda.tf) - removed, module already manages this (fixes ResourceConflictException)
- ✅ aws_cloudwatch_log_group.update_dns (cloudwatch.tf) - removed, module handles this

3.2 Remove custom packaging infrastructure ✅
Delete these resources/files:
- ✅ null_resource.install_python_dependencies (lambda_code.tf)
- ✅ data.archive_file.lambda (lambda_code.tf)
- ✅ aws_s3_bucket.lambda_tmp (lambda_code.tf)
- ✅ aws_s3_object.lambda_package (lambda_code.tf)
- ✅ aws_s3_bucket_public_access_block.lambda_tmp (lambda_code.tf)
- ✅ aws_s3_bucket_policy.lambda_tmp_deny_insecure_transport (lambda_code.tf)
- ✅ random_uuid.lamda_src_hash (lambda_code.tf)
- ✅ package_update_dns.sh script
- ✅ lambda_code.tf file (deleted entirely)

3.3 Update Lambda permissions resource ✅
resource "aws_lambda_permission" "allow_cloudwatch_asg_lifecycle_hook" {
statement_id  = "AllowExecutionFromCloudWatch"
action        = "lambda:InvokeFunction"
function_name = module.update_dns_lambda.lambda_function_name  # Use module output
principal     = "events.amazonaws.com"
source_arn    = aws_cloudwatch_event_rule.scale.arn
}

### Phase 4: Update EventBridge Integration ✅ COMPLETED

4.1 Update CloudWatch Event target ✅
resource "aws_cloudwatch_event_target" "scale-out" {
rule      = aws_cloudwatch_event_rule.scale.name
target_id = "lambda"
arn       = module.update_dns_lambda.lambda_function_arn  # Use module output
}

### Phase 5: Update Outputs ✅ COMPLETED

5.1 Update outputs to expose module values ✅
output "lambda_name" {
value = module.update_dns_lambda.lambda_function_name
}

output "lambda_arn" {
value = module.update_dns_lambda.lambda_function_arn
}

output "lambda_role_name" {
value = module.update_dns_lambda.lambda_role_name
}

5.2 Add new monitoring outputs ✅

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

### Phase 6: Update Variables ✅ COMPLETED (except default value)

6.1 Add new required variable ✅
variable "alarm_emails" {
description = "Email addresses to receive Lambda monitoring alerts"
type        = list(string)
}

6.2 Optional: Add alert strategy variable ✅

variable "alert_strategy" {
description = "Alert strategy: 'immediate' or 'threshold'"
type        = string
default     = "immediate"
validation {
  condition     = contains(["immediate", "threshold"], var.alert_strategy)
  error_message = "Alert strategy must be either 'immediate' or 'threshold'."
}
}

###  Phase 7: Update Documentation ✅ COMPLETED

7.1 Update README.md ✅
- ✅ Add alarm_emails to required inputs
- ✅ Document new monitoring outputs (new Monitoring section)
- ✅ Update example usage (includes alarm_emails parameter)
- ✅ Add notes about CloudWatch alarms
- ✅ Update Inputs table with alarm_emails and alert_strategy
- ✅ Update Outputs table with cloudwatch_alarm_arns, lambda_arn, lambda_role_name, sns_topic_arn

7.2 Update module version ⏸️ PENDING
- Will be bumped to 1.0.0 using `make release-major` (breaking change: new required variable)

---
## Migration Status

✅ **RESOLVED**: Terraform validation bug - Fixed in terraform-aws-lambda-monitored v1.0.3

All blocking issues have been resolved. The module is using `infrahouse/lambda-monitored/aws` version **1.0.3** which includes the fix for the `duration_threshold_percent` validation issue.

---
File-by-File Changes

| File                        | Action        | Changes                                                        |
  |-----------------------------|---------------|----------------------------------------------------------------|
| variables.tf                | Modify        | Add alarm_emails variable                                      |
| lambda.tf                   | Major Rewrite | Replace resources with module call, keep aws_lambda_permission |
| lambda_code.tf              | DELETE        | All packaging logic removed                                    |
| package_update_dns.sh       | DELETE        | No longer needed                                               |
| cloudwatch.tf               | Modify        | Update event target ARN reference                              |
| outputs.tf                  | Modify        | Update to use module outputs, add monitoring outputs           |
| README.md                   | Modify        | Document new variable and monitoring features                  |
| versions.tf                 | Modify        | Add version constraint for new module                          |
| dynamodb.tf                 | No Change     | Keep as-is                                                     |
| lifecycle_hooks.tf          | No Change     | Keep as-is                                                     |
| data_sources.tf             | No Change     | Keep as-is                                                     |
| update_dns/main.py          | No Change     | Lambda code unchanged                                          |
| update_dns/requirements.txt | No Change     | Dependencies unchanged                                         |

  ---
## Testing Strategy

1. Pre-migration validation
   terraform plan  # Ensure current state is clean

2. Migration testing
   terraform init -upgrade  # Get new module
   terraform plan           # Review all changes

3. Post-migration validation
- Verify Lambda function exists and is configured correctly
- Confirm CloudWatch alarms are created
- Test SNS topic subscription (check email for confirmation)
- Trigger test ASG scale event
- Monitor CloudWatch Logs for successful execution
- Verify Route53 records are updated correctly

4. Rollback plan
- Keep backup of current module code
- Terraform state backup before applying changes

  ---
## Breaking Changes for Module Users

Required Actions:
1. Add alarm_emails variable to all module calls
2. Update any references to lambda_name output (should still work)
3. Confirm email subscriptions to new SNS topics

Benefits:
- Automatic error monitoring and alerting
- Simplified Lambda deployment and packaging
- Better observability with pre-configured alarms
- Reduced maintenance burden
- Multi-architecture support for future migrations

  ---
## Risk Assessment

Low Risk:
- Lambda function code unchanged
- Event-driven architecture unchanged
- DynamoDB lock table unchanged

Medium Risk:
- IAM role replacement (test permissions thoroughly)
- New S3 bucket for Lambda code (old bucket can be removed after migration)

Mitigation:
- Test in non-production environment first
- Keep old resources during parallel testing
- Monitor CloudWatch Logs closely after migration

  ---
Estimated Effort

- Code changes: 2-3 hours
- Testing: 2-3 hours
- Documentation updates: 1 hour
- Total: 5-7 hours
