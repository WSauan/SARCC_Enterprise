import re
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from core.ps_loader import load_ps_template
from gui.views.dashboard_view import (
    _is_temp_profile, _sort_profiles, format_smart_badge, DashboardView
)

_QAPP = QApplication.instance() or QApplication([])


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


def test_format_smart_badge_colors():
    badge_ok = format_smart_badge("NVMe SSD", "Saudável (OK)")
    assert "NVMe SSD" in badge_ok
    assert "#4CAF50" in badge_ok

    badge_warn = format_smart_badge("HDD", "Alerta (Warning)")
    assert "#f0ad4e" in badge_warn


def test_dashboard_updates_hardware_and_smart_telemetry():
    fake_main = MagicMock()
    fake_main.queue_manager = MagicMock()
    fake_repo = MagicMock()

    view = DashboardView(main_window_ref=fake_main, exec_repo=fake_repo)
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
    }
    view.update_telemetry_ui(sample_data)

    assert "UTI Adulto - Leito 01" in view.lbl_desc.text()
    assert "Daten DC3D-U" in view.lbl_hw_model.text()
    assert "BR12345678" in view.lbl_serial.text()
    assert "NVMe SSD" in view.lbl_disk_smart.text()
    assert "2/2 slots (3200 MHz)" in view.lbl_ram_slots.text()
    view.close()


def test_repair_agent_template_loads_properly():
    script = load_ps_template("dashboard", "repair_agent", agent_target="zabbix")
    assert "Repair-ZabbixAgent" in script
    assert "Repair-DesktopInfo" in script
    assert re.search(r'\$AgentTarget\s*=\s*"zabbix"', script) is not None