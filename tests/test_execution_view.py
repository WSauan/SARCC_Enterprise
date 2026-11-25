from gui.views.execution_view import (
    _ip_in_subnet,
    expand_subnet_range,
    parse_targets_string,
)


def test_parse_targets_string_deduplicates_and_strips_bom():
    """Garante que alvos repetidos, com BOM ou separados por ';' são limpos e deduplicados."""
    raw = "\ufeffhul-wk-01, HUL-WK-02; hul-wk-01\n10.8.128.14 , "
    targets = parse_targets_string(raw)
    assert targets == ["HUL-WK-01", "HUL-WK-02", "10.8.128.14"]


def test_expand_subnet_range_and_ip_match():
    """Valida expansão de intervalos e CIDR além da pertinência na sub-rede."""
    ips = expand_subnet_range("192.168.1.10-12")
    assert ips == ["192.168.1.10", "192.168.1.11", "192.168.1.12"]

    cidr_ips = expand_subnet_range("10.8.128.0/30")
    assert cidr_ips == ["10.8.128.1", "10.8.128.2"]

    assert _ip_in_subnet("10.8.128.25", "10.8.128.0/24") is True
    assert _ip_in_subnet("10.8.129.25", "10.8.128.0/24") is False
