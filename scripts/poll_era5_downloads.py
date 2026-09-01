#!/usr/bin/env python3
"""Poll CDS request IDs in data/raw/era5_download_status.json and download zips."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ecmwf.datastores import Client


def _cds_client() -> Client:
    cfg: dict[str, str] = {}
    for line in Path.home().joinpath(".cdsapirc").read_text().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            cfg[k.strip()] = v.strip()
    return Client(url=cfg["url"], key=cfg["key"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--status", default="data/raw/era5_download_status.json")
    p.add_argument("--budget-min", type=float, default=45.0)
    p.add_argument("--sleep", type=float, default=30.0)
    args = p.parse_args()
    status_path = Path(args.status)
    items = json.loads(status_path.read_text())
    client = _cds_client()
    t0 = time.time()
    budget = args.budget_min * 60
    round_n = 0
    while time.time() - t0 < budget:
        round_n += 1
        pending = [
            it
            for it in items
            if it.get("request_id")
            and it.get("state") not in {"downloaded", "exists", "skipped", "failed", "deleted"}
        ]
        print(f"round {round_n} pending={len(pending)}")
        if not pending:
            break
        for it in pending:
            rid = it["request_id"]
            out = Path(it["path"])
            try:
                remote = client.get_remote(rid)
                remote.update()
                st = remote.status
                it["state"] = st
                if st in ("successful", "completed") or remote.results_ready:
                    if not (out.exists() and out.stat().st_size > 1000):
                        print(f"download {it.get('year')} {it.get('half')} → {out}")
                        remote.download(str(out))
                    if out.exists():
                        it["state"] = "downloaded"
                        it["size"] = out.stat().st_size
                elif st in ("failed", "rejected"):
                    it["error"] = str(getattr(remote, "reply", st))[:500]
                    print(f"failed {it.get('year')} {it.get('half')}: {it['error'][:160]}")
            except Exception as exc:  # noqa: BLE001
                it["poll_error"] = str(exc)[:300]
                print(f"poll_err {it.get('year')} {it.get('half')}: {exc}")
        status_path.write_text(json.dumps(items, indent=2))
        done = sum(1 for it in items if it.get("state") in {"downloaded", "exists"})
        print(f"done={done}/{len(items)}")
        if done == len(items):
            break
        time.sleep(args.sleep)
    status_path.write_text(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
