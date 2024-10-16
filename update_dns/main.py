import contextlib
import json
import os
import time
from os import environ
from pprint import pprint

import botocore

import boto3
from botocore.exceptions import ClientError


def complete_lifecycle_action(
    lifecyclehookname,
    autoscalinggroupname,
    lifecycleactiontoken,
    instanceid,
    lifecycleactionresult="CONTINUE",
):
    print("Completing lifecycle hook action")
    print(f"{lifecyclehookname=}")
    print(f"{autoscalinggroupname=}")
    print(f"{lifecycleactiontoken=}")
    print(f"{lifecycleactionresult=}")
    print(f"{instanceid=}")
    client = boto3.client("autoscaling")
    client.complete_lifecycle_action(
        LifecycleHookName=lifecyclehookname,
        AutoScalingGroupName=autoscalinggroupname,
        LifecycleActionToken=lifecycleactiontoken,
        LifecycleActionResult=lifecycleactionresult,
        InstanceId=instanceid,
    )


def add_record(
    zone_id,
    zone_name,
    hostname,
    instance_id,
    ttl: int,
    public: bool = True,
    route53_client=None,
    ec2_client=None,
):
    """Add the instance to DNS."""
    print(
        f"Adding instance {instance_id} as a hostname {hostname} to zone {zone_name}."
    )
    if not zone_name.endswith("."):
        zone_name += "."

    print(f"{zone_name = }")

    instance_ip = get_instance_ip(instance_id, public=public)
    print(f"{instance_ip = }")

    route53_client = route53_client or boto3.client("route53")
    start_record_type = None
    start_record_name = None
    start_record_identifier = None
    ip_set = {instance_ip}
    while True:
        kwargs = {
            "HostedZoneId": zone_id,
            "MaxItems": "100",
        }
        if start_record_name:
            kwargs["StartRecordName"] = start_record_name

        if start_record_type:
            kwargs["StartRecordType"] = start_record_type

        if start_record_identifier:
            kwargs["StartRecordIdentifier"] = start_record_identifier

        response = route53_client.list_resource_record_sets(**kwargs)
        print(json.dumps(response, indent=4))
        for rr_set in response["ResourceRecordSets"]:
            print(f"{rr_set = }")
            if (
                rr_set["Name"] == f"{hostname}.{zone_name}"
                and rr_set["Type"] == "A"
                and "ResourceRecords" in rr_set
            ):
                for rr in rr_set["ResourceRecords"]:
                    ip_set.add(rr["Value"])

        r_records = [{"Value": ip} for ip in sorted(list(ip_set))]
        if response["IsTruncated"]:
            start_record_type = response["NextRecordType"]
            start_record_name = response["NextRecordName"]
            start_record_identifier = response["NextRecordIdentifier"]
        else:
            break

    print(f"{ip_set =}")
    route53_client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": f"{hostname}.{zone_name}",
                        "Type": "A",
                        "ResourceRecords": r_records,
                        "TTL": ttl,
                    },
                }
            ]
        },
    )
    ec2_client = ec2_client or boto3.client("ec2")
    ec2_client.create_tags(
        Resources=[
            instance_id,
        ],
        Tags=[
            {
                "Key": "PublicIpAddress" if public else "PrivateIpAddress",
                "Value": instance_ip,
            },
            {
                "Key": "Name",
                "Value": resolve_hostname(instance_id),
            },
        ],
    )


def remove_record(
    zone_id, zone_name, hostname, instance_id, ttl: int, public: bool = True
):
    """Remove the instance from DNS."""
    print(f"Removing instance {instance_id} from zone {zone_id}")
    print(f"{zone_name =}")
    instance_ip = get_instance_ip(instance_id, public=public)
    print(f"{instance_ip = }")

    route53_client = boto3.client("route53")
    response = route53_client.list_resource_record_sets(
        HostedZoneId=zone_id,
        StartRecordType="A",
        StartRecordName=f"{hostname}.{zone_name}",
        MaxItems="1",
    )
    ip_set = set()
    for rr_set in response["ResourceRecordSets"]:
        for rr in rr_set["ResourceRecords"]:
            ip = rr["Value"]
            if ip != instance_ip:
                ip_set.add(rr["Value"])
    r_records = [{"Value": ip} for ip in list(ip_set)]
    if r_records:
        route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": f"{hostname}.{zone_name}",
                            "Type": "A",
                            "ResourceRecords": r_records,
                            "TTL": ttl,
                        },
                    }
                ]
            },
        )
    else:
        route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "DELETE",
                        "ResourceRecordSet": {
                            "Name": f"{hostname}.{zone_name}",
                            "Type": "A",
                            "ResourceRecords": [{"Value": instance_ip}],
                            "TTL": ttl,
                        },
                    }
                ]
            },
        )


def get_instance_ip(instance_id, public: bool = True):
    """Get the instance's public or private IP address by its instance_id"""
    ec2_client = boto3.client("ec2")

    ip_kind = "PublicIpAddress" if public else "PrivateIpAddress"

    response = ec2_client.describe_instances(
        InstanceIds=[
            instance_id,
        ],
    )
    print(f"describe_instances({instance_id}): {response=}")
    if ip_kind in response["Reservations"][0]["Instances"][0]:
        return response["Reservations"][0]["Instances"][0][ip_kind]
    else:
        for tag in response["Reservations"][0]["Instances"][0]["Tags"]:
            if tag["Key"] == ip_kind:
                return tag["Value"]

        raise RuntimeError(f"Could not determine IP of {instance_id}")


def get_instance_asg(instance_id) -> str:
    """Get instance's autoscaling group. If not a member, return None"""
    ec2_client = boto3.client("ec2")
    response = ec2_client.describe_instances(
        InstanceIds=[
            instance_id,
        ],
    )
    print(f"describe_instances({instance_id}): {response=}")
    for tag in response["Reservations"][0]["Instances"][0]["Tags"]:
        if tag["Key"] == "aws:autoscaling:groupName":
            return tag["Value"]


def get_instance_hostname(instance_id) -> str:
    """Get instance's hostname. Usually, something like ip-10-1-0-104."""
    ec2_client = boto3.client("ec2")
    response = ec2_client.describe_instances(
        InstanceIds=[
            instance_id,
        ],
    )
    print(f"describe_instances({instance_id}): {response=}")
    return response["Reservations"][0]["Instances"][0]["PrivateDnsName"].split(".")[0]


def resolve_hostname(instance_id):
    if environ["ROUTE53_HOSTNAME"] == "_PrivateDnsName_":
        return get_instance_hostname(instance_id)

    return environ["ROUTE53_HOSTNAME"]


@contextlib.contextmanager
def lock(my_resource_id):
    timeout = 30
    table_name = os.getenv("LOCK_TABLE_NAME")
    now = time.time()
    dyn_table = boto3.resource("dynamodb").Table(table_name)
    while True:
        if time.time() > now + timeout:
            raise RuntimeError(
                "Failed to lock DNS lock table after %d seconds" % timeout
            )

        try:
            # Put item with conditional expression to acquire the lock

            dyn_table.put_item(
                Item={"ResourceId": my_resource_id},
                ConditionExpression="attribute_not_exists(#r)",
                ExpressionAttributeNames={"#r": "ResourceId"},
            )
            # Lock acquired
            break
        except botocore.exceptions.ClientError as e:
            # Another exception than ConditionalCheckFailedException was caught, raise as-is
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            else:
                # Else, lock cannot be acquired because already locked
                time.sleep(1)
    try:
        yield

    finally:
        dyn_table.delete_item(
            Key={
                "ResourceId": my_resource_id,
            }
        )


def lambda_handler(event, context):
    print(f"{event = }")
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
    if "LifecycleTransition" in event["detail"] and event["detail"][
        "LifecycleHookName"
    ] in ["update-dns-launching", "update-dns-terminating"]:
        try:
            lifecycle_transition = event["detail"]["LifecycleTransition"]
            print(f"{lifecycle_transition = }")

            if lifecycle_transition == "autoscaling:EC2_INSTANCE_TERMINATING":
                with lock("update-dns"):
                    remove_record(
                        environ["ROUTE53_ZONE_ID"],
                        environ["ROUTE53_ZONE_NAME"],
                        resolve_hostname(event["detail"]["EC2InstanceId"]),
                        event["detail"]["EC2InstanceId"],
                        int(environ["ROUTE53_TTL"]),
                    )

        finally:
            print(
                f"Completing lifecycle hook {event['detail']['LifecycleHookName']} "
                f"on instance {event['detail']['EC2InstanceId']}"
            )
            complete_lifecycle_action(
                lifecyclehookname=event["detail"]["LifecycleHookName"],
                autoscalinggroupname=event["detail"]["AutoScalingGroupName"],
                lifecycleactiontoken=event["detail"]["LifecycleActionToken"],
                instanceid=event["detail"]["EC2InstanceId"],
                lifecycleactionresult="CONTINUE",
            )

    else:
        instance_id = event["detail"]["instance-id"]
        if (
            "ASG_NAME" in environ
            and get_instance_asg(instance_id) == environ["ASG_NAME"]
        ):
            print(
                f"instance {instance_id} is a member of the {environ['ASG_NAME']} autoscaling group."
            )
            if event["detail"]["state"] == "running":
                print(
                    f"Instance state is {event['detail']['state']}. Will add an A record."
                )
                with lock("update-dns"):
                    add_record(
                        environ["ROUTE53_ZONE_ID"],
                        environ["ROUTE53_ZONE_NAME"],
                        resolve_hostname(instance_id),
                        instance_id,
                        int(environ["ROUTE53_TTL"]),
                        public=public,
                    )
            elif event["detail"]["state"] in ["shutting-down", "terminated"]:
                print(
                    f"Instance state is {event['detail']['state']}. Will remove an A record."
                )
                with lock("update-dns"):
                    remove_record(
                        environ["ROUTE53_ZONE_ID"],
                        environ["ROUTE53_ZONE_NAME"],
                        resolve_hostname(instance_id),
                        instance_id,
                        int(environ["ROUTE53_TTL"]),
                        public=public,
                    )
        else:
            print(
                f"Instance {instance_id} does not belong to {environ['ASG_NAME']} autoscaling group. "
                f"Will do nothing."
            )
