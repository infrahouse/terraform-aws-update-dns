variable "role_arn" {
  default = null
}
variable "route53_zone_id" {
  description = "Route53 zone ID for testing"
  type        = string
}
variable "region" {}


variable "subnet_public_ids" {}
variable "subnet_private_ids" {}
variable "internet_gateway_id" {}

variable "asg_min_size" {
  description = "Minimum number of instances in ASG"
  type        = number
  default     = 1
}

variable "asg_max_size" {
  description = "Maximum number of instances in ASG"
  type        = number
  default     = 10
}

variable "route53_hostname" {}

variable "alarm_emails" {
  description = "Email addresses to receive Lambda monitoring alerts"
  type        = list(string)
  default = [
    "aleks+terraform-aws-update-dns@infrahouse.com"
  ]
}
