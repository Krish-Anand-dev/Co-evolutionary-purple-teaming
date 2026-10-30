# Kickoff call agenda (T01) - 45 minutes - DRAFT by Bhavit

Goal of the call: close the three decisions that block the build, agree who builds the adaptive Red, and fix how we work. Everything else is already in the sheet.

**Read first (10 min, before the call):** Decision Log (D1-D3), `docs/llm-speed-benchmark.md` (section "Proposal"), `docs/related-work.md` (sections 2-3), `docs/telemetry-bridge-design.md` (sections 3 and 9a).

## 0. Where we are (5 min, Bhavit)
- Done and merged: repo + setup (T02, T04, T05), contract v1 (T03, with the native/synthetic scope flag), cheat sheet (T06), rules + executor + Blue agent (T15, T17, T18), bridge native layer incl. a live-episode check (T16 part 1), speed benchmark (T09), related-work check.
- Not started: Red side (T07, T13, T19, T20, T21), runner and loop (T22, T24), baselines (T10, T23), CI (T26).
- D1 is decided: LLM once per round, llama-server, GLM-4.7-Flash for the reported runs (26.7 s/call), Qwen3-4B for development. Say so if you disagree.

## 1. D2 - what does Blue's rule match against? (10 min)
Fact: Blue natively sees only exploits and scans (3 seeds, 6 episodes). PrivilegeEscalate, Impact, DegradeServices, DiscoverRemoteSystems and DiscoverDeception leave nothing.
**Proposed:** A (bridge), native-first. The pilot uses native events only; synthetic PrivilegeEscalate / Impact events are a flagged, separate condition in the ablations, and every event carries `provenance` so the paper reports how much is real. Fallback: G3 option B (native flags only).

## 2. D3 - which attack scope? (5 min)
**Proposed:** A (discovery -> exploit -> privilege escalation -> impact) as the stated scope, with the results split into "natively visible part" and "synthetic part". B (decoy interplay) as a stretch; decoy hits are already flagged by the bridge. Krish confirms the ATT&CK table in T13; Bhavit checks the IDs.

## 3. The adaptive Red - the one thing the claim needs (10 min)
Fact: related work (Hemberg, Du) already co-evolves on CAGE-4 or runs red-vs-blue LLM loops. Our edge is rule-level co-evolution with measured dynamics and generalization, which needs a Red that adapts to Blue's rules.
**Proposed minimum:** T19 scripted variants (3 + 1 held out) as the sparring pool; Red picks the strategy that evaded the most rules last round; T20 LLM Red as the stretch. Blue keeps an archive of past Red strategies and is re-tested on all of them each round (tests for forgetting). Decide: who owns it (Krish), by when T07 lands (stubs unblock T19/T20/T28), and what counts as "adaptive enough".
Ambition check (optional, 3 min): do we also try the sim-to-real test (final rules exported to Sigma and run on a public attack-log dataset)? Decide after the pilot, not now.

## 4. Ownership and dates for the next two weeks (5 min)
| Person | Next | By |
|---|---|---|
| Krish | T07 stubs; T13 table; confirm the labeling hook (T21); run `benchmark_llamaserver.py` with the 4B model and post the CSV | 8 Nov |
| Prateek | T22 runner and T24 loop skeleton against the Blue mock in `src/agents/blue`; T10 (Hemberg code); T11 shortlist; set T14 / G2 | 15 Nov |
| Bhavit | D2/D3 write-up; Blue prompt tuning for the 4B dev model; bridge noise option; T12 close-out | 15 Nov |

## 5. How we work (5 min)
- PRs: author may merge docs-only PRs; code PRs get one review from someone on a different assistant (sheet rule 3). Say in the PR when it was merged without review.
- Lint: agree one `pyproject.toml` (line length 120?) in T26 before anyone reformats files (Black default would reformat about 34 files).
- Repo is currently public: make it private until we choose to publish?
- Weekly 30-min sync slot; chat for questions. Sheet updates: each person updates their own rows within a day of a PR merging.
- Compute: Bhavit's PC runs the reported runs (T34); B5 (env seconds per episode, assumed 60 s, T04 measured ~15 s) to be re-measured in the T32 pilot.

## Decisions to record in the Decision Log at the end
D2, D3, "what counts as adaptive Red", PR/merge convention, lint config, repo visibility, sync slot.
