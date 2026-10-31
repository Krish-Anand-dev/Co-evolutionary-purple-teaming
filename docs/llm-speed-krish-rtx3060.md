# LLM speed benchmark on Krish's laptop (T09, second machine) - 31-Oct-2026

Same script, prompt and settings as Bhavit's run in [llm-speed-benchmark.md](llm-speed-benchmark.md): the real Blue
rule-writing prompt (nested layout + limits hint, 5 rules requested, `max_tokens` 1000, thinking off, temperature 0.2),
1 warm-up call then 10 measured calls per model (seeds 1-10), one model at a time.
Raw rows: `results/summaries/bench_llamaserver_t09_krish_rtx3060.csv` (20 rows).

## Machine and software
- Laptop: AMD Ryzen 9 5900HX (16 threads), 15.4 GB RAM, **RTX 3060 Laptop GPU with 6 GB VRAM** (Bhavit's note guessed 8 GB;
  `nvidia-smi` says 6144 MiB), Windows 11, NVIDIA driver 610.88 (CUDA UMD 13.3).
- llama.cpp **b12019**, Windows **CUDA 12.4** build plus the matching cudart zip. Bhavit used b11756 with CUDA 13.4. I picked
  12.4 because the driver reports CUDA 13.3 and a 13.4 build might not load. This is a build difference to keep in mind when comparing.
- Server command (port 8080), flags as in `blue-agent-and-rules.md` except `--threads 8` (not 16; this CPU has 16 threads):
  `llama-server --model <gguf> --alias <name> --host 127.0.0.1 --port 8080 --ctx-size 8192 --parallel 1 --device CUDA0 --fit on --fit-target 768 --flash-attn on --threads 8 --threads-batch 8 --jinja`
- Nothing else heavy was running during the timed calls (the CAGE-4 Red experiments had finished).
- Files: both GGUFs match the sha256 values in Bhavit's doc (checked after download).

## Results (median over 10 calls)
| Model | Quant | Size | sec/call | tokens/s | tokens out | Valid rules | Cut off | Parses as JSON |
|---|---|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 | Q4_K_M | 2.5 GB | **8.7** (mean 8.8, sd 0.4) | 80.2 | 633-706 | 45/50 (90%) | 0/10 | 10/10 |
| Qwen3-8B | Q4_K_M | 5.0 GB | **44.4** (mean 44.2, sd 2.7) | 13.4 | 504-640 | 50/50 (100%) | 0/10 | 10/10 |

## Next to Bhavit's RTX 4050 6 GB numbers (same models)
| Model | RTX 3060 (Krish) | RTX 4050 (Bhavit) |
|---|---|---|
| Qwen3-4B-Instruct-2507 Q4_K_M | 8.7 s, 80 tok/s, 90% valid | 12.4 s, 54 tok/s, 88% valid |
| Qwen3-8B Q4_K_M | 44.4 s, 13.4 tok/s, 100% valid | 41.8 s, 14.4 tok/s, 100% valid |

## What it means
- The 4B fits fully on this GPU (3.7 GB used) and is 1.4x faster than on the 4050: **8.7 s/call**. On the sheet's assumptions
  (about 2,550 Mode B calls, from Bhavit's reading) that is roughly 6.2 LLM hours, which is a comfortable development model on this laptop.
- The 8B does NOT fully fit in 6 GB with the 8192 context (4.4 GB used on the GPU, the rest runs on the CPU), so it is as slow
  as on the 4050 (about 44 s/call, roughly 31 h). Bhavit's proposal to use the 4B for development on smaller machines matches this.
  The earlier hope that this laptop "may have 8 GB and run the 8B much faster" does not hold: it is 6 GB.
- Both runs only measure speed and rule VALIDITY. Validity is not detection quality (needs the bridge T16 and labels T21).
  The 4B wrote 5 invalid rules in 50 (90%), in line with Bhavit's 88%.
- Limits: 10 calls per model, one prompt type, one machine, one run each; fine for the order of magnitude, not for ranking.
- Not run here: GLM-4.7-Flash (14.6 GB) and Gemma-4-26B (12.7 GB). They are too large for this laptop's 15.4 GB RAM and 6 GB VRAM.

## Still open for T09 / T14
- The 'Experiments & Compute' B4 input is Bhavit's/the team's call (D1 is decided as option B with GLM for reported runs).
  This file only adds the second machine's measured speed; it does not change B4.
