import json
import time
from os import path as osp
from pprint import pprint, pformat
from textwrap import dedent

import pytest
from infrahouse_toolkit.terraform import terraform_apply

from tests.conftest import (
    LOG,
    TRACE_TERRAFORM,
    DESTROY_AFTER,
    TEST_ZONE,
    TEST_ROLE_ARN,
    REGION,
    TERRAFORM_ROOT_DIR,
)


@pytest.mark.parametrize(
    "route53_hostname, asg_size",
    [("update-dns-test", 1), ("update-dns-test", 2), ("_PrivateDnsName_", 3)],
)
def test_module(
    service_network,
    autoscaling_client,
    route53_client,
    ec2_client,
    route53_hostname,
    asg_size,
):
    subnet_public_ids = service_network["subnet_public_ids"]["value"]
    subnet_private_ids = service_network["subnet_private_ids"]["value"]
    internet_gateway_id = service_network["internet_gateway_id"]["value"]

    terraform_module_dir = osp.join(TERRAFORM_ROOT_DIR, "update-dns")
    with open(osp.join(terraform_module_dir, "terraform.tfvars"), "w") as fp:
        fp.write(
            dedent(
                f"""
                    region = "{REGION}"
                    role_arn = "{TEST_ROLE_ARN}"
                    test_zone = "{TEST_ZONE}"

                    subnet_public_ids = {json.dumps(subnet_public_ids)}
                    subnet_private_ids = {json.dumps(subnet_private_ids)}
                    internet_gateway_id = "{internet_gateway_id}"
                    route53_hostname = "{route53_hostname}"
                    asg_min_size = {asg_size}
                    asg_max_size = {asg_size}
                    """
            )
        )

    with terraform_apply(
        terraform_module_dir,
        destroy_after=DESTROY_AFTER,
        json_output=True,
        enable_trace=TRACE_TERRAFORM,
    ) as tf_output:
        LOG.info("%s", json.dumps(tf_output, indent=4))
        asg_name = tf_output["asg_name"]["value"]
        zone_id = tf_output["zone_id"]["value"]
        # refresh_id = autoscaling_client.start_instance_refresh(
        #     AutoScalingGroupName=tf_output["asg_name"]["value"],
        #     Preferences={
        #         "MinHealthyPercentage": 0,
        #         "InstanceWarmup": 60,
        #         "SkipMatching": False,
        #         "ScaleInProtectedInstances": "Refresh",
        #     },
        # )["InstanceRefreshId"]
        LOG.info("Wait until all refreshes are done")
        LOG.info("Waiting %d * 60 seconds until lambda is done", asg_size)
        time.sleep(asg_size * 60)
        while True:
            response = autoscaling_client.describe_instance_refreshes(
                AutoScalingGroupName=tf_output["asg_name"]["value"],
            )
            LOG.debug("describe_instance_refreshes() = %s", pformat(response))
            all_done = True
            for refresh in response["InstanceRefreshes"]:
                status = refresh["Status"]
                if status not in [
                    "Successful",
                    "Failed",
                    "Cancelled",
                    "RollbackFailed",
                    "RollbackSuccessful",
                ]:
                    all_done = False
            if all_done:
                break
            else:
                time.sleep(60)

        if route53_hostname == "_PrivateDnsName_":
            response = autoscaling_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name],
            )
            for instance in response["AutoScalingGroups"][0]["Instances"]:
                instance_id = instance["InstanceId"]
                response = ec2_client.describe_instances(
                    InstanceIds=[
                        instance_id,
                    ],
                )
                LOG.debug("describe_instances() = %s", pformat(response))
                ipaddress = response["Reservations"][0]["Instances"][0][
                    "PrivateIpAddress"
                ]
                hostname = None
                for tag in response["Reservations"][0]["Instances"][0]["Tags"]:
                    if tag["Key"] == "Name":
                        hostname = tag["Value"]

                assert ipaddress
                assert hostname
                response = route53_client.list_resource_record_sets(
                    HostedZoneId=zone_id,
                    StartRecordName=f"{hostname}.{TEST_ZONE}",
                    StartRecordType="A",
                )
                assert (
                    response["ResourceRecordSets"][0]["ResourceRecords"][0]["Value"]
                    == ipaddress
                )
        else:
            now = time.time()
            timeout = 60
            while True:
                if time.time() > now + timeout:
                    raise RuntimeError(
                        f"There is no DNS update after {timeout} seconds"
                    )

                response = route53_client.list_resource_record_sets(
                    HostedZoneId=zone_id,
                    StartRecordName=f"{route53_hostname}.{TEST_ZONE}",
                    StartRecordType="A",
                )
                LOG.debug("list_resource_record_sets() = %s", pformat(response))

                # Wait up to $timeout seconds for lambda to add $asg_size values to the DNS record.
                if (
                    response["ResourceRecordSets"]
                    and len(response["ResourceRecordSets"][0]["ResourceRecords"])
                    == asg_size
                ):
                    assert (
                        response["ResourceRecordSets"][0]["Name"]
                        == f"{route53_hostname}.{TEST_ZONE}."
                    )
                    assert response["ResourceRecordSets"][0]["Type"] == "A"
                    assert (
                        len(response["ResourceRecordSets"][0]["ResourceRecords"])
                        == asg_size
                    )
                    break
                else:
                    time.sleep(5)
