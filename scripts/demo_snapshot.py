#!/usr/bin/env python3
"""Print Cork Ocean Hackathon demo metrics + figure paths from existing JSON/CSV.

No retrain, no network. Safe to run offline after clone (committed reports) or
with local processed parquets/figures present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
FIG = PROC / "figures"


def _load(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  ! failed to read {path.relative_to(ROOT)}: {e}", file=sys.stderr)
        return None


def _fmt(x, digits: int = 3) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.{digits}f}"
    except (TypeError, ValueError):
        return str(x)


def _pick_lgbm_test_cal(blob: dict | None, target: str = "y_dinophysis_nowcast") -> dict | None:
    if not blob:
        return None
    # Ireland-style: top-level target → model keys
    block = blob.get(target) if isinstance(blob.get(target), dict) else None
    if block and "lightgbm_test_calibrated" in block:
        return block["lightgbm_test_calibrated"]
    # Scotland-style: metrics.lightgbm_test_calibrated
    metrics = blob.get("metrics")
    if isinstance(metrics, dict) and "lightgbm_test_calibrated" in metrics:
        return metrics["lightgbm_test_calibrated"]
    return None


def _print_metric_row(label: str, m: dict | None, meta_extra: str = "") -> None:
    if not m:
        print(f"  {label}: (missing)")
        return
    clim = m.get("pr_auc_clim")
    print(
        f"  {label}: PR-AUC cal={_fmt(m.get('pr_auc'))}  "
        f"clim={_fmt(clim)}  skill={_fmt(m.get('pr_auc_skill'))}  "
        f"Brier={_fmt(m.get('brier'))}  n={m.get('n')}  "
        f"prev={_fmt(m.get('prevalence'), 3)}"
        + (f"  {meta_extra}" if meta_extra else "")
    )


def main() -> int:
    print("=" * 72)
    print("PA-Marine-Model — Cork Ocean Hackathon Challenge 4 demo snapshot")
    print(f"root: {ROOT}")
    print("=" * 72)

    # --- Ireland strong ---
    print("\n[Ireland] Dinophysis nowcast — strong (9 features)")
    strong = _load(PROC / "metrics_dino_strong.json")
    meta = (strong or {}).get("_meta") or {}
    _print_metric_row(
        "LightGBM test",
        _pick_lgbm_test_cal(strong),
        meta_extra=f"feature_mode={meta.get('feature_mode')} n_feat={meta.get('n_features')}",
    )
    # also surface raw for honesty
    if strong and "y_dinophysis_nowcast" in strong:
        raw = strong["y_dinophysis_nowcast"].get("lightgbm_test")
        if raw:
            print(
                f"  LightGBM test raw PR-AUC={_fmt(raw.get('pr_auc'))} "
                f"(prefer calibrated for deck)"
            )

    # ablation pointer
    abl = _load(PROC / "dino_ablation_metrics.json")
    if isinstance(abl, dict):
        print("  ablation JSON: data/processed/dino_ablation_metrics.json")
        for key in ("baseline", "strong", "drop_weak", "sst"):
            block = abl.get(key)
            if not isinstance(block, dict):
                continue
            cal = block.get("lightgbm_test_cal") or block.get("lightgbm_test_calibrated")
            if cal:
                label = block.get("label", key)
                print(
                    f"    {label}: n_feat={block.get('n_features')} "
                    f"test PR-AUC cal={_fmt(cal.get('pr_auc'))}"
                )

    # --- Scotland ---
    print("\n[Scotland] SMC Dinophysis nowcast — strong (high/medium geocode)")
    sco = _load(PROC / "scotland_dino_metrics.json")
    sco_meta = (sco or {}).get("_meta") or {}
    _print_metric_row(
        "LightGBM test",
        _pick_lgbm_test_cal(sco),
        meta_extra=f"n_feat={sco_meta.get('n_features')}",
    )
    if sco and "irish_strong_reference" in sco:
        ref = sco["irish_strong_reference"].get("lightgbm_test_calibrated")
        _print_metric_row("Irish strong ref (same JSON)", ref)

    # --- What didn't help (compact) ---
    print("\n[Ablations that did not beat strong OISST]")
    era5 = _load(PROC / "metrics_dino_era5_wind.json")
    # ERA5 report stores both modes sometimes under nested keys — also try metrics files
    era5_strong = _load(PROC / "metrics_dino_era5_strong.json")
    if era5_strong:
        _print_metric_row("ERA5 join / strong baseline", _pick_lgbm_test_cal(era5_strong))
    if era5:
        # may be full evaluate dump for wind mode
        m = _pick_lgbm_test_cal(era5)
        if m:
            _print_metric_row("ERA5 strong+wind", m)
        else:
            print("  ERA5 wind metrics present — see era5_wind_dino_report.md")
    ostia = _load(PROC / "metrics_dino_ostia.json")
    _print_metric_row("OSTIA strong", _pick_lgbm_test_cal(ostia))
    ibi_abl = _load(PROC / "ibi_ablation_metrics.json")
    if isinstance(ibi_abl, dict):
        # common shapes: list of ablations or dict keyed by name
        rows = ibi_abl.get("ablations") if isinstance(ibi_abl.get("ablations"), list) else None
        if rows:
            for row in rows:
                name = row.get("ablation") or row.get("name") or "?"
                pr = row.get("test_pr_auc_cal") or row.get("pr_auc_cal")
                if pr is None and isinstance(row.get("lightgbm_test_cal"), dict):
                    pr = row["lightgbm_test_cal"].get("pr_auc")
                print(f"  IBI ablation {name}: test PR-AUC cal={_fmt(pr)}")
        else:
            for name, row in ibi_abl.items():
                if name.startswith("_") or not isinstance(row, dict):
                    continue
                cal = row.get("lightgbm_test_cal") or row.get("lightgbm_test_calibrated")
                pr = None
                if isinstance(cal, dict):
                    pr = cal.get("pr_auc")
                elif "test_pr_auc_cal" in row:
                    pr = row["test_pr_auc_cal"]
                if pr is not None:
                    print(f"  IBI {name}: test PR-AUC cal={_fmt(pr)} n_feat={row.get('n_features')}")
            if not any(
                isinstance(v, dict)
                and (
                    "lightgbm_test_cal" in v
                    or "lightgbm_test_calibrated" in v
                    or "test_pr_auc_cal" in v
                )
                for k, v in ibi_abl.items()
                if not str(k).startswith("_")
            ):
                print("  IBI ablation JSON present — see ibi_light_mhw_report.md")

    print("  reports: ostia_vs_oisst_report.md | era5_wind_dino_report.md | ibi_light_mhw_report.md")

    # --- Local / case study ---
    print("\n[Local Connemara + June 2023 case study]")
    local = _load(PROC / "local_sites_summary.json")
    if isinstance(local, dict):
        for key in ("mace_head", "lehanagh"):
            site = local.get(key) or local.get(key.replace("_", ""))
            # keys may be nested differently
            if site is None:
                # try top-level sites list / dict variants
                for k, v in local.items():
                    if isinstance(v, dict) and key.replace("_", "") in k.replace("_", "").lower():
                        site = v
                        break
            if isinstance(site, dict):
                print(
                    f"  {site.get('label', key)}: lat={site.get('lat')} lon={site.get('lon')} "
                    f"days={site.get('n_days')} weeks={site.get('n_weeks')} "
                    f"t=[{site.get('t_min')} … {site.get('t_max')}]"
                )
            else:
                print(f"  {key}: (see local_sites_report.md)")
    else:
        print("  local_sites_summary.json missing — see local_sites_report.md if present")

    summary_csv = PROC / "june2023_case_study_summary.csv"
    if summary_csv.exists():
        print(f"  case-study summary: {summary_csv.relative_to(ROOT)}")
        try:
            import csv

            with summary_csv.open(newline="", encoding="utf-8") as f:
                for i, row in enumerate(csv.DictReader(f)):
                    if i >= 8:
                        print("    …")
                        break
                    print(f"    {row.get('metric')}: {row.get('value')} {row.get('unit', '')}")
        except OSError as e:
            print(f"  ! could not read summary CSV: {e}")
    else:
        print("  june2023_case_study_summary.csv missing — run scripts/build_june2023_case_study.py")

    case_md = PROC / "june2023_case_study.md"
    print(f"  narrative: {case_md.relative_to(ROOT) if case_md.exists() else '(missing)'}")

    # --- Figures ---
    print("\n[Figures]")
    expected = [
        "june2023_mhw_met_temp.png",
        "june2023_dinophysis_connemara.png",
        "june2023_mace_head_tsdo.png",
    ]
    if FIG.is_dir():
        for name in expected:
            p = FIG / name
            status = "OK" if p.exists() else "MISSING"
            print(f"  [{status}] {p.relative_to(ROOT)}")
        extras = sorted(p.name for p in FIG.glob("*.png") if p.name not in expected)
        for name in extras:
            print(f"  [OK] { (FIG / name).relative_to(ROOT) }")
    else:
        print(f"  figures dir missing: {FIG.relative_to(ROOT)}")

    # --- How to run ---
    print("\n[Quick commands]")
    print("  Fixture smoke:     python scripts/run_pipeline.py --fixture")
    print("  Re-eval strong:    python scripts/evaluate.py --feature-mode strong --calibration auto")
    print("  Scotland:          python scripts/train_scotland_dino.py --skip-download")
    print("  Rebuild case:      python scripts/build_june2023_case_study.py")
    print("  Guide:             docs/HACKATHON_DEMO.md")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
