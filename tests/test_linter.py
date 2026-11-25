import subprocess
import sys


def test_ruff_linter_passes():
    """Garante que o código-fonte está livre de erros de lint (imports não usados, variáveis mortas, etc)."""
    # Roda o ruff em todo o projeto (ignorando pastas de build e venv)
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    assert result.returncode == 0, f"O linter encontrou problemas no código:\n{result.stdout}"
