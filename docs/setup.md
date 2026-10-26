# Setup: CAGE-4 (CybORG) in a clean venv

Written for T04 by Krish. Verified on Windows 11, Python 3.12.10, git 2.53, CPU-only torch.
Commands below are PowerShell; the Git Bash equivalents differ only in the venv
activation line. Linux/macOS notes are at the end and are **not yet tested**.

Versions installed: CybORG 4.0 (`CybORG/version.txt`), cage-challenge-4 commit
`8c3c50ca54b176c2de199847944e8dcc035497e3`. The full list of installed packages is in
`docs/pip-freeze.txt`.

## 1. Clone this repo and create the venv

```powershell
git clone https://github.com/Krish-Anand-dev/Co-evolutionary-purple-teaming.git
cd Co-evolutionary-purple-teaming
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Git Bash: `source venv/Scripts/activate`. Python 3.12 worked; the CAGE-4 `setup.py` requires 3.7+.

## 2. Clone CAGE-4 into `external/` (gitignored)

```powershell
mkdir external
git clone https://github.com/cage-challenge/cage-challenge-4.git external/cage-challenge-4
cd external/cage-challenge-4
git checkout 8c3c50ca54b176c2de199847944e8dcc035497e3
```

## 3. Install

These are the steps from the CAGE-4 docs (`documentation/docs/pages/tutorials/01_Getting_Started/1_Introduction.md`),
plus one extra pin.

```powershell
pip install -r Requirements.txt
pip install -r ../../requirements-extra.txt
pip install -e .
cd ../..
```

**Why the extra pin:** `Requirements.txt` leaves `ray[rllib]` unpinned, so pip pulls the
newest `pyarrow` (26.0.0 when I ran it). That needs NumPy 2, but CAGE-4 pins
`numpy==1.26.4`, and every import of `ray.rllib` then fails with
`ImportError: pyarrow requires NumPy 2.0 or newer, found 1.26.4`.
`requirements-extra.txt` pins `pyarrow==17.0.0`, which works with ray 2.38.0 and NumPy 1.26.4.
(If you already ran step 3 without it, `pip install pyarrow==17.0.0` fixes it.)

Expect a large download (torch, ray). A harmless `Gym has been unmaintained since 2022`
warning prints on import.

## 4. Check the install

```powershell
cd external/cage-challenge-4
pytest ./CybORG/Tests/test_cc4
```

My result: `680 passed, 15 skipped, 13 warnings in 784.80s (0:13:04)`.
It is slow; for a quick check skip to step 5.

Linux only: the docs also ask for `sudo apt install python3-tk --assume-yes`. Not needed on Windows.

## 5. Run the default evaluation

The evaluation script needs a "submission" folder. The upstream example
(`CybORG/Evaluation/example_submission/submission.py`) has a bug: it puts
`from __future__ import annotations` after other imports, which raises
`SyntaxError: from __future__ imports must occur at the beginning of the file`.
We keep a fixed copy at `scripts/eval_submission/` (a dummy blue agent that always
takes the last action in its action space).

Run from `external/cage-challenge-4`, with the venv active:

```powershell
python -m CybORG.Evaluation.evaluation --max-eps 2 --seed 0 ../../scripts/eval_submission ../../results/eval_check
```

Output on my machine:

```
CybORG v4.0, Scenario4
Author: Dummy baseline, Team: MAIT purple team, Technique: Last-action dummy
Using agents {'blue_agent_0': DummyAgent, ... 'blue_agent_4': DummyAgent}, ...
Average reward is: -6828 with a standard deviation of 739.6336931211287
File took 0:00:29.744488 amount of time to finish evaluation
```

That is about 15 s per 500-step episode on CPU. The full upstream evaluation is
100 episodes (`--max-eps` default), so budget roughly 25 min. Results land in the output
folder as `summary.txt`, `summary.json`, `scores.txt`, `actions.txt`, `full.txt`.
The red agent in this evaluation is `FiniteStateRedAgent`; blue is whatever your submission defines.

`results/` is gitignored, so these logs are not committed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pyarrow requires NumPy 2.0 or newer` | `pip install pyarrow==17.0.0` (step 3) |
| `SyntaxError: from __future__ imports...` | Use `scripts/eval_submission`, not upstream `example_submission` |
| Windows path error from `rmkdir` | Make sure the output folder's parent exists (`results/` does) |

## Linux / macOS (untested)

Same steps with `python3 -m venv venv`, `source venv/bin/activate`, forward slashes, and
`python3-tk` on Linux. Prateek: if anything differs when you do T05, please edit this file.
