# Examples

Common use cases for the update-dns module.

## Basic Usage with Private IP

The simplest setup -- create DNS records using private IP addresses:

```hcl
locals {
  asg_name = "my-app"
}

module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name        = local.asg_name
  route53_zone_id = data.aws_route53_zone.internal.zone_id
  route53_public_ip = false
  alarm_emails    = ["ops@example.com"]
}
```

This creates records like `ip-10-1-2-3.internal.example.com` for
each instance in the ASG.

## Public IP Records

For instances with public IPs (e.g., behind no load balancer):

```hcl
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name          = local.asg_name
  route53_zone_id   = data.aws_route53_zone.public.zone_id
  route53_public_ip = true
  route53_hostname  = "_PublicDnsName_"
  alarm_emails      = ["ops@example.com"]
}
```

## Custom Hostname

Use a fixed hostname instead of auto-generated IP-based names:

```hcl
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name         = local.asg_name
  route53_zone_id  = data.aws_route53_zone.public.zone_id
  route53_hostname = "myapp"
  alarm_emails     = ["ops@example.com"]
}
```

This creates `myapp.example.com` pointing to the instance IP.

!!! note
    With a custom hostname, `route53_hostname_prefixes` is ignored
    and only one record is created per instance.

## Multiple DNS Prefixes

Create several DNS records per instance with different prefixes:

```hcl
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name                  = local.asg_name
  route53_zone_id           = data.aws_route53_zone.public.zone_id
  route53_hostname          = "_PublicDnsName_"
  route53_hostname_prefixes = ["ip", "api", "web"]
  route53_public_ip         = true
  alarm_emails              = ["ops@example.com"]
}
```

For an instance with IP `54.183.154.109`, this creates:

- `ip-54-183-154-109.example.com`
- `api-54-183-154-109.example.com`
- `web-54-183-154-109.example.com`

All three records point to the same IP and are deleted when
the instance terminates.

## Production Setup with Threshold Alerts

For production environments where transient Lambda errors are expected:

```hcl
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name        = local.asg_name
  route53_zone_id = data.aws_route53_zone.prod.zone_id
  alarm_emails    = ["oncall@example.com", "platform@example.com"]
  alert_strategy  = "threshold"
}
```

## Disabling Lifecycle Hook Completion

If another process needs to complete the lifecycle hooks (e.g., a custom
bootstrap script that runs after DNS is set up):

```hcl
module "update-dns" {
  source  = "registry.infrahouse.com/infrahouse/update-dns/aws"
  version = "1.3.0"

  asg_name                            = local.asg_name
  route53_zone_id                     = data.aws_route53_zone.my_zone.zone_id
  alarm_emails                        = ["ops@example.com"]
  complete_launching_lifecycle_hook   = false
  complete_terminating_lifecycle_hook = false
}
```

## Complete Example with ASG

See the [Getting Started](getting-started.md) guide for a full example
including the ASG and lifecycle hook configuration.

Working examples are also available in the repository:

- [`examples/basic/`](https://github.com/infrahouse/terraform-aws-update-dns/tree/main/examples/basic)
  -- Basic single-hostname setup
- [`examples/multi-prefix/`](https://github.com/infrahouse/terraform-aws-update-dns/tree/main/examples/multi-prefix)
  -- Multiple DNS prefixes per instance
