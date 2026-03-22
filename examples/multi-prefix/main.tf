locals {
  asg_name = "my-api-servers"
}

data "aws_route53_zone" "public" {
  name = "example.com"
}

module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.2.1"

  asg_name                  = local.asg_name
  route53_zone_id           = data.aws_route53_zone.public.zone_id
  route53_hostname          = "_PublicDnsName_"
  route53_hostname_prefixes = ["ip", "api", "web"]
  route53_public_ip         = true
  alarm_emails              = ["ops@example.com"]
}

resource "aws_autoscaling_group" "api" {
  name                = local.asg_name
  min_size            = 1
  max_size            = 5
  vpc_zone_identifier = var.subnet_ids

  launch_template {
    id      = var.launch_template_id
    version = "$Latest"
  }

  initial_lifecycle_hook {
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
    name                 = module.update-dns.lifecycle_name_launching
  }

  depends_on = [module.update-dns]
}

resource "aws_autoscaling_lifecycle_hook" "launching" {
  autoscaling_group_name = aws_autoscaling_group.api.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_LAUNCHING"
  name                   = module.update-dns.lifecycle_name_launching
  heartbeat_timeout      = 3600
}

resource "aws_autoscaling_lifecycle_hook" "terminating" {
  autoscaling_group_name = aws_autoscaling_group.api.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_TERMINATING"
  name                   = module.update-dns.lifecycle_name_terminating
  heartbeat_timeout      = 3600
}
