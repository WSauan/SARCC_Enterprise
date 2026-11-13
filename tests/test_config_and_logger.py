import logging
import sys
from core import config, logger


def test_get_data_dir_respects_env_override(tmp_path, monkeypatch):
    """Garante que a variável SARCC_DATA_DIR sobrepõe o caminho padrão."""
    custom_dir = tmp_path / "custom_sarcc_data"
    monkeypatch.setenv("SARCC_DATA_DIR", str(custom_dir))

    assert config.get_data_dir() == custom_dir.resolve()
    assert config.get_db_path() == custom_dir.resolve() / "sarcc.db"
    assert config.get_logs_dir() == custom_dir.resolve() / "logs"


def test_get_data_dir_uses_appdata_when_frozen(tmp_path, monkeypatch):
    """Verifica se o executável compilado (sys.frozen=True) grava em %APPDATA%\\SARCC."""
    monkeypatch.delenv("SARCC_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert config.is_dev_mode() is False
    assert config.get_data_dir() == tmp_path / "SARCC"


def test_get_max_threads_validation(monkeypatch):
    """Valida leitura e fallback de SARCC_MAX_THREADS."""
    monkeypatch.delenv("SARCC_MAX_THREADS", raising=False)
    assert config.get_max_threads(default=12) == 12

    monkeypatch.setenv("SARCC_MAX_THREADS", "20")
    assert config.get_max_threads(default=12) == 20

    monkeypatch.setenv("SARCC_MAX_THREADS", "-5")
    assert config.get_max_threads(default=12) == 12

    monkeypatch.setenv("SARCC_MAX_THREADS", "invalido")
    assert config.get_max_threads(default=12) == 12


def test_ensure_dirs_creates_data_and_logs(tmp_path, monkeypatch):
    """Garante que ensure_dirs cria as pastas de dados e logs automaticamente."""
    monkeypatch.setenv("SARCC_DATA_DIR", str(tmp_path / "sarcc_store"))
    config.ensure_dirs()

    assert config.get_data_dir().is_dir()
    assert config.get_logs_dir().is_dir()


def test_logger_works_when_stdout_is_none(tmp_path, monkeypatch):
    """Simula execução PyInstaller --windowed (sys.stdout = None) sem gerar exceções."""
    monkeypatch.setenv("SARCC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)

    root = logging.getLogger("sarcc")
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    monkeypatch.setattr(logger, "_configured", False)

    log = logger.get_logger(" gui.views.teste_windowed ")
    log.warning("Teste de aviso em modo windowed sem consola")
    log.error("Teste de erro em modo windowed")

    for h in root.handlers:
        h.flush()

    log_file = tmp_path / "logs" / "sarcc.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Teste de aviso em modo windowed sem consola" in content