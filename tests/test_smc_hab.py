from pathlib import Path

import pandas as pd

from pa_marine.smc import (
    load_smc_phytoplankton,
    smc_phyto_station_week_panel,
    _parse_count,
    _parse_toxin_value,
)


def test_parse_count_rejects():
    assert pd.isna(_parse_count("Rejected "))
    assert pd.isna(_parse_count("Unsuitable "))
    assert _parse_count("160") == 160.0
    assert _parse_count("ND") == 0.0


def test_parse_toxin_flag():
    assert _parse_toxin_value("<RL") == 0.0
    assert _parse_toxin_value("287") == 287.0
    assert pd.isna(_parse_toxin_value("-"))


def test_phyto_panel_no_coords(tmp_path: Path):
    csv = tmp_path / "phy.csv"
    csv.write_text(
        "OverallCategory,PseudoNitzschiaResultValue,AlexandriumResultValue,DinophysisResultValue,"
        "ProrocentrumLimaResultValue,ProrocentrumCordatumResultValue,LingulodiniumPolyedrumResultValue,"
        "LingulaulaxPolyedraResultValue,ProtoceratiumReticulatumResultValue,Id,CollectedTimestamp,"
        "ReceivedTimestamp,Sin,LocalAuthorityName,AreaName,SiteName,SpeciesCommonName,PodNumber\n"
        ",0,0,200,0,0,,,0,1,15/07/2024 00:00:00,15/07/2024 00:00:00,AB-1-1-08,Argyll,Loch Test,Site A,mussel,1\n"
        ",60000,50,50,0,0,,,0,2,22/07/2024 00:00:00,22/07/2024 00:00:00,AB-1-1-08,Argyll,Loch Test,Site A,mussel,1\n"
    )
    areas = pd.DataFrame(
        [{"AreaName": "Loch Test", "Sin": "AB-1-1-08", "LocalAuthorityName": "Argyll"}]
    )
    df = load_smc_phytoplankton(csv)
    panel = smc_phyto_station_week_panel(df, areas=areas)
    assert panel["y_dinophysis"].sum() == 1
    assert panel["y_pseudo_nitzschia"].sum() == 1
    assert panel["y_alexandrium"].sum() == 1
    assert panel["latitude"].isna().all()
    assert panel["in_smc_areas"].all()
