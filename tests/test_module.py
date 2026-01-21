import json
import os
import shutil
from os import path as osp
from textwrap import dedent
from time import sleep

import pytest
from infrahouse_core.aws.asg import ASG
from infrahouse_core.aws.route53.exceptions import IHRecordNotFound
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
            with timeout(
                seconds=300
            ):  # 5 minute timeout for instances to get public IPs
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


@pytest.mark.parametrize(
    "aws_provider_version", ["~> 5.31", "~> 6.0"], ids=["aws-5", "aws-6"]
)
def test_dns_record_deletion_on_manual_termination(
    service_network,
    aws_provider_version,
    keep_after,
    test_role_arn,
    aws_region,
    subzone,
    boto3_session,
):
    """
    Test that DNS records are properly deleted when instances are manually terminated.

    When an instance is manually terminated, the public IP is released quickly,
    causing instance.public_ip to return None. This test verifies that the Lambda
    correctly falls back to the IP stored in instance tags to delete the DNS record.
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

    # Use _PublicDnsName_ to test public IP scenarios
    route53_hostname = "_PublicDnsName_"
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

        # Create EC2 client using boto3_session
        ec2_client = boto3_session.client("ec2", region_name=aws_region)

        # Step 1: Wait for initial instance refresh to complete
        LOG.info("Waiting for initial instance refresh to complete...")
        with timeout(seconds=600):
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

        # Step 2: Wait for instance to have public IP
        LOG.info("Waiting for instance to have public IP...")
        with timeout(seconds=300):
            while True:
                if len(asg.instances) == 0:
                    LOG.info("No instances yet, waiting...")
                    sleep(10)
                    continue

                instance = asg.instances[0]
                if instance.public_ip is None:
                    LOG.info(
                        f"Instance {instance.instance_id} doesn't have public IP yet, waiting..."
                    )
                    sleep(10)
                    continue

                LOG.info(
                    f"Instance {instance.instance_id} has public IP: {instance.public_ip}"
                )
                break

        # Step 3: Verify DNS record was created
        target_instance = asg.instances[0]
        target_instance_id = target_instance.instance_id
        target_public_ip = target_instance.public_ip
        target_hostname = f"ip-{target_public_ip.replace('.', '-')}"

        LOG.info(f"Verifying DNS record for {target_hostname} -> {target_public_ip}")
        with timeout(seconds=120):
            while True:
                dns_ips = zone.search_hostname(target_hostname)
                if dns_ips == [target_public_ip]:
                    LOG.info(
                        f"DNS record verified: {target_hostname} -> {target_public_ip}"
                    )
                    break
                LOG.info(f"Waiting for DNS record to be created... Current: {dns_ips}")
                sleep(5)

        # Step 4: Manually terminate the instance
        LOG.info(f"Manually terminating instance {target_instance_id}...")
        ec2_client.terminate_instances(InstanceIds=[target_instance_id])
        LOG.info(f"Termination initiated for {target_instance_id}")

        # Step 4a: Wait for instance to disappear from ASG (lifecycle hook processed)
        LOG.info(f"Waiting for instance {target_instance_id} to be removed from ASG...")
        with timeout(
            seconds=600
        ):  # 10 minutes for ASG detection, lifecycle hook, and connection draining
            while True:
                current_instance_ids = [i.instance_id for i in asg.instances]
                if target_instance_id not in current_instance_ids:
                    LOG.info(f"Instance {target_instance_id} removed from ASG")
                    break
                LOG.info(f"Instance {target_instance_id} still in ASG, waiting...")
                sleep(5)

        # Step 5: Verify DNS record was deleted
        # Lambda has already completed (since instance was removed from ASG)
        # We just need to check if the record is gone
        LOG.info("Verifying DNS record was deleted...")
        try:
            dns_ips = zone.search_hostname(target_hostname)
            # If we get here, record still exists - this is the bug!
            raise AssertionError(
                f"DNS record {target_hostname} still exists with IPs: {dns_ips}. "
                f"Lambda failed to delete the record (likely due to instance_ip being None)."
            )
        except IHRecordNotFound:
            # This is the expected result - record was successfully deleted
            LOG.info(f"DNS record {target_hostname} successfully deleted")


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
    boto3_session,
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
        ec2_client = boto3_session.client("ec2", region_name=aws_region)

        # Step 1: Wait for instance to have public IP
        LOG.info("Waiting for instance to have public IP...")
        with timeout(seconds=300):
            while True:
                if len(asg.instances) == 0:
                    LOG.info("No instances yet, waiting...")
                    sleep(10)
                    continue

                instance = asg.instances[0]
                if instance.public_ip is None:
                    LOG.info(
                        f"Instance {instance.instance_id} doesn't have public IP yet, waiting..."
                    )
                    sleep(10)
                    continue

                LOG.info(
                    f"Instance {instance.instance_id} has public IP: {instance.public_ip}"
                )
                break

        # Step 2: Verify BOTH DNS records were created
        instance = asg.instances[0]
        public_ip = instance.public_ip
        instance_id = instance.instance_id

        # Expected hostnames with different prefixes
        expected_hostnames = [
            f"ip-{public_ip.replace('.', '-')}",
            f"api-{public_ip.replace('.', '-')}",
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

        # Step 3: Manually terminate the instance (triggers Lambda deletion)
        LOG.info(f"Manually terminating instance {instance_id}...")
        ec2_client.terminate_instances(InstanceIds=[instance_id])
        LOG.info(f"Termination initiated for {instance_id}")

        # Step 4: Wait for instance to be removed from ASG (lifecycle hook processed)
        LOG.info(f"Waiting for instance {instance_id} to be removed from ASG...")
        with timeout(seconds=600):
            while True:
                current_instance_ids = [i.instance_id for i in asg.instances]
                if instance_id not in current_instance_ids:
                    LOG.info(f"Instance {instance_id} removed from ASG")
                    break
                LOG.info(f"Instance {instance_id} still in ASG, waiting...")
                sleep(5)

        # Step 5: Verify ALL DNS records were deleted
        LOG.info("Verifying all DNS records were deleted...")
        for hostname in expected_hostnames:
            LOG.info(f"Checking deletion of: {hostname}")
            try:
                dns_ips = zone.search_hostname(hostname)
                # If we get here, record still exists - feature not implemented!
                raise AssertionError(
                    f"DNS record {hostname} still exists with IPs: {dns_ips}. "
                    f"Multiple prefix feature not yet implemented."
                )
            except IHRecordNotFound:
                # This is the expected result - record was successfully deleted
                LOG.info(f"✓ DNS record {hostname} successfully deleted")

        LOG.info(
            "✓ All DNS records with multiple prefixes successfully created and deleted"
        )
