import json
import logging
import os
from os import environ

from infrahouse_core.aws.route53.zone import Zone

from infrahouse_core.aws.asg import ASG


from infrahouse_core.aws.dynamodb import DynamoDBTable
from infrahouse_core.aws.ec2_instance import EC2Instance

LOG = logging.getLogger()
LOG.setLevel(level=logging.INFO)

# Parse the hostname prefixes from environment variable
ROUTE53_HOSTNAME_PREFIXES = json.loads(
    os.environ.get("ROUTE53_HOSTNAME_PREFIXES", '["ip"]')
)


def add_record(
    zone_id,
    hostname,
    instance_id,
    ttl: int = 300,
    public: bool = True,
):
    """Add the instance to DNS (backward compatibility - single hostname)."""
    add_records(zone_id, [hostname], instance_id, ttl, public)


def add_records(
    zone_id,
    hostnames,
    instance_id,
    ttl: int = 300,
    public: bool = True,
):
    """Add DNS A records for the instance (supports multiple hostnames)."""
    LOG.info(
        f"Adding instance {instance_id}: {zone_id = }, {hostnames = }, {public = }, {ttl = }."
    )
    assert instance_id
    assert zone_id
    assert hostnames
    assert len(hostnames) > 0

    zone = Zone(zone_id=zone_id)
    LOG.info(f"{zone.zone_name = }")
    instance_ip = get_instance_ip(instance_id, public=public)
    LOG.info(f"{instance_ip = }")

    # Create multiple DNS records for the same IP
    for hostname in hostnames:
        LOG.info(f"Creating DNS record: {hostname} -> {instance_ip}")
        zone.add_record(hostname, instance_ip, ttl=ttl)

    instance = EC2Instance(instance_id=instance_id)
    instance.add_tag("PublicIpAddress" if public else "PrivateIpAddress", instance_ip)
    instance.add_tag(
        "Name",
        resolve_hostname(instance_id),
    )
    # Store first hostname for backward compatibility, but also store all hostnames
    instance.add_tag("update-dns:hostname", hostnames[0])
    instance.add_tag("update-dns:hostnames", json.dumps(hostnames))

    LOG.info(f"Successfully created {len(hostnames)} DNS record(s)")


def remove_record(zone_id, instance_id, public: bool = True):
    """Remove the instance from DNS (backward compatibility - single hostname)."""
    remove_records(zone_id, instance_id, public)


def remove_records(zone_id, instance_id, public: bool = True):
    """Delete DNS A records for the instance (supports multiple hostnames)."""
    LOG.info(f"Removing instance {instance_id}: {zone_id = }, {public = }.")
    assert instance_id
    assert zone_id

    instance = EC2Instance(instance_id=instance_id)
    instance_ip = get_instance_ip(instance_id, public=public)
    LOG.info(f"{instance_ip = }")

    # Try to get hostnames from the new tag first, fall back to old tag
    try:
        hostnames_json = instance.tags.get("update-dns:hostnames")
        if hostnames_json:
            hostnames = json.loads(hostnames_json)
        else:
            # Fallback to single hostname tag for backward compatibility
            hostnames = [instance.tags["update-dns:hostname"]]
    except (KeyError, json.JSONDecodeError):
        # If all else fails, try to resolve hostnames from current config
        hostnames = resolve_hostnames(instance_id)

    LOG.info(f"{hostnames = }")

    zone = Zone(zone_id=zone_id)

    # Delete multiple DNS records
    deleted_count = 0
    failed_count = 0

    for hostname in hostnames:
        try:
            LOG.info(f"Deleting DNS record: {hostname} -> {instance_ip}")
            zone.delete_record(hostname, instance_ip)
            deleted_count += 1
        except Exception as e:
            LOG.warning(f"Failed to delete DNS record {hostname}: {e}")
            failed_count += 1

    LOG.info(
        f"Deleted {deleted_count}/{len(hostnames)} DNS record(s), {failed_count} failed"
    )

    if deleted_count == 0:
        raise Exception(f"Failed to delete all {len(hostnames)} DNS records")


def get_instance_ip(instance_id, public: bool = True):
    """Get the instance's public or private IP address by its instance_id.

    During instance termination, the IP address may be None (released).
    In that case, fall back to the IP stored in instance tags.
    """
    instance = EC2Instance(instance_id=instance_id)
    try:
        ip = instance.public_ip if public else instance.private_ip
        # If IP is None (e.g., during termination), fall back to tags
        if ip is not None:
            return ip
    except KeyError:
        pass  # Fall through to tag lookup

    # Fallback: retrieve IP from instance tags
    return instance.tags["PublicIpAddress" if public else "PrivateIpAddress"]


def resolve_hostname(instance_id):
    """
    Resolve hostname for backward compatibility with single prefix.
    Returns the first hostname from resolve_hostnames().
    """
    return resolve_hostnames(instance_id)[0]


def resolve_hostnames(instance_id):
    """
    Get list of hostnames based on ROUTE53_HOSTNAME setting.

    Special values:
    - _PrivateDnsName_: Returns list like ["ip-10-1-1-1", "api-10-1-1-1"] based on prefixes
    - _PublicDnsName_: Returns list like ["ip-80-90-1-1", "api-80-90-1-1"] based on prefixes
    - Any other string: Returns single-item list with that string

    The number of hostnames depends on ROUTE53_HOSTNAME_PREFIXES.
    """
    route53_hostname = environ["ROUTE53_HOSTNAME"]

    if route53_hostname == "_PrivateDnsName_":
        instance = EC2Instance(instance_id)
        base_hostname = (
            instance.tags["Name"] if instance.hostname is None else instance.hostname
        )
        # For PrivateDnsName, AWS already provides the full hostname, just return it
        # wrapped in a list (prefixes don't apply to AWS-provided hostnames)
        return [base_hostname]

    elif route53_hostname == "_PublicDnsName_":
        instance = EC2Instance(instance_id)
        public_ip = instance.public_ip
        # Convert IP like 80.90.1.1 to hostname like ip-80-90-1-1
        ip_formatted = public_ip.replace(".", "-")
        # Create one hostname per prefix
        return [f"{prefix}-{ip_formatted}" for prefix in ROUTE53_HOSTNAME_PREFIXES]

    # Custom hostname - ignore prefixes, return single hostname
    return [route53_hostname]


def lambda_handler(event, context):
    LOG.info(f"{event = }")
    # Credit: https://stackoverflow.com/questions/715417/converting-from-a-string-to-boolean-in-python
    public = environ.get("ROUTE53_PUBLIC_IP", "True").lower() in [
        "true",
        "1",
        "t",
        "y",
        "yes",
        "yeah",
        "yup",
        "certainly",
        "uh-huh",
    ]
    instance_id = event["detail"]["EC2InstanceId"]
    lc_hook_name = event["detail"]["LifecycleHookName"]
    lc_transition = event["detail"]["LifecycleTransition"]

    if "LifecycleTransition" in event["detail"]:
        try:
            if (
                lc_hook_name == environ["LIFECYCLE_HOOK_TERMINATING"]
                and lc_transition == "autoscaling:EC2_INSTANCE_TERMINATING"
            ):
                with DynamoDBTable(os.getenv("LOCK_TABLE_NAME")).lock("update-dns"):
                    remove_record(
                        environ["ROUTE53_ZONE_ID"],
                        instance_id,
                        public=public,
                    )
                LOG.info(
                    f"Completing lifecycle hook {lc_hook_name} on instance {instance_id}"
                )
                ASG(event["detail"]["AutoScalingGroupName"]).complete_lifecycle_action(
                    hook_name=lc_hook_name,
                    result="CONTINUE",
                    instance_id=instance_id,
                )
            elif (
                lc_hook_name == environ["LIFECYCLE_HOOK_LAUNCHING"]
                and lc_transition == "autoscaling:EC2_INSTANCE_LAUNCHING"
            ):
                with DynamoDBTable(os.getenv("LOCK_TABLE_NAME")).lock("update-dns"):
                    add_records(
                        environ["ROUTE53_ZONE_ID"],
                        resolve_hostnames(instance_id),
                        instance_id,
                        int(environ["ROUTE53_TTL"]),
                        public=public,
                    )
                LOG.info(
                    f"Completing lifecycle hook {lc_hook_name} on instance {instance_id}"
                )
                ASG(event["detail"]["AutoScalingGroupName"]).complete_lifecycle_action(
                    hook_name=lc_hook_name,
                    result="CONTINUE",
                    instance_id=instance_id,
                )
            else:
                LOG.warning("No action for this event.")

        except Exception as err:
            LOG.exception(err)

    else:
        LOG.warning("Event is not LifecycleTransition. Skip action.")
