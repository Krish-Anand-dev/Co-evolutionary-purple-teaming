# Interface Contract v1



**Status:** Interface contract for team review

**Scope:** Shared interfaces for parallel development

**Important:** The event schema remains DRAFT until Decision D2 is resolved.



## 1. Repository Layout



- `src/agents/blue/`: Blue agent and LLM integration.

- `src/agents/red/`: Red agent implementation.

- `src/agents/baselines/`: Baseline agents and mocks.

- `src/rules/`: Rule schema, validation, execution, loading and response playbook.

- `src/bridge/`: Telemetry bridge and ground-truth labeling.

- `src/loop/`: Co-evolution loop, reward functions and checkpoints.

- `src/eval/`: Evaluation metrics, confidence intervals and plots.

- `configs/`: Experiment configuration files.

- `docs/`: Design and interface documentation.

- `scripts/`: Utility and analysis scripts.

- `tests/`: Automated tests.

- `results/`: Experiment outputs; raw logs should not be committed unless explicitly required.



## 2. Rule Interface



A rule contains:



- `rule_id`: Unique rule identifier.

- `round`: Co-evolution round number.

- `agent_id`: Blue agent identifier, such as `blue_0` through `blue_4`.

- `title`: Human-readable rule title.

- `level`: `low`, `medium` or `high`.

- `logsource.category`: Event category to which the rule applies.

- `detection.selection`: Mapping of named selections, each defining event fields and their values, lists or supported patterns.

- `detection.condition`: Boolean expression over named selections.

- `confidence`: Numeric value between 0 and 1.

- `rationale`: Short explanation, approximately 300 characters maximum.



The validator must reject malformed rules, unsupported event fields, hidden fields and invalid conditions. The executor must only evaluate validated rules.



The initial condition grammar supports named selections with `AND`, `OR` and `NOT`. Parentheses may be supported by the current validator and should be retained if confirmed by the implementation.



## 3. Event Interface - DRAFT



### Blue-visible fields



`event_id`, `step`, `blue_agent`, `host_id`, `subnet`, `zone`, `category`, `process_name`, `parent_process`, `privilege`, `src_ip`, `dst_ip`, `dst_port`, `protocol`, `service_name`, `is_decoy`.



Allowed categories:



- `process_creation`

- `network_connection`

- `service_event`



Allowed privilege values:



- `user`

- `elevated`



### Hidden ground-truth fields



- `label_red`: Binary ground-truth label.

- `source_action`: Originating action.

- `source_agent`: Source agent, such as `red_k` or `green`.



**Security boundary:** Hidden ground-truth fields must never be exposed to the Blue agent.



### Bridge requirements



The bridge converts native CAGE-4 observations into the agreed event representation. Any enriched or synthetic events must be documented, seeded deterministically where applicable, and reported transparently in experiments.



CAGE-4 exposes limited telemetry, so the paper must disclose when events are derived or synthetic rather than native observations.



**Decision D2 is required before this event schema can be declared final.** The team must also confirm the synthetic-event scope and ground-truth labeling approach.



## 4. Agent APIs



### BlueAgent



- `reset(seed)`: Reset agent state for a reproducible run.

- `observe(events, step)`: Receive Blue-visible events.

- `act(step)`: Return legal CAGE-4 Blue action or actions through the response playbook.

- `propose_rules(round_ctx)`: Return a list of proposed rules at a round boundary.

- `update(trajectories)`: Update agent state using collected trajectories.



### RedAgent



- `reset(seed)`: Reset agent state.

- `act(obs)`: Return a legal CAGE-4 Red action.

- `plan(round_ctx)`: Return round-level planning information for Mode B.

- `update(trajectories)`: Update agent state using collected trajectories.



Exact argument and return types must be aligned with the implemented CAGE-4 adapter before integration.



### LLMClient



`generate(prompt, schema=None) -> (text, meta)`



All LLM calls must go through the shared client abstraction. Metadata should record the model name and version, temperature, seed, latency in seconds and token usage when available.



## 5. Logging Contract



JSONL logs use one JSON object per line.



### Step-level records



Required fields:



`run_id`, `condition`, `seed`, `round`, `phase`, `episode`, `step`, `agent`, `action`, `reward_components`, `alerts`, `active_rules`, `tp`, `fp`, `fn`, `llm_calls`, `llm_latency_s`.



Allowed phases: `red`, `blue`, `eval`.



### Round-level records



Required fields:



`run_id`, `condition`, `seed`, `round`, `rules_emitted`, `rules_valid`, `rule_validity`, `precision`, `recall`, `fpr`, `red_success`, `time_to_detect`.



The team should agree on the exact field types and null-value conventions before integration.



## 6. Experiment Configuration



Configuration files use YAML and should support:



- `condition`

- `seed`

- `rounds`

- `episodes_per_round`

- `steps`

- `llm_model`

- `temperature`

- `noise_level`

- Reward weights: `alpha1`, `alpha2`, `beta1`, `beta2`, `beta3`, `beta4`

- Playbook parameters

- `tuning_seeds`

- `test_seeds`



Default seed split:



- Tuning seeds: `0–9`

- Test seeds: `100–109`



Test seeds must never be used for tuning. All random sources must be seeded from the experiment configuration.



## 7. Engineering Conventions



- Use Python type hints.

- Format code with Black and lint with Ruff.

- Add pytest coverage for each module.

- Use logging rather than `print` in project code.

- Record durations in seconds.

- Branch naming convention: `feat/T##-short-name`.

- Pull requests require at least one review from another team member.



## 8. Mock-First Integration



Modules should be testable with mock agents and mock events before full integration. The mock agents `random_blue` and `random_red` are planned under the agent packages.



Full integration is planned for T27–T29.



## 9. Open Decisions Before Final Freeze



1. Confirm Decision D2 and the final status of the event schema.

2. Confirm whether synthetic events for privilege escalation and impact actions are within scope.

3. Confirm the ground-truth labeling hook with the relevant owners.

4. Verify exact agent API types against the CAGE-4 adapter.

5. Resolve all review comments before marking T03 complete.



## 10. Acceptance Criteria



T03 is complete when:



- All contract review comments are resolved.

- This document is reviewed and aligned with the agreed interfaces.

- `docs/contract-v1.md` is committed to the correct GitHub repository.

- The agreed contract version is tagged in Git.

- Any unresolved event-schema decisions remain explicitly documented rather than being treated as approved.
