data "aws_route53_zone" "asg_zone" {
  zone_id = var.route53_zone_id
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
