import json
import time
from os import path as osp
from textwrap import dedent
from time import sleep

import pytest
from infrahouse_core.aws.asg import ASG
from infrahouse_core.aws.route53.zone import Zone
from pytest_infrahouse import terraform_apply

from tests.conftest import (
    LOG,
    TERRAFORM_ROOT_DIR,
)


@pytest.mark.parametrize(
    "route53_hostname, asg_size",
    [("update-dns-test", 1), ("update-dns-test", 2), ("_PrivateDnsName_", 3)],
)
def test_module(
    service_network,
    route53_hostname,
    asg_size,
    keep_after,
    test_role_arn,
    aws_region,
    test_zone_name,
):
    subnet_public_ids = service_network["subnet_public_ids"]["value"]
    subnet_private_ids = service_network["subnet_private_ids"]["value"]
    internet_gateway_id = service_network["internet_gateway_id"]["value"]

    terraform_module_dir = osp.join(TERRAFORM_ROOT_DIR, "update-dns")
    with open(osp.join(terraform_module_dir, "terraform.tfvars"), "w") as fp:
        fp.write(
            dedent(
                f"""
                    region = "{aws_region}"
                    test_zone = "{test_zone_name}"

                    subnet_public_ids = {json.dumps(subnet_public_ids)}
                    subnet_private_ids = {json.dumps(subnet_private_ids)}
                    internet_gateway_id = "{internet_gateway_id}"
                    route53_hostname = "{route53_hostname}"
                    asg_min_size = {asg_size}
                    asg_max_size = {asg_size}
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
        asg = ASG(tf_output["asg_name"]["value"], region=aws_region, role_arn=test_role_arn)
        zone = Zone(zone_id=tf_output["zone_id"]["value"], role_arn=test_role_arn)

        if route53_hostname == "_PrivateDnsName_":
            try:
                for instance in asg.instances:
                    assert instance.private_ip
                    assert instance.hostname
                    assert zone.search_hostname(instance.hostname) == [instance.private_ip]

            finally:
                if not keep_after:
                    LOG.info("Deleting record %s=%s", route53_hostname, instance.private_ip)
                    zone.delete_record(instance.hostname, instance.private_ip)
        else:
            try:
                now = time.time()
                timeout = 60 * len(asg.instances)
                while True:
                    if time.time() > now + timeout:
                        raise RuntimeError(
                            f"There is no DNS update after {timeout} seconds"
                        )
                    try:
                        assert sorted(zone.search_hostname(route53_hostname)) == sorted(
                            [i.private_ip for i in asg.instances]
                        )
                        break
                    except AssertionError:
                        LOG.info("Waiting 5 more seconds for DNS update")
                        sleep(5)
            finally:
                # Clean up the zone, because the lambda doesn't delete DNS records
                # when the ASG is deleted. Terraform deletes the terminating lifecycle hook
                # and the lambda never triggers.
                if not keep_after:
                    for ip in zone.search_hostname(route53_hostname):
                        LOG.info("Deleting record %s=%s", route53_hostname, ip)
                        zone.delete_record(route53_hostname, ip)
