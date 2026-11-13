from PyQt6.QtWidgets import QApplication
from gui.widgets.code_editor import CodeEditorWidget

_QAPP = QApplication.instance() or QApplication([])


def test_code_editor_plain_text_roundtrip():
    """Garante leitura, escrita e cálculo da área de numeração de linhas."""
    widget = CodeEditorWidget()
    sample = "Line 1\nLine 2\nLine 3"
    widget.setPlainText(sample)

    assert widget.toPlainText() == sample
    assert widget.editor.blockCount() == 3
    assert widget.editor.lineNbrAreaWidth() > 15
    widget.close()


def test_code_editor_search_find_next_and_prev():
    """Valida contagem de ocorrências e navegação circular (próximo/anterior) na barra de busca."""
    widget = CodeEditorWidget()
    widget.setPlainText("Get-Service Spooler\nStart-Service Spooler\nStop-Service Spooler")

    widget.find_input.setText("Spooler")
    assert widget.total_matches == 3
    assert widget.lbl_count.text() == "0 de 3"

    widget.find_next()
    assert widget.current_match == 1
    assert widget.lbl_count.text() == "1 de 3"

    widget.find_next()
    assert widget.current_match == 2

    widget.find_prev()
    assert widget.current_match == 1
    widget.close()


def test_code_editor_search_no_results():
    """Verifica feedback visual quando o termo pesquisado não existe no código."""
    widget = CodeEditorWidget()
    widget.setPlainText("Write-Output 'SARCC'")
    widget.find_input.setText("Inexistente")

    assert widget.total_matches == 0
    assert widget.lbl_count.text() == "Sem resultados"
    widget.close()