# Labeler spot-check sample (50 events)

CAGE-4 decoy-deploying Blue vs FiniteStateRedAgent, seed 0. 25 red-labelled and 25 benign events, spread over source actions.

| # | step | host | category | src -> dst:port | label | source action | source agent | Red actions at this step on this agent / target |
|---|---|---|---|---|---|---|---|---|
| 1 | 129 | restricted_zone_b_subnet_server_host_1 | network_connection | 10.0.234.72 -> 10.0.234.253:22 | 1 | AggressiveServiceDiscovery | red_agent_3 | AggressiveServiceDiscovery->10.0.234.253; RedSessionCheck->None |
| 2 | 328 | operational_zone_b_subnet_server_host_0 | network_connection | 10.0.234.254 -> 10.0.68.254:22 | 1 | ExploitRemoteService | red_agent_3 | ExploitRemoteService->10.0.68.254; RedSessionCheck->None |
| 3 | 83 | operational_zone_a_subnet_server_host_0 | network_connection | 10.0.157.206 -> 10.0.157.254:80 | 1 | StealthServiceDiscovery | red_agent_2 | StealthServiceDiscovery->10.0.157.254; RedSessionCheck->None |
| 4 | 7 | operational_zone_b_subnet_user_host_0 | network_connection | 10.0.68.195 -> 10.0.68.253:22 | 1 | AggressiveServiceDiscovery | red_agent_4 | AggressiveServiceDiscovery->10.0.68.253; RedSessionCheck->None |
| 5 | 81 | public_access_zone_subnet_router | network_connection | 10.0.43.196 -> 10.0.97.99:22 | 1 | ExploitRemoteService | red_agent_5 | ExploitRemoteService->10.0.97.99; RedSessionCheck->None |
| 6 | 116 | restricted_zone_b_subnet_server_host_4 | network_connection | 10.0.234.72 -> 10.0.234.250:22 | 1 | StealthServiceDiscovery | red_agent_3 | StealthServiceDiscovery->10.0.234.250; RedSessionCheck->None |
| 7 | 188 | admin_network_subnet_user_host_4 | network_connection | 10.0.97.193 -> 10.0.184.166:3390 | 1 | AggressiveServiceDiscovery | red_agent_5 | AggressiveServiceDiscovery->10.0.184.166; RedSessionCheck->None |
| 8 | 142 | restricted_zone_b_subnet_server_host_0 | network_connection | 10.0.68.143 -> 10.0.234.254:22 | 1 | ExploitRemoteService | red_agent_4 | ExploitRemoteService->10.0.234.254; RedSessionCheck->None |
| 9 | 76 | operational_zone_a_subnet_user_host_1 | network_connection | 10.0.157.206 -> 10.0.157.83:3390 | 1 | StealthServiceDiscovery | red_agent_2 | StealthServiceDiscovery->10.0.157.83; RedSessionCheck->None |
| 10 | 188 | admin_network_subnet_user_host_4 | network_connection | 10.0.97.193 -> 10.0.184.166:22 | 1 | AggressiveServiceDiscovery | red_agent_5 | AggressiveServiceDiscovery->10.0.184.166; RedSessionCheck->None |
| 11 | 119 | operational_zone_a_subnet_user_host_2 | network_connection | 10.0.157.206 -> 10.0.157.85:22 | 1 | ExploitRemoteService | red_agent_2 | ExploitRemoteService->10.0.157.85; RedSessionCheck->None |
| 12 | 135 | public_access_zone_subnet_server_host_2 | network_connection | 10.0.43.94 -> 10.0.97.252:443 | 1 | StealthServiceDiscovery | red_agent_5 | StealthServiceDiscovery->10.0.97.252; RedSessionCheck->None |
| 13 | 31 | restricted_zone_a_subnet_user_host_3 | network_connection | 10.0.244.201 -> 10.0.244.9:22 | 1 | AggressiveServiceDiscovery | red_agent_1 | AggressiveServiceDiscovery->10.0.244.9; RedSessionCheck->None |
| 14 | 174 | operational_zone_b_subnet_server_host_1 | process_creation | None -> None:None | 1 | ExploitRemoteService | red_agent_4 | ExploitRemoteService->10.0.68.252; RedSessionCheck->None |
| 15 | 37 | operational_zone_b_subnet_server_host_2 | network_connection | 10.0.68.195 -> 10.0.68.251:1 | 1 | StealthServiceDiscovery | red_agent_4 | StealthServiceDiscovery->10.0.68.251; RedSessionCheck->None |
| 16 | 64 | public_access_zone_subnet_server_host_0 | network_connection | 10.0.97.99 -> 10.0.97.254:80 | 1 | AggressiveServiceDiscovery | red_agent_5 | AggressiveServiceDiscovery->10.0.97.254; RedSessionCheck->None |
| 17 | 46 | restricted_zone_a_subnet_user_host_7 | process_creation | None -> None:None | 1 | ExploitRemoteService | red_agent_1 | ExploitRemoteService->10.0.244.91; RedSessionCheck->None |
| 18 | 32 | operational_zone_b_subnet_user_host_1 | network_connection | 10.0.68.195 -> 10.0.68.213:443 | 1 | StealthServiceDiscovery | red_agent_4 | StealthServiceDiscovery->10.0.68.213; RedSessionCheck->None |
| 19 | 53 | office_network_subnet_user_host_8 | network_connection | 10.0.97.99 -> 10.0.43.94:80 | 1 | AggressiveServiceDiscovery | red_agent_5 | AggressiveServiceDiscovery->10.0.43.94; RedSessionCheck->None |
| 20 | 181 | restricted_zone_b_subnet_router | network_connection | 10.0.234.72 -> 10.0.234.254:22 | 1 | ExploitRemoteService | red_agent_3 | ExploitRemoteService->10.0.234.254; RedSessionCheck->None |
| 21 | 278 | admin_network_subnet_user_host_2 | network_connection | 10.0.97.99 -> 10.0.184.138:80 | 1 | StealthServiceDiscovery | red_agent_5 | StealthServiceDiscovery->10.0.184.138; RedSessionCheck->None |
| 22 | 16 | office_network_subnet_user_host_5 | network_connection | 10.0.43.196 -> 10.0.43.202:25 | 1 | AggressiveServiceDiscovery | red_agent_5 | AggressiveServiceDiscovery->10.0.43.202; RedSessionCheck->None |
| 23 | 94 | operational_zone_b_subnet_server_host_0 | process_creation | None -> None:None | 1 | ExploitRemoteService | red_agent_4 | ExploitRemoteService->10.0.68.254; RedSessionCheck->None |
| 24 | 37 | operational_zone_b_subnet_server_host_2 | network_connection | 10.0.68.195 -> 10.0.68.251:22 | 1 | StealthServiceDiscovery | red_agent_4 | StealthServiceDiscovery->10.0.68.251; RedSessionCheck->None |
| 25 | 9 | operational_zone_b_subnet_user_host_6 | network_connection | 10.0.68.195 -> 10.0.68.210:3390 | 1 | AggressiveServiceDiscovery | red_agent_4 | AggressiveServiceDiscovery->10.0.68.210; RedSessionCheck->None |
| 26 | 289 | public_access_zone_subnet_server_host_0 | network_connection | 10.0.97.254 -> 10.0.234.160:50431 | 0 | GreenAccessService | green | - |
| 27 | 234 | public_access_zone_subnet_user_host_6 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 28 | 90 | operational_zone_a_subnet_server_host_0 | network_connection | 10.0.157.254 -> 10.0.157.54:58316 | 0 | GreenAccessService | green | - |
| 29 | 190 | operational_zone_b_subnet_user_host_7 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 30 | 411 | restricted_zone_b_subnet_server_host_4 | network_connection | 10.0.234.250 -> 10.0.43.39:55630 | 0 | GreenAccessService | green | - |
| 31 | 183 | restricted_zone_a_subnet_user_host_7 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 32 | 160 | restricted_zone_a_subnet_server_host_0 | network_connection | 10.0.244.253 -> 10.0.157.83:50701 | 0 | GreenAccessService | green | - |
| 33 | 265 | office_network_subnet_user_host_1 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 34 | 211 | restricted_zone_b_subnet_server_host_2 | network_connection | 10.0.234.252 -> 10.0.234.87:51432 | 0 | GreenAccessService | green | - |
| 35 | 235 | restricted_zone_b_subnet_user_host_0 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 36 | 441 | public_access_zone_subnet_server_host_4 | network_connection | 10.0.97.250 -> 10.0.234.87:59888 | 0 | GreenAccessService | green | - |
| 37 | 264 | public_access_zone_subnet_user_host_5 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 38 | 123 | restricted_zone_a_subnet_server_host_0 | network_connection | 10.0.244.253 -> 10.0.184.9:51979 | 0 | GreenAccessService | green | - |
| 39 | 57 | operational_zone_b_subnet_user_host_2 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 40 | 405 | restricted_zone_b_subnet_server_host_5 | network_connection | 10.0.234.249 -> 10.0.43.229:58949 | 0 | GreenAccessService | green | - |
| 41 | 339 | public_access_zone_subnet_user_host_1 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 42 | 498 | operational_zone_b_subnet_server_host_0 | network_connection | 10.0.68.254 -> 10.0.68.132:57683 | 0 | GreenAccessService | green | - |
| 43 | 0 | admin_network_subnet_user_host_1 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 44 | 45 | operational_zone_b_subnet_server_host_0 | network_connection | 10.0.68.254 -> 10.0.68.101:49428 | 0 | GreenAccessService | green | - |
| 45 | 496 | admin_network_subnet_user_host_0 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 46 | 459 | restricted_zone_a_subnet_server_host_0 | network_connection | 10.0.244.253 -> 10.0.43.180:49922 | 0 | GreenAccessService | green | - |
| 47 | 231 | operational_zone_b_subnet_user_host_2 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 48 | 341 | admin_network_subnet_server_host_1 | network_connection | 10.0.184.253 -> 10.0.244.205:58055 | 0 | GreenAccessService | green | - |
| 49 | 451 | office_network_subnet_user_host_1 | process_creation | None -> None:None | 0 | GreenLocalWork | green | - |
| 50 | 316 | operational_zone_a_subnet_server_host_1 | network_connection | 10.0.157.253 -> 10.0.157.83:50825 | 0 | GreenAccessService | green | - |
