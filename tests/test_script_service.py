from core.database import DatabaseManager
from infrastructure.repositories.script_repository import ScriptRepository
from domain.services.script_service import ScriptService


def test_script_service_detects_credential_placeholders():
    """Verifica detecção de placeholders de credenciais em scripts."""
    assert ScriptService.requires_credentials("Get-Date") is False
    assert ScriptService.requires_credentials("$u = '[[ADMIN_USER]]'") is True
    assert ScriptService.any_requires_credentials([
        {"nome": "S1", "conteudo": "Get-Process"},
        {"nome": "S2", "conteudo": "$p = '[[VNC_PASS]]'"},
    ]) is True


def test_script_service_import_and_export_batch(tmp_path):
    """Testa importação em lote (criação + atualização) e exportação para diretório."""
    db = DatabaseManager(db_path=tmp_path / "svc_scripts.db")
    repo = ScriptRepository(db_manager=db)
    service = ScriptService(repository=repo)

    src_dir = tmp_path / "import_src"
    src_dir.mkdir()
    f1 = src_dir / "Inventario_Rapido.ps1"
    f1.write_text("Get-ComputerInfo", encoding="utf-8")

    created, updated = service.import_files([f1])
    assert (created, updated) == (1, 0)

    # Reimportar o mesmo arquivo deve atualizar em vez de falhar
    f1.write_text("Get-ComputerInfo | Select-Object CsName", encoding="utf-8")
    created2, updated2 = service.import_files([f1])
    assert (created2, updated2) == (0, 1)

    export_dir = tmp_path / "export_out"
    count = service.export_to_directory(repo.list_as_dicts(), export_dir)
    assert count == 1
    assert (export_dir / "Inventario_Rapido.ps1").exists()