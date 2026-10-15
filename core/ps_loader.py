"""
Loader de templates PowerShell.

Estrutura:
    ps_scripts/<namespace>/<nome>.ps1

Os .ps1 são recursos read-only do bundle. São carregados em runtime e têm
placeholders {{VAR}} substituídos pelos valores passados.

POR QUE {{VAR}} E NÃO str.format()?
────────────────────────────────────
PowerShell usa { e } intensamente: blocos (if {}), hashtables (@{...}),
scriptblocks ({ $_ }). Se usássemos str.format(), TODA chave teria que ser
escrita como {{ e }} nos .ps1 — ilegível e frágil.

O delimitador {{VAR}} (duplo) é substituído literalmente por str.replace()
sem nenhuma mágica. Chaves simples { } do PowerShell ficam intactas.

EXEMPLO:
    template  →  "Stop-Process -Id {{pid}} -Force"
    chamada   →  load_ps_template("ns", "kill", pid=1234)
    resultado →  "Stop-Process -Id 1234 -Force"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import get_ps_scripts_dir


class PsTemplateError(Exception):
    """Falha ao carregar ou renderizar um template PowerShell."""


def load_ps_template(namespace: str, name: str, **variables: Any) -> str:
    """
    Carrega e renderiza um script PowerShell.

    Args:
        namespace: subpasta em ps_scripts/ (ex: "system_manager").
        name:      nome do arquivo SEM extensão (ex: "kill_process").
        **variables: pares chave/valor substituídos em {{chave}}.

    Returns:
        Conteúdo do script com os placeholders substituídos.

    Raises:
        PsTemplateError: se o arquivo não existir ou não puder ser lido.

    Exemplo:
        script = load_ps_template(
            "system_manager", "kill_process",
            pid=1234, nome="notepad",
        )
    """
    path = get_ps_scripts_dir() / namespace / f"{name}.ps1"
    if not path.exists():
        raise PsTemplateError(f"Template PowerShell não encontrado: {path}")

    try:
        template = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PsTemplateError(f"Falha ao ler {path}: {e}") from e

    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value))

    return template