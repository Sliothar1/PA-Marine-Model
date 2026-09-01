import pandas as pd

from pa_marine.biotoxin import (
    dinophysis_dsp_agreement,
    toxin_station_week_panel,
)


def test_toxin_station_week_panel_exceedance():
    pivot = pd.DataFrame(
        {
            "species": ["Mytilus edulis", "Mytilus edulis", "Ostrea edulis"],
            "sampleid": ["1", "2", "3"],
            "time": pd.to_datetime(
                ["2020-06-03T00:00:00Z", "2020-06-04T00:00:00Z", "2020-06-10T00:00:00Z"], utc=True
            ),
            "latitude": [53.0, 53.0, 53.1],
            "longitude": [-9.0, -9.0, -9.1],
            "location_name": ["A", "A", "B"],
            "week_no": ["23", "23", "24"],
            "weekdatefrom": ["", "", ""],
            "location_id": [10, 10, 20],
            "region_name": ["West", "West", "West"],
            "parent_area_id": ["1", "1", "2"],
            "parent_area_code": ["X", "X", "Y"],
            "parent_area_name": ["AreaA", "AreaA", "AreaB"],
            "location_code": ["X-A", "X-A", "Y-B"],
            "tissue_type_name": ["Whole", "Whole", "Whole"],
            "samplecode": ["S1", "S2", "S3"],
            "dsp_resultvalue": [0.2, 0.05, 0.0],
            "dsp_threshold": [0.16, 0.16, 0.16],
            "dsp_result_value_text": ["0.2", "0.05", "<LOD"],
            "asp_resultvalue": [1.0, 1.0, 25.0],
            "asp_threshold": [20.0, 20.0, 20.0],
            "asp_result_value_text": ["", "", ""],
            "azp_resultvalue": [0.0, 0.0, 0.0],
            "azp_threshold": [0.16, 0.16, 0.16],
            "azp_result_value_text": ["", "", ""],
            "psp_resultvalue": [None, None, None],
            "psp_threshold": [None, None, None],
            "psp_result_value_text": ["", "", ""],
            "ptx_resultvalue": [None, None, None],
            "ptx_threshold": [None, None, None],
            "ptx_result_value_text": ["", "", ""],
            "ytx_resultvalue": [0.0, 0.0, 0.0],
            "ytx_threshold": [3.75, 3.75, 3.75],
            "ytx_result_value_text": ["", "", ""],
        }
    )
    panel = toxin_station_week_panel(pivot)
    assert len(panel) == 2
    a = panel[panel["location_id"] == 10].iloc[0]
    assert int(a["exceed_dsp"]) == 1  # max over samples
    assert int(a["exceed_asp"]) == 0
    b = panel[panel["location_id"] == 20].iloc[0]
    assert int(b["exceed_asp"]) == 1
    assert int(b["exceed_dsp"]) == 0


def test_dinophysis_dsp_agreement_smoke():
    phyto = pd.DataFrame(
        {
            "location_id": [10, 10, 20],
            "iso_year": [2020, 2020, 2020],
            "iso_week": [23, 24, 24],
            "y_dinophysis": [1, 0, 1],
            "count_dinophysis": [200.0, 0.0, 150.0],
        }
    )
    toxin = pd.DataFrame(
        {
            "location_id": [10, 10, 20],
            "iso_year": [2020, 2020, 2020],
            "iso_week": [23, 24, 24],
            "exceed_dsp": [1, 0, 0],
            "measured_dsp": [1, 1, 1],
            "max_dsp": [0.2, 0.0, 0.0],
        }
    )
    # pad to >=20 with negatives so usable path can run if we want — for smoke just check keys
    # Force small path: function returns usable False when <20
    out = dinophysis_dsp_agreement(phyto, toxin)
    assert out["n_joined_station_weeks"] == 3
    assert out["location_overlap"] == 2
    assert out["usable"] is False  # too few overlaps
