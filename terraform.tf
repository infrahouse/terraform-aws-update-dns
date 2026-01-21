terraform {
  required_version = "~> 1.5"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 6.28.0 has a bug with DynamoDB table names depending on unknown values
      # https://github.com/hashicorp/terraform-provider-aws/issues/46016
      version = ">= 5.11, < 7.0, != 6.28.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
