import os
from pathlib import Path
from typing import Any
from core.logger import get_logger
from core.config import get_ps_scripts_dir

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
        
    try:
        content = script_path.read_text(encoding='utf-8')
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