resource "random_string" "asg-name" {
  length  = 32
  special = false
}

locals {
  asg_name = "update-dns-${random_string.asg-name.result}"
}
resource "aws_autoscaling_group" "website" {
  name                = local.asg_name
  min_size            = var.asg_min_size
  max_size            = var.asg_max_size
  vpc_zone_identifier = var.subnet_ids
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0
      instance_warmup        = 60
    }
    triggers = ["tag"]
  }
  launch_template {
    id      = aws_launch_template.website.id
    version = aws_launch_template.website.latest_version
  }
  tag {
    key                 = "update-dns-rule"
    propagate_at_launch = true
    value               = var.route53_hostname
  }
  initial_lifecycle_hook {
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
    name                 = module.update-dns.lifecycle_name_launching
  }
  depends_on = [
    module.update-dns
  ]
}

resource "aws_launch_template" "website" {
  name_prefix   = "update-dns-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"

  lifecycle {
    create_before_destroy = true
  }
}

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
