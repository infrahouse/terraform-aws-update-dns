from unittest import mock

from update_dns.main import add_record


def test_add_record():
    zone_id = "zone_test_id"
    zone_name = "ci-cd.infrahouse.com"
    mock_route53_client = mock.MagicMock()
    mock_route53_client.list_resource_record_sets.return_value = {
        "IsTruncated": False,
        "MaxItems": "100",
        "ResourceRecordSets": [
            {
                "Name": "ci-cd.infrahouse.com.",
                "ResourceRecords": [
                    {"Value": "ns-261.awsdns-32.com."},
                    {"Value": "ns-1795.awsdns-32.co.uk."},
                    {"Value": "ns-776.awsdns-33.net."},
                    {"Value": "ns-1311.awsdns-35.org."},
                ],
                "TTL": 172800,
                "Type": "NS",
            },
            {
                "Name": "ci-cd.infrahouse.com.",
                "ResourceRecords": [
                    {
                        "Value": "ns-261.awsdns-32.com. "
                        "awsdns-hostmaster.amazon.com. "
                        "1 7200 900 1209600 "
                        "86400"
                    }
                ],
                "TTL": 900,
                "Type": "SOA",
            },
            {
                "Name": "update-dns-test.ci-cd.infrahouse.com.",
                "ResourceRecords": [{"Value": "10.1.3.223"}],
                "TTL": 300,
                "Type": "A",
            },
        ],
    }
    with mock.patch(
        "update_dns.main.get_instance_ip", return_value="10.1.2.80"
    ), mock.patch("update_dns.main.resolve_hostname", return_value="update-dns-test"):
        add_record(
            zone_id=zone_id,
            zone_name=zone_name,
            hostname="update-dns-test",
            instance_id="i-0757254d0627cbd0c",
            ttl=300,
            public=False,
            route53_client=mock_route53_client,
            ec2_client=mock.MagicMock(),
        )
        mock_route53_client.change_resource_record_sets.assert_called_once_with(
            HostedZoneId="zone_test_id",
            ChangeBatch={
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": "update-dns-test.ci-cd.infrahouse.com.",
                            "Type": "A",
                            "ResourceRecords": [
                                {"Value": "10.1.2.80"},
                                {"Value": "10.1.3.223"},
                            ],
                            "TTL": 300,
                        },
                    }
                ]
            },
        )
