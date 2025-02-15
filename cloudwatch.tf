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
}

resource "aws_cloudwatch_event_target" "scale-out" {
  arn  = aws_lambda_function.update_dns.arn
  rule = aws_cloudwatch_event_rule.scale.name
}

resource "aws_cloudwatch_log_group" "update_dns" {
  name              = "/aws/lambda/${aws_lambda_function.update_dns.function_name}"
  retention_in_days = var.log_retention_in_days
}
