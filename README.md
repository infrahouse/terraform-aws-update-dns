# terraform-aws-update-dns

[![Need Help?](https://img.shields.io/badge/Need%20Help%3F-Contact%20Us-0066CC)](https://infrahouse.com/contact)
[![Docs](https://img.shields.io/badge/docs-github.io-blue)](https://infrahouse.github.io/terraform-aws-update-dns/)
[![Registry](https://img.shields.io/badge/Terraform-Registry-purple?logo=terraform)](https://registry.terraform.io/modules/infrahouse/update-dns/aws/latest)
[![Release](https://img.shields.io/github/release/infrahouse/terraform-aws-update-dns.svg)](https://github.com/infrahouse/terraform-aws-update-dns/releases/latest)
[![AWS Route 53](https://img.shields.io/badge/AWS-Route%2053-orange?logo=amazonroute53)](https://aws.amazon.com/route53/)
[![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-orange?logo=awslambda)](https://aws.amazon.com/lambda/)
[![Security](https://img.shields.io/github/actions/workflow/status/infrahouse/terraform-aws-update-dns/vuln-scanner-pr.yml?label=Security)](https://github.com/infrahouse/terraform-aws-update-dns/actions/workflows/vuln-scanner-pr.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

This Terraform module automatically manages Route53 DNS A records for EC2 instances
in an Auto Scaling Group. A Lambda function responds to ASG lifecycle hook events
via CloudWatch EventBridge, creating DNS records on instance launch and deleting
them on termination.

## Why This Module?

Some services running on EC2 instances in an Auto Scaling Group need a stable,
predictable DNS name for each node -- not just a load balancer endpoint.
The most common reason is **TLS certificates**: if a node needs its own
certificate (e.g., for inter-node encryption in an Elasticsearch cluster),
the certificate's Subject Alternative Name must match a resolvable hostname.
An ephemeral IP address won't work.

For example, [terraform-aws-elasticsearch](https://github.com/infrahouse/terraform-aws-elasticsearch)
uses this module to give every node a DNS name like `ip-10-1-2-3.example.com`.
Puppet on the node then requests a TLS certificate for that FQDN and configures
Elasticsearch's transport layer (`xpack.security.transport.ssl`) to use it.
Without a known hostname, inter-node TLS verification would fail.

Another use case is **poor man's load balancing**: set `route53_hostname` to a
fixed string like `"api"` and every instance in the ASG gets an A record with
the same name. Route53 returns all IPs in round-robin order, giving you
DNS-based load balancing with zero extra infrastructure -- no ALB required.

Other use cases include cluster node discovery (nodes find peers by DNS name
rather than hard-coded IPs) and direct SSH/debugging access to specific
instances behind an ASG.

This module solves the problem natively within AWS:

- **Zero external dependencies** -- uses only AWS services
  (Lambda, EventBridge, Route53, DynamoDB)
- **Lifecycle-hook driven** -- DNS records are created before the instance
  enters service and cleaned up on termination
- **Concurrency safe** -- DynamoDB-based locking prevents race conditions
  during rapid scale events
- **Multiple DNS records per instance** -- create several prefixed records
  (e.g., `ip-`, `api-`, `web-`) pointing to the same instance
- **Built-in monitoring** -- Lambda errors, throttles, and duration are
  monitored via CloudWatch alarms with SNS notifications

## Features

- Automatic DNS A record creation on instance launch
- Automatic DNS record cleanup on instance termination
- Support for private or public IP addresses
- Support for custom hostnames or auto-generated names from IP
- Multiple DNS record prefixes per instance
- DynamoDB-based concurrency locking
- CloudWatch monitoring with configurable alert strategies
- Compatible with AWS provider v5 and v6

## Quick Start

```hcl
# 1. Choose an ASG name upfront
locals {
  asg_name = "my-web-servers"
}

# 2. Create the update-dns module
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.2.1"

  asg_name        = local.asg_name
  route53_zone_id = data.aws_route53_zone.my_zone.zone_id
  alarm_emails    = ["ops-team@example.com"]
}

# 3. Create the ASG with the initial lifecycle hook
resource "aws_autoscaling_group" "web" {
  name = local.asg_name
  # ... other configuration ...

  initial_lifecycle_hook {
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
    name                 = module.update-dns.lifecycle_name_launching
  }

  depends_on = [module.update-dns]
}

# 4. Create lifecycle hooks for ongoing events
resource "aws_autoscaling_lifecycle_hook" "launching" {
  autoscaling_group_name = aws_autoscaling_group.web.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_LAUNCHING"
  name                   = module.update-dns.lifecycle_name_launching
  heartbeat_timeout      = 3600
}

resource "aws_autoscaling_lifecycle_hook" "terminating" {
  autoscaling_group_name = aws_autoscaling_group.web.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_TERMINATING"
  name                   = module.update-dns.lifecycle_name_terminating
  heartbeat_timeout      = 3600
}
```

## Documentation

- [Getting Started](https://infrahouse.github.io/terraform-aws-update-dns/getting-started/)
  -- Prerequisites and first deployment
- [Architecture](https://infrahouse.github.io/terraform-aws-update-dns/architecture/)
  -- How the module works
- [Configuration](https://infrahouse.github.io/terraform-aws-update-dns/configuration/)
  -- All variables explained
- [Examples](https://infrahouse.github.io/terraform-aws-update-dns/examples/)
  -- Common use cases
- [Troubleshooting](https://infrahouse.github.io/terraform-aws-update-dns/troubleshooting/)
  -- Common issues and solutions

## Examples

See the [`examples/`](examples/) directory for working configurations:

- [`examples/basic/`](examples/basic/) -- Basic single-hostname setup
- [`examples/multi-prefix/`](examples/multi-prefix/) -- Multiple DNS prefixes per instance

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

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[Apache 2.0](LICENSE)
