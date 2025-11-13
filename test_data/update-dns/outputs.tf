output "zone_id" {
  value = var.route53_zone_id
}

output "asg_name" {
  value = aws_autoscaling_group.website.name
}