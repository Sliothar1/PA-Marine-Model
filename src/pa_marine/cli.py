from __future__ import annotations

import argparse
from pathlib import Path

from pa_marine.config import load_config


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="pa-marine")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="Hit ERDDAP with a tiny request and print schema")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    if args.cmd == "probe":
        from pa_marine.erddap import tabledap_csv, griddap_csv, lon_to_oisst_360

        hab = tabledap_csv(
            cfg["hab"]["erddap_base"],
            cfg["hab"]["dataset_id"],
            ["scientific_name", "time", "latitude", "longitude", "location_id", "count"],
            constraints=["time>=2023-08-01T00:00:00Z", "time<=2023-08-02T00:00:00Z"],
        )
        print("HAB rows", len(hab), "cols", list(hab.columns))
        lo = lon_to_oisst_360(-9.8)
        q = "sst[(2023-08-01T12:00:00Z)][(0.0)][(51.875)][(%.3f)]" % lo
        sst = griddap_csv(cfg["sst"]["erddap_base"], cfg["sst"]["dataset_id"], q)
        print("OISST", sst.to_dict(orient="records")[:1])


if __name__ == "__main__":
    main()
