locals {
  module         = "infrahouse/update-dns/aws"
  module_version = "1.2.1"
  lambda_timeout = 60

  default_module_tags = merge(
    {
      created_by_module : local.module
    },
  )

  asg_arn                    = "arn:aws:autoscaling:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:autoScalingGroup:*:autoScalingGroupName/${var.asg_name}"
  lifecycle_hook_launching   = "update-dns-${random_string.lch_suffix.result}-launching"
  lifecycle_hook_terminating = "update-dns-${random_string.lch_suffix.result}-terminating"
}
