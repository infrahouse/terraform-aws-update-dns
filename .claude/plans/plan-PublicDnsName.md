# Implementation Plan: _PublicDnsName_ Support

## Overview
Add support for `_PublicDnsName_` special value in `route53_hostname` variable. When set, the Lambda function 
will create DNS records based on the instance's public IP address (e.g., `ip-80-90-1-1.example.com` for public IP `80.90.1.1`).

## Current Implementation Analysis

### How _PrivateDnsName_ Works
1. **Location**: `update_dns/main.py:70-75`
2. **Logic**: The `resolve_hostname()` function checks if `ROUTE53_HOSTNAME` environment variable equals `_PrivateDnsName_`
3. **Behavior**: Returns `instance.hostname` (EC2's private DNS name like `ip-10-1-1-1.ec2.internal`) 
   or the instance's `Name` tag if hostname is None
4. **IP Used**: Uses private IP (controlled by `route53_public_ip` variable)

### Key Files to Modify
- `update_dns/main.py` - Lambda function code
- `variables.tf` - Update documentation
- `tests/test_module.py` - Add test case
- `test_data/update-dns/asg.tf` - Configure ASG for public subnet testing

## Implementation Steps

### 1. Add Test Case (TDD Approach)
**File**: `tests/test_module.py`

**Action**: Add `_PublicDnsName_` as a new test parameter in the parametrize decorator

**Current**:
```python
@pytest.mark.parametrize(
    "route53_hostname, asg_size",
    [("update-dns-test", 1), ("update-dns-test", 2), ("_PrivateDnsName_", 3)],
)
```

**New**:
```python
@pytest.mark.parametrize(
    "route53_hostname, asg_size",
    [
        ("update-dns-test", 1),
        ("update-dns-test", 2),
        ("_PrivateDnsName_", 3),
        ("_PublicDnsName_", 1),  # New test case
    ],
)
```

**Test Logic Addition**:
Add a new conditional block after the `_PrivateDnsName_` test (after line 122):

```python
elif route53_hostname == "_PublicDnsName_":
    try:
        for instance in asg.instances:
            assert instance.public_ip
            # Hostname should be ip-80-90-1-1 format based on public IP
            expected_hostname = "ip-" + instance.public_ip.replace(".", "-")
            assert instance.tags.get("update-dns:hostname") == expected_hostname
            assert zone.search_hostname(expected_hostname) == [instance.public_ip]
    finally:
        if not keep_after:
            for instance in asg.instances:
                expected_hostname = "ip-" + instance.public_ip.replace(".", "-")
                LOG.info(
                    "Deleting record %s=%s", expected_hostname, instance.public_ip
                )
                zone.delete_record(expected_hostname, instance.public_ip)
```

**Update terraform.tfvars Generation**:
Modify the tfvars writing section (around line 71-96) to conditionally pass subnet IDs and route53_public_ip:

```python
# Determine which subnets to use based on hostname
if route53_hostname == "_PublicDnsName_":
    subnet_ids = subnet_public_ids
    route53_public_ip = True
else:
    subnet_ids = subnet_private_ids
    route53_public_ip = False

with open(osp.join(terraform_module_dir, "terraform.tfvars"), "w") as fp:
    fp.write(
        dedent(
            f"""
                region = "{aws_region}"
                route53_zone_id = "{subzone["subzone_id"]["value"]}"

                subnet_ids = {json.dumps(subnet_ids)}
                internet_gateway_id = "{internet_gateway_id}"
                route53_hostname = "{route53_hostname}"
                route53_public_ip = {str(route53_public_ip).lower()}
                asg_min_size = {asg_size}
                asg_max_size = {asg_size}
                alarm_emails = ["test@example.com"]
                """
        )
    )
    if test_role_arn:
        fp.write(
            dedent(
                f"""
                role_arn      = "{test_role_arn}"
                """
            )
        )
```

### 2. Simplify Test Infrastructure Variables
**Files**:
- `test_data/update-dns/variables.tf`
- `test_data/update-dns/asg.tf`

**Strategy**: Move conditional logic from Terraform to Python test code. The test will decide which subnets to pass.

**File: test_data/update-dns/variables.tf**

Replace `subnet_public_ids` and `subnet_private_ids` with a single variable:

**Remove**:
```terraform
variable "subnet_public_ids" {}
variable "subnet_private_ids" {}
```

**Add**:
```terraform
variable "subnet_ids" {
  description = "Subnet IDs for ASG (public or private based on test requirements)"
  type        = list(string)
}

variable "route53_public_ip" {
  description = "Use public IP for Route53 records"
  type        = bool
  default     = false
}
```

**File: test_data/update-dns/asg.tf**

**Modify line 13** - Simply use the subnet_ids variable:
```terraform
vpc_zone_identifier = var.subnet_ids
```

**Note**: If changing subnets requires instance refresh, the ASG already has 
an `instance_refresh` block configured (lines 14-21), but we may need to verify 
instances are refreshed after the subnet change.

### 3. Configure Test Module Settings
**File**: `test_data/update-dns/main.tf`

**Current**:
```terraform
module "update-dns" {
  source            = "../../"
  asg_name          = local.asg_name
  route53_zone_id   = var.route53_zone_id
  route53_public_ip = false
  route53_hostname  = var.route53_hostname
  alarm_emails      = var.alarm_emails
}
```

**Modify**: Set `route53_public_ip` conditionally - true when using `_PublicDnsName_`, otherwise use the variable:
```terraform
module "update-dns" {
  source            = "../../"
  asg_name          = local.asg_name
  route53_zone_id   = var.route53_zone_id
  route53_public_ip = var.route53_hostname == "_PublicDnsName_" ? true : var.route53_public_ip
  route53_hostname  = var.route53_hostname
  alarm_emails      = var.alarm_emails
}
```

**Rationale**: When `route53_hostname` is `_PublicDnsName_`, we must use public IPs for the A records. 
This conditional ensures the correct IP type is always used with this special value, while still allowing users 
to control `route53_public_ip` for other hostname configurations.

### 4. Ensure Instance Refresh After Subnet Change

**Important**: When changing `vpc_zone_identifier` in an ASG, instances need to be refreshed to join the new subnets. 
The ASG configuration already includes an `instance_refresh` block (test_data/update-dns/asg.tf:14-21), 
but we need to verify it triggers correctly.

**Options**:
1. **Automatic refresh**: Check if changing `vpc_zone_identifier` automatically triggers instance refresh
2. **Manual trigger**: If automatic refresh doesn't occur, we may need to:
   - Add a null_resource trigger in Terraform, OR
   - Wait in the test code for instances to be in the correct subnets, OR
   - Explicitly set a trigger in the instance_refresh configuration

**Verification in test**:
After terraform_apply, verify instances are in the correct subnets:
```python
for instance in asg.instances:
    if route53_hostname == "_PublicDnsName_":
        assert instance.public_ip is not None, f"Instance {instance.instance_id} should have public IP"
    # Could also verify subnet_id is in the expected subnet_ids list
```

### 5. Run Tests - Verify Failure
**Command**:
```bash
pytest tests/test_module.py::test_module -k "_PublicDnsName_" -v
```

**Expected Result**: Test should FAIL because the Lambda doesn't yet implement `_PublicDnsName_` logic

### 6. Implement Lambda Function Logic
**File**: `update_dns/main.py`

**Modify**: Update the `resolve_hostname()` function (lines 70-75)

**Current**:
```python
def resolve_hostname(instance_id):
    if environ["ROUTE53_HOSTNAME"] == "_PrivateDnsName_":
        instance = EC2Instance(instance_id)
        return instance.tags["Name"] if instance.hostname is None else instance.hostname

    return environ["ROUTE53_HOSTNAME"]
```

**New**:
```python
def resolve_hostname(instance_id):
    route53_hostname = environ["ROUTE53_HOSTNAME"]

    if route53_hostname == "_PrivateDnsName_":
        instance = EC2Instance(instance_id)
        return instance.tags["Name"] if instance.hostname is None else instance.hostname

    elif route53_hostname == "_PublicDnsName_":
        instance = EC2Instance(instance_id)
        public_ip = instance.public_ip
        # Convert IP like 80.90.1.1 to hostname like ip-80-90-1-1
        return f"ip-{public_ip.replace('.', '-')}"

    return route53_hostname
```

### 7. Update Documentation
**File**: `variables.tf`

**Modify line 41** (description for `route53_hostname`):

**Current**:
```terraform
description = "An A record with this name will be created in the rout53 zone. Can be either a string or one of special values: _PrivateDnsName_, tbc."
```

**New**:
```terraform
description = "An A record with this name will be created in the route53 zone. Can be either a string or one of special values: _PrivateDnsName_ (creates ip-10-1-1-1 based on private IP), _PublicDnsName_ (creates ip-80-90-1-1 based on public IP)."
```

### 8. Run Tests - Verify Success
**Command**:
```bash
pytest tests/test_module.py::test_module -k "_PublicDnsName_" -v
```

**Expected Result**: Test should PASS

### 9. Run Full Test Suite
**Command**:
```bash
pytest tests/test_module.py -v
```

**Expected Result**: All tests should PASS, including existing tests for:
- Static hostname with 1 instance
- Static hostname with 2 instances
- `_PrivateDnsName_` with 3 instances
- `_PublicDnsName_` with 1 instance (new)

All parametrized with both AWS provider versions (~> 5.31 and ~> 6.0)

### 10. Code Review and Cleanup
- Review error handling (what if instance doesn't have public IP?)
- Check logging statements are appropriate
- Verify tag creation is correct
- Ensure cleanup in test finally blocks works properly
- Verify instance refresh completes after subnet changes

### 11. Update CHANGELOG and Documentation
- Add entry to CHANGELOG.md
- Update README.md if necessary
- Document the new special value behavior

## Implementation Notes

### Error Handling Considerations
- What happens if `_PublicDnsName_` is used but instance is in private subnet?
- The `get_instance_ip()` function (line 61-67) has fallback to tags - verify this works for public IP
- Consider adding validation/warning if public IP is None

### Testing Considerations
- Test uses public subnets when `route53_hostname == "_PublicDnsName_"`
- Instances must have public IPs assigned (via launch template network_interfaces)
- Internet Gateway must be configured (already available via `service_network` fixture)
- Cleanup must delete the dynamically created hostnames

### Dependencies
- Relies on `infrahouse_core.aws.ec2_instance.EC2Instance` - verify `public_ip` attribute exists
- Requires ASG instances to be in public subnets with public IPs
- Assumes Route53 zone can handle the DNS records

## Summary
This implementation follows TDD principles:
1. Write failing test
2. Implement minimal code to pass test
3. Verify all tests pass
4. Refactor and document

The change is minimal and mirrors the existing `_PrivateDnsName_` implementation, reducing risk and maintaining consistency with the existing codebase.
