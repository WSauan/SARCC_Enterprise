from core.credential_store import CredentialStore


def test_credential_store_dpapi_roundtrip(tmp_path, monkeypatch):
    """Valida gravação, leitura cifrada DPAPI e remoção sem tocar no APPDATA real."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert CredentialStore.exists() is False
    assert CredentialStore.load() is None

    saved = CredentialStore.save("EBSERHNET\\adm.wsauan", "SenhaSegura#2026", "VncPass#123")
    assert saved is True
    assert CredentialStore.exists() is True

    # Verifica que o ficheiro em disco não contém a senha em texto plano
    with open(CredentialStore.location(), "rb") as f:
        raw_bytes = f.read()
    assert b"SenhaSegura#2026" not in raw_bytes

    loaded = CredentialStore.load()
    assert loaded is not None
    assert loaded["user"] == "EBSERHNET\\adm.wsauan"
    assert loaded["pass"] == "SenhaSegura#2026"
    assert loaded["vnc_pass"] == "VncPass#123"

    cleared = CredentialStore.clear()
    assert cleared is True
    assert CredentialStore.exists() is False


def test_credential_store_handles_corrupted_blob(tmp_path, monkeypatch):
    """Garante que um ficheiro corrompido retorna None sem quebrar a aplicação."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    path = CredentialStore.location()
    with open(path, "wb") as f:
        f.write(b"dados_binarios_invalidos_nao_dpapi")

    assert CredentialStore.load() is None
