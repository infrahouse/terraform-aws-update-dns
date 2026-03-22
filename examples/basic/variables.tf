variable "subnet_ids" {
  description = "List of subnet IDs for the ASG."
  type        = list(string)
}

variable "launch_template_id" {
  description = "Launch template ID for the ASG."
  type        = string
}
