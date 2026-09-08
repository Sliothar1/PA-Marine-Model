#!/usr/bin/env python3
"""Discover / stage EUMETSAT OSI SAF SST for Irish HAB domain.

Default product: OSI-202-c NAR L3C (GHRSST AVHRR_SST_METOP_B_NAR-OSISAF-L3C-v1.0).

Steps this script can do without Earthdata:
  --manifest-only  → CMR granule list + HTTPS URLs under data/raw/osi_saf_sst/

Download of protected PO.DAAC granules needs Earthdata ~/.netrc.
Ifremer FTP path is printed as a fallback (see docs/CLIMATE_DRIVERS.md).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pa_marine.config import load_config
from pa_marine.osi_saf_sst import ftp_hint, write_granule_manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=None)
    p.add_argument("--t0", default="2023-06-01", help="start date for CMR search")
    p.add_argument("--t1", default="2023-06-30", help="end date for CMR search")
    p.add_argument(
        "--out",
        default="data/raw/osi_saf_sst/nar_metop_b_manifest.csv",
        help="manifest CSV path",
    )
    p.add_argument(
        "--product",
        choices=["nar", "glb"],
        default=None,
        help="override config osi_saf_sst.product",
    )
    args = p.parse_args()

    cfg = load_config(args.config)
    if args.product:
        cfg.setdefault("osi_saf_sst", {})["product"] = args.product
    product = (cfg.get("osi_saf_sst") or {}).get("product", "nar")

    out = Path(args.out)
    df = write_granule_manifest(out, cfg, args.t0, args.t1)
    print(f"FTP fallback: {ftp_hint(product)}", flush=True)
    print(
        "Next: Earthdata login + wget/curl granules, then "
        "scripts/join_oc_osi_week.py --osi-daily …",
        flush=True,
    )
    if df.empty:
        print("WARNING: empty CMR manifest (network / short_name / temporal?)", flush=True)


if __name__ == "__main__":
    main()
