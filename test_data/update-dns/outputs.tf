output "zone_id" {
  value = data.aws_route53_zone.cicd.zone_id
}

output "asg_name" {
  value = aws_autoscaling_group.website.name
}