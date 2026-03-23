# Getting Started

This guide walks you through deploying the update-dns module
for your Auto Scaling Group.

## Prerequisites

### AWS Resources

Before deploying, you need:

1. **A Route53 hosted zone** -- the zone where DNS records will be created
2. **An Auto Scaling Group** -- or a plan to create one
   (the ASG name must be known before deploying this module)

### Terraform Version

- Terraform >= 1.5
- AWS provider >= 5.11, < 7.0

## Step-by-Step Deployment

### Step 1: Define the ASG Name

The ASG name must be known before creating the module because it's used
to set up the EventBridge rule. Use a local value:

```hcl
locals {
  asg_name = "my-web-servers"
}
```

### Step 2: Create the update-dns Module

```hcl
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name        = local.asg_name
  route53_zone_id = data.aws_route53_zone.my_zone.zone_id
  alarm_emails    = ["ops-team@example.com"]
}
```

### Step 3: Create the ASG with Initial Lifecycle Hook

The `initial_lifecycle_hook` ensures DNS records are created
for the very first instances that launch with the ASG:

```hcl
resource "aws_autoscaling_group" "web" {
  name                = local.asg_name
  min_size            = 1
  max_size            = 3
  vpc_zone_identifier = var.subnet_ids

  launch_template {
    id      = aws_launch_template.web.id
    version = "$Latest"
  }

  initial_lifecycle_hook {
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
    name                 = module.update-dns.lifecycle_name_launching
  }

  depends_on = [module.update-dns]
}
```

### Step 4: Create Lifecycle Hooks for Ongoing Events

These hooks handle DNS updates for instances that launch or terminate
after the ASG is created:

```hcl
resource "aws_autoscaling_lifecycle_hook" "launching" {
  autoscaling_group_name = aws_autoscaling_group.web.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_LAUNCHING"
  name                   = module.update-dns.lifecycle_name_launching
  heartbeat_timeout      = 3600
}

resource "aws_autoscaling_lifecycle_hook" "terminating" {
  autoscaling_group_name = aws_autoscaling_group.web.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_TERMINATING"
  name                   = module.update-dns.lifecycle_name_terminating
  heartbeat_timeout      = 3600
}
```

### Step 5: Apply and Verify

```bash
terraform init
terraform plan
terraform apply
```

After applying, verify by checking the Route53 hosted zone for
new A records corresponding to your ASG instances.

## Confirm SNS Subscription

After the first deployment, you'll receive an email at the addresses
specified in `alarm_emails`. **Confirm the SNS subscription** to start
receiving Lambda monitoring alerts.

## Next Steps

- [Configure multiple DNS prefixes](examples.md#multiple-dns-prefixes)
- [Use private IPs instead of public](configuration.md#dns-configuration)
- [Set up custom hostnames](configuration.md#dns-configuration)
- [Review the architecture](architecture.md)
