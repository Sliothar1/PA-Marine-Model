from pa_marine.erddap import lon_to_oisst_360


def test_lon_conversion():
    assert abs(lon_to_oisst_360(-10.125) - 349.875) < 1e-6
    assert lon_to_oisst_360(5.0) == 5.0
