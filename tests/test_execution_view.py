from gui.views.execution_view import parse_targets_string


def test_parse_targets_string_deduplicates_and_strips_bom():
    """Garante que alvos repetidos, com BOM ou separados por ';' são limpos e deduplicados."""
    raw = "\ufeffhul-wk-01, HUL-WK-02; hul-wk-01\n10.8.128.14 , "
    targets = parse_targets_string(raw)
    assert targets == ["HUL-WK-01", "HUL-WK-02", "10.8.128.14"]