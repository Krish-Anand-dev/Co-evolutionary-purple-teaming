
# Ollama LLM Benchmark

## Purpose

Measures local Ollama model performance using a realistic SOC detection-engineering prompt.

The benchmark records:
- Average and median response latency (seconds per call)
- Input and output token counts
- Output generation speed (tokens/second)
- Valid JSON response rate

## Requirements

- Python 3.10 or later
- Ollama installed and running
- Benchmark models pulled locally

No additional Python packages are required. The script uses Python's standard library.

## Prepare Ollama

Start Ollama and pull the models you want to test. Include models in both the 3–4B and 7–8B parameter ranges where available.

Example:

```powershell
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
```

Check available models:

```powershell
ollama list
```

Use the exact model tags shown by `ollama list`.

## Run the benchmark

From the repository root:

```powershell
python scripts/benchmark_ollama.py --models qwen2.5:3b,qwen2.5:7b
```

Default settings:
- 1 warm-up call per model (excluded from measurements)
- 10 measured calls per model
- Temperature: 0.2
- Maximum generated tokens: 250
- Request timeout: 600 seconds

## Optional arguments

| Argument | Default | Description |
|---|---:|---|
| `--models` | Required | Comma-separated Ollama model tags |
| `--runs` | 10 | Measured calls per model |
| `--warmup` | 1 | Warm-up calls per model |
| `--num-predict` | 250 | Maximum generated tokens |
| `--temperature` | 0.2 | Generation temperature |
| `--seed` | 42 | Base random seed |
| `--timeout` | 600 | Request timeout in seconds |
| `--host` | `http://localhost:11434` | Ollama server address |
| `--out` | `results/ollama_benchmark.csv` | CSV output path |

Example with custom settings:

```powershell
python scripts/benchmark_ollama.py --models qwen2.5:3b,qwen2.5:7b --runs 15 --warmup 2 --out results/ollama_benchmark.csv
```

## Output

The script writes one CSV row per measured call. It includes:
- Model and run number
- Latency in seconds
- Input and output token counts
- Output tokens per second
- Whether the response is valid JSON
- Any request error

The terminal also displays per-model mean latency, median latency, latency standard deviation, and valid JSON rate.

## Notes

- Warm-up calls are not included in the CSV or summary.
- Actual input and output token counts are reported by Ollama.
- The prompt is designed to represent a SOC detection-engineering task; actual token counts may vary by model tokenizer.
- JSON validity is checked by parsing the complete model response.
- Run benchmarks under comparable hardware, model quantization, and Ollama settings when comparing models.
- This script performs the benchmark; GPU-PC execution and result reporting are handled separately.
