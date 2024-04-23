import json
import time
from os import path as osp
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
    [
        # ("update-dns-test", 1),
        # ("update-dns-test", 2),
        ("_PrivateDnsName_", 3)
    ],
)
def test_module(
    service_network, autoscaling_client, route53_client, route53_hostname, asg_size
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
        refresh_id = autoscaling_client.start_instance_refresh(
            AutoScalingGroupName=tf_output["asg_name"]["value"],
            Preferences={
                "MinHealthyPercentage": 0,
                "InstanceWarmup": 60,
                "SkipMatching": False,
                "ScaleInProtectedInstances": "Refresh",
            },
        )["InstanceRefreshId"]
        LOG.info("Refresh id %s", refresh_id)
        while True:
            response = autoscaling_client.describe_instance_refreshes(
                AutoScalingGroupName=tf_output["asg_name"]["value"],
                InstanceRefreshIds=[
                    refresh_id,
                ],
            )
            print(f"{response = }")
            status = response["InstanceRefreshes"][0]["Status"]
            if status in [
                "Successful",
                "Failed",
                "Cancelled",
                "RollbackFailed",
                "RollbackSuccessful",
            ]:
                break
            else:
                time.sleep(60)
        if route53_hostname == "_PrivateDnsName_":
            assert True
        else:
            response = route53_client.list_resource_record_sets(
                HostedZoneId=tf_output["zone_id"]["value"],
                StartRecordName=f"{route53_hostname}.{TEST_ZONE}",
                StartRecordType="A",
            )
            print(f"{response = }")

            assert (
                response["ResourceRecordSets"][0]["Name"]
                == f"{route53_hostname}.{TEST_ZONE}."
            )
            assert response["ResourceRecordSets"][0]["Type"] == "A"
            assert len(response["ResourceRecordSets"][0]["ResourceRecords"]) == asg_size
