module "update-dns" {
  source            = "../../"
  asg_name          = aws_autoscaling_group.website.name
  route53_zone_id   = data.aws_route53_zone.cicd.zone_id
  route53_public_ip = false
  route53_hostname  = var.route53_hostname
}
