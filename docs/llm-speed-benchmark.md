# LLM speed benchmark on llama-server (T09) - Bhavit, 30-Oct-2026

Seconds per call for the REAL Blue rule-writing prompt, on the machine that will run the experiments. This is the number the compute sheet needs (`Experiments & Compute`, cell B4, currently an assumption of 2 s) and the input to Decision D1 / gate G2 (T14).

## How it was measured
- Script: `scripts/benchmark_llamaserver.py` (new). It calls a running llama.cpp `llama-server` with the exact prompt the Blue agent sends (`build_prompt`, nested layout + limits hint, nested JSON schema, 5 rules requested, `max_tokens` 1000, thinking disabled, temperature 0.2). Each call is timed end to end. One CSV row per call: latency, prompt/output tokens, tokens per second, finish reason, whether it was cut off at the token cap, whether the answer parses as JSON, rules found, rules valid.
- This is the llama-server counterpart of Prateek's `scripts/benchmark_ollama.py` (T08): same idea and CSV shape, but it targets the server we actually use and our real prompt. His script is unchanged. His defaults would not work for us: `--num-predict 250` cuts off every answer (ours are 580-760 tokens), and his prompt is a generic SOC task, not our rule schema.
- Machine: Bhavit's laptop, RTX 4050 6 GB, 15.7 GB RAM, llama.cpp b11756 CUDA 13.4, `--ctx-size 8192 --fit on --fit-target 768 --flash-attn on --threads 16 --jinja`, one model at a time, 1 warm-up call then 10 measured calls per model (seeds 1-10).
- Raw rows: `results/summaries/bench_llamaserver_t09.csv` (30 rows).

## Results (median over 10 calls)
| Model | Quant | Size | sec/call | tokens/s | tokens in / out | Valid rules | Cut off | Parses as JSON |
|---|---|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 (dense, 4B) | Q4_K_M | 2.5 GB | **12.4** (mean 12.7, sd 1.3) | 53.9 | 884 / 642 | 44/50 (88%) | 0/10 | 10/10 |
| Qwen3-8B (dense, 8B) | Q4_K_M | 5.0 GB | 41.8 (mean 41.7, sd 2.9) | 14.4 | 888 / 583 | 50/50 (100%) | 0/10 | 10/10 |
| Gemma-4-26B-A4B-it (MoE, ~4B active) | UD-Q3_K_M | 12.7 GB | 40.3 (mean 40.7, sd 3.4) | 21.0 | 983 / 760 | 50/50 (100%) | 0/10 | 10/10 |
| GLM-4.7-Flash (MoE), with hint | Q3_K_M | 14.6 GB | 23.9 (mean 24.0, sd 1.9) | 23.8 | 874 / 531 | 48/50 (96%) | 0/10 | 10/10 |
| GLM-4.7-Flash (MoE), **no hint** | Q3_K_M | 14.6 GB | **26.7** (mean 26.7, sd 1.8) | 23.5 | 767 / 564 | **50/50 (100%)** | 0/10 | 10/10 |

All rows except the last GLM row use the hint (the config that was best for Gemma and Qwen3-30B). GLM was run both ways on the same 10 contexts and seeds (`--no-hint` flag): the two invalid rules in the hint run both came from one answer, so this is a small-sample hint, but it agrees with the earlier T18 result (GLM nested layout, no hint, 250/250 valid, 26.5 s/call). Hence GLM is best run WITHOUT the hint. Qwen3-30B-A3B-Instruct-2507 (T18, 50 calls, ~31-35 s/call, 99.6% with hint) was not re-run here (see `blue-agent-and-rules.md`).

"Valid" = passes the rule validator after the parser's cosmetic repairs, with NO repair call (the agent allows one extra call when nothing valid comes back, so the real agent does a bit better than the 4B's 88%).

## What it means for the compute budget
Using the sheet's own assumptions (3 LLM calls per Blue agent per round x 5 Blue agents, 3 per Red agent, 10 rounds, 5 seeds, conditions 3-5 use the LLM) there are about 2,550 LLM calls in total in Mode B (my reading of the sheet; its formulas decide the final value). That is roughly:
- 8.8 h with the 4B model (12.4 s)
- 18.9 h with GLM-4.7-Flash, no hint (26.7 s)
- 28.5 h with Gemma (40.3 s)
- 29.6 h with Qwen3-8B (41.8 s)
These are LLM hours only (environment time is separate), against the 100 h budget. So Mode B (Decision D1 option B) fits with all three; the 4B leaves a lot more room.

## Reading the numbers carefully
- The 8B is as slow as the 26B MoE on this laptop because a 5 GB dense model plus the context does not fully fit in 6 GB of VRAM and part of it runs on the CPU (14 tokens/s). A GPU with more VRAM (Krish's RTX 3060, if it has 8 GB) may run it much faster. Only Bhavit's laptop was measured.
- The 4B is 3.3x faster but wrote 12% invalid rules in the first call. Whether that matters depends on the repair call and on rule QUALITY, which this does not measure (validity is not detection quality; that needs the bridge + labels in the loop).
- 10 calls per model, one prompt type, one run: good for the order of magnitude, not for fine ranking.
- The results use rule-writing prompts only; Red LLM calls (T20) will have different lengths.

## Proposal for T14 / Decision D1 (Bhavit; the team decides)
- **Server:** keep llama.cpp `llama-server`. The Blue agent already talks to it (`LlamaServerClient`), it constrains output to our JSON schema (the nested schema took validity from ~96% to 100%), it can switch off thinking mode, and every number here comes from it. Ollama would need a new install, a different structured-output path and re-testing.
- **Model for the reported experiments (Bhavit's GPU PC runs these, T34): GLM-4.7-Flash Q3_K_M, nested layout, no hint.** Fastest of the models that wrote 100% valid rules (26.7 s/call, 18.9 LLM hours on the sheet's assumptions, well inside 100 h). Gemma is as valid but 1.5x slower; Qwen3-8B is as slow as Gemma on this laptop; the 4B is fastest but 88% valid.
- **Model for development on smaller machines (Krish's RTX 3060 laptop, 16 GB RAM; Prateek's CPU-only machine): Qwen3-4B-Instruct-2507 Q4_K_M** (2.5 GB, 12 s/call on the 4050, 54 tokens/s). The 12-15 GB MoE files are too tight for 16 GB of RAM; the 4B lets the Red agent and the runner be built and tested anywhere. The Blue prompt would need tuning for it before it is used for results.
- **Not yet measured:** speeds on Krish's laptop. One command on his machine (see Reproduce) would settle it.
- **Caveats:** validity is not detection quality, so the choice among the big models rests mostly on speed; 10 calls per row; every figure is from one RTX 4050 6 GB laptop. If the team prefers a single model everywhere, the 4B is the only one that runs on all three machines.

## Reproduce
Start the server for one model, then (from the repo root, in the Blue-side environment):
```
python scripts/benchmark_llamaserver.py --label <model-name> --runs 10 --warmup 1 --out results/bench_llamaserver.csv
```
Rows are appended, so run it once per model with a different `--label`. Add `--no-hint` to leave out the "limits of the rule language" paragraph. Server command: see `blue-agent-and-rules.md`.

## Models used (so others can fetch the same files)
- `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`, from `huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF`, 2,497,281,120 bytes, sha256 `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`
- `Qwen3-8B-Q4_K_M.gguf`, from `huggingface.co/unsloth/Qwen3-8B-GGUF`, 5,027,784,512 bytes, sha256 `120307ba529eb2439d6c430d94104dabd578497bc7bfe7e322b5d9933b449bd4`
Both sizes and hashes were checked after download. Files live on Bhavit's HDD (`D:\AI\Models`); the 26B Gemma stays on the SSD.
