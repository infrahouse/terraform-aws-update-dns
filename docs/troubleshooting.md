# Troubleshooting

Common issues and their solutions.

## DNS Records Not Created

### Symptoms

- Instance launches but no A record appears in Route53
- ASG instances stuck in `Pending:Wait` state

### Check 1: Lambda Logs

```bash
aws logs tail /aws/lambda/update-dns-<asg_name> --follow
```

Look for:

- Permission errors (IAM policy issues)
- Route53 zone not found
- Instance not found (timing issue)

### Check 2: EventBridge Rule

Verify the EventBridge rule exists and is enabled:

```bash
aws events list-rules --name-prefix asg-scale
```

### Check 3: Lifecycle Hook

Verify the lifecycle hook is configured:

```bash
aws autoscaling describe-lifecycle-hooks \
  --auto-scaling-group-name <asg_name>
```

The hook names should match the module outputs
(`lifecycle_name_launching` and `lifecycle_name_terminating`).

### Common Fixes

**Wrong ASG name:**
The `asg_name` variable must exactly match the Auto Scaling Group name.
The EventBridge rule filters on this name.

**Route53 zone permissions:**
Ensure the Lambda role has permissions on the correct hosted zone ID.

**Instance has no public IP:**
If `route53_public_ip = true` but the instance has no public IP,
the Lambda will fail. Set `route53_public_ip = false` for instances
in private subnets.

## DNS Records Not Deleted on Termination

### Symptoms

- Instance terminates but DNS records remain
- Stale records pointing to non-existent IPs

### Check: Terminating Lifecycle Hook

Ensure you've created both launching AND terminating hooks:

```hcl
resource "aws_autoscaling_lifecycle_hook" "terminating" {
  autoscaling_group_name = aws_autoscaling_group.web.name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_TERMINATING"
  name                   = module.update-dns.lifecycle_name_terminating
  heartbeat_timeout      = 3600
}
```

If the terminating hook is missing, the Lambda is never invoked
on termination and records are left behind.

## Lambda Timeout

### Symptoms

- CloudWatch duration alarm fires
- Lifecycle hook times out instead of completing

### Possible Causes

**DynamoDB lock contention:**
During rapid scale events, multiple Lambda invocations may compete
for the lock. The default Lambda timeout is 60 seconds, which should
be sufficient in most cases.

**Route53 API throttling:**
If you're creating many records simultaneously, Route53 may throttle
requests. Check Lambda logs for `Throttling` errors.

## Lifecycle Hook Timeout

### Symptoms

- Instances stuck in `Pending:Wait` or `Terminating:Wait`

### Fix

The default `heartbeat_timeout` should be at least 3600 seconds (1 hour)
to give the Lambda sufficient time to process, including retries:

```hcl
resource "aws_autoscaling_lifecycle_hook" "launching" {
  # ...
  heartbeat_timeout = 3600
}
```

If the hook times out, you can manually complete it:

```bash
aws autoscaling complete-lifecycle-action \
  --lifecycle-action-result CONTINUE \
  --lifecycle-hook-name <hook_name> \
  --auto-scaling-group-name <asg_name> \
  --instance-id <instance_id>
```

## CloudWatch Alarm Notifications Not Received

### Symptoms

- Lambda errors occur but no email notifications

### Fix

After the first `terraform apply`, check your email for the SNS
subscription confirmation. You must click the confirmation link
before notifications will be delivered.

## Multiple Prefixes Not Working

### Symptoms

- Only one DNS record created instead of multiple

### Check

The `route53_hostname_prefixes` variable only works with
`_PrivateDnsName_` or `_PublicDnsName_`. If `route53_hostname`
is set to a custom string, prefixes are ignored:

```hcl
# This creates THREE records per instance:
route53_hostname          = "_PublicDnsName_"
route53_hostname_prefixes = ["ip", "api", "web"]

# This creates ONE record per instance (prefixes ignored):
route53_hostname          = "myhost"
route53_hostname_prefixes = ["ip", "api", "web"]  # ignored
```

## Getting Help

### Collect Debug Information

```bash
# Lambda logs
aws logs tail /aws/lambda/update-dns-<asg_name> --since 1h

# ASG lifecycle hooks
aws autoscaling describe-lifecycle-hooks \
  --auto-scaling-group-name <asg_name>

# EventBridge rules
aws events list-rules --name-prefix asg-scale

# Route53 records
aws route53 list-resource-record-sets \
  --hosted-zone-id <zone_id> \
  --query "ResourceRecordSets[?Type=='A']"
```

### Open an Issue

[Open a GitHub issue](https://github.com/infrahouse/terraform-aws-update-dns/issues/new)
with:

- Module version
- Terraform plan/apply output
- Lambda logs
- ASG and lifecycle hook configuration
