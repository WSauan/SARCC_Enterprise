import logging
import sys

from core import logger


def test_logger_works_when_stdout_is_none(tmp_path, monkeypatch):
    """Simula execução PyInstaller --windowed (sys.stdout = None) sem gerar exceções."""
    monkeypatch.setenv("SARCC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)

    root = logging.getLogger("sarcc")
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    monkeypatch.setattr(logger, "_configured", False)

    log = logger.get_logger("gui.views.teste_windowed")
    log.warning("Teste de aviso em modo windowed sem consola")
    log.error("Teste de erro em modo windowed")

    for h in root.handlers:
        h.flush()

    log_file = tmp_path / "logs" / "sarcc.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Teste de aviso em modo windowed sem consola" in content
