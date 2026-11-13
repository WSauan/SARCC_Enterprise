from gui.views.dashboard_view import _is_temp_profile, _sort_profiles


def test_is_temp_profile_detects_temp_folders():
    assert _is_temp_profile({"Name": "TEMP", "IsTemp": True}) is True
    assert _is_temp_profile({"Name": "TEMP.EBSERHNET.001"}) is True
    assert _is_temp_profile({"Name": "adm.wsauan", "IsTemp": False}) is False
    assert _is_temp_profile({"Name": "ofelia.lisboa"}) is False


def test_sort_profiles_prioritizes_logged_then_normal_then_temp():
    profiles = [
        {"Name": "TEMP.EBSERHNET.001", "LastUse": "2026-11-10 10:00", "IsTemp": True},
        {"Name": "almeida.alisson", "LastUse": "2026-11-10 09:13", "IsTemp": False},
        {"Name": "ofelia.lisboa", "LastUse": "2026-11-11 14:21", "IsTemp": False},
    ]
    logged = {"ofelia.lisboa"}
    sorted_list = _sort_profiles(profiles, logged)

    assert sorted_list[0]["Name"] == "ofelia.lisboa"
    assert sorted_list[1]["Name"] == "almeida.alisson"
    assert sorted_list[2]["Name"] == "TEMP.EBSERHNET.001"