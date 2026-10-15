import os
from cryptography.fernet import Fernet

class SecurityManager:
    @staticmethod
    def _get_key_path():
        # A chave mestre fica escondida na pasta data
        base_dir = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(base_dir, "data", "master.key")

    @staticmethod
    def _get_or_create_key():
        key_path = SecurityManager._get_key_path()
        if not os.path.exists(key_path):
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            key = Fernet.generate_key()
            with open(key_path, "wb") as key_file:
                key_file.write(key)
        
        with open(key_path, "rb") as key_file:
            return key_file.read()

    @staticmethod
    def encrypt(text: str) -> str:
        if not text:
            return ""
        f = Fernet(SecurityManager._get_or_create_key())
        return f.encrypt(text.encode()).decode()

    @staticmethod
    def decrypt(crypto_text: str) -> str:
        if not crypto_text:
            return ""
        try:
            f = Fernet(SecurityManager._get_or_create_key())
            return f.decrypt(crypto_text.encode()).decode()
        except Exception:
            return "" # Falha na descriptografia (chave errada ou corrompida)