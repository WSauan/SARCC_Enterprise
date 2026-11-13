from gui.views.shell_view import format_console_html


def test_format_console_html_escapes_angle_brackets_and_repairs_mojibake():
    """Garante que tags do PowerShell não sejam engolidas pelo QTextEdit.insertHtml."""
    raw = "CÃ¢mera [System.String] & <# Comentario #>\nLinha 2"
    html = format_console_html(raw)
    assert "Câmera" in html
    assert "&amp;" in html
    assert "&lt;# Comentario #&gt;<br>Linha 2" in html