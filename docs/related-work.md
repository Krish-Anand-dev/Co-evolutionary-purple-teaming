# Related work check v1.0 (28-Oct-2026) - Bhavit

All 15 PDFs in `papers_to_download/` were converted to text and read (abstract, introduction and related work for each; method, baselines, results or limitations where it mattered: Hemberg, Du, ThreatPilot, CTI-REALM, RulePilot). This is still NOT a systematic review: it covers the papers in the folder plus a few web searches. Still to do: a "cited by" pass on Hemberg and Du (see section 4).

## 1. What exists

| Group | Paper | What it does | Why it is not our paper |
|---|---|---|---|
| Rule generation from threat reports | RulePilot, arXiv 2511.12224 (ICSE '26) | Analyst's natural-language description -> LLM agent with an intermediate representation and reflection -> Splunk SPL / Sentinel KQL rules, plus SPL<->KQL conversion. Scored by text similarity and execution on a live Splunk. | No attacker, no loop over time; input is a description. Says Sigma generation was explored before and targets the harder SIEM-specific case. |
| | AUTOSIGMA, arXiv 2608.19011 | CTI report -> enrichment from a knowledge base -> retrieval of similar existing Sigma rules as templates -> LLM-as-judge loop. Evaluated on APT41/28/29 reports and security blogs for validity, relevance, ATT&CK coverage. | Static; the judge is another LLM, not an attacker. |
| | LLMCloudHunter, arXiv 2407.05194 | Cloud CTI (text and images) -> Sigma candidates; 99.18% compile and convert to Splunk. | Static, report in, rule out. |
| | ThreatPilot, arXiv 2412.10872 | CTI -> attack-driven intelligence (tactics, techniques, procedures, variants) -> Sigma rules and attack commands, with syntax checks and Splunk feedback. Rules evaluated on 229,968 logs from 61 atomic tests spanning 12 tactics, plus honeypot logs (64,185). | The attacks are fixed atomic tests used for evaluation; the attacker never adapts to the rules and rules are not revised against it. |
| Benchmark for detection engineering | CTI-REALM, arXiv 2603.13517 (Microsoft) | Agent reads CTI, explores real telemetry from emulated attacks (Linux, cloud, AKS), runs KQL queries, outputs Sigma + KQL; ground truth plus trajectory rewards; 16 frontier models, best reward 0.637; a memory-augmentation study closes 33% of the small-vs-large model gap. | Closest on "grounded benchmark with ground truth", but one-shot per task, fixed attacks, frontier models, real Azure telemetry; no adversarial adaptation. Useful as a metric reference and as evidence that small models lag. |
| LLM defender on CAGE-4 | "LLMs are Autonomous Cyber Defenders", arXiv 2505.04843 | LLM blue agents (and LLM + RL) on CAGE-4: natural-language observations, JSON actions, 8-bit communication. | Chooses actions, no rules; Red is the stock scripted Red. |
| Co-evolution on CAGE-4 | Hemberg et al. (MIT), arXiv 2507.05534 | Extends CAGE-4 so Red can be trained too. Evolves red and blue team controllers (finite-state action matrices and grammar-based code-like controllers) with GA / ES / grammatical evolution, one variant with an LLM-supported mutation operator (GPT-3.5 and Phi-4 timings). Result: co-evolved teams reach lower rewards than teams trained against a fixed adversary; co-evolution dampens highs and lows and induces fluctuations; grammar representation has the highest fitness; the LLM operator is very sensitive to model and prompt. Future work: out-of-sample performance and transfer. | **Closest to our dynamics claim.** The evolved artifact is a controller (which action on which host), not a detection rule; the LLM is only a mutation operator. They name out-of-sample generalization as future work, which is our generalization angle. |
| LLM red-vs-blue loop | Du, J. Cyber Security 2026 (TSP_JCS_75976) | Red and Blue LLM agents iterate on a 3-host testbed plus a larger emulation with SIEM / IDS nodes. Blue picks from a fixed action menu; learning is mainly prompt augmentation (the text also mentions adding signatures to the detection rules). Baselines: scripted attacker with static detection rules, LLM agents without learning, LLM agents with learning. Attack success 72% -> 5% over six iterations. | Blue does not write executable rules; hand-built small testbed; admits the baselines are simple, learning may overfit repeated scenarios, and generalization to new attackers is not tested. Some inconsistencies in the numbers. |
| LLM red teaming on CAGE-4 | Shaikh et al., arXiv 2605.17075 | Hierarchical LLM planner + RL controller as Red against the H-MARL Expert Blue defenders; standalone LLM Red agents (0.6B-70B) fail to sustain multi-stage campaigns. | Red side only. Candidate source for an adaptive Red on CAGE-4. |
| Out of scope (LLM or code safety) | ACEA 2609.08256; AutoPT (PRDC 2025); PAD 2407.01850; BlueCodeAgent 2510.18131; Co-RedTeam 2602.02164 | Red/blue loops, arenas and agents that attack or protect an LLM or a code generator (prompt injection, jailbreaks, guardrails, vulnerability discovery). | Different target. Only transferable ideas: ACEA scores attack strength even when blocked; BlueCodeAgent distils red-team findings into reusable rules ("constitutions") and uses execution to cut false positives. |

## 2. What we did not find
An adaptive attacker plus an LLM whose output is an executable, validated, human-readable detection rule (Sigma-style) that is revised round after round, in a simulated enterprise network with hidden ground-truth labels, with measured dynamics (convergence, cycling, forgetting of old attacks) and generalization to unseen attack variants.

## 3. Consequences for the paper
- Do not lead with "LLMs can write rules" (RulePilot, AUTOSIGMA, ThreatPilot, LLMCloudHunter, CTI-REALM) or with "an adversarial loop improves an LLM defender" (Du).
- Position against Hemberg for dynamics. Their finding (co-evolved teams do worse than teams trained against a fixed opponent, with fluctuations) is a hypothesis we can test with rules: does rule-level co-evolution beat Blue refining against a fixed attacker? Either answer is publishable. Their stated future work (out-of-sample performance) is a gap we fill by design (tuning seeds 0-9, test seeds 100-109, held-out attacker strategies).
- "Beats static rules" is a baseline row, not the contribution (Du already shows that in spirit; CTI-REALM and ThreatPilot compare against rule sets).
- Position against CTI-REALM and ThreatPilot on evaluation: they use fixed attack emulations; we use an adaptive Red and hidden-label scoring in an interactive environment.
- An adaptive Red is required. Options from the literature: Shaikh's LLM+RL Red, Hemberg's evolved Red, or a scripted pool of Red strategies (what FiniteStateRedAgent variants give us). Needs a team decision (links to D3).
- Report the real vs invented telemetry share (bridge provenance) as a limitation; CTI-REALM and ThreatPilot use real emulation logs and will be the comparison.
- Small local models: CTI-REALM reports a gap between small and large models and a memory-augmentation trick that closes a third of it; our MoE-on-6GB-GPU result is a practical angle, and "memory" maps onto our feedback to Blue each round.

## 4. Still to do
1. Complete a "cited by" search on Hemberg and Du for follow-ups, and on Sigma + evolutionary / genetic methods.
2. Check the CAGE-4 LLM defender paper's follow-ups and any CAGE-5 work.
3. Decide, as a team, whether Hemberg's controller co-evolution is a baseline to reproduce or only related work.

### Initial follow-up search notes (28-Oct-2026)
- Hemberg et al. (2025): no indexed citing follow-up was identified in the initial search. Recheck Google Scholar, Semantic Scholar and OpenAlex before treating this as complete.
- Du (TSP_JCS_75976): publication identity and cited-by results still need verification against the exact paper record.
- Castro et al. (2025), "Large Language Models are Autonomous Cyber Defenders": no clearly verified follow-up identified in the initial search.
- CAGE-5: no authoritative CAGE-5 release or benchmark record verified in the initial search.
- Adjacent evolutionary IDS work includes SIGMA (2019), which evolves adversarial examples for IDS retraining, and EvoSIEM (2025), which generates evasive command variants against SIEM rules. Neither should be described as direct evidence of evolutionary Sigma-rule generation without checking the full methods.
