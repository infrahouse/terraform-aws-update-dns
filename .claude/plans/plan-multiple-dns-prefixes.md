# Implementation Plan: Multiple DNS Record Prefixes

## Overview
Implement a new feature that allows users to create multiple DNS records with different prefixes for 
the same EC2 instance IP address. This enables creating multiple DNS names pointing to the same instance, 
useful for scenarios like API endpoints, service discovery, or multi-purpose servers.

## Feature Description

### Current Behavior
When an EC2 instance has IP address `a.b.c.d`, the module creates a single DNS A record:
- `ip-a-b-c-d.example.com` → `a.b.c.d`

### Desired Behavior
Users can specify multiple prefixes via a new variable `route53_hostname_prefixes` (default: `["ip"]`).

**Example**: If user passes `["ip", "api"]`, the Lambda will create two DNS records:
- `ip-a-b-c-d.example.com` → `a.b.c.d`
- `api-a-b-c-d.example.com` → `a.b.c.d`

When the instance is terminated, **both records should be deleted**.

### Use Cases
1. **Multi-purpose servers**: Create both `web-x-x-x-x` and `api-x-x-x-x` for the same instance
2. **Service discovery**: Multiple service names for the same backend
3. **Migration scenarios**: Old and new naming conventions during transition
4. **Testing**: Create `prod-x-x-x-x` and `staging-x-x-x-x` variations

## Implementation Steps

### 1. Define Input Variable ✅ COMPLETE
**File**: `variables.tf`

**Add new variable** (after `route53_hostname`):

```hcl
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
      can(regex("^[a-z0-9-]+$", prefix))
    ])
    error_message = "Each prefix must contain only lowercase letters, numbers, and hyphens."
  }
}
```

**Rationale**:
- Default `["ip"]` maintains backward compatibility
- Validation ensures at least one prefix exists
- Validation enforces DNS-safe characters
- Only applies when using auto-generated names (`_PrivateDnsName_` or `_PublicDnsName_`)

### 2. Pass Variable to Lambda ✅ COMPLETE
**File**: `lambda.tf`

**Modify**: Update the `lambda_environment_variables` local (around line ~50)

**Current**:
```hcl
locals {
  lambda_environment_variables = {
    ROUTE53_ZONE_ID         = var.route53_zone_id
    ROUTE53_HOSTNAME        = var.route53_hostname
    ROUTE53_PUBLIC_IP       = var.route53_public_ip ? "true" : "false"
    ROUTE53_TTL             = var.route53_ttl
    # ... other vars ...
  }
}
```

**Updated**:
```hcl
locals {
  lambda_environment_variables = {
    ROUTE53_ZONE_ID              = var.route53_zone_id
    ROUTE53_HOSTNAME             = var.route53_hostname
    ROUTE53_HOSTNAME_PREFIXES    = jsonencode(var.route53_hostname_prefixes)
    ROUTE53_PUBLIC_IP            = var.route53_public_ip ? "true" : "false"
    ROUTE53_TTL                  = var.route53_ttl
    # ... other vars ...
  }
}
```

**Rationale**:
- Use `jsonencode()` to pass list as JSON string
- Lambda will parse this back to a Python list
- Environment variables only support strings

### 3. Write Integration Test (TDD Approach) ✅ COMPLETE
**File**: `tests/test_module.py`

**Add new test function**:

```python
@pytest.mark.parametrize(
    "aws_provider_version", ["~> 5.31", "~> 6.0"], ids=["aws-5", "aws-6"]
)
def test_multiple_dns_prefixes(
    service_network,
    aws_provider_version,
    keep_after,
    test_role_arn,
    aws_region,
    subzone,
):
    """
    Test that multiple DNS records with different prefixes are created
    for the same instance IP, and all are deleted on termination.

    This test verifies:
    1. Multiple DNS records are created with different prefixes (ip, api)
    2. All records point to the same IP address
    3. All records are deleted when instance is terminated
    """
    subnet_public_ids = service_network["subnet_public_ids"]["value"]
    internet_gateway_id = service_network["internet_gateway_id"]["value"]

    terraform_module_dir = osp.join(TERRAFORM_ROOT_DIR, "update-dns")

    # Clean up Terraform cache files
    try:
        shutil.rmtree(osp.join(terraform_module_dir, ".terraform"))
    except FileNotFoundError:
        pass

    try:
        os.remove(osp.join(terraform_module_dir, ".terraform.lock.hcl"))
    except FileNotFoundError:
        pass

    # Update terraform.tf with the specified AWS provider version
    with open(osp.join(terraform_module_dir, "terraform.tf"), "w") as tf_fp:
        tf_fp.write(
            dedent(
                f"""
                terraform {{
                  required_providers {{
                    aws = {{
                      source  = "hashicorp/aws"
                      version = "{aws_provider_version}"
                    }}
                  }}
                }}
                """
            )
        )

    # Use _PublicDnsName_ to test public IP scenarios with multiple prefixes
    route53_hostname = "_PublicDnsName_"
    route53_hostname_prefixes = ["ip", "api"]
    asg_size = 1

    with open(osp.join(terraform_module_dir, "terraform.tfvars"), "w") as fp:
        fp.write(
            dedent(
                f"""
                    region = "{aws_region}"
                    route53_zone_id = "{subzone["subzone_id"]["value"]}"

                    subnet_ids = {json.dumps(subnet_public_ids)}
                    internet_gateway_id = "{internet_gateway_id}"
                    route53_hostname = "{route53_hostname}"
                    route53_hostname_prefixes = {json.dumps(route53_hostname_prefixes)}
                    route53_public_ip = true
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

    with terraform_apply(
        terraform_module_dir,
        destroy_after=not keep_after,
        json_output=True,
    ) as tf_output:
        LOG.info("%s", json.dumps(tf_output, indent=4))
        asg = ASG(
            tf_output["asg_name"]["value"], region=aws_region, role_arn=test_role_arn
        )
        zone = Zone(zone_id=tf_output["zone_id"]["value"], role_arn=test_role_arn)

        # Step 1: Wait for instance to have public IP
        LOG.info("Waiting for instance to have public IP...")
        with timeout(seconds=300):
            while True:
                asg.refresh()
                if len(asg.instances) == 0:
                    LOG.info("No instances yet, waiting...")
                    sleep(10)
                    continue

                instance = asg.instances[0]
                if instance.public_ip is None:
                    LOG.info(f"Instance {instance.instance_id} doesn't have public IP yet, waiting...")
                    sleep(10)
                    continue

                LOG.info(f"Instance {instance.instance_id} has public IP: {instance.public_ip}")
                break

        # Step 2: Verify BOTH DNS records were created
        instance = asg.instances[0]
        public_ip = instance.public_ip

        # Expected hostnames with different prefixes
        expected_hostnames = [
            f"ip-{public_ip.replace('.', '-')}",
            f"api-{public_ip.replace('.', '-')}"
        ]

        LOG.info(f"Verifying multiple DNS records for IP {public_ip}")
        for hostname in expected_hostnames:
            LOG.info(f"Checking DNS record: {hostname} -> {public_ip}")
            with timeout(seconds=120):
                while True:
                    dns_ips = zone.search_hostname(hostname)
                    if dns_ips == [public_ip]:
                        LOG.info(f"✓ DNS record verified: {hostname} -> {public_ip}")
                        break
                    LOG.info(f"Waiting for DNS record {hostname}... Current: {dns_ips}")
                    sleep(5)

        # Step 3: Terminate the instance (triggers Lambda deletion)
        LOG.info(f"Manually terminating instance {instance.instance_id}...")
        instance.terminate()

        # Step 4: Wait for instance to be terminated
        LOG.info("Waiting for instance termination...")
        with timeout(seconds=300):
            while True:
                asg.refresh()
                current_instances = [i for i in asg.instances if i.instance_id == instance.instance_id]
                if not current_instances:
                    LOG.info(f"Instance {instance.instance_id} terminated")
                    break
                state = current_instances[0].state
                LOG.info(f"Instance state: {state}")
                sleep(10)

        # Step 5: Verify ALL DNS records were deleted
        LOG.info("Verifying all DNS records were deleted...")
        for hostname in expected_hostnames:
            LOG.info(f"Checking deletion of: {hostname}")
            with timeout(seconds=120):
                while True:
                    dns_ips = zone.search_hostname(hostname)
                    if len(dns_ips) == 0:
                        LOG.info(f"✓ DNS record {hostname} successfully deleted")
                        break
                    LOG.info(f"DNS record {hostname} still exists: {dns_ips}, waiting...")
                    sleep(5)

        LOG.info("✓ All DNS records with multiple prefixes successfully created and deleted")
```

**Test Coverage**:
1. Creates ASG with Lambda using `route53_hostname_prefixes = ["ip", "api"]`
2. Waits for instance to launch and get public IP
3. Verifies TWO DNS records are created: `ip-a-b-c-d` and `api-a-b-c-d`
4. Both records point to the same IP address
5. Manually terminates the instance
6. Verifies BOTH records are deleted
7. No mocking - uses real AWS infrastructure

### 4. Run Test - Verify Failure (TDD) ✅ COMPLETE
**Command**:
```bash
pytest tests/test_module.py::test_multiple_dns_prefixes -v -k "aws-6"
```

**Expected Result**: Test should FAIL because the feature is not yet implemented

**Likely Failure Points**:
1. Lambda doesn't recognize `ROUTE53_HOSTNAME_PREFIXES` environment variable
2. Only one DNS record created instead of two
3. Lambda crashes due to missing implementation

**Success Criteria for This Step**: Test fails with clear error indicating feature is missing

### 5. Implement Lambda Feature ✅ COMPLETE

#### 5.1 Update Lambda to Parse Prefixes List
**File**: `update_dns/main.py`

**Modify**: Update environment variable parsing (around line ~15-30)

**Add**:
```python
import json
import os

# ... existing imports ...

# Parse the hostname prefixes from environment variable
ROUTE53_HOSTNAME_PREFIXES = json.loads(
    os.environ.get("ROUTE53_HOSTNAME_PREFIXES", '["ip"]')
)
```

**Rationale**:
- Parse JSON string back to Python list
- Default to `["ip"]` for backward compatibility
- Use `json.loads()` to handle list parsing

#### 5.2 Update `get_hostname()` Function
**File**: `update_dns/main.py`

**Current Function** (around line ~45-60):
```python
def get_hostname(instance_id, public: bool = True):
    """
    Get hostname based on ROUTE53_HOSTNAME setting.

    Special values:
    - _PrivateDnsName_: Returns ip-10-1-1-1 format based on private IP
    - _PublicDnsName_: Returns ip-80-90-1-1 format based on public IP
    - Any other string: Returns that string as-is
    """
    if ROUTE53_HOSTNAME == "_PrivateDnsName_":
        ip = get_instance_ip(instance_id, public=False)
        return f"ip-{ip.replace('.', '-')}"
    elif ROUTE53_HOSTNAME == "_PublicDnsName_":
        ip = get_instance_ip(instance_id, public=True)
        return f"ip-{ip.replace('.', '-')}"
    else:
        return ROUTE53_HOSTNAME
```

**Updated Function** (returns list of hostnames):
```python
def get_hostnames(instance_id, public: bool = True):
    """
    Get list of hostnames based on ROUTE53_HOSTNAME setting.

    Special values:
    - _PrivateDnsName_: Returns list like ["ip-10-1-1-1", "api-10-1-1-1"] based on prefixes
    - _PublicDnsName_: Returns list like ["ip-80-90-1-1", "api-80-90-1-1"] based on prefixes
    - Any other string: Returns single-item list with that string

    The number of hostnames depends on ROUTE53_HOSTNAME_PREFIXES.
    """
    if ROUTE53_HOSTNAME == "_PrivateDnsName_":
        ip = get_instance_ip(instance_id, public=False)
        ip_formatted = ip.replace('.', '-')
        return [f"{prefix}-{ip_formatted}" for prefix in ROUTE53_HOSTNAME_PREFIXES]
    elif ROUTE53_HOSTNAME == "_PublicDnsName_":
        ip = get_instance_ip(instance_id, public=True)
        ip_formatted = ip.replace('.', '-')
        return [f"{prefix}-{ip_formatted}" for prefix in ROUTE53_HOSTNAME_PREFIXES]
    else:
        # Custom hostname - ignore prefixes, return single hostname
        return [ROUTE53_HOSTNAME]
```

**Rationale**:
- Renamed to `get_hostnames()` (plural) to reflect multiple return values
- Returns a list instead of a single string
- For auto-generated names, creates one hostname per prefix
- For custom names, ignores prefixes and returns single-item list
- Maintains backward compatibility when prefixes = ["ip"]

#### 5.3 Update `add_record()` Function
**File**: `update_dns/main.py`

**Current Function** (around line ~70-90):
```python
def add_record(zone_id, instance_id, hostname, public: bool = True, ttl: int = 300):
    """Add DNS A record for the instance"""
    zone = Zone(zone_id=zone_id)
    instance = EC2Instance(instance_id=instance_id)
    instance_ip = get_instance_ip(instance_id, public=public)

    logger.info(
        "Adding instance %s: zone_id = %r, hostname = %r, public = %s, ttl = %s.",
        instance_id,
        zone_id,
        hostname,
        public,
        ttl,
    )
    logger.info("instance_ip = %r", instance_ip)

    zone.add_record(hostname, instance_ip, ttl=ttl)

    # Store IP in instance tags for deletion fallback
    instance.create_tags(
        {("PublicIpAddress" if public else "PrivateIpAddress"): instance_ip}
    )
```

**Updated Function** (handles multiple hostnames):
```python
def add_records(zone_id, instance_id, hostnames, public: bool = True, ttl: int = 300):
    """Add DNS A records for the instance (supports multiple hostnames)"""
    zone = Zone(zone_id=zone_id)
    instance = EC2Instance(instance_id=instance_id)
    instance_ip = get_instance_ip(instance_id, public=public)

    logger.info(
        "Adding instance %s: zone_id = %r, hostnames = %r, public = %s, ttl = %s.",
        instance_id,
        zone_id,
        hostnames,
        public,
        ttl,
    )
    logger.info("instance_ip = %r", instance_ip)

    # Create multiple DNS records for the same IP
    for hostname in hostnames:
        logger.info(f"Creating DNS record: {hostname} -> {instance_ip}")
        zone.add_record(hostname, instance_ip, ttl=ttl)

    # Store IP and hostnames in instance tags for deletion fallback
    instance.create_tags({
        ("PublicIpAddress" if public else "PrivateIpAddress"): instance_ip,
        "DnsHostnames": json.dumps(hostnames)  # Store list of hostnames
    })

    logger.info(f"Successfully created {len(hostnames)} DNS record(s)")
```

**Key Changes**:
- Renamed to `add_records()` (plural)
- Takes `hostnames` list instead of single `hostname`
- Loops through hostnames to create multiple records
- Stores hostnames list in instance tags for deletion
- Logs each record creation

#### 5.4 Update `delete_record()` Function
**File**: `update_dns/main.py`

**Current Function** (around line ~95-115):
```python
def delete_record(zone_id, instance_id, hostname, public: bool = True):
    """Delete DNS A record for the instance"""
    zone = Zone(zone_id=zone_id)
    instance_ip = get_instance_ip(instance_id, public=public)

    logger.info(
        "Deleting record for instance %s: zone_id = %r, hostname = %r, public = %s.",
        instance_id,
        zone_id,
        hostname,
        public,
    )
    logger.info("instance_ip = %r", instance_ip)

    zone.delete_record(hostname, instance_ip)
```

**Updated Function** (handles multiple hostnames):
```python
def delete_records(zone_id, instance_id, hostnames, public: bool = True):
    """Delete DNS A records for the instance (supports multiple hostnames)"""
    zone = Zone(zone_id=zone_id)
    instance_ip = get_instance_ip(instance_id, public=public)

    logger.info(
        "Deleting records for instance %s: zone_id = %r, hostnames = %r, public = %s.",
        instance_id,
        zone_id,
        hostnames,
        public,
    )
    logger.info("instance_ip = %r", instance_ip)

    # Delete multiple DNS records
    deleted_count = 0
    failed_count = 0

    for hostname in hostnames:
        try:
            logger.info(f"Deleting DNS record: {hostname} -> {instance_ip}")
            zone.delete_record(hostname, instance_ip)
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete DNS record {hostname}: {e}")
            failed_count += 1

    logger.info(f"Deleted {deleted_count}/{len(hostnames)} DNS record(s), {failed_count} failed")

    if deleted_count == 0:
        raise Exception(f"Failed to delete all {len(hostnames)} DNS records")
```

**Key Changes**:
- Renamed to `delete_records()` (plural)
- Takes `hostnames` list instead of single `hostname`
- Loops through hostnames to delete multiple records
- Error handling per record (continues if one fails)
- Logs success/failure counts

#### 5.5 Update Lambda Handler
**File**: `update_dns/main.py`

**Modify**: Update the `lambda_handler()` function (around line ~120-180)

**Current Calls**:
```python
# In lambda_handler()
hostname = get_hostname(instance_id, public=ROUTE53_PUBLIC_IP)

if lifecycle_transition == "autoscaling:EC2_INSTANCE_LAUNCHING":
    add_record(ROUTE53_ZONE_ID, instance_id, hostname, public=ROUTE53_PUBLIC_IP, ttl=ROUTE53_TTL)
elif lifecycle_transition == "autoscaling:EC2_INSTANCE_TERMINATING":
    delete_record(ROUTE53_ZONE_ID, instance_id, hostname, public=ROUTE53_PUBLIC_IP)
```

**Updated Calls**:
```python
# In lambda_handler()
hostnames = get_hostnames(instance_id, public=ROUTE53_PUBLIC_IP)

if lifecycle_transition == "autoscaling:EC2_INSTANCE_LAUNCHING":
    add_records(ROUTE53_ZONE_ID, instance_id, hostnames, public=ROUTE53_PUBLIC_IP, ttl=ROUTE53_TTL)
elif lifecycle_transition == "autoscaling:EC2_INSTANCE_TERMINATING":
    delete_records(ROUTE53_ZONE_ID, instance_id, hostnames, public=ROUTE53_PUBLIC_IP)
```

**Key Changes**:
- Call `get_hostnames()` instead of `get_hostname()`
- Call `add_records()` instead of `add_record()`
- Call `delete_records()` instead of `delete_record()`
- All existing logic remains the same

### 6. Run Test - Verify Success ✅ COMPLETE
**Command**:
```bash
pytest tests/test_module.py::test_multiple_dns_prefixes -v -k "aws-6"
```

**Expected Result**: Test should PASS, verifying:
1. Multiple DNS records created with different prefixes
2. All records point to the same IP
3. All records deleted on instance termination

**Success Criteria**:
- ✓ Test passes
- ✓ CloudWatch logs show multiple record creations
- ✓ Both records visible in Route53 during test
- ✓ Both records deleted after termination

### 7. Run All Existing Tests - Verify No Regressions
**Command**:
```bash
pytest tests/test_module.py -v
```

**Expected Result**: All existing tests should PASS

**Why This Should Work**:
- Default value `["ip"]` maintains backward compatibility
- When only one prefix, behavior is identical to previous version
- Function signatures changed but logic is backward compatible

**If Any Test Fails**:
1. Check if test assumes single hostname instead of list
2. Verify default value `["ip"]` is correctly applied
3. Check CloudWatch logs for Lambda errors

### 8. Update Terraform Outputs (Optional) ✅ COMPLETE
**File**: `outputs.tf`

**Consider adding** (optional enhancement):
```hcl
output "route53_hostname_prefixes" {
  description = "List of DNS hostname prefixes configured for the module"
  value       = var.route53_hostname_prefixes
}
```

**Rationale**:
- Helps users verify their configuration
- Useful for debugging
- Optional - can be added in a follow-up

### 9. Update Documentation ✅ COMPLETE

#### 9.1 Update README.md - Variables Table
**File**: `README.md`

**Find the variables table** and add new row:

```markdown
| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| ... existing variables ... |
| route53_hostname_prefixes | List of prefixes to use when creating DNS records. Each prefix creates a separate A record pointing to the same IP. Only used with _PrivateDnsName_ or _PublicDnsName_. Examples: ["ip"], ["ip", "api"], ["web", "app"] | list(string) | ["ip"] | no |
```

#### 9.2 Update README.md - Usage Examples
**File**: `README.md`

**Add new usage example section**:

```markdown
### Multiple DNS Records Per Instance

You can create multiple DNS records with different prefixes for the same instance:

```hcl
module "update-dns" {
  source  = "infrahouse/update-dns/aws"
  version = "~> 1.2"

  asg_name                   = aws_autoscaling_group.my_asg.name
  route53_zone_id            = aws_route53_zone.my_zone.zone_id
  route53_hostname           = "_PublicDnsName_"
  route53_hostname_prefixes  = ["ip", "api", "web"]
  route53_public_ip          = true
  alarm_emails               = ["ops@example.com"]
}
```

This will create three DNS records for an instance with IP `54.183.154.109`:
- `ip-54-183-154-109.example.com` → `54.183.154.109`
- `api-54-183-154-109.example.com` → `54.183.154.109`
- `web-54-183-154-109.example.com` → `54.183.154.109`

When the instance terminates, all three records are automatically deleted.

**Note**: The `route53_hostname_prefixes` variable only applies when using `_PrivateDnsName_` or `_PublicDnsName_`. When using a custom hostname string, prefixes are ignored.
```

#### 9.3 Update CHANGELOG.md
**File**: `CHANGELOG.md`

**Add entry**:

```markdown
## [1.2.0] - 2025-11-25

### Added
- New variable `route53_hostname_prefixes` to create multiple DNS records with different prefixes for the same instance IP. Useful for creating multiple service names (e.g., "ip", "api", "web") pointing to the same instance. Default: `["ip"]` maintains backward compatibility.

### Changed
- Lambda function now supports creating and deleting multiple DNS records per instance
- Internal functions renamed from singular to plural (`add_record` → `add_records`, etc.) to reflect multi-record support
```

#### 9.4 Update terraform-docs
**Run command to regenerate docs**:
```bash
make docs
```

This will update the automatically generated documentation with the new variable.

### 10. Code Review Checklist
Before submitting PR, verify:
- [ ] New variable `route53_hostname_prefixes` added to `variables.tf` with validation
- [ ] Variable passed to Lambda as environment variable (JSON encoded)
- [ ] Integration test covers multiple prefixes creation and deletion
- [ ] Test uses real infrastructure (no mocking)
- [ ] Lambda parses prefixes list from environment variable
- [ ] Lambda creates multiple DNS records (one per prefix)
- [ ] Lambda deletes all DNS records on termination
- [ ] All existing integration tests pass (no regressions)
- [ ] Default value `["ip"]` maintains backward compatibility
- [ ] README.md updated with new variable and examples
- [ ] CHANGELOG.md updated with feature description
- [ ] Code comments explain multi-record logic
- [ ] Error handling logs success/failure per record
- [ ] CloudWatch logs are clear and informative

## Testing Strategy

### Integration Tests (End-to-End, Real Infrastructure)
1. **New test**: `test_multiple_dns_prefixes`
   - Creates ASG with Lambda using `route53_hostname_prefixes = ["ip", "api"]`
   - Waits for instance to launch and get public IP
   - Verifies TWO DNS records created with different prefixes
   - Both records point to same IP address
   - Manually terminates instance
   - Verifies BOTH records are deleted
   - No mocking - uses real AWS infrastructure

2. **Existing tests**: All tests in `test_module.py`
   - Should continue passing with default `["ip"]`
   - Verifies backward compatibility
   - Covers single-prefix scenarios

### Test Data Updates
**File**: `test_data/update-dns/variables.tf`

Consider adding test variable:
```hcl
variable "route53_hostname_prefixes" {
  description = "List of DNS hostname prefixes for testing"
  type        = list(string)
  default     = ["ip"]
}
```

**File**: `test_data/update-dns/main.tf`

Update module call to include:
```hcl
module "update-dns" {
  source = "../.."

  # ... existing vars ...
  route53_hostname_prefixes = var.route53_hostname_prefixes
}
```

## Risk Analysis

### Low-Medium Risk Change
**Scope**:
- New input variable (opt-in feature)
- Lambda function modifications (multi-record support)
- Backward compatible with default value

**Behavior**:
- Default `["ip"]` maintains 100% backward compatibility
- Only users who opt-in will see new behavior
- No changes to existing single-record logic

**Test Coverage**:
- Integration test with real infrastructure
- Covers creation, lookup, and deletion
- Existing tests verify no regressions

### Potential Edge Cases

1. **Empty prefix list**
   - **Risk**: User passes `[]`
   - **Mitigation**: Validation rule prevents empty lists
   - **Error**: Terraform validation fails at plan time

2. **Invalid prefix characters**
   - **Risk**: User passes prefix with invalid DNS characters
   - **Mitigation**: Validation rule enforces `^[a-z0-9-]+$`
   - **Error**: Terraform validation fails at plan time

3. **Too many prefixes**
   - **Risk**: User passes 100+ prefixes, causing Lambda timeout
   - **Mitigation**: Could add validation for max length (e.g., 10)
   - **Future enhancement**: Add `max_length` validation

4. **Duplicate prefixes**
   - **Risk**: User passes `["ip", "ip"]`
   - **Behavior**: Two identical records created (harmless but wasteful)
   - **Future enhancement**: Add validation for uniqueness

5. **Custom hostname with prefixes**
   - **Risk**: User sets both custom `route53_hostname` and `route53_hostname_prefixes`
   - **Behavior**: Prefixes are ignored (documented)
   - **Consideration**: Could log warning in Lambda

6. **Partial deletion failure**
   - **Risk**: One record deletes but another fails
   - **Mitigation**: Error handling continues through all deletions
   - **Logging**: Logs success/failure count

### Backward Compatibility
**100% Backward Compatible**:
- Default value `["ip"]` maintains existing behavior
- Existing modules without the variable will continue working
- No breaking changes to module interface

## Dependencies

### Required
- `infrahouse_core.aws.route53.zone.Zone` - Supports multiple `add_record()` calls
- Instance tags support storing JSON list

### Assumptions
- Route53 Zone can handle multiple A records with different names
- Lambda execution time sufficient for multiple record operations
- No Route53 rate limiting issues with multiple record creations

## Performance Considerations

### Lambda Execution Time
- **Current**: ~1-3 seconds per instance lifecycle event
- **With 2 prefixes**: ~2-4 seconds (adds ~1 record operation)
- **With 5 prefixes**: ~3-6 seconds (adds ~4 record operations)
- **Timeout**: 300 seconds (plenty of headroom)

### Route53 Rate Limits
- **Route53 API**: 5 requests/second per account
- **Typical ASG scaling**: 1-10 instances at a time
- **Risk**: Low - unlikely to hit rate limits
- **Future enhancement**: Batch record operations if needed

## Summary

This feature enables creating multiple DNS records with different prefixes for the same EC2 instance IP. It's fully backward compatible (default `["ip"]`), follows TDD methodology, and is well-tested with integration tests on real infrastructure.

**Key Benefits**:
1. Multi-purpose servers (web, api, admin on same instance)
2. Service discovery (multiple names for same backend)
3. Migration scenarios (old + new naming)
4. Zero impact on existing users (opt-in feature)

**Implementation Approach**:
1. Add variable with validation
2. Write failing integration test (TDD)
3. Implement Lambda changes (parse, create, delete multiple)
4. Verify test passes
5. Ensure no regressions
6. Update documentation

## Follow-up Considerations

1. **Add validation for max prefixes** (e.g., limit to 10)
2. **Add validation for unique prefixes** (prevent duplicates)
3. **Add CloudWatch metric** for number of records per instance
4. **Consider batch operations** if Route53 rate limits become an issue
5. **Add warning log** when prefixes used with custom hostname
6. **Performance testing** with large prefix lists (20+)
