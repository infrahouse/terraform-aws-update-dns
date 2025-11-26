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
  description = <<-EOT
    An A record with this name will be created in the route53 zone.
    Can be either a string or one of special values:
    - _PrivateDnsName_ (creates ip-10-1-1-1 based on private IP)
    - _PublicDnsName_ (creates ip-80-90-1-1 based on public IP)
  EOT
  type        = string
  default     = "_PrivateDnsName_"
}

variable "route53_hostname_prefixes" {
  description = <<-EOT
    List of prefixes to use when creating DNS records.
    Each prefix will create a separate DNS A record pointing to the same IP.

    Examples:
    - ["ip"] (default): Creates ip-a-b-c-d
    - ["ip", "api"]: Creates ip-a-b-c-d and api-a-b-c-d
    - ["web", "app"]: Creates web-a-b-c-d and app-a-b-c-d

    Only used when route53_hostname is set to _PrivateDnsName_ or _PublicDnsName_.
    Ignored when route53_hostname is a custom string.
  EOT
  type        = list(string)
  default     = ["ip"]

  validation {
    condition     = length(var.route53_hostname_prefixes) > 0
    error_message = "route53_hostname_prefixes must contain at least one prefix."
  }

  validation {
    condition = alltrue([
      for prefix in var.route53_hostname_prefixes :
      can(regex("^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$|^[a-z0-9]$", prefix))
    ])
    error_message = "Each prefix must start and end with alphanumeric character, contain only lowercase letters, numbers, and hyphens, and be 1-63 characters long."
  }

  validation {
    condition     = length(var.route53_hostname_prefixes) == length(distinct(var.route53_hostname_prefixes))
    error_message = "route53_hostname_prefixes must contain unique values. Duplicates are not allowed."
  }
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
