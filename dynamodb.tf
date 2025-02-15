resource "random_string" "dynamodb-suffix" {
  length  = 20
  special = false
}

resource "aws_dynamodb_table" "update_dns_lock" {
  name         = "update-dns-${random_string.dynamodb-suffix.result}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ResourceId"
  attribute {
    name = "ResourceId"
    type = "S"
  }
  tags = {
    asg_name : var.asg_name
    VantaNoAlert : "Table used for global lock and does not contain user data"
  }
}
