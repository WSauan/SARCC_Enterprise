"""
Armazenamento seguro de credenciais usando DPAPI do Windows.

- Credenciais são criptografadas com a chave do usuário atual (DPAPI user-scoped).
- Só o MESMO usuário no MESMO Windows consegue decifrar.
- Arquivo: data/credentials.dat (blob binário cifrado).
- Nunca guarda nada em texto plano.
"""

import ctypes
import json
import os
from ctypes import wintypes

from core.logger import get_logger

log = get_logger(__name__)


# --- DPAPI via ctypes (sem pywin32) ---

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32

_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptProtectData.restype = wintypes.BOOL

_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL


def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
    data = ctypes.string_at(blob.pbData, blob.cbData)
    _kernel32.LocalFree(blob.pbData)
    return data


def _dpapi_encrypt(plaintext: bytes) -> bytes:
    buf = ctypes.create_string_buffer(plaintext, len(plaintext))
    in_blob = _DATA_BLOB(len(plaintext), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise OSError("CryptProtectData falhou")
    return _blob_to_bytes(out_blob)


def _dpapi_decrypt(ciphertext: bytes) -> bytes:
    buf = ctypes.create_string_buffer(ciphertext, len(ciphertext))
    in_blob = _DATA_BLOB(len(ciphertext), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise OSError("CryptUnprotectData falhou")
    return _blob_to_bytes(out_blob)


# --- API pública ---

class CredentialStore:
    """Armazena credenciais cifradas em %APPDATA%\\SARCC\\credentials.dat.

    Por que %APPDATA% e não a pasta do projeto?
    - DPAPI é *user-scoped*: o blob cifrado só pode ser decifrado pelo MESMO
      usuário no MESMO Windows. Se ficasse num share de rede, o blob de um
      técnico seria ilegível para outro (cada um teria que digitar a senha
      1× por máquina de qualquer forma, mas com fricção adicional).
    - Em %APPDATA%, cada técnico tem o seu próprio blob, sem colisão.
    - A pasta do projeto pode ser read-only (Program Files, share de rede),
      o que quebraria a gravação.
    """

    @classmethod
    def _store_path(cls) -> str:
        """Retorna o caminho absoluto do blob cifrado (local à máquina+usuário).

        Estrutura: %APPDATA%\\SARCC\\credentials.dat
        Fallback: ~/SARCC/credentials.dat (se APPDATA não existir)
        """
        appdata = os.environ.get("APPDATA")
        if appdata and os.path.isdir(appdata):
            store_dir = os.path.join(appdata, "SARCC")
        else:
            # Fallback para ambientes sem APPDATA (raro no Windows)
            store_dir = os.path.join(os.path.expanduser("~"), "SARCC")

        os.makedirs(store_dir, exist_ok=True)
        return os.path.join(store_dir, "credentials.dat")

    @classmethod
    def save(cls, user: str, password: str, vnc_pass: str = None) -> bool:
        try:
            payload = json.dumps({
                "user": user,
                "pass": password,
                "vnc_pass": vnc_pass or password,
            }).encode("utf-8")
            ciphertext = _dpapi_encrypt(payload)

            path = cls._store_path()
            with open(path, "wb") as f:
                f.write(ciphertext)
            log.info(f"Credenciais salvas em disco (DPAPI) em {path}")
            return True
        except Exception as e:
            log.error(f"Falha ao salvar credenciais em disco: {e}", exc_info=True)
            return False

    @classmethod
    def load(cls):
        path = cls._store_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                ciphertext = f.read()
            payload = _dpapi_decrypt(ciphertext)
            data = json.loads(payload.decode("utf-8"))
            if not data.get("user") or not data.get("pass"):
                return None
            log.info(f"Credenciais carregadas do disco para '{data['user']}'")
            return data
        except Exception as e:
            # Falha silenciosa: acontece quando outro usuário/máquina tentou
            # decifrar (DPAPI rejeita). Cai no popup normal.
            log.warning(f"Falha ao decifrar credenciais salvas (serão ignoradas): {e}")
            return None

    @classmethod
    def clear(cls) -> bool:
        try:
            path = cls._store_path()
            if os.path.exists(path):
                os.remove(path)
                log.info(f"Arquivo de credenciais removido: {path}")
                return True
            return False
        except Exception as e:
            log.error(f"Falha ao remover arquivo de credenciais: {e}")
            return False

    @classmethod
    def exists(cls) -> bool:
        return os.path.exists(cls._store_path())

    @classmethod
    def location(cls) -> str:
        """Retorna o caminho atual (útil para debug e exibição na UI)."""
        return cls._store_path()