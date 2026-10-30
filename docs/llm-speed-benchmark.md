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

Earlier T18 timings of the other two big models on the same laptop (50 calls each, same kind of prompt): GLM-4.7-Flash Q3_K_M 26.5 s/call, Qwen3-30B-A3B-Instruct-2507 ~31-35 s/call (see `blue-agent-and-rules.md`). They were not re-run here.

"Valid" = passes the rule validator after the parser's cosmetic repairs, with NO repair call (the agent allows one extra call when nothing valid comes back, so the real agent does a bit better than the 4B's 88%).

## What it means for the compute budget
Using the sheet's own assumptions (3 LLM calls per Blue agent per round x 5 Blue agents, 3 per Red agent, 10 rounds, 5 seeds, conditions 3-5 use the LLM) there are about 2,550 LLM calls in total in Mode B (my reading of the sheet; its formulas decide the final value). That is roughly:
- 8.8 h with the 4B model (12.4 s)
- 28.5 h with Gemma (40.3 s)
- 29.6 h with Qwen3-8B (41.8 s)
These are LLM hours only (environment time is separate), against the 100 h budget. So Mode B (Decision D1 option B) fits with all three; the 4B leaves a lot more room.

## Reading the numbers carefully
- The 8B is as slow as the 26B MoE on this laptop because a 5 GB dense model plus the context does not fully fit in 6 GB of VRAM and part of it runs on the CPU (14 tokens/s). A GPU with more VRAM (Krish's RTX 3060, if it has 8 GB) may run it much faster. Only Bhavit's laptop was measured.
- The 4B is 3.3x faster but wrote 12% invalid rules in the first call. Whether that matters depends on the repair call and on rule QUALITY, which this does not measure (validity is not detection quality; that needs the bridge + labels in the loop).
- 10 calls per model, one prompt type, one run: good for the order of magnitude, not for fine ranking.
- The results use rule-writing prompts only; Red LLM calls (T20) will have different lengths.

## Reproduce
Start the server for one model, then (from the repo root, in the Blue-side environment):
```
python scripts/benchmark_llamaserver.py --label <model-name> --runs 10 --warmup 1 --out results/bench_llamaserver.csv
```
Rows are appended, so run it once per model with a different `--label`. Server command: see `blue-agent-and-rules.md`.

## Models used (so others can fetch the same files)
- `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`, from `huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF`, 2,497,281,120 bytes, sha256 `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`
- `Qwen3-8B-Q4_K_M.gguf`, from `huggingface.co/unsloth/Qwen3-8B-GGUF`, 5,027,784,512 bytes, sha256 `120307ba529eb2439d6c430d94104dabd578497bc7bfe7e322b5d9933b449bd4`
Both sizes and hashes were checked after download. Files live on Bhavit's HDD (`D:\AI\Models`); the 26B Gemma stays on the SSD.
