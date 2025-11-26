module "update-dns" {
  source                    = "../../"
  asg_name                  = local.asg_name
  route53_zone_id           = var.route53_zone_id
  route53_public_ip         = var.route53_hostname == "_PublicDnsName_" ? true : var.route53_public_ip
  route53_hostname          = var.route53_hostname
  route53_hostname_prefixes = var.route53_hostname_prefixes
  alarm_emails              = var.alarm_emails
}
