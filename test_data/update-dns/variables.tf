variable "role_arn" {}
variable "test_zone" {}
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
