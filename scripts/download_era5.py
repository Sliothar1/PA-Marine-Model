#!/usr/bin/env python3
"""Download ERA5 daily 10 m wind (CDS) for Irish HAB bbox as yearly zips."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pa_marine.config import load_config
from pa_marine.era5 import CDS_TERMS_URL, download_era5_years


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--years", default=None, help="Comma years, e.g. 2002,2003 or 2002-2006")
    p.add_argument("--max-years", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--async",
        dest="async_submit",
        action="store_true",
        help="Submit without waiting; print request IDs",
    )
    p.add_argument("--status-out", default="data/raw/era5_download_status.json")
    args = p.parse_args()
    cfg = load_config(args.config)

    years = None
    if args.years:
        years = []
        for part in args.years.split(","):
            part = part.strip()
            if "-" in part and part.count("-") == 1:
                a, b = part.split("-")
                years.extend(range(int(a), int(b) + 1))
            else:
                years.append(int(part))

    print(f"CDS terms (if licence error): {CDS_TERMS_URL}")
    results = download_era5_years(
        cfg,
        years=years,
        force=args.force,
        wait=not args.async_submit,
        max_years=args.max_years,
    )
    out = Path(args.status_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    ok = sum(1 for r in results if r.get("state") in {"downloaded", "exists"})
    print(f"status → {out} ok={ok}/{len(results)}")
    for r in results:
        print(
            f"  year={r.get('year')} half={r.get('half')} state={r.get('state')} "
            f"size={r.get('size')} request_id={r.get('request_id')} "
            f"err={str(r.get('error') or '')[:120]}"
        )


if __name__ == "__main__":
    main()
