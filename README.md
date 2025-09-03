# terraform-aws-update-dns

The module updates Route53 to create an A record in a zone for instances in an autoscaling group.
When the instance is terminated, the respective record is removed.

## Usage

* Chose autoscaling group name. It must be known before we create the autoscaling group or the update-dns module.
* Create the update-dns module.
```hcl
module "update-dns" {
  source  = "infrahouse/update-dns/aws"
  version = "0.11.0"

  asg_name          = local.asg_name
  route53_zone_id   = data.aws_route53_zone.cicd.zone_id
  route53_public_ip = false
  route53_hostname  = var.route53_hostname
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
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.5 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 5.11, < 7.0 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.6 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | n/a |
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 5.11, < 7.0 |
| <a name="provider_null"></a> [null](#provider\_null) | n/a |
| <a name="provider_random"></a> [random](#provider\_random) | ~> 3.6 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_event_rule.scale](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_target.scale-out](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_target) | resource |
| [aws_cloudwatch_log_group.update_dns](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_dynamodb_table.update_dns_lock](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/dynamodb_table) | resource |
| [aws_iam_policy.lambda_logging](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy.lambda_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role.iam_for_lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.AWSLambdaBasicExecutionRole](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.lambda_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.lambda_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_lambda_function.update_dns](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_function_event_invoke_config.update_dns](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function_event_invoke_config) | resource |
| [aws_lambda_permission.allow_cloudwatch_asg_lifecycle_hook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_s3_bucket.lambda_tmp](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket_policy.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_policy) | resource |
| [aws_s3_bucket_public_access_block.public_access](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block) | resource |
| [aws_s3_object.lambda_package](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_object) | resource |
| [null_resource.install_python_dependencies](https://registry.terraform.io/providers/hashicorp/null/latest/docs/resources/resource) | resource |
| [random_string.dynamodb-suffix](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |
| [random_string.lch_suffix](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |
| [random_uuid.lamda_src_hash](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/uuid) | resource |
| [archive_file.lambda](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_iam_policy.AWSLambdaBasicExecutionRole](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy) | data source |
| [aws_iam_policy_document.assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.bucket_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.lambda-permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.lambda_logging](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |
| [aws_route53_zone.asg_zone](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/route53_zone) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_asg_name"></a> [asg\_name](#input\_asg\_name) | Autoscaling group name to assign this lambda to. | `string` | n/a | yes |
| <a name="input_complete_launching_lifecycle_hook"></a> [complete\_launching\_lifecycle\_hook](#input\_complete\_launching\_lifecycle\_hook) | Lambda function will complete the launching lifecycle hook. | `bool` | `true` | no |
| <a name="input_complete_terminating_lifecycle_hook"></a> [complete\_terminating\_lifecycle\_hook](#input\_complete\_terminating\_lifecycle\_hook) | Lambda function will complete the terminating lifecycle hook. | `bool` | `true` | no |
| <a name="input_log_retention_in_days"></a> [log\_retention\_in\_days](#input\_log\_retention\_in\_days) | Number of days to retain logs in CloudWatch. | `number` | `365` | no |
| <a name="input_route53_hostname"></a> [route53\_hostname](#input\_route53\_hostname) | An A record with this name will be created in the rout53 zone. Can be either a string or one of special values: \_PrivateDnsName\_, tbc. | `string` | `"_PrivateDnsName_"` | no |
| <a name="input_route53_public_ip"></a> [route53\_public\_ip](#input\_route53\_public\_ip) | If true, create the A record with the public IP address. Otherwise, private instance IP address. | `bool` | `true` | no |
| <a name="input_route53_ttl"></a> [route53\_ttl](#input\_route53\_ttl) | TTL in seconds on the route53 A record. | `number` | `300` | no |
| <a name="input_route53_zone_id"></a> [route53\_zone\_id](#input\_route53\_zone\_id) | Route53 zone id of a zone where A record will be created. | `any` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambda_name"></a> [lambda\_name](#output\_lambda\_name) | Lambda function name that manages DNS records |
| <a name="output_lifecycle_name_launching"></a> [lifecycle\_name\_launching](#output\_lifecycle\_name\_launching) | User must create a launching lifecycle hook with this name. |
| <a name="output_lifecycle_name_terminating"></a> [lifecycle\_name\_terminating](#output\_lifecycle\_name\_terminating) | User must create a terminating lifecycle hook with this name. |
