from gui.views.history_view import HistoryView, extract_json_from_result


def test_extract_json_from_result_handles_warnings_and_timer_footer():
    """Verifica se o histórico consegue extrair o JSON mesmo com avisos antes e rodapé de tempo depois."""
    raw_log = (
        "WARNING: Aviso prévio do PowerShell\n"
        '{"Script": "Limpeza", "StatusFinal": "SUCESSO", "Inicio": "2026-11-13 08:00:00", "Fim": "2026-11-13 08:00:05"}\n\n'
        "[⏱️ Tempo de Execução da Conexão: 5.12 segundos]"
    )
    js = extract_json_from_result(raw_log)
    assert js is not None
    assert js["StatusFinal"] == "SUCESSO"
    assert js["Script"] == "Limpeza"


def test_history_format_duration():
    """Valida a formatação de segundos, minutos e horas no histórico."""
    assert HistoryView._format_duration(12.34) == "12.3s"
    assert HistoryView._format_duration(125) == "2m 5s"
    assert HistoryView._format_duration(3665) == "1h 1m 5s"
