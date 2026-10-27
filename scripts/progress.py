"""Print one line each time another 5 prompts of a measure_blue_validity run have finished.

Usage: python scripts/progress.py results/<run>.raw.jsonl [total_prompts]
Reads the raw-answer JSONL the measurement script appends to. Exits when the total is reached.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.agents.blue.repair import extract_rule_objects, normalise_rule  # noqa: E402
from src.rules.validator import validate_rule_dict  # noqa: E402


def snapshot(path: pathlib.Path) -> tuple[int, str]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:                      # run started but no answer written yet
        return 0, "0 prompts done"
    # A prompt = one first call plus the repair call(s) that directly follow it (same grouping as the agent).
    groups: list[list[dict]] = []
    for r in rows:
        if r["is_repair"] and groups:
            groups[-1].append(r)
        else:
            groups.append([r])
    objects = raw_ok = final_ok = empty = fallbacks = repairs = 0
    for group in groups:
        repairs += len(group) - 1
        empty += sum(not r["text"].strip() for r in group)
        valid_in_group = 0
        for r in group:
            for i, obj in enumerate(extract_rule_objects(r["text"])):
                stamped = {**{k: v for k, v in obj.items() if k not in {"rule_id", "round", "agent_id"}},
                           "rule_id": f"x{i}", "round": 1, "agent_id": "blue_0"}
                objects += 1
                raw_ok += validate_rule_dict(stamped).valid
                ok = validate_rule_dict(normalise_rule(stamped)).valid
                final_ok += ok
                valid_in_group += ok
        fallbacks += valid_in_group == 0
    pct = lambda n: f"{100 * n / objects:.0f}%" if objects else "n/a"  # noqa: E731
    lat = [r["meta"].get("latency_s") or 0 for r in rows]
    line = (f"{len(groups)} prompts done | rules found {objects} | valid as written {raw_ok} ({pct(raw_ok)}) "
            f"| valid after cosmetic fixes {final_ok} ({pct(final_ok)}) | prompts with NO valid rule {fallbacks} "
            f"| repair calls {repairs} | empty answers {empty} | avg {sum(lat) / len(lat):.0f}s/call")
    return len(groups), line


def main() -> None:
    path = pathlib.Path(sys.argv[1])
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    reported = 0
    while True:
        if path.exists():
            done, line = snapshot(path)
            if done // 5 > reported // 5 or done >= total:
                if done != reported:
                    print(line, flush=True)
                reported = done
            if done >= total:
                return
        time.sleep(20)


if __name__ == "__main__":
    main()
