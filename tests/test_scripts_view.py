from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication

from core.database import DatabaseManager
from domain.services.script_service import ScriptService
from gui.views.scripts_view import PowerShellHighlighter, ScriptsView
from infrastructure.repositories.script_repository import ScriptRepository

_QAPP = QApplication.instance() or QApplication([])


def test_powershell_highlighter_processes_keywords_and_multiline_comments():
    """Garante que o realçador de sintaxe PowerShell processa blocos sem erros."""
    doc = QTextDocument()
    highlighter = PowerShellHighlighter(doc)
    doc.setPlainText("<#\nComentário de múltiplas linhas\n#>\nforeach ($p in $ items) { Write-Output 'OK' }")
    assert highlighter.document() == doc


def test_scripts_view_loads_and_filters_tree(tmp_path, monkeypatch):
    """Verifica carregamento da árvore de scripts por categoria e filtragem por texto."""
    db = DatabaseManager(db_path=tmp_path / "scripts_view_test.db")
    repo = ScriptRepository(db_manager=db)
    repo.create("Reiniciar Spooler", "Impressora", "Manutenção", "Restart-Service Spooler")
    repo.create("Auditoria Firewall", "Portas", "Segurança", "Get-NetFirewallProfile")

    view = ScriptsView()
    view.repo = repo
    view.service = ScriptService(repo)
    view.load_scripts_list()

    assert view.tree_scripts.topLevelItemCount() == 2

    view.filter_scripts("spooler")
    visible_categories = sum(
        1 for i in range(view.tree_scripts.topLevelItemCount())
        if not view.tree_scripts.topLevelItem(i).isHidden()
    )
    assert visible_categories == 1
    view.close()
