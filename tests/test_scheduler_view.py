from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

from core.database import DatabaseManager
from gui.views.scheduler_view import SchedulerView
from infrastructure.repositories.script_repository import ScriptRepository

_QAPP = QApplication.instance() or QApplication([])


def test_scheduler_loads_scripts_from_sqlite_and_resolves_content(tmp_path, monkeypatch):
    """Garante que o SchedulerView carrega scripts do ScriptRepository e resolve o conteúdo corretamente."""
    monkeypatch.setenv("SARCC_DATA_DIR", str(tmp_path))
    db = DatabaseManager(db_path=tmp_path / "sched_test.db")
    repo = ScriptRepository(db_manager=db)
    repo.create("Limpeza Noturna", "Expurgo", "Manutenção", "Clear-RecycleBin -Force")

    fake_main = MagicMock()
    fake_main.queue_manager = MagicMock()

    view = SchedulerView(main_window_ref=fake_main, script_repo=repo)
    assert view.cmb_scripts.count() >= 1
    assert view.cmb_scripts.itemText(0) == "Limpeza Noturna"

    name, content = view._resolve_selected_script()
    assert name == "Limpeza Noturna"
    assert content == "Clear-RecycleBin -Force"
    view.close()


def test_scheduler_toggle_trigger_visibility(tmp_path, monkeypatch):
    """Verifica a alternância dos seletores de data, hora e dias da semana conforme o gatilho."""
    monkeypatch.setenv("SARCC_DATA_DIR", str(tmp_path))
    db = DatabaseManager(db_path=tmp_path / "sched_trig.db")
    repo = ScriptRepository(db_manager=db)

    fake_main = MagicMock()
    fake_main.queue_manager = MagicMock()

    view = SchedulerView(main_window_ref=fake_main, script_repo=repo)

    # Semanalmente deve exibir os dias da semana
    view.cmb_trigger.setCurrentText("Semanalmente")
    assert view.widget_days.isHidden() is False

    # Ao Iniciar o Computador (Boot) deve ocultar data, hora e dias
    view.cmb_trigger.setCurrentText("Ao Iniciar o Computador (Boot)")
    assert view.widget_days.isHidden() is True
    assert view.date_picker.isHidden() is True
    assert view.time_picker.isHidden() is True
    view.close()
