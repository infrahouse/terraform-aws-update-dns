import logging
import os
from os import environ

from infrahouse_core.aws.route53.zone import Zone

from infrahouse_core.aws.asg import ASG


from infrahouse_core.aws.dynamodb import DynamoDBTable
from infrahouse_core.aws.ec2_instance import EC2Instance

LOG = logging.getLogger()
LOG.setLevel(level=logging.INFO)


def add_record(
    zone_id,
    hostname,
    instance_id,
    ttl: int = 300,
    public: bool = True,
):
    """Add the instance to DNS."""
    LOG.info(
        f"Adding instance {instance_id}: {zone_id = }, {hostname = }, {public = }, {ttl = }."
    )
    assert instance_id
    assert zone_id
    assert hostname

    zone = Zone(zone_id=zone_id)
    LOG.info(f"{zone.zone_name = }")
    instance_ip = get_instance_ip(instance_id, public=public)
    LOG.info(f"{instance_ip = }")
    zone.add_record(hostname, instance_ip, ttl=ttl)
    instance = EC2Instance(instance_id=instance_id)
    instance.add_tag("PublicIpAddress" if public else "PrivateIpAddress", instance_ip)
    instance.add_tag(
        "Name",
        resolve_hostname(instance_id),
    )
    instance.add_tag("update-dns:hostname", resolve_hostname(instance_id))


def remove_record(zone_id, instance_id, public: bool = True):
    """Remove the instance from DNS."""
    LOG.info(f"Removing instance {instance_id}: {zone_id = }, {public = }.")
    assert instance_id
    assert zone_id

    instance_ip = get_instance_ip(instance_id, public=public)
    LOG.info(f"{instance_ip = }")
    hostname = EC2Instance(instance_id=instance_id).tags["update-dns:hostname"]
    LOG.info(f"{hostname = }")
    zone = Zone(zone_id=zone_id)
    zone.delete_record(hostname, instance_ip)


def get_instance_ip(instance_id, public: bool = True):
    """Get the instance's public or private IP address by its instance_id"""
    instance = EC2Instance(instance_id=instance_id)
    try:
        return instance.public_ip if public else instance.private_ip
    except KeyError:
        return instance.tags["PublicIpAddress" if public else "PrivateIpAddress"]


def resolve_hostname(instance_id):
    if environ["ROUTE53_HOSTNAME"] == "_PrivateDnsName_":
        instance = EC2Instance(instance_id)
        return instance.tags["Name"] if instance.hostname is None else instance.hostname

    return environ["ROUTE53_HOSTNAME"]


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
            elif (
                lc_hook_name == environ["LIFECYCLE_HOOK_LAUNCHING"]
                and lc_transition == "autoscaling:EC2_INSTANCE_LAUNCHING"
            ):
                with DynamoDBTable(os.getenv("LOCK_TABLE_NAME")).lock("update-dns"):
                    add_record(
                        environ["ROUTE53_ZONE_ID"],
                        resolve_hostname(instance_id),
                        instance_id,
                        int(environ["ROUTE53_TTL"]),
                        public=public,
                    )
            else:
                LOG.warning("No action for this event.")

        except Exception as err:
            LOG.exception(err)

        finally:
            LOG.info(
                f"Completing lifecycle hook {lc_hook_name} on instance {instance_id}"
            )
            ASG(event["detail"]["AutoScalingGroupName"]).complete_lifecycle_action(
                hook_name=lc_hook_name,
                result="CONTINUE",
                instance_id=instance_id,
            )
    else:
        LOG.warning("Event is not LifecycleTransition. Skip action.")
