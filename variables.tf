variable "asg_name" {
  description = "Autoscaling group name to assign this lambda to."
  type        = string
}

variable "complete_launching_lifecycle_hook" {
  description = "Lambda function will complete the launching lifecycle hook."
  type        = bool
  default     = true
}

variable "complete_terminating_lifecycle_hook" {
  description = "Lambda function will complete the terminating lifecycle hook."
  type        = bool
  default     = true
}

variable "log_retention_in_days" {
  description = "Number of days to retain logs in CloudWatch."
  type        = number
  default     = 365
}

variable "route53_ttl" {
  description = "TTL in seconds on the route53 A record."
  type        = number
  default     = 300
}

variable "route53_zone_id" {
  description = "Route53 zone id of a zone where A record will be created."
}

variable "route53_public_ip" {
  description = "If true, create the A record with the public IP address. Otherwise, private instance IP address."
  type        = bool
  default     = true
}

variable "route53_hostname" {
  description = "An A record with this name will be created in the rout53 zone. Can be either a string or one of special values: _PrivateDnsName_, tbc."
  type        = string
  default     = "_PrivateDnsName_"
}
