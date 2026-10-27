"""Summarise results/native_events_*.jsonl (from dump_native_events.py): which Red actions leave native Blue events.

Usage (main venv, no CybORG needed):  python scripts/analyze_native_events.py results/native_events_seed0.jsonl [more files]
An event is attributed to a Red action when that action targeted the same host (by hostname or interface IP) in the same step.
Caveat: attribution by host+step is approximate (path-side events land on intermediate hosts that are not the target).
"""
from __future__ import annotations

import collections
import json
import sys


def kind(proc: dict) -> str:
    conns = proc.get("Connections") or []
    if not conns:
        return "pid_only"
    c = conns[0]
    if "local_port" in c and "remote_port" in c:
        return "conn_target_side"       # local service port + remote ephemeral port
    if "remote_port" in c:
        return "conn_path_side"         # remote service port, no local port
    return "conn_local_only"            # local address + port only (Green false process alert)


def analyse(paths: list[str]) -> None:
    red_steps = collections.Counter()
    total, unlinked = collections.Counter(), collections.Counter()
    link: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    ports, steps, steps_with_events, n4444 = collections.Counter(), 0, 0, 0
    for path in paths:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            steps += 1
            steps_with_events += bool(r["blue_obs"])
            targets: dict[str, set] = collections.defaultdict(set)
            for d in r["red"].values():
                red_steps[d["type"]] += 1
                targets[d["type"]].add(d["action"].split(" ", 1)[1] if " " in d["action"] else "")
            for o in r["blue_obs"].values():
                for host, h in o.items():
                    ips = {i.get("ip_address") for i in h.get("Interface", [])}
                    for p in h.get("Processes", []):
                        k = kind(p)
                        total[k] += 1
                        for c in p.get("Connections", []):
                            n4444 += 4444 in (c.get("remote_port"), c.get("local_port"))
                            for key in ("local_port", "remote_port"):
                                if key in c and c[key] < 1024:
                                    ports[c[key]] += 1
                        hits = [t for t, tg in targets.items() if host in tg or ips & tg]
                        for t in hits:
                            link[k][t] += 1
                        if not hits:
                            unlinked[k] += 1
    print(f"steps {steps}, steps where any Blue agent got events: {steps_with_events}")
    print("Red action-steps (a multi-tick action counts each step):", dict(red_steps))
    print("events mentioning port 4444:", n4444, "| well-known ports in events:", dict(ports.most_common(6)))
    for k in total:
        print(f"{k}: {total[k]} records, not matched to a Red target: {unlinked[k]}; co-occurring Red action: {dict(link[k].most_common())}")
    silent = [a for a in red_steps if not any(link[k].get(a) for k in total)]
    print("Red actions with NO matched Blue event:", silent)


if __name__ == "__main__":
    analyse(sys.argv[1:])
