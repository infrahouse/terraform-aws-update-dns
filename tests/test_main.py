"""
Unit tests for the update-dns Lambda handler (``update_dns/main.py``).

Unlike the integration tests in ``test_module.py`` (which stand up real AWS
infrastructure via pytest-infrahouse), these are fast, hermetic tests of the
``lambda_handler`` branching logic. They mock every AWS-touching dependency and
assert which DNS side-effect runs and that the lifecycle hook is always
completed -- in particular covering the warm-pool transitions that must skip DNS
work (see the warm-pool-aware filtering change).
"""

import os
import sys
from os import path as osp
from unittest.mock import MagicMock

import pytest

# ``update_dns/main.py`` lives in the Lambda build bundle. Append (not prepend)
# the bundle dir so the installed infrahouse_core wins over the vendored copy.
sys.path.append(osp.join(osp.dirname(osp.dirname(osp.abspath(__file__))), "update_dns"))

import main  # noqa: E402  pylint: disable=wrong-import-position

TERMINATING_HOOK = "terminating-hook"
LAUNCHING_HOOK = "launching-hook"


def _make_event(transition, hook_name, origin=None, destination=None):
    """Build an EventBridge ASG lifecycle event, omitting absent Origin/Destination."""
    detail = {
        "EC2InstanceId": "i-0123456789abcdef0",
        "LifecycleHookName": hook_name,
        "LifecycleTransition": transition,
        "AutoScalingGroupName": "asg-under-test",
    }
    if origin is not None:
        detail["Origin"] = origin
    if destination is not None:
        detail["Destination"] = destination
    return {"detail": detail}


@pytest.fixture(autouse=True)
def mocked_main(monkeypatch):
    """
    Patch every AWS-touching symbol in ``main`` and set the env vars the handler
    reads. Yields the mocks so each test can assert on DNS calls and the hook.
    """
    monkeypatch.setenv("LIFECYCLE_HOOK_TERMINATING", TERMINATING_HOOK)
    monkeypatch.setenv("LIFECYCLE_HOOK_LAUNCHING", LAUNCHING_HOOK)
    monkeypatch.setenv("ROUTE53_ZONE_ID", "Z123456")
    monkeypatch.setenv("ROUTE53_TTL", "300")
    monkeypatch.setenv("LOCK_TABLE_NAME", "update-dns-lock")
    # Custom hostname so resolve_hostnames() returns a static value without AWS calls.
    monkeypatch.setenv("ROUTE53_HOSTNAME", "update-dns-test")

    asg = MagicMock(name="ASG")
    add_records = MagicMock(name="add_records")
    remove_record = MagicMock(name="remove_record")
    log_exception = MagicMock(name="LOG.exception")

    monkeypatch.setattr(main, "ASG", asg)
    monkeypatch.setattr(main, "DynamoDBTable", MagicMock(name="DynamoDBTable"))
    monkeypatch.setattr(main, "add_records", add_records)
    monkeypatch.setattr(main, "remove_record", remove_record)
    # The handler swallows exceptions via LOG.exception; fail loudly instead so a
    # broken mock setup can't masquerade as "the branch did nothing".
    monkeypatch.setattr(main.LOG, "exception", log_exception)

    yield {
        "asg": asg,
        "add_records": add_records,
        "remove_record": remove_record,
        "log_exception": log_exception,
    }


def _assert_hook_completed(asg):
    """The hook must always be completed with CONTINUE."""
    asg.return_value.complete_lifecycle_action.assert_called_once()
    _, kwargs = asg.return_value.complete_lifecycle_action.call_args
    assert kwargs["result"] == "CONTINUE"
    assert (
        kwargs["hook_name"] == LAUNCHING_HOOK or kwargs["hook_name"] == TERMINATING_HOOK
    )


# --- Launching transitions ---


def test_launching_cold_launch_adds_record(mocked_main):
    """EC2 -> AutoScalingGroup: a real cold launch. DNS record is created."""
    main.lambda_handler(
        _make_event(
            "autoscaling:EC2_INSTANCE_LAUNCHING",
            LAUNCHING_HOOK,
            origin="EC2",
            destination="AutoScalingGroup",
        ),
        None,
    )
    mocked_main["add_records"].assert_called_once()
    mocked_main["remove_record"].assert_not_called()
    _assert_hook_completed(mocked_main["asg"])


def test_launching_warm_pool_activation_adds_record(mocked_main):
    """WarmPool -> AutoScalingGroup: instance activating out of the pool. DNS record is created."""
    main.lambda_handler(
        _make_event(
            "autoscaling:EC2_INSTANCE_LAUNCHING",
            LAUNCHING_HOOK,
            origin="WarmPool",
            destination="AutoScalingGroup",
        ),
        None,
    )
    mocked_main["add_records"].assert_called_once()
    mocked_main["remove_record"].assert_not_called()
    _assert_hook_completed(mocked_main["asg"])


def test_launching_into_warm_pool_skips_add(mocked_main):
    """EC2 -> WarmPool: instance entering the pool. No DNS record, but hook still completed."""
    main.lambda_handler(
        _make_event(
            "autoscaling:EC2_INSTANCE_LAUNCHING",
            LAUNCHING_HOOK,
            origin="EC2",
            destination="WarmPool",
        ),
        None,
    )
    mocked_main["add_records"].assert_not_called()
    mocked_main["remove_record"].assert_not_called()
    _assert_hook_completed(mocked_main["asg"])


# --- Terminating transitions ---


def test_terminating_in_service_removes_record(mocked_main):
    """AutoScalingGroup -> EC2: a real in-service termination. DNS record is removed."""
    main.lambda_handler(
        _make_event(
            "autoscaling:EC2_INSTANCE_TERMINATING",
            TERMINATING_HOOK,
            origin="AutoScalingGroup",
            destination="EC2",
        ),
        None,
    )
    mocked_main["remove_record"].assert_called_once()
    mocked_main["add_records"].assert_not_called()
    _assert_hook_completed(mocked_main["asg"])


def test_terminating_from_warm_pool_skips_remove(mocked_main):
    """
    WarmPool -> EC2: warmed instance being trimmed. It never held a DNS record.

    Regression test: previously remove_record crashed on the missing IP tag, the
    hook was never completed, and the ASG hung until HeartbeatTimeout -> ABANDON.
    """
    main.lambda_handler(
        _make_event(
            "autoscaling:EC2_INSTANCE_TERMINATING",
            TERMINATING_HOOK,
            origin="WarmPool",
            destination="EC2",
        ),
        None,
    )
    mocked_main["remove_record"].assert_not_called()
    mocked_main["add_records"].assert_not_called()
    _assert_hook_completed(mocked_main["asg"])


# --- Positive-match contract: missing fields fall through to today's behavior ---


def test_launching_without_origin_destination_adds_record(mocked_main):
    """Event with no Origin/Destination (non-warm-pool consumer) still adds the record."""
    main.lambda_handler(
        _make_event("autoscaling:EC2_INSTANCE_LAUNCHING", LAUNCHING_HOOK),
        None,
    )
    mocked_main["add_records"].assert_called_once()
    _assert_hook_completed(mocked_main["asg"])


def test_terminating_without_origin_destination_removes_record(mocked_main):
    """Event with no Origin/Destination (non-warm-pool consumer) still removes the record."""
    main.lambda_handler(
        _make_event("autoscaling:EC2_INSTANCE_TERMINATING", TERMINATING_HOOK),
        None,
    )
    mocked_main["remove_record"].assert_called_once()
    _assert_hook_completed(mocked_main["asg"])


# --- Exceptions must propagate, not be silently swallowed ---


def test_add_records_failure_propagates(mocked_main):
    """
    A DNS failure on launch must propagate so the Lambda Errors metric fires and
    EventBridge retries -- and the hook must NOT be completed with CONTINUE, since
    the DNS work did not succeed.
    """
    mocked_main["add_records"].side_effect = RuntimeError("route53 boom")
    with pytest.raises(RuntimeError, match="route53 boom"):
        main.lambda_handler(
            _make_event(
                "autoscaling:EC2_INSTANCE_LAUNCHING",
                LAUNCHING_HOOK,
                origin="EC2",
                destination="AutoScalingGroup",
            ),
            None,
        )
    mocked_main["asg"].return_value.complete_lifecycle_action.assert_not_called()
    mocked_main["log_exception"].assert_called_once()


def test_remove_record_failure_propagates(mocked_main):
    """A DNS failure on termination must propagate (not be reported as success)."""
    mocked_main["remove_record"].side_effect = RuntimeError("dynamodb boom")
    with pytest.raises(RuntimeError, match="dynamodb boom"):
        main.lambda_handler(
            _make_event(
                "autoscaling:EC2_INSTANCE_TERMINATING",
                TERMINATING_HOOK,
                origin="AutoScalingGroup",
                destination="EC2",
            ),
            None,
        )
    mocked_main["asg"].return_value.complete_lifecycle_action.assert_not_called()
    mocked_main["log_exception"].assert_called_once()
