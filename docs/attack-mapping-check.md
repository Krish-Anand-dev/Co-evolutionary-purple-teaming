# ATT&CK ID check for T13 (input from Bhavit) - 27-Oct-2026

Checked on attack.mitre.org (page fetched and read via a summarising tool, so IDs/names/tactics are as the site showed them on 27-Oct-2026; Krish should re-open the pages when writing the final table). Sources for the CAGE-4 side: README Appendix A in `cage-challenge-4-main`.

## CAGE-4 Red actions vs ATT&CK
| CAGE-4 action | ID the CAGE-4 README gives | ATT&CK page says | Verdict |
|---|---|---|---|
| DiscoverRemoteSystems | T1018 Remote System Discovery | T1018 Remote System Discovery, tactic Discovery (TA0007) | matches |
| AggressiveServiceDiscovery | T1046 "Network Service Scanning" | T1046 is named **Network Service Discovery**, tactic Discovery (TA0007) | ID matches; README uses the old name, use the current one |
| StealthServiceDiscovery | (same as above, quieter) | T1046 | matches by description |
| ExploitRemoteService | T1210 Exploitation of Remote Services | T1210 Exploitation of Remote Services, tactic **Lateral Movement** (TA0008) | matches; note its tactic is Lateral Movement, not Initial Access |
| PrivilegeEscalate | TA0004 (a tactic, not a technique) | TA0004 Privilege Escalation | matches; it is a tactic ID, so say "tactic TA0004" in the table (or pick a technique if you want one) |
| Impact | T1489 Service Stop | T1489 Service Stop, tactic Impact (TA0040) | matches |
| DegradeServices | none given | not mapped | open: T1499 Endpoint Denial of Service (Impact, TA0040) is a plausible candidate; NOT verified as the right fit, Krish to judge |
| DiscoverDeception, Withdraw | none given | not mapped | open: no obvious technique; I did not search further |

## The draft paper's old Table 2 (what must go)
- T1595 Active Scanning: real, tactic Reconnaissance (TA0043); but CAGE-4 has no such action, its scanning actions map to Discovery (T1018, T1046).
- T1070 Indicator Removal: real, but the site showed its tactic as **Stealth (TA0005)** (the draft said "Defense Evasion"; ATT&CK renamed that tactic, re-check when citing). CAGE-4 has no matching action (Withdraw only removes Red's presence from a host).
- T1110 Brute Force, T1021 Remote Services, T1543 Create/Modify System Process, "credential-based access", "Install": not checked against the site and not CAGE-4 Red actions, so they should be dropped as already decided in D3.

## Visibility note (for the attack-scope choice)
From the native-event dumps (see telemetry-bridge-design.md): Blue sees events only for ExploitRemoteService and the two service-discovery actions. PrivilegeEscalate, Impact, DegradeServices, DiscoverRemoteSystems and DiscoverDeception leave no native event. Any ATT&CK coverage figure (T37) for the invisible techniques would rest on synthetic events and has to say so.
