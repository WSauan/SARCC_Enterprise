import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from gui.views.base_view import read_text_file_safe, sanitize_filename
from infrastructure.repositories.script_repository import ScriptRepository

CREDENTIAL_PLACEHOLDERS = ("[[ADMIN_PASS]]", "[[VNC_PASS]]", "[[ADMIN_USER]]")


class ScriptService:
    """Serviço de domínio para regras de negócio, importação e validação de scripts."""

    def __init__(self, repository: Optional[ScriptRepository] = None):
        self.repo = repository or ScriptRepository()

    @staticmethod
    def requires_credentials(script_content: str) -> bool:
        """Verifica se o conteúdo de um script exige injeção de credenciais do cofre."""
        if not script_content:
            return False
        return any(ph in script_content for ph in CREDENTIAL_PLACEHOLDERS)

    @classmethod
    def any_requires_credentials(cls, scripts: List[Dict[str, Any]]) -> bool:
        """Verifica se qualquer script de uma lista selecionada para lote exige credenciais."""
        return any(cls.requires_credentials(s.get("conteudo", "")) for s in scripts)

    def import_files(self, file_paths: List[str | Path]) -> Tuple[int, int]:
        """Importa uma lista de arquivos .ps1/.txt realizando upsert. Retorna (criados, atualizados)."""
        created = 0
        updated = 0
        for path in file_paths:
            content = read_text_file_safe(path).strip()
            if not content:
                continue
            name = os.path.splitext(os.path.basename(str(path)))[0].strip()
            if not name:
                continue
            action = self.repo.upsert(
                nome=name,
                descricao="Importado via Lote",
                categoria="Outros",
                conteudo=content,
            )
            if action == "created":
                created += 1
            else:
                updated += 1
        return created, updated

    @staticmethod
    def export_to_directory(scripts: List[Dict[str, Any]], dest_dir: str | Path) -> int:
        """Exporta múltiplos scripts para arquivos .ps1 numa pasta de destino."""
        target_folder = Path(dest_dir)
        target_folder.mkdir(parents=True, exist_ok=True)
        exported = 0
        for item in scripts:
            nome = item.get("nome", "Script_SARCC")
            conteudo = (item.get("conteudo") or "").strip()
            if not conteudo:
                continue
            safe_name = sanitize_filename(nome, default="Script_SARCC").replace(" ", "_")
            file_path = target_folder / f"{safe_name}.ps1"
            file_path.write_text(conteudo, encoding="utf-8")
            exported += 1
        return exported
