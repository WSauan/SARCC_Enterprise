from pathlib import Path
from core.logger import get_logger
from core.config import get_ps_scripts_dir
import hashlib
import json

log = get_logger(__name__)


class PsTemplateError(Exception):
    pass


def load_ps_template(category: str, template_name: str, **kwargs) -> str:
    base_dir = get_ps_scripts_dir()
    script_path = base_dir / category / f"{template_name}.ps1"

    if not script_path.exists():
        error_msg = f"Ficheiro não encontrado: {script_path}"
        log.error(error_msg)
        raise PsTemplateError(error_msg)

    manifest_path = base_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # A chave no manifesto é o caminho relativo (ex: dashboard/telemetry.ps1)
            rel_key = script_path.relative_to(base_dir).as_posix()
            
            expected_hash = manifest.get(rel_key)
            if not expected_hash:
                log.warning(f"Script '{rel_key}' não encontrado no manifesto. Pulando validação.")
            else:
                actual_hash = hashlib.sha256(script_path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    error_msg = f"Falha de integridade: O hash do script {rel_key} não corresponde ao manifesto. Possível adulteração."
                    log.critical(error_msg)
                    raise PsTemplateError(error_msg)
        except json.JSONDecodeError:
            log.error("Erro ao ler manifest.json. Verifique a sintaxe do arquivo.")
            # aborta por segurança.
            raise PsTemplateError("Manifesto de integridade corrompido.")

    try:
        with open(script_path, "r", encoding="utf-8-sig") as f:
            content = f.read().lstrip("\ufeff")

        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, bool):
                val_str = "$true" if value else "$false"
            else:
                val_str = str(value)
            content = content.replace(placeholder, val_str)
        return content
    except Exception as e:
        log.error(f"Falha ao processar o template {script_path}: {e}", exc_info=True)
        raise PsTemplateError(f"Falha ao ler o ficheiro: {e}")