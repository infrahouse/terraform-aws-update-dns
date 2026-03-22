# Configuration Reference

This page documents all available configuration options.

## Required Variables

| Variable | Description |
|----------|-------------|
| `asg_name` | Autoscaling group name to assign the Lambda to. |
| `route53_zone_id` | Route53 zone ID where A records will be created. |
| `alarm_emails` | Email addresses for Lambda monitoring alerts. |

## DNS Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `route53_hostname` | `string` | `"_PrivateDnsName_"` | Hostname for the A record. See below. |
| `route53_hostname_prefixes` | `list(string)` | `["ip"]` | Prefixes for auto-generated hostnames. |
| `route53_public_ip` | `bool` | `true` | Use public IP (`true`) or private IP (`false`). |
| `route53_ttl` | `number` | `300` | TTL in seconds for the A record. |

### `route53_hostname` Values

The hostname can be one of three types:

**`_PrivateDnsName_`** (default) -- generates a hostname from the
instance's private IP. For example, `10.1.2.3` becomes
`ip-10-1-2-3.example.com`.

**`_PublicDnsName_`** -- generates a hostname from the instance's
public IP. For example, `54.183.154.109` becomes
`ip-54-183-154-109.example.com`.

**Custom string** -- uses the literal string as the hostname.
For example, `"myhost"` creates `myhost.example.com`.
Prefixes are ignored when using a custom string.

### `route53_hostname_prefixes`

Only applies when `route53_hostname` is `_PrivateDnsName_` or
`_PublicDnsName_`. Each prefix creates a separate A record:

```hcl
route53_hostname_prefixes = ["ip", "api", "web"]
# Creates: ip-10-1-2-3.example.com, api-10-1-2-3.example.com,
#          web-10-1-2-3.example.com
```

Validation rules:

- At least one prefix required
- Each prefix: lowercase alphanumeric and hyphens, 1-63 characters
- No duplicates allowed

## Lifecycle Hook Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `complete_launching_lifecycle_hook` | `bool` | `true` | Lambda completes the launching hook. |
| `complete_terminating_lifecycle_hook` | `bool` | `true` | Lambda completes the terminating hook. |

Set these to `false` if you have another process that should complete
the lifecycle hooks instead.

## Monitoring Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `alarm_emails` | `list(string)` | (required) | Email addresses for alerts. |
| `alert_strategy` | `string` | `"immediate"` | `"immediate"` or `"threshold"`. |
| `log_retention_in_days` | `number` | `365` | CloudWatch log retention. |

### Alert Strategies

- **`immediate`** -- alert on the first Lambda error. Good for
  critical environments where any failure needs attention.
- **`threshold`** -- alert after multiple errors. Better for
  production environments with expected transient failures.

## Outputs

| Output | Description |
|--------|-------------|
| `lifecycle_name_launching` | Name for the launching lifecycle hook. |
| `lifecycle_name_terminating` | Name for the terminating lifecycle hook. |
| `lambda_name` | Lambda function name. |
| `lambda_arn` | Lambda function ARN. |
| `lambda_role_name` | IAM role name for the Lambda. |
| `cloudwatch_alarm_arns` | Map of alarm ARNs (error, throttle, duration). |
| `sns_topic_arn` | SNS topic ARN for alerts. |
| `route53_hostname_prefixes` | Configured hostname prefixes. |
