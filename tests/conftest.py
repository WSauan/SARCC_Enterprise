import os
import tempfile
import uuid
import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Direciona basetemp e cache_dir do pytest para %TEMP%, evitando bloqueios de ACL ou sincronização do OneDrive."""
    temp_root = tempfile.gettempdir()
    if not getattr(config.option, "basetemp", None):
        config.option.basetemp = os.path.join(
            temp_root, f"sarcc_pytest_{uuid.uuid4().hex[:8]}"
        )
    if hasattr(config, "_inicache"):
        config._inicache["cache_dir"] = os.path.join(temp_root, "sarcc_pytest_cache")