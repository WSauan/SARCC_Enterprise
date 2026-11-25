import hashlib
import json
import re

from core.config import GLPI_URL, SERVER_ROOT, SHARE_ROOT, ZABBIX_IP, get_ps_scripts_dir
from core.logger import get_logger

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
            raise PsTemplateError("Manifesto de integridade corrompido.")

    try:
        with open(script_path, "r", encoding="utf-8-sig") as f:
            content = f.read().lstrip("\ufeff")

        # Injeção automática de variáveis de infraestrutura (R05)
        global_vars = {
            "share_root": SHARE_ROOT,
            "server_root": SERVER_ROOT,
            "zabbix_ip": ZABBIX_IP,
            "glpi_url": GLPI_URL,
        }
        all_vars = {**global_vars, **kwargs}

        for key, value in all_vars.items():
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


# --- Função adicionada FORA da classe, no final do arquivo (R06) ---
def extract_script_timeout(script_content: str, default_timeout: int = 300) -> int:
    """Lê a diretiva # @timeout: <segundos> no topo do script."""
    match = re.search(r"^#\s*@timeout:\s*(\d+)", script_content, re.MULTILINE)
    if match:
        return int(match.group(1))
    return default_timeout
