EC2 instances in an autoscaling group have dynamic IP addresses.
Whether the ASG is deployed in the public or private subnets, the IP addresses are unpredictable.
Therefore, there are no DNS records that would resolve into those dynamic private addresses.

This module solves that problem. When an instance is launched, a lambda function gets the instnace's IP - private or public -
and add an A record to a Route53 zone. Respectively, when the EC2 instance is terminated, the lambda deletes the record.

This module deploys that lambda.
