# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## First Steps

**Your first tool call in this repository MUST be reading .claude/CODING_STANDARD.md.
Do not read any other files, search, or take any actions until you have read it.**
This contains InfraHouse's comprehensive coding standards for Terraform, Python, and general formatting rules.

## Project Overview

Terraform module that manages Route53 DNS A records for EC2 instances in an Auto Scaling Group.
A Lambda function responds to ASG lifecycle hook events via CloudWatch EventBridge:
creating DNS records on instance launch and deleting them on termination.
Uses DynamoDB for concurrency locking.

## Commands

```bash
make bootstrap          # Install pip dependencies (requires virtualenv)
make lint               # terraform fmt --check -recursive
make format             # terraform fmt -recursive && black tests update_dns/main.py
make test               # pytest -xvvs tests/
make test-keep          # Run tests, keep AWS resources for debugging
make test-clean         # Run tests, destroy resources (run before PRs)
make clean              # Remove .pytest_cache, .terraform dirs, test logs
make release-patch      # Bump patch version with git-cliff + bumpversion
```

Test parameters are configurable: `TEST_REGION`, `TEST_ROLE`, `TEST_SELECTOR`.

## Architecture

**Event flow:** ASG lifecycle hook -> CloudWatch EventBridge rule -> Lambda -> Route53 + DynamoDB

**Key Terraform files:**
- `lambda.tf` — Lambda module invocation (infrahouse/lambda-monitored/aws v1.0.4),
  IAM permissions, environment variables
- `cloudwatch.tf` — EventBridge rule and target connecting lifecycle events to Lambda
- `dynamodb.tf` — DynamoDB lock table for concurrency control
- `lifecycle_hooks.tf` — Random suffix for lifecycle hook names (users must create the actual hooks)
- `variables.tf` — 11 input variables; `asg_name`, `route53_zone_id`, `alarm_emails` are required

**Lambda code:** `update_dns/main.py` (Python 3.12) — handles
`add_records`/`remove_records` with support for multiple hostname prefixes
and special values (`_PrivateDnsName_`, `_PublicDnsName_`).

**Test infrastructure:** `test_data/update-dns/` contains a root module that creates
an ASG and invokes this module. Tests in `tests/test_module.py` are parametrized
across hostname scenarios and AWS provider versions (~>5.31, ~>6.0).

## Coding Standards

Full standards in `.claude/CODING_STANDARD.md`. Key points:

- **120 char line limit** for all files
- **Terraform:** snake_case everywhere, exact module version pinning (no ranges),
  `aws_iam_policy_document` data sources instead of jsonencode for IAM policies,
  HEREDOC for long descriptions
- **Validation blocks:** use ternary operators for nullable variables (`var.x == null ? true : ...`), not logical OR
- **Python:** Black formatter, type hints required, RST docstrings,
  catch specific exceptions only (never bare `except Exception:`),
  raise exceptions instead of returning booleans for errors
- **Dependencies:** pin to major version with `~=` syntax (e.g., `requests ~= 2.31`)
- **Modules:** source from `registry.infrahouse.com`, always exact version
- **Commits:** conventional commits format (`feat:`, `fix:`, `docs:`, `refactor:`)
- **Testing:** integration tests with real AWS infrastructure via pytest-infrahouse fixtures
