# T13: Red attack scope and corrected ATT&CK mapping (Krish) - DRAFT for D3

Sources: CAGE-4 source at commit `8c3c50c` (`CybORG/Simulator/Actions/...`), the live action space of a running
scenario (seed 0, all Red agents), README Appendix A, and Bhavit's `attack-mapping-check.md`.
**What I did not do:** re-open attack.mitre.org. The ATT&CK IDs below are Bhavit's 27-Oct check
(read through a summarising tool) plus the README; re-open the pages before the final table goes in the paper.

## 1. What Red can really do (verified in a running environment)

The set of action classes in `get_action_space(red_agent_*)` is exactly these 10, the same for every Red agent:

`AggressiveServiceDiscovery, StealthServiceDiscovery, DiscoverRemoteSystems, ExploitRemoteService,
PrivilegeEscalate, Impact, DegradeServices, DiscoverDeception, Withdraw, Sleep`

Two corrections to wording used elsewhere in the plan (`00_PROJECT_CONTEXT.md`, README Appendix A):
- **`DiscoverNetworkServices` is not a Red action.** It is the parent class; Red only plays its two subclasses
  `AggressiveServiceDiscovery` and `StealthServiceDiscovery` (`AbstractActions/DiscoverNetworkServices.py`, lines 103 and 140).
- The README calls the exploit action "Exploit Network Services"; the class is **`ExploitRemoteService`**.

## 2. Per-action facts from the source

| Action | Ticks | Needs | What the code does | Blue-visible event? (Bhavit measured 3 seeds) |
|---|---|---|---|---|
| DiscoverRemoteSystems | 1 | session, subnet | ping sweep of a subnet (`Pingsweep`) | no |
| AggressiveServiceDiscovery | 1 | session, ip | port scan (`Portscan`), `detection_rate` 0.75 | yes |
| StealthServiceDiscovery | 3 | session, ip | same scan, `detection_rate` 0.25 | yes |
| ExploitRemoteService | 4 | session, ip | picks a concrete exploit by open ports; gives a **user** shell | yes (bare PID record) |
| PrivilegeEscalate | 2 | session, host | `JuicyPotato` on Windows, else `V4L2KernelExploit`; gives **root** | no |
| Impact | 2 | session, host | stops an OT service; needs a privileged shell on the host | no |
| DegradeServices | 2 | session, host | stops a random service on a host where Red has root; green work then fails more | no |
| DiscoverDeception | 2 | session, ip | probes for decoys; `detection_rate` 0.5 (README: 50% false negative, 10% false positive) | no |
| Withdraw | 1 | session, host, ip | removes all of this Red agent's sessions from a host | not measured |
| Sleep | 1 | none | nothing | not measured |

Concrete exploits `ExploitRemoteService` can pick (`AbstractActions/ExploitRemoteService.py`, lines 46-50): `HTTPRFI, HTTPSRFI,
SSHBruteForce, SQLInjection, HarakaRCE, FTPDirectoryTraversal`. `EternalBlue` and `BlueKeep` are in the list but the code
comment says they are never used in CC4.

Not Red actions: phishing (`PhishingEmail`) is something **Green** users do that can create a Red foothold, and Red always starts
with a session in the Contractor network. There is no credential theft, no lateral-movement action as such (moving on = discover +
exploit on another host), no persistence, no log tampering.

## 3. Proposed corrected ATT&CK table (replaces the draft's Table 2)

| CAGE-4 action | ATT&CK | Tactic | Confidence |
|---|---|---|---|
| DiscoverRemoteSystems | T1018 Remote System Discovery | Discovery | checked (Bhavit) |
| Aggressive / StealthServiceDiscovery | T1046 Network Service Discovery (README says "Scanning", old name) | Discovery | checked (Bhavit) |
| ExploitRemoteService | T1210 Exploitation of Remote Services | Lateral Movement (not Initial Access) | checked (Bhavit) |
| PrivilegeEscalate | tactic TA0004 Privilege Escalation (a tactic, not a technique) | Privilege Escalation | checked (Bhavit); technique optional |
| Impact | T1489 Service Stop | Impact | checked (Bhavit) |
| DegradeServices | T1489 Service Stop (the code stops a service, same as Impact). T1499 Endpoint Denial of Service (Impact) fits the intent: say "T1489; T1499 for intent" | Impact | checked (Bhavit, 31-Oct) |
| DiscoverDeception | no direct technique. T1497 Virtualization/Sandbox Evasion covers VM/sandbox checks only, not honeypot probing, so do not use it | - | checked (Bhavit, 31-Oct) |
| Withdraw | no direct technique. T1070 Indicator Removal (tactic now named Stealth, TA0005) is only a partial fit (it covers removing traces such as logs and files, not dropping sessions) | - | checked (Bhavit, 31-Oct) |
| Sleep | not an attack action; leave out of the table | - | - |

Rows to delete from the old Table 2: T1595 Active Scanning, T1070 Indicator Removal (no CAGE-4 counterpart), T1110, T1021, T1543,
"credential-based access", "Install".
One nuance for the team: the concrete exploit `SSHBruteForce` sits *inside* `ExploitRemoteService`, so brute force does exist in CAGE-4,
just not as its own Red action. If we want T1110 or T1190 in the paper we must say it maps to a concrete exploit, not to an action.
I have not checked those IDs.

## 4. Proposed wording for Decision D3 (needs a team decision)

> The attack scope is the ten action classes CAGE-4 gives its Red agents (listed above). The paper does not claim credential-based
> lateral movement, persistence or defence evasion. ATT&CK IDs are used as labels for what each action does; the mapping is approximate.
> Only three of the ten actions leave any event in Blue's native observation (ExploitRemoteService and the two service-discovery
> actions); coverage claims for the other actions rest on synthetic events (D2) and are reported as such.

## 5. Open items before T13 is done
1. Team decision on D3 (this scope vs narrowing it to the three Blue-visible actions). Linked to D2 / T12.
2. ~~Bhavit: re-open the ATT&CK pages~~ DONE 31-Oct (T1499, T1489, T1497, T1070 re-opened; pages read through a summarising fetch tool, so Krish should glance at the live pages once when finalising the table).
3. **Regenerate the paper PDF:** I only have the finished PDF, not its source (LaTeX/Word). Whoever built the draft has to apply
   the new Table 2 and the per-step-LLM / telemetry wording and regenerate it.
4. The single-line action list in `00_PROJECT_CONTEXT.md` (which includes `DiscoverNetworkServices`) should be corrected too.
