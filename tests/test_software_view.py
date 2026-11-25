from gui.views.software_view import SoftwareView, fix_mojibake


def test_fix_mojibake_repairs_corrupted_utf8():
    """Garante que strings UTF-8 lidas como CP1252 têm a acentuação restaurada."""
    assert fix_mojibake("CÃ¢mera do Windows") == "Câmera do Windows"
    assert fix_mojibake("Captura e EsboÃ§o") == "Captura e Esboço"
    assert fix_mojibake("Texto Limpo") == "Texto Limpo"
    assert fix_mojibake("") == ""


def test_is_system_app_identifies_windows_packages():
    """Valida se pacotes MSIX e componentes de sistema são filtrados corretamente."""
    assert SoftwareView._is_system_app(SoftwareView, "MSIX\\Microsoft.WindowsCamera_2026", "Câmera do Windows") is True
    assert SoftwareView._is_system_app(SoftwareView, "Microsoft.EdgeWebView2Runtime", "Microsoft Edge WebView2") is True
    assert SoftwareView._is_system_app(SoftwareView, "VideoLAN.VLC", "VLC media player") is False
    assert SoftwareView._is_system_app(SoftwareView, "PuTTY.PuTTY", "PuTTY") is False
