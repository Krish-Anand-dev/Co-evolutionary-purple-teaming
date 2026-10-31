# Ground-truth labeler (T21) - Krish

Code: `src/bridge/labeler.py`. Check script: `scripts/label_check.py`. Tests: `tests/test_labeler.py`.
Results: `results/summaries/labeler_check.json`, 50-event sample for checking by hand: `results/summaries/labeler_spotcheck.md`.
Answers Q3 in `telemetry-bridge-design.md` section 6 (Bhavit's proposal): yes, a context variable set around each action,
read when an event is created. This file is the implementation.

## Definition
`label_red = 1` iff the event record was created while a **Red** agent's action was executing. Events created under a Green
agent's action (false alerts, connection failures) or anything else are `0`. `source_action` = the outermost action class that
was running (e.g. `ExploitRemoteService`); `source_agent` = the Red agent's name, or `green` / `blue` / `unknown`.
These are the hidden fields of the event schema. They are never shown to Blue.

## Why not "match host and step afterwards"
A path-side event is recorded on a router along the route, not on the target, so the host does not say who caused it.
The label is therefore captured at creation. (The T12 analysis used host+step matching only as an approximation.)

## How it works (no CybORG file is edited)
`GroundTruthLabeler.install()` wraps three CybORG methods and `uninstall()` restores them (`with GroundTruthLabeler() as lb:` works):
1. `SimulationController.execute_action`: sets a context variable (agent, action class) while any action runs, and writes every
   Red action to `lb.action_log` (step, agent, action, target, success).
2. `HostEvents.__init__`: each host's two event lists remember, per item, the context it was appended under.
3. `Monitor.execute`: when Blue's Monitor consumes a host's events, their tags move to a ledger keyed by
   (Blue agent, host, record key).
`TelemetryBridge(seed, labeler=lb)` then calls `lb.label_event(...)` for each event it builds and claims the matching ledger entry.
Matching is by content (PID and connection fields), not by position, because `Observation.add_process` merges records that share
a PID and can reorder them. The labels live only in the labeler and in the hidden event fields; no observation CybORG gives an
agent is changed.

Use in the loop (T27/T28):
```python
lb = GroundTruthLabeler().install()          # BEFORE the environment is built
env = CybORG(sg, "sim", seed=seed); env.reset(); lb.reset()
bridge = TelemetryBridge(seed, labeler=lb)
# per step: env.step(); events = bridge.step_events(step, {blue: native_obs, ...})   # events now carry label_red
```
`lb.reset()` between episodes. `lb.action_log` is the independent record of what Red did, which is also what synthetic
PrivilegeEscalate / Impact events (if D2 chooses them) should be derived from and labelled by.

The only change to existing code is in `src/bridge/native_tap.py` (Bhavit's file): an optional `labeler=None` argument and a
3-line call in `step_events`. Without a labeler the events are identical (there is a test).

## Result: acceptance test "every event carries label_red"
`scripts/label_check.py`: 18 full 500-step episodes (Blue: passive, decoy-deploying, traffic-blocking; Red: CAGE-4's
`FiniteStateRedAgent` and `RandomSelectRedAgent`; tuning seeds 0, 1, 2).

| Measure | Value |
|---|---|
| Events | 35,817 |
| Labelled | 35,817 (**0 unlabelled**) |
| Red-caused / benign | 8,488 / 27,329 |
| Unclaimed ledger entries | 0 |
| Red events with no matching Red action in the independent action log | 0 |
| Target-side Red events whose destination equals that action's target | 8,009 of 8,009 |
| Benign events attributed to a Red agent | 0 |

By source: ExploitRemoteService 5,829, AggressiveServiceDiscovery 1,974, StealthServiceDiscovery 685 (all red);
GreenAccessService 26,074 and GreenLocalWork 1,255 (all benign). Red labels are consistent with the action log: same action
type, same agent, same step.

## Spot check of 50 events (`labeler_spotcheck.md`)
25 red and 25 benign events, spread over source actions (decoy Blue vs FSM Red, seed 0). I went through the table:
- Red rows 1-25 (scans, exploits, router path-side events, PID-only session events): each names a Red action of the same type by
  the same agent at the same step, and the destination IP equals that action's target. No discrepancy.
- Benign rows 26-50: all Green work (13 connection alerts, 12 local-work alerts). Honest limit: for benign rows the only evidence
  is the construction (the event was created under a Green action) plus the global check above that no benign event is attributed
  to a Red agent. There is no second source that independently says "this was Green". Krish should still eyeball the table.

## Findings the team should know
1. **Traffic blocking floods Blue with benign events.** Blue's `BlockTrafficZone` makes Green connections fail, and each failure is
   an event on the Green host (destination port 8800). With a Blue that blocks every 15 decisions there are about 3,400-4,700 benign
   events per episode, against 500-700 red events: 26,074 of the 27,329 benign events above are these. A Blue that blocks freely will
   see a huge false-positive pool, and noise-level settings (T16) need to account for it.
2. **Green connection events do not follow the Red shape.** For Green events `local_address` is the Green client, but the bridge
   assumes `local_address` is the target (true for Red events). So `src_ip`/`dst_ip` on those benign events look reversed or odd
   (for example ephemeral-looking destination ports). Labels are unaffected. Bhavit may want to special-case them.
3. **A Red that withdraws from its only host is stranded.** `RandomSelectRedAgent` on seed 2 played `Withdraw` as its first action
   and produced no events for the rest of the episode (labelled correctly: 0 red events, action log agrees). Same hazard as the
   `hit_and_run` bug fixed in T19.
4. Blue's own decoy-deployment confirmation is not a host event, so it never reaches the ledger or the bridge (0 unclaimed).

## Limits
- It depends on three CybORG internals (`execute_action`, `HostEvents`, `Monitor.execute`), checked against commit `8c3c50c`.
  A CAGE-4 update could break it; the live test would catch that.
- Tested with Red = CAGE-4's FSM and random Red only. The T19 scripted strategies and T20 LLM Red live on other branches and
  were not run through it, though they use the same action classes.
- Synthetic events (PrivilegeEscalate / Impact, pending D2) are not generated by the bridge yet, so there is nothing to label for
  them; `action_log` has what they would need.
- 3 seeds, tuning seeds only; test seeds 100-109 untouched.
- `uninstall()` restores the three methods; the patch is global to the process, so install it once per process.
