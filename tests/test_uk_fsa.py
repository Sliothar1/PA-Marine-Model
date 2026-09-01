from pathlib import Path

import pandas as pd

from pa_marine.uk_fsa import load_fsa_csv, osgb_to_lonlat, uk_station_week_panel


def test_osgb_trafalgar():
    lon, lat = osgb_to_lonlat(pd.Series(["TQ300804"]))
    assert abs(lon.iloc[0] - (-0.128)) < 0.01
    assert abs(lat.iloc[0] - 51.508) < 0.01


def test_parse_tidy_fixture(tmp_path: Path):
    csv = tmp_path / "tiny_uk.csv"
    csv.write_text(
        "SampleNumber,ProductionArea,BedID,LocalAuthority,GridReference,SamplingPoint,"
        "DateSampleCollected,PSP-Alexandrium_spp.CellsL-1,DSP-DinophysiaceaeCellsL-1,"
        "DSP-ProrocentrumLimaCellsL-1,ASP-Pseudo-nitzschia_spp.CellsL-1\n"
        "1,West Mersea,B013Z,Colchester BC,TM00001301,The Hard,2020-07-06,ND,200,ND,ND\n"
        "2,West Mersea,B013Z,Colchester BC,TM00001301,The Hard,2020-07-13,ND,ND,ND,60000\n"
    )
    df = load_fsa_csv(csv)
    assert df.iloc[0]["dinophysiaceae"] == 200.0
    assert df.iloc[1]["pseudo_nitzschia"] == 60000.0
    assert df["latitude"].notna().all()
    panel = uk_station_week_panel(df)
    assert panel["y_dinophysis"].sum() >= 1
    assert panel["y_pseudo_nitzschia"].sum() >= 1


def test_cp1252_excel_export(tmp_path: Path):
    csv = tmp_path / "uk_cp1252.csv"
    # Em-dash (0x97 in cp1252) in a title row, then tidy header — mirrors 2024 Azure exports.
    body = (
        "Phytoplankton results \u2014 FSA\n"
        "Sample number,Production area,Bed ID,Local authority,Grid reference,Sampling point,"
        "Date sample collected,Alexandrium spp. cells L-1 (PSP),Dinophysiaceae cells L-1 (DSP),"
        "Prorocentrum lima cells L-1 (DSP),Pseudo-nitzschia spp. cells L-1 (ASP)\n"
        "1,West Mersea,B013Z,Colchester BC,TM00001301,The Hard,2024-07-06,ND,150,ND,ND\n"
    )
    csv.write_bytes(body.encode("cp1252"))
    df = load_fsa_csv(csv)
    assert float(df.iloc[0]["dinophysiaceae"]) == 150.0
