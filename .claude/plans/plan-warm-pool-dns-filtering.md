# Implementation Plan: Warm-Pool-Aware DNS Filtering (flagless)

## Overview

Make the update-dns Lambda correctly skip DNS work for ASG **warm-pool** lifecycle
transitions. Today the module treats every `LAUNCHING`/`TERMINATING` event as a real
in-service launch/terminate, which is wrong (and in one case fatal) once a consumer
enables a warm pool. This change teaches the Lambda to recognise the two warm-pool
transitions from the standard `Origin`/`Destination` fields and skip DNS for them,
while still completing its own lifecycle hook.

This is the upstream-ready half of the tetra-data `update-dns` fork. It is
intentionally **flagless** — no new variables, no new Lambda env vars. The
provisioning-readiness concern that the fork also bolted onto this module
(`warm_pool_launch_auto_continue`) is explicitly **out of scope** and stays in the
consumer (see "Out of scope" below).

## Background / Motivation

`update-dns` pairs with `website-pod`, which now ships warm-pool support
(`website-pod` 6.1.0). So a public consumer can now enable a warm pool on the ASG —
and the moment they do, this Lambda misbehaves:

1. **`LAUNCHING` into the warm pool** (`Destination=WarmPool`): the instance is not
   in service and serves no traffic (and in `Stopped`/`Hibernated` pools has no
   stable IP). Adding a DNS record for it publishes an endpoint that should never
   receive traffic. The record's correct lifecycle is created-on-activation,
   removed-on-terminate.
2. **`TERMINATING` from the warm pool** (`Origin=WarmPool`): a warmed instance never
   had a DNS record. `remove_record` then crashes on the missing
   `PublicIpAddress`/`PrivateIpAddress` tag, the hook is never completed, and it
   hangs until `HeartbeatTimeout` -> ASG `ABANDON`. This is a hard failure, not a
   cosmetic one.

### Field availability — verified in production

The whole design rests on `Origin`/`Destination` always being present. Confirmed
against a live warm-pool ASG (`tetra-data`, account 722222646194, 45 days,
**658 events, 0 missing either field**). Observed transition taxonomy:

| Transition  | Origin -> Destination       | Count | Correct DNS action |
|-------------|-----------------------------|-------|--------------------|
| LAUNCHING   | EC2 -> **WarmPool**         | 207   | **skip add**       |
| LAUNCHING   | WarmPool -> AutoScalingGroup | 175  | add (activation)   |
| LAUNCHING   | EC2 -> AutoScalingGroup     | 38    | add (cold launch)  |
| TERMINATING | AutoScalingGroup -> EC2     | 214   | remove             |
| TERMINATING | **WarmPool** -> EC2         | 24    | **skip remove**    |

~35% of lifecycle traffic on a warm-pool ASG (the 207 + 24) is cases the stock
module handles incorrectly.

## Problem Analysis

**Location**: `update_dns/main.py`, `lambda_handler()` (the
`TERMINATING`/`LAUNCHING` branches near the `LIFECYCLE_HOOK_*` matches).

The handler matches on `LifecycleHookName` + `LifecycleTransition` only. It never
inspects `event["detail"]["Origin"]` / `["Destination"]`, so warm-pool internal
moves are processed as if they were real launches/terminations.

## Design Decision: unconditional, positive-match on the WarmPool sentinel

Skipping DNS for a warm-pool instance is never the wrong thing to do — it's a
property of what the module is *for*, not a user preference. So this is **not**
behind a flag (mirrors the existing always-on correctness behavior of the module).

Predicates use a **positive match on `WarmPool`**, not `!= AutoScalingGroup`:

- skip the **add** only when `Destination == "WarmPool"`
- skip the **remove** only when `Origin == "WarmPool"`

Why positive-match: any event that lacks the field, or carries an unexpected value,
falls through to today's behavior (add on launch / remove on terminate). That makes
the change provably non-breaking for every existing consumer — a non-warm-pool ASG
only ever emits `Destination=AutoScalingGroup` (launch) and `Origin=AutoScalingGroup`
/ `Destination=EC2` (terminate), so none of these branches ever fire for them. The
`!= AutoScalingGroup` phrasing from the fork is deny-by-default and would skip DNS on
a real launch if `Destination` were ever absent; we avoid it.

In all skip cases the Lambda **still completes its own lifecycle hook** (CONTINUE).
update-dns owns its hook and must release it; it simply does no DNS work.

## Changes

### `update_dns/main.py`

Read the two fields once near the top of `lambda_handler()` (alongside
`instance_id` / `lc_hook_name` / `lc_transition`):

```python
origin = event["detail"].get("Origin")
destination = event["detail"].get("Destination")
```

**Terminating branch** — add a guard before acquiring the lock / `remove_record`:

```python
if origin == "WarmPool":
    # Warm-pool instance being terminated (Warmed:* -> EC2). It never held a
    # DNS record, and remove_record would crash on the missing IP tag. Skip
    # DNS and complete the hook so the ASG isn't left waiting for HeartbeatTimeout.
    LOG.info(
        f"Terminating event Origin=WarmPool on {instance_id}; "
        f"completing hook with no DNS removal."
    )
    ASG(event["detail"]["AutoScalingGroupName"]).complete_lifecycle_action(
        hook_name=lc_hook_name, result="CONTINUE", instance_id=instance_id,
    )
    return
```

**Launching branch** — add a guard before acquiring the lock / `add_records`:

```python
if destination == "WarmPool":
    # Instance entering the warm pool (EC2 -> WarmPool). Not in service, no
    # traffic, no stable IP — no DNS record wanted. It will be registered when
    # it activates out of the pool (Destination=AutoScalingGroup). Complete this
    # module's hook immediately; any readiness gating is the consumer's separate
    # hook, not ours.
    LOG.info(
        f"Launching event Destination=WarmPool on {instance_id}; "
        f"completing hook with no DNS add."
    )
    ASG(event["detail"]["AutoScalingGroupName"]).complete_lifecycle_action(
        hook_name=lc_hook_name, result="CONTINUE", instance_id=instance_id,
    )
    return
```

No other `*.tf` changes. **No new variables. No new Lambda env vars.**

## Out of scope (do NOT port)

The fork also carries `warm_pool_launch_auto_continue` (and its
`WARM_POOL_LAUNCH_AUTO_CONTINUE` env var), which makes the Lambda *optionally leave
the launching hook in Wait* so the instance can signal readiness itself. That is a
**provisioning-readiness** concern, not a DNS concern, and conflates two
responsibilities onto one hook. The correct pattern (see
`terraform-aws-actions-runner`: separate `registration` and `bootstrap` launching
hooks) is for the consumer to add its **own** bootstrap lifecycle hook that the
instance completes. update-dns must stay single-purpose: manage a DNS record and
complete its own hook. This flag is deliberately excluded; tetra-data will grow a
dedicated bootstrap hook instead (tracked separately).

## Backward compatibility

Non-warm-pool consumers are unaffected: their events never carry `Origin=WarmPool`
or `Destination=WarmPool`, so neither guard fires and behavior is byte-for-byte
identical. Verified field presence (above) means there is no fall-through risk.
No interface change (no new inputs/outputs), so this is a **minor** release.

## Testing

Unit tests (pytest) for `lambda_handler`, one per transition tuple from the table —
asserting DNS side-effects and that the hook is completed in every case:

- LAUNCHING `EC2->AutoScalingGroup` -> `add_records` called, hook CONTINUE
- LAUNCHING `WarmPool->AutoScalingGroup` -> `add_records` called, hook CONTINUE
- LAUNCHING `EC2->WarmPool` -> `add_records` NOT called, hook CONTINUE
- TERMINATING `AutoScalingGroup->EC2` -> `remove_record` called, hook CONTINUE
- TERMINATING `WarmPool->EC2` -> `remove_record` NOT called, hook CONTINUE (regression
  test for the crash/hang)
- Event with `Origin`/`Destination` absent -> behaves as today (add/remove) — guards
  the positive-match contract.

Integration: the existing pytest-infrahouse harness against a real ASG; if feasible,
add a warm-pool variant that exercises pool entry + activation + trim.

## Release

Standard release flow (`make release-minor`; git-cliff + bumpversion own CHANGELOG /
version — do not hand-edit). Ship as the next minor (e.g. 1.5.0).

## Rollout / downstream

Once released, the tetra-data fork can be retired: switch
`modules/tetra-data/update-dns.tf` `source` back to the registry at the new version,
delete the vendored `modules/tetra-data/modules/update-dns/`, and drop the
`FILTER_BY_DESTINATION` / `WARM_POOL_LAUNCH_AUTO_CONTINUE` wiring — moving readiness
to a dedicated bootstrap hook (tracked in the tetra-data issue).
