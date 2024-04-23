provider "aws" {
  region = var.region
  assume_role {
    role_arn = var.role_arn
  }
  default_tags {
    tags = {
      "created_by" : "infrahouse/terraform-aws-update-dns" # GitHub repository that created a resource
    }
  }
}
