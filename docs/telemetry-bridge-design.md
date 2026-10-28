# Telemetry bridge design v0.2 (T12, Decision D2) - Bhavit - DRAFT for Krish/Prateek review

v0.1 (27-Oct) was based on reading CybORG source. v0.2 (27-Oct, later) replaces guesses with measurements: CAGE-4 (commit in `papers_to_download/cage-challenge-4-main.zip`) was run in an isolated venv with default agents (Blue = SleepAgent, Red = FiniteStateRedAgent, Green = EnterpriseGreenAgent), seeds 0, 1, 2, 500 steps each, and every Blue agent's native observation was dumped next to the Red/Green actions of that step. Reproduce: `scripts/dump_native_events.py` (CAGE venv) and `scripts/analyze_native_events.py` (main venv). Raw dumps are in `results/` (gitignored).

## 1. Problem
The Blue wrapper exposes only two booleans per host. Sigma-style rules need fields. The simulator does record richer events (Monitor), so the bridge is HYBRID: real native events + enrichment.

## 2. What CAGE-4 natively gives Blue (measured, 3 seeds, 1,500 steps)
Blue got events on 499 of 1,500 steps. Each host record has `Processes` (list), `Interface` (ip_address), `System info` (hostname, OS: Linux/Kali in the dumps, architecture). Four process-record shapes:
| Shape | Count | Fields | Comes from (matched to Red action on same host + step) |
|---|---|---|---|
| target-side connection | 1,482 | local_address, local_port (service port), remote_address (attacker), remote_port (ephemeral) | ExploitRemoteService 1,160; AggressiveServiceDiscovery 249; StealthServiceDiscovery 73; DegradeServices 2 |
| path-side connection | 553 | local_address, remote_address, remote_port (service port); NO local_port | ExploitRemoteService 354 (196 land on intermediate hosts that are not the target, so unmatched by host) |
| PID-only process | 132 | just `{"PID": n}` | ExploitRemoteService 116 (a successful exploit's session process) |
| local-only record | 167 | local_address, local_port only | Green false alerts (166 unmatched to any Red action) |
Ports in events (well-known): 22 (1,623), 80 (63), 25 (61). Port 4444 appears in NO event, even though the code builds a 4444 callback (`ExploitAction._create_new_session_event`): it is not surfaced to Blue. (v0.1 and two early static rules assumed it; now corrected.)

## 3. Which Red actions leave native events (answers Q1)
| Red action | Native Blue event? |
|---|---|
| ExploitRemoteService | YES: target-side + path-side connection events; PID-only record on success |
| AggressiveServiceDiscovery / StealthServiceDiscovery | YES: target-side connection events (Aggressive more than Stealth, as the README's 75% / 25% says) |
| DiscoverRemoteSystems | NO (zero matched events in 3 seeds) |
| PrivilegeEscalate | NO (zero) |
| Impact, DegradeServices, DiscoverDeception | NO meaningful events (1-2 coincidental matches in about 1,000 action-steps each = noise) |
Green: both Green actions run ~20k times per episode; only the ~1% false alerts become events. Blue SleepAgents never deployed decoys here, so decoy interaction events (README: "blue will be alerted") are NOT covered by this dump yet.
Limits: one Red strategy (FiniteStateRedAgent), Blue passive, attribution by host+step is approximate, Windows hosts/other exploit types may differ.

## 4. Design: two layers
**Layer A - native tap (real).** Per step, read the same events Monitor would deliver (native Observation; do not use the boolean wrapper): real IPs, service ports, ephemeral ports, host, subnet, PID.
**Layer B - enrichment (synthetic, seeded).** Add the Sigma-style fields the simulator lacks, deterministically from (seed, host, port, pid): `process_name`, `parent_process`, `privilege`, `service_name` (from port: 22 sshd, 80 http, 25 smtp), `protocol`, `is_decoy`, `zone`/`subnet` (from hostname).
**Synthetic events for actions that leave nothing natively** (needed because the paper's scope includes privilege escalation and impact, and Blue otherwise cannot see them at all):
- PrivilegeEscalate -> `process_creation`, privilege=elevated, parent_process=the daemon of the earlier exploit.
- Impact / DegradeServices -> `service_event` (stopped / degraded) on the host.
- DiscoverRemoteSystems -> no event (invisible recon, kept honest) or optional sweep event, decide with the team.
These are fully invented by the bridge and must be disclosed as such (limitation text for D2). Native-only vs enriched share of Red-caused events should be reported in the paper.
**Noise.** Native Green false alerts + optional seeded benign background events (`noise_level` in config).

## 5. Event schema (Interface Contract section 3; DRAFT until D2 closes)
Blue-visible: event_id, step, blue_agent, host_id, subnet, zone, category {process_creation, network_connection, service_event}, process_name, parent_process, privilege {user, elevated}, src_ip, dst_ip, dst_port, protocol, service_name, is_decoy.
Hidden (Blue never sees): label_red {0,1}, source_action, source_agent {red_k, green}, plus `provenance` {native, enriched, synthetic} (new; lets us report how much is real).
Mapping of native fields: target-side connection -> category=network_connection, src_ip=remote_address, dst_ip=local_address, dst_port=local_port. Path-side -> src_ip=remote_address, dst_ip=local_address, dst_port=remote_port (in both connection shapes local_address is the TARGET and remote_address the SOURCE; the path-side event is recorded on a router along the route, not on the target; v0.2 first said dst_ip=remote_address, which was wrong, corrected after reading ExploitAction). PID-only -> category=process_creation, privilege=user.

## 6. Ground truth (Q3 - proposal for Krish, not tested)
Labels must be assigned when the event is created, not guessed afterwards. Proposal: wrap `Action.execute` so a context variable holds (agent, action type) while it runs, and make the host event lists record that context when appended. Events appended during a Red agent's action get label_red=1, source_action=<type>; Green-created get 0. This needs light monkey-patching of CybORG (no source edits). Post-hoc host+step matching (used for the analysis above) is too approximate for labels (path-side events land on non-target hosts).

## 7. Concrete exploit identity (Q4)
Native events carry the service PORT, not the exploit name; the port identifies it well enough for `service_name` (22 -> SSH brute force, 80 -> HTTP exploit, 25 -> SMTP exploit). The exploit class name is not needed.

## 8. service_event (Q2)
No native source. Keep it, but only as synthetic events from Impact / DegradeServices (and optionally decoy hits), marked `provenance=synthetic`. If the team prefers a smaller claim, drop it and scope Blue to what is natively visible (Fallback 1 in Gates & Risks).

## 9. Decoy events (measured 27-Oct, 3 seeds, Blue = `DecoyBlueAgent` that deploys a decoy on every non-router host it can reach; `scripts/dump_native_events.py --blue decoy`)
- 113 `DeployDecoy` actions over 3 episodes. Exploit success rate stayed about the same (168 successes of 722 vs 161 of 725 with passive Blue), so these decoys did not visibly change Red's success here (Blue only decoys its own zones; not a tuned defence).
- The only NEW record shape is Blue's own confirmation of a deployment: `{"PID", "PPID", "service_name" (apache2/tomcat/haraka/vsftpd), "username", optionally "Properties"}`. 37 of 37 such records in seed 0 land on the step of that agent's `DeployDecoy`. It is NOT a Red interaction.
- Red interaction with a decoy produces the SAME event shapes as with a real service (target-side connection etc.). There is no native decoy flag.
- But Blue knows where its decoys are (from the confirmation + the decoy's fixed port: apache2 80, tomcat 443, haraka 25, vsftpd 80 per the CybORG decoy classes), and CAGE-4 forbids a decoy on a port already used by a real service. So `is_decoy` can be set by the bridge from Blue-side knowledge only (host, port) of Blue's own decoys. No ground truth leaks.
- Check: 153 target-side events landed on a decoy's own port; 95 of them coincide (same step) with a Red scan or exploit aimed at that host (AggressiveServiceDiscovery 42, StealthServiceDiscovery 41, ExploitRemoteService 12); the other 58 are unmatched (multi-tick actions make same-step matching approximate), so do not read 62% as precision. 760 events on decoyed hosts hit OTHER ports, so flagging the whole host would be wrong. Scans, not exploits, dominate decoy hits.
- Consequence for the schema: `is_decoy` stays a Blue-visible field, computed by (host, port) lookup; decoy-touch rules (static_01) become expressible.

## 9a. Implementation status of the native layer (T16, part 1; 28-Oct-2026)
`src/bridge/` implements Layer A and the enrichment of Layer B for the natively visible events only: `events.py` (`Event` with a strict `visible()` view of exactly the 16 Blue-visible fields and a `to_log()` view that adds the hidden ones) and `native_tap.py` (`TelemetryBridge(seed).step_events(step, {blue_agent: native observation})`). It does NOT produce synthetic events for PrivilegeEscalate / Impact / etc. (waits for the D2/D3 decision) and does NOT set `label_red` / `source_*` (the labeler, T21, owns those; they stay `None`). Not yet run inside a live environment: it reads the same dict that `env.get_observation(blue_agent)` returns, minus `success` and `action`.
- Checked on the recorded episodes (3 seeds each): passive Blue 2,334 native records produce 2,334 events; decoy-deploying Blue 2,549 records produce 2,436 events (the 113 decoy confirmations are not events); 0 unrecognised records; 153 events flagged `is_decoy`, the same number found separately by hand in section 9.
- Decoy rule learned while building it: the DeployDecoy confirmation carries the host name but NO IP, so decoys are keyed by (host, port); the IP-to-host map is learned from any record that has an Interface and is used to flag path-side events seen on routers. Blue's own deployment confirmation is not emitted as an event (otherwise Blue would alert on itself).
- Enriched fields are invented by a seeded hash (sha256, not Python's hash): `protocol` = tcp, `service_name` from a short well-known-port table (unknown ports get none), and for PID-only / Green-alert records `process_name`, `parent_process`, `privilege`. They are listed per event in `enriched_fields`; the paper should report how much of the stream this covers.
- Seeded benign background noise (`noise_level`) is not implemented yet.

## 10a. Gate G3 (design half)
Every in-scope Red action maps to events OR is explicitly "no observable event" with justification: done in sections 3-4 and 9. Still to do for the build half: a scripted-Red episode with hand-checked precision/recall.

## 10. Open questions for Krish / Prateek
1. Q3 labeler hook above: Krish, does the context-variable approach look right to you, and will your T21 labeler own it?
2. Are synthetic events for PrivilegeEscalate / Impact acceptable for the paper, or should the attack scope be reduced to the natively visible actions (Exploit + scans)? This is a Decision D2/D3 call for all three.
3. Prateek: bridge output goes into the JSONL log format; keep `provenance` and the hidden fields out of the Blue-visible view.
