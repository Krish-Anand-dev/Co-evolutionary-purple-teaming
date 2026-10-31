# Setup

Written for T04 by Krish, extended for T26. Everything below installs ONE pinned environment (CAGE-4 simulator, our code, the
Blue side with pySigma, the tests). It is CPU only and needs Python 3.12. CAGE-4 is pinned to commit
`8c3c50ca54b176c2de199847944e8dcc035497e3` (CybORG 4.0).

Verified on 31-Oct-2026, all with the same result, **253 passed, 1 skipped** (the skip needs a gitignored local data dump):
- Docker image built from the `Dockerfile` (about 3 min the first time, 1.6 GB), tests run inside it
- a clean `python:3.12-slim` Linux container
- a fresh venv on Windows 11, Python 3.12.10

## Route 1: Docker (any OS)

```bash
docker build -t purple-team .
docker run --rm purple-team                         # runs the whole test suite
docker run --rm -v "$PWD/results:/app/results" purple-team python scripts/hello_agents.py --seed 0
```

The image contains Python 3.12, the pinned packages, CAGE-4 at the pinned commit and the project, and runs as a normal user.
It does NOT contain the local LLM server: `llama-server` and the GGUF models stay on the host (they need the GPU). The LLM agents
talk to it over HTTP (`--llama-server URL`), see `docs/llm-speed-benchmark.md`. Reaching a host server from inside a container
(`host.docker.internal`, and starting `llama-server` with `--host 0.0.0.0` instead of `127.0.0.1`) is NOT tested; running the LLM scripts natively
is the tested path.

## Route 2: native virtual environment (Windows / Linux / macOS)

```powershell
git clone https://github.com/Krish-Anand-dev/Co-evolutionary-purple-teaming.git
cd Co-evolutionary-purple-teaming
python -m venv venv
.\venv\Scripts\Activate.ps1                         # Git Bash: source venv/Scripts/activate ; Linux/macOS: source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints-py312.txt
pip install -r requirements-dev.txt                 # ruff + black, only needed for linting

mkdir external
git clone https://github.com/cage-challenge/cage-challenge-4.git external/cage-challenge-4
git -C external/cage-challenge-4 checkout 8c3c50ca54b176c2de199847944e8dcc035497e3

python -m pytest -q                                 # 253 passed, 1 skipped
```

CAGE-4 is not a pip package here. Our scripts and tests add `external/cage-challenge-4` to the import path themselves. To run
CAGE-4's own modules directly (for example `python -m CybORG.Evaluation.evaluation`), put it on the path yourself:
PowerShell `$env:PYTHONPATH = "$PWD\external\cage-challenge-4"`, bash `export PYTHONPATH=$PWD/external/cage-challenge-4`.
(`pip install -e external/cage-challenge-4` does NOT do this: its `setup.py` declares no packages.)
`external/` is gitignored.

## What is pinned, and why it is not CAGE-4's own Requirements.txt
- `requirements.txt`: exact top-level versions. `constraints-py312.txt`: the full lock (80 packages, top-level and transitive) from a
  clean Python 3.12 Linux install. Passing it with `-c` pins every transitive package.
- **PyYAML 6.0.3.** CAGE-4's `Requirements.txt` pins `PyYAML==6.0.1`, while pySigma 2.0.1 needs `>=6.0.3`. That conflict is why we
  used to keep two virtual environments. We do not install CAGE-4's requirements file (only its metadata mentions 6.0.1), and
  CAGE-4 runs on 6.0.3, so one environment now works.
- **`pyarrow==17.0.0`.** CAGE-4 leaves `ray[rllib]` unpinned, so pip picks the newest `pyarrow`, which needs NumPy 2, while CAGE-4
  pins `numpy==1.26.4`. Result: `ImportError: pyarrow requires NumPy 2.0 or newer` on every `ray.rllib` import.
- **No torch, torch_geometric, stable-baselines, tensorboard, GUI stack.** CAGE-4's `Requirements.txt` installs them, but the
  CybORG simulator does not import them (checked on its source: only numpy, gym, gymnasium, matplotlib, networkx, paramiko,
  prettytable, pygame, ray and yaml are imported by the core code; torch and sb3 only by its example RL training/evaluation code).
  Leaving them out keeps the install much smaller (torch alone is hundreds of MB to several GB depending on the platform; the
  size difference was not measured). If you want to TRAIN RL agents with CAGE-4's examples, use the manual
  route at the end of this file.
- A harmless `Gym has been unmaintained since 2022` warning prints on import.

## Updating the pins
Change `requirements.txt`, then regenerate the lock and re-test:
```bash
bash scripts/regenerate_constraints.sh            # needs Docker; rewrites constraints-py312.txt
docker build -t purple-team . && docker run --rm purple-team
```
Regenerating from the same `requirements.txt` gives an identical file (checked). The lock is for Linux / Python 3.12; the same
file also installed cleanly on Windows. If a future pin has no Windows wheel, install on Windows without `-c`.
Keep the CAGE-4 commit in sync in three places: `Dockerfile` (`CAGE4_COMMIT`), `.github/workflows/ci.yml`, and this file.

## Continuous integration and linting
GitHub Actions (`.github/workflows/ci.yml`) runs on every push and pull request:
- **lint**: `ruff check .` (blocking; the rules are the correctness set in `pyproject.toml`) and `black --check .` (informational).
- **test**: installs `requirements.txt` with the lock, clones CAGE-4 at the pinned commit, runs `python -m pytest -q`.
A second workflow (`docker.yml`) builds the image and runs the tests inside it, only when the Dockerfile or the requirements change.

Run the same checks locally: `ruff check .` then `python -m pytest -q`.
**Black is not enforced yet**: 54 of 65 existing files are not black-formatted, and reformatting them all at once would collide with
every open branch. Proposal: one agreed `black .` pull request when no feature branches are open, then remove
`continue-on-error` from the black step.

## Manual route: CAGE-4's own requirements (full RL stack, includes torch)
Only needed to train RL agents with CAGE-4's example code. These are the steps from the CAGE-4 docs
(`documentation/docs/pages/tutorials/01_Getting_Started/1_Introduction.md`) plus our pyarrow pin. Use a SEPARATE venv: it installs
PyYAML 6.0.1, which pySigma cannot use.

```powershell
python -m venv venv-rl
.\venv-rl\Scripts\Activate.ps1
cd external/cage-challenge-4
pip install -r Requirements.txt
pip install pyarrow==17.0.0
pip install -e .
```
CAGE-4's own test suite (`pytest ./CybORG/Tests/test_cc4`) gave `680 passed, 15 skipped` in 13 minutes on Windows (T04). On Linux the
docs also ask for `sudo apt install python3-tk --assume-yes`.

## Run the default CAGE-4 evaluation
The evaluation script needs a "submission" folder. The upstream example (`CybORG/Evaluation/example_submission/submission.py`) has a
bug: it puts `from __future__ import annotations` after other imports, which raises
`SyntaxError: from __future__ imports must occur at the beginning of the file`. We keep a fixed copy at `scripts/eval_submission/`
(a dummy Blue agent that always takes the last action in its action space). From `external/cage-challenge-4`, with the venv active and
`PYTHONPATH` set as above:

```powershell
python -m CybORG.Evaluation.evaluation --max-eps 2 --seed 0 ../../scripts/eval_submission ../../results/eval_check
```
Output on one machine (T04): `Average reward is: -6828 with a standard deviation of 739.6...`, about 15 s per 500-step episode on CPU;
the full upstream evaluation is 100 episodes (`--max-eps` default), roughly 25 minutes. Results land in the output folder as
`summary.txt`, `summary.json`, `scores.txt`, `actions.txt`, `full.txt`. `results/` is gitignored.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `pyarrow requires NumPy 2.0 or newer` | `pip install pyarrow==17.0.0`, or install with `-r requirements.txt -c constraints-py312.txt` |
| `No module named 'CybORG'` | `external/cage-challenge-4` is missing or not on `PYTHONPATH` (see Route 2) |
| `No module named 'sigma'` | you are in an old CAGE-only venv; use the single pinned environment above |
| `SyntaxError: from __future__ imports...` | use `scripts/eval_submission`, not upstream `example_submission` |
| Windows path error from `rmkdir` | make sure the output folder's parent exists (`results/` does) |
| `docker build` cannot reach GitHub | CAGE-4 is cloned during the build; check the network or proxy |
