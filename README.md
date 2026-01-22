# terraform-aws-update-dns

The module updates Route53 to create an A record in a zone for instances in an autoscaling group.
When the instance is terminated, the respective record is removed.

## Usage

* Chose autoscaling group name. It must be known before we create the autoscaling group or the update-dns module.
* Create the update-dns module.
```hcl
module "update-dns" {
  source  = "infrahouse/update-dns/aws"
  version = "1.2.0"

  asg_name          = local.asg_name
  route53_zone_id   = data.aws_route53_zone.cicd.zone_id
  route53_public_ip = false
  route53_hostname  = var.route53_hostname

  # Monitoring configuration (required)
  alarm_emails      = ["ops-team@example.com"]

  # Optional: Alert strategy (defaults to "immediate")
  # alert_strategy    = "threshold"  # Use "threshold" for alerts after multiple errors
}
```
* Create the autoscaling group. In the autoscaling group, create the initial lifecycle hook. It is needed to ensure the DNS records are created for the first instances in the ASG.
```hcl
resource "aws_autoscaling_group" "website" {
  name                = local.asg_name
...
  initial_lifecycle_hook {
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
    name                 = module.update-dns.lifecycle_name_launching
  }
  depends_on = [
    module.update-dns
  ]
}
```
* Create lifecycle launching and terminating hook. Note the lifecycle names. They are semi-random and should be taken from the update-dns module outputs.

```hcl
resource "aws_autoscaling_lifecycle_hook" "launching" {
  autoscaling_group_name = aws_autoscaling_group.website.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_LAUNCHING"
  name                   = module.update-dns.lifecycle_name_launching
  heartbeat_timeout      = 3600
}

resource "aws_autoscaling_lifecycle_hook" "terminating" {
  autoscaling_group_name = aws_autoscaling_group.website.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_TERMINATING"
  name                   = module.update-dns.lifecycle_name_terminating
  heartbeat_timeout      = 3600
}

```

### Multiple DNS Records Per Instance

You can create multiple DNS records with different prefixes for the same instance using the `route53_hostname_prefixes` variable:

```hcl
module "update-dns" {
  source  = "infrahouse/update-dns/aws"
  version = "1.2.0"

  asg_name                   = local.asg_name
  route53_zone_id            = data.aws_route53_zone.cicd.zone_id
  route53_hostname           = "_PublicDnsName_"  # Required for prefixes
  route53_hostname_prefixes  = ["ip", "api", "web"]
  route53_public_ip          = true
  alarm_emails               = ["ops-team@example.com"]
}
```

This configuration will create three DNS records for each instance. For example, if an instance gets IP `54.183.154.109`, the following records are created:
- `ip-54-183-154-109.example.com` → `54.183.154.109`
- `api-54-183-154-109.example.com` → `54.183.154.109`
- `web-54-183-154-109.example.com` → `54.183.154.109`

When the instance terminates, all three records are automatically deleted.

**Note**: The `route53_hostname_prefixes` variable only works with `_PrivateDnsName_` or `_PublicDnsName_`.
When using a custom hostname string, prefixes are ignored and only that exact hostname is used.

## Monitoring

This module includes built-in CloudWatch monitoring and alerting via the [terraform-aws-lambda-monitored](https://registry.terraform.io/modules/infrahouse/lambda-monitored/aws) module.

### CloudWatch Alarms

The following alarms are automatically created:
- **Error Alarm**: Triggered when Lambda function errors occur
- **Throttle Alarm**: Triggered when Lambda function is throttled
- **Duration Alarm**: Triggered when function execution exceeds timeout threshold

### Alert Strategy

You can configure the alert strategy using the `alert_strategy` variable:
- **`immediate`** (default): Alert on first error occurrence
- **`threshold`**: Alert only after multiple errors (more suitable for production environments with expected transient failures)

### SNS Notifications

All alarm notifications are sent to the email addresses specified in `alarm_emails`. You'll need to confirm the SNS subscription via email after the first deployment.

### Monitoring Outputs

The module exposes monitoring-related outputs:
- `cloudwatch_alarm_arns`: Map of alarm ARNs (error, throttle, duration)
- `sns_topic_arn`: ARN of the SNS topic for alerts
- `lambda_role_name`: IAM role name for attaching additional policies

<!-- BEGIN_TF_DOCS -->

## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.5 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 5.11, < 7.0, != 6.28.0 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.6 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 5.11, < 7.0, != 6.28.0 |
| <a name="provider_random"></a> [random](#provider\_random) | ~> 3.6 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_update_dns_lambda"></a> [update\_dns\_lambda](#module\_update\_dns\_lambda) | registry.infrahouse.com/infrahouse/lambda-monitored/aws | 1.0.4 |

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_event_rule.scale](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_target.scale-out](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_target) | resource |
| [aws_dynamodb_table.update_dns_lock](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/dynamodb_table) | resource |
| [aws_iam_policy.lambda_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role_policy_attachment.lambda_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_lambda_permission.allow_cloudwatch_asg_lifecycle_hook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [random_string.dynamodb-suffix](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |
| [random_string.lch_suffix](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_iam_policy_document.lambda_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |
| [aws_route53_zone.asg_zone](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/route53_zone) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_alarm_emails"></a> [alarm\_emails](#input\_alarm\_emails) | Email addresses to receive Lambda monitoring alerts from CloudWatch alarms. | `list(string)` | n/a | yes |
| <a name="input_alert_strategy"></a> [alert\_strategy](#input\_alert\_strategy) | Alert strategy for CloudWatch alarms: 'immediate' (alert on first error) or 'threshold' (alert after multiple errors). | `string` | `"immediate"` | no |
| <a name="input_asg_name"></a> [asg\_name](#input\_asg\_name) | Autoscaling group name to assign this lambda to. | `string` | n/a | yes |
| <a name="input_complete_launching_lifecycle_hook"></a> [complete\_launching\_lifecycle\_hook](#input\_complete\_launching\_lifecycle\_hook) | Lambda function will complete the launching lifecycle hook. | `bool` | `true` | no |
| <a name="input_complete_terminating_lifecycle_hook"></a> [complete\_terminating\_lifecycle\_hook](#input\_complete\_terminating\_lifecycle\_hook) | Lambda function will complete the terminating lifecycle hook. | `bool` | `true` | no |
| <a name="input_log_retention_in_days"></a> [log\_retention\_in\_days](#input\_log\_retention\_in\_days) | Number of days to retain logs in CloudWatch. | `number` | `365` | no |
| <a name="input_route53_hostname"></a> [route53\_hostname](#input\_route53\_hostname) | An A record with this name will be created in the route53 zone.<br/>Can be either a string or one of special values:<br/>- _PrivateDnsName_ (creates ip-10-1-1-1 based on private IP)<br/>- _PublicDnsName_ (creates ip-80-90-1-1 based on public IP) | `string` | `"_PrivateDnsName_"` | no |
| <a name="input_route53_hostname_prefixes"></a> [route53\_hostname\_prefixes](#input\_route53\_hostname\_prefixes) | List of prefixes to use when creating DNS records.<br/>Each prefix will create a separate DNS A record pointing to the same IP.<br/><br/>Examples:<br/>- ["ip"] (default): Creates ip-a-b-c-d<br/>- ["ip", "api"]: Creates ip-a-b-c-d and api-a-b-c-d<br/>- ["web", "app"]: Creates web-a-b-c-d and app-a-b-c-d<br/><br/>Only used when route53\_hostname is set to _PrivateDnsName_ or \_PublicDnsName\_.<br/>Ignored when route53\_hostname is a custom string. | `list(string)` | <pre>[<br/>  "ip"<br/>]</pre> | no |
| <a name="input_route53_public_ip"></a> [route53\_public\_ip](#input\_route53\_public\_ip) | If true, create the A record with the public IP address. Otherwise, private instance IP address. | `bool` | `true` | no |
| <a name="input_route53_ttl"></a> [route53\_ttl](#input\_route53\_ttl) | TTL in seconds on the route53 A record. | `number` | `300` | no |
| <a name="input_route53_zone_id"></a> [route53\_zone\_id](#input\_route53\_zone\_id) | Route53 zone id of a zone where A record will be created. | `any` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_cloudwatch_alarm_arns"></a> [cloudwatch\_alarm\_arns](#output\_cloudwatch\_alarm\_arns) | Map of CloudWatch alarm ARNs monitoring the Lambda function |
| <a name="output_lambda_arn"></a> [lambda\_arn](#output\_lambda\_arn) | ARN of the Lambda function that manages DNS records |
| <a name="output_lambda_name"></a> [lambda\_name](#output\_lambda\_name) | Lambda function name that manages DNS records |
| <a name="output_lambda_role_name"></a> [lambda\_role\_name](#output\_lambda\_role\_name) | IAM role name for the Lambda function |
| <a name="output_lifecycle_name_launching"></a> [lifecycle\_name\_launching](#output\_lifecycle\_name\_launching) | User must create a launching lifecycle hook with this name. |
| <a name="output_lifecycle_name_terminating"></a> [lifecycle\_name\_terminating](#output\_lifecycle\_name\_terminating) | User must create a terminating lifecycle hook with this name. |
| <a name="output_route53_hostname_prefixes"></a> [route53\_hostname\_prefixes](#output\_route53\_hostname\_prefixes) | List of DNS hostname prefixes configured for the module |
| <a name="output_sns_topic_arn"></a> [sns\_topic\_arn](#output\_sns\_topic\_arn) | ARN of SNS topic for Lambda monitoring alerts |
<!-- END_TF_DOCS -->
