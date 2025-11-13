resource "aws_cloudwatch_event_rule" "scale" {
  name_prefix = "asg-scale"
  description = "ASG lifecycle hook"
  event_pattern = jsonencode(
    {
      "source" : ["aws.autoscaling"],
      "detail-type" : [
        "EC2 Instance-launch Lifecycle Action",
        "EC2 Instance-terminate Lifecycle Action"
      ],
      "detail" : {
        "AutoScalingGroupName" : [
          var.asg_name
        ]
      }
    }
  )
  tags = local.default_module_tags
}

resource "aws_cloudwatch_event_target" "scale-out" {
  arn  = module.update_dns_lambda.lambda_function_arn
  rule = aws_cloudwatch_event_rule.scale.name
}
