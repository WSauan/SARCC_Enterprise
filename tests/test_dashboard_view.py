import re
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QHeaderView

from core.ps_loader import load_ps_template
from gui.views.dashboard_view import (
    DashboardView,
    _is_temp_profile,
    _sort_profiles,
    format_profile_session_status,
    format_smart_badge,
)

_QAPP = QApplication.instance() or QApplication([])


def test_is_temp_profile_detects_temp_folders():
    assert _is_temp_profile({"Name": "TEMP", "IsTemp": True}) is True
    assert _is_temp_profile({"Name": "TEMP.EBSERHNET.001"}) is True
    assert _is_temp_profile({"Name": "adm.wsauan", "IsTemp": False}) is False
    assert _is_temp_profile({"Name": "ofelia.lisboa"}) is False


def test_format_profile_session_status_distinguishes_active_and_disconnected():
    p_active = {"Name": "adm.wsauan", "SessionState": "Ativo", "SessionId": 1, "Loaded": True}
    txt, color, can_logoff = format_profile_session_status(p_active)
    assert "Ativo (ID 1)" in txt
    assert color == Qt.GlobalColor.green
    assert can_logoff is True

    p_disc = {"Name": "maria.silva", "SessionState": "Desconectado", "SessionId": 2, "Loaded": True}
    txt_d, color_d, can_logoff_d = format_profile_session_status(p_disc)
    assert "Desconectado (ID 2)" in txt_d
    assert color_d == Qt.GlobalColor.yellow
    assert can_logoff_d is True

    p_inactive = {"Name": "joao.souza", "SessionState": "Inativo", "Loaded": False}
    txt_i, _, can_logoff_i = format_profile_session_status(p_inactive)
    assert "Inativo" in txt_i
    assert can_logoff_i is False


def test_sort_profiles_prioritizes_active_then_disconnected_then_normal_then_temp():
    profiles = [
        {"Name": "TEMP.EBSERHNET.001", "LastUse": "2026-11-10 10:00", "IsTemp": True, "SessionState": "Temp"},
        {"Name": "almeida.alisson", "LastUse": "2026-11-12 09:13", "IsTemp": False, "SessionState": "Inativo"},
        {"Name": "maria.desc", "LastUse": "2026-11-11 08:00", "IsTemp": False, "SessionState": "Desconectado", "SessionId": 2},
        {"Name": "ofelia.ativa", "LastUse": "2026-11-11 14:21", "IsTemp": False, "SessionState": "Ativo", "SessionId": 1},
    ]
    logged = {"ofelia.ativa", "maria.desc"}
    sorted_list = _sort_profiles(profiles, logged)

    assert sorted_list[0]["Name"] == "ofelia.ativa"
    assert sorted_list[1]["Name"] == "maria.desc"
    assert sorted_list[2]["Name"] == "almeida.alisson"
    assert sorted_list[3]["Name"] == "TEMP.EBSERHNET.001"


def test_format_smart_badge_colors():
    badge_ok = format_smart_badge("NVMe SSD", "Saudável (OK)")
    assert "NVMe SSD" in badge_ok
    assert "#4CAF50" in badge_ok

    badge_warn = format_smart_badge("HDD", "Alerta (Warning)")
    assert "#f0ad4e" in badge_warn


def test_dashboard_updates_hardware_smart_and_interactive_user_columns():
    fake_main = MagicMock()
    fake_main.queue_manager = MagicMock()
    fake_repo = MagicMock()

    view = DashboardView(main_window_ref=fake_main, exec_repo=fake_repo)
    assert view.tbl_profiles.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive

    sample_data = {
        "HostName": "HUL-WK-UTI01",
        "ComputerDesc": "UTI Adulto - Leito 01",
        "HardwareModel": "Daten DC3D-U",
        "SerialNumber": "BR12345678",
        "DiskPct": 45.0,
        "DiskFree": 120.0,
        "DiskTotal": 240.0,
        "DiskType": "NVMe SSD",
        "DiskSmart": "Saudável (OK)",
        "TotalRAM": 16.0,
        "UsedRAM": 6.5,
        "RAMPct": 40.6,
        "RAMSlots": "2/2 slots (3200 MHz)",
        "ActiveUsersCount": 1,
        "DisconnectedUsersCount": 1,
        "LoggedNames": ["adm.wsauan", "maria.silva"],
        "ProfilesList": [
            {"Name": "adm.wsauan", "LastUse": "2026-11-13 18:00", "Loaded": True, "IsTemp": False, "SessionState": "Ativo", "SessionId": 1},
            {"Name": "maria.silva", "LastUse": "2026-11-13 10:00", "Loaded": True, "IsTemp": False, "SessionState": "Desconectado", "SessionId": 2},
        ]
    }
    view.update_telemetry_ui(sample_data)

    assert "UTI Adulto - Leito 01" in view.lbl_desc.text()
    assert "1 Ativo / 1 Desc." in view.lbl_logged_count.text()
    assert "Ativo (ID 1)" in view.tbl_profiles.item(0, 2).text()
    assert "Desconectado (ID 2)" in view.tbl_profiles.item(1, 2).text()
    view.close()


def test_dashboard_templates_load_properly():
    script_rep = load_ps_template("dashboard", "repair_agent", agent_target="zabbix")
    assert "Repair-ZabbixAgent" in script_rep
    assert re.search(r'\$AgentTarget\s*=\s*"zabbix"', script_rep) is not None

    script_desc = load_ps_template("dashboard", "set_description", desc_b64="VVRJ")
    assert "srvcomment" in script_desc

    script_logoff = load_ps_template("dashboard", "logoff_session", username_b64="dXNlcjE=", session_id_b64="Mg==")
    assert "logoff.exe" in script_logoff

    script_net = load_ps_template("dashboard", "net_diag_reset", mode="reset_and_diag")
    assert "10.8.245.12" in script_net
    assert "flushdns" in script_net
