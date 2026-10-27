# CAGE-4 cheat sheet (T06) - Bhavit

Sources: `cage-challenge-4-main` README (Challenge Details, Rewards, Appendix A/B) and the CybORG code in that repo
(`Agents/Wrappers/*`, `Simulator/Actions/*`, `Shared/BlueRewardMachine.py`, `Evaluation/evaluation.py`).
Everything below was read from those files, not guessed. Items marked VERIFY need a real run (T04/T07).

## 1. What does Blue actually see?
- Through `BlueEnterpriseWrapper` (README Appendix B) each Blue agent gets ONE flat boolean/int vector:
  - index 0: mission phase (0 = Phase 1, 1 = Phase 2A, 2 = Phase 2B)
  - per subnet it defends: one-hot subnet (S=9), blocked subnets (S), "communication policy: should be blocked" (S),
    **malicious process event detected per host (H=16)**, **malicious network event detected per host (H=16)**
  - 4 x 8-bit messages from the other Blue agents (user defined, default 0)
- blue_agent_0..3 defend one subnet each; blue_agent_4 (HQ) defends three, so its vector is longer
  (`pad_spaces=True` zero-pads). Hosts are slotted servers 0-6 then users 0-10; absent hosts stay 0.
- So the wrapper view = booleans only: NO ports, IPs, process names, parents, privilege, timestamps.

### Important hidden fact (changes Decision D2)
The simulator DOES record richer events internally, and the wrapper throws them away:
- `Simulator/HostEvents.py`: every host has `events.network_connections` (list of `NetworkConnection`:
  local_address, local_port, remote_address, remote_port, pid, application_protocol, transport_protocol)
  and `events.process_creation` (dicts: `pid`, `Connections` [local/remote address+port], or just local address+port for false alerts).
- `Actions/AbstractActions/Monitor.py` runs automatically every step. It copies those events into the Blue observation
  (`obs.add_process(...)`, limited to "Network Connection events and Process Creation events"), then clears them.
  The `BlueFlatWrapper` collapses them into the two boolean-per-host vectors.
- Therefore the bridge does not have to be 100% invented: we can tap the native (unwrapped) Monitor observation or the
  `host.events` lists and keep real IPs/ports. Fields that do NOT exist natively and must be synthesised/enriched:
  process_name, parent_process, privilege, service_name (partly derivable from port), command line, timestamps.
  VERIFIED 27-Oct by dumping native observations for 3 seeds (`scripts/dump_native_events.py`): the native event fields are local/remote IP, local/remote port, PID, host IP, hostname/OS; see telemetry-bridge-design.md.

## 2. What can Blue do? (README Appendix A, Blue rows)
| Action | Ticks | Notes |
|---|---|---|
| Monitor | 1 | automatic every step; no effect if called |
| Analyse(host) | 2 | more info on files tied to recent alerts |
| DeployDecoy(host) | 2 | decoy service; any access = unambiguous Red signal; Red exploit on decoy always fails |
| Remove(host) | 3 | kills processes flagged malicious |
| Restore(host) | 5 | back to known good; costs availability |
| BlockTraffic(from,to subnet) | 1 | green traffic blocked -> penalties |
| AllowTraffic(from,to subnet) | 1 | undo block |
| Sleep | 1 | no-op |
Actions have durations: an agent only gets a new decision when its current action finishes. Action indices are fixed per agent
by `BlueFixedActionWrapper` (host not present this episode -> index becomes Sleep; `info["action_mask"]` says which are real).

## 3. Red actions (needed for D3 / T13 - verify classes in `Simulator/Actions/AbstractActions`)
DiscoverRemoteSystems (T1018, 1t), AggressiveServiceDiscovery (T1046, 1t, 75% flagged), StealthServiceDiscovery (3t, 25% flagged),
DiscoverNetworkServices, ExploitRemoteService (T1210, 4t; concrete exploits in `ConcreteActions/ExploitActions`: EternalBlue, BlueKeep,
HTTP(S)RFI, SQLInjection, SSHBruteForce, HarakaRCE, FTPDirectoryTraversal, RemoteCodeExecutionOnSMTP),
PrivilegeEscalate (TA0004, 2t; JuicyPotato, V4L2KernelExploit), Impact (T1489, 2t), DegradeServices (2t, needs root),
DiscoverDeception (2t, 50% false negative / 10% false positive), Withdraw (1t), Sleep.
Exploit success logs a process-creation event with prob `detection_rate` (0.95 default in `ExploitAction`).
MEASURED (3 seeds, see telemetry-bridge-design.md sec. 2-3): the exploit's port-4444 callback in the code never reaches Blue's observation; a successful exploit appears only as a bare `{"PID": n}` process record. PrivilegeEscalate, DiscoverRemoteSystems, Impact, DegradeServices and DiscoverDeception leave no (meaningful) native Blue event.

## 4. How is reward computed?
`Shared/BlueRewardMachine.py`. Only two things generate reward, summed across agents and the same for all Blue agents (shared team reward - VERIFY the wrapper averaging):
- green action FAILS: GreenLocalWork fail ("LWF") or GreenAccessService fail ("ASF")
- Red `Impact` succeeds ("RIA")
Values depend on subnet and mission phase (README Tables 4A-4C; e.g. Operational Zone A in Phase 2A: LWF -10, RIA -10; Contractor Network RIA -5 in Phase 1).
All values are negative penalties; Blue starts at 0 and tries to lose as little as possible. There is NO reward term for detection, alerts or rules.
=> Our precision/recall/FPR/RuleValidity must come from OUR layer (needs ground-truth labels, T21).
Evaluation (`Evaluation/evaluation.py`): 100 episodes x 500 steps, Blue vs `FiniteStateRedAgent`, reports mean reward per episode (mean over agents' rewards, summed over steps), seeds via `CybORG(sg, "sim", seed=...)`.

## 5. How do we plug in our own Red / Blue?
- Scenario: `EnterpriseScenarioGenerator(blue_agent_class=..., green_agent_class=EnterpriseGreenAgent, red_agent_class=FiniteStateRedAgent, steps=500)`.
  `red_agent_class` takes a class; the generator instantiates it per red agent as `cls(name, np_random=...)` (FSM variants also get `agent_subnets`).
  A custom RedAgent must therefore be a `BaseAgent` subclass with that constructor signature (`_generate_red_agents`, line ~806). Krish's T07 confirms.
- Blue: submission pattern in `Evaluation/example_submission/submission.py`: `AGENTS = {blue_agent_0..4: YourAgent()}`, `wrap(env) -> EnterpriseMAE(env)`;
  each agent implements `get_action(observation, action_space)`.
- Red-side agents already in `Agents/SimpleAgents`: FiniteStateRedAgent, FSMRedVariants, RandomSelectRedAgent (starting points for T19).
- Green agents (EnterpriseGreenAgent) create benign noise: false network alerts (~1% via `fp_detection_rate`) and false process alerts
  (local address+port only) and can introduce Red via phishing. This is our natural "benign" event source for FPR.

## 6. Consequences for our project
1. Telemetry bridge can be hybrid: real native events (ports, IPs, pid) + enrichment for missing fields. Better for realism claims than fully synthetic.
2. Native events carry no label of who caused them; ground truth (label_red) must be added by us: events created inside Red action `execute()` vs Green actions.
3. Blue's CAGE reward ignores detection quality, so our own rewards (Eq. 2) are separate and must be logged separately.
4. Time/ticks: a "step" is not one action for every agent; define the event `step` as the env tick.
