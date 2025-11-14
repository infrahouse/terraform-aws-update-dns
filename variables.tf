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
  description = "An A record with this name will be created in the route53 zone. Can be either a string or one of special values: _PrivateDnsName_ (creates ip-10-1-1-1 based on private IP), _PublicDnsName_ (creates ip-80-90-1-1 based on public IP)."
  type        = string
  default     = "_PrivateDnsName_"
}

variable "alarm_emails" {
  description = "Email addresses to receive Lambda monitoring alerts from CloudWatch alarms."
  type        = list(string)
}

variable "alert_strategy" {
  description = "Alert strategy for CloudWatch alarms: 'immediate' (alert on first error) or 'threshold' (alert after multiple errors)."
  type        = string
  default     = "immediate"
  validation {
    condition     = contains(["immediate", "threshold"], var.alert_strategy)
    error_message = "Alert strategy must be either 'immediate' or 'threshold'."
  }
}
