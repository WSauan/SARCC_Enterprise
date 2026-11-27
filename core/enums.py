from enum import Enum


class ExecutionStatus(str, Enum):
    SUCCESS = "Sucesso"
    WARNING = "Alerta"
    ERROR = "Erro"
    PENDING = "Pendente"

    @classmethod
    def normalize(cls, raw_status: str) -> str:
        """Converte qualquer string de status do sistema para o padrão amigável."""
        if not raw_status:
            return cls.PENDING.value

        s = str(raw_status).upper()
        if "SUCESSO" in s or "SUCCESS" in s:
            return cls.SUCCESS.value
        if "ALERTA" in s or "WARNING" in s or "PARCIAL" in s:
            return cls.WARNING.value
        if "ERRO" in s or "FALHA" in s or "ERROR" in s or "FATAL" in s:
            return cls.ERROR.value
        if "PENDENTE" in s:
            return cls.PENDING.value

        return raw_status.capitalize()
