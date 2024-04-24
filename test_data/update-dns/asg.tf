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
  vpc_zone_identifier = var.subnet_private_ids
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
  lifecycle {
    create_before_destroy = true
  }
  tag {
    key                 = "update-dns-rule"
    propagate_at_launch = true
    value               = var.route53_hostname
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
