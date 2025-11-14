import json
import os
import shutil
from os import path as osp
from textwrap import dedent
from time import sleep

import pytest
from infrahouse_core.aws.asg import ASG
from infrahouse_core.aws.route53.zone import Zone
from infrahouse_core.timeout import timeout
from pytest_infrahouse import terraform_apply

from tests.conftest import (
    LOG,
    TERRAFORM_ROOT_DIR,
)


@pytest.mark.parametrize(
    "route53_hostname, asg_size",
    [
        ("update-dns-test", 1),
        ("update-dns-test", 2),
        ("_PrivateDnsName_", 3),
        ("_PublicDnsName_", 1),
    ],
)
@pytest.mark.parametrize(
    "aws_provider_version", ["~> 5.31", "~> 6.0"], ids=["aws-5", "aws-6"]
)
def test_module(
    service_network,
    route53_hostname,
    asg_size,
    aws_provider_version,
    keep_after,
    test_role_arn,
    aws_region,
    subzone,
):
    subnet_public_ids = service_network["subnet_public_ids"]["value"]
    subnet_private_ids = service_network["subnet_private_ids"]["value"]
    internet_gateway_id = service_network["internet_gateway_id"]["value"]

    terraform_module_dir = osp.join(TERRAFORM_ROOT_DIR, "update-dns")

    # Clean up Terraform cache files to ensure fresh provider installation
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

    # Determine which subnets to use based on hostname
    subnet_ids = (
        subnet_public_ids
        if route53_hostname == "_PublicDnsName_"
        else subnet_private_ids
    )
    route53_public_ip = True if route53_hostname == "_PublicDnsName_" else False

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

        # Step 1: Wait for instance refreshes to complete (if any are running)
        LOG.info("Checking for active instance refreshes...")
        with timeout(seconds=600):  # 10 minute timeout for instance refreshes
            while True:
                active_refreshes = [
                    r for r in asg.instance_refreshes if r.get("Status") == "InProgress"
                ]
                if not active_refreshes:
                    LOG.info("No active instance refreshes")
                    break
                LOG.info(
                    f"Waiting for {len(active_refreshes)} instance refresh(es) to complete..."
                )
                sleep(10)

        # Step 2: Wait for instances to be ready with expected properties
        if route53_hostname == "_PublicDnsName_":
            LOG.info("Waiting for instances to have public IPs...")
            with timeout(seconds=300):  # 5 minute timeout for instances to get public IPs
                while True:
                    instances_ready = True
                    for instance in asg.instances:
                        if instance.public_ip is None:
                            LOG.info(
                                f"Instance {instance.instance_id} doesn't have public IP yet, waiting..."
                            )
                            instances_ready = False
                            break

                    if instances_ready:
                        LOG.info("All instances have public IPs")
                        for instance in asg.instances:
                            LOG.info(
                                f"Instance {instance.instance_id} has public IP: {instance.public_ip}"
                            )
                        break

                    sleep(10)

        try:
            if route53_hostname == "_PrivateDnsName_":
                for instance in asg.instances:
                    assert instance.private_ip
                    assert instance.hostname
                    assert zone.search_hostname(instance.hostname) == [
                        instance.private_ip
                    ]
            elif route53_hostname == "_PublicDnsName_":
                for instance in asg.instances:
                    assert instance.public_ip
                    # Hostname should be ip-80-90-1-1 format based on public IP
                    expected_hostname = "ip-" + instance.public_ip.replace(".", "-")
                    assert instance.tags.get("update-dns:hostname") == expected_hostname
                    assert zone.search_hostname(expected_hostname) == [
                        instance.public_ip
                    ]
            else:
                with timeout(seconds=60 * len(asg.instances)):
                    while True:
                        try:
                            assert sorted(
                                zone.search_hostname(route53_hostname)
                            ) == sorted([i.private_ip for i in asg.instances])
                            break
                        except AssertionError:
                            LOG.info("Waiting 5 more seconds for DNS update")
                            sleep(5)
        finally:
            # Clean up the zone, because the lambda doesn't delete DNS records
            # when the ASG is deleted. Terraform deletes the terminating lifecycle hook
            # and the lambda never triggers.
            if not keep_after:
                if route53_hostname == "_PrivateDnsName_":
                    for instance in asg.instances:
                        LOG.info(
                            "Deleting record %s=%s",
                            instance.hostname,
                            instance.private_ip,
                        )
                        zone.delete_record(instance.hostname, instance.private_ip)
                elif route53_hostname == "_PublicDnsName_":
                    for instance in asg.instances:
                        expected_hostname = "ip-" + instance.public_ip.replace(".", "-")
                        LOG.info(
                            "Deleting record %s=%s",
                            expected_hostname,
                            instance.public_ip,
                        )
                        zone.delete_record(expected_hostname, instance.public_ip)
                else:
                    for ip in zone.search_hostname(route53_hostname):
                        LOG.info("Deleting record %s=%s", route53_hostname, ip)
                        zone.delete_record(route53_hostname, ip)
