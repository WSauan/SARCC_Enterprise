import sys
from core import resources


def test_resource_path_prioritizes_external_file_when_frozen(tmp_path, monkeypatch):
    """Em modo .exe (frozen), deve priorizar ficheiros ao lado do executável antes do _MEIPASS."""
    exe_dir = tmp_path / "exe_folder"
    meipass_dir = tmp_path / "meipass_folder"
    exe_dir.mkdir()
    meipass_dir.mkdir()

    external_logo = exe_dir / "logo.ico"
    external_logo.write_bytes(b"ICON")
    internal_file = meipass_dir / "interno.txt"
    internal_file.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "SARCC.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

    assert resources.resource_path("logo.ico") == str(external_logo)
    assert resources.resource_path("interno.txt") == str(internal_file)