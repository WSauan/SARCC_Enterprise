from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict

@dataclass
class ExecutionLog:
    target_pc: str
    script_name: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    result_data: Optional[Dict] = None
    id: Optional[int] = None

@dataclass
class ScriptDefinition:
    nome: str
    descricao: str
    caminho: str
    categoria: str
    params_fixos: str
    id: Optional[int] = None