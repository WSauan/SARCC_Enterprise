import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from gui.views.software_view import fix_mojibake
from infrastructure.repositories.execution_repository import ExecutionRepository


def format_duration(seconds: float) -> str:
    """Formata uma duração em segundos para leitura humana (ex: 12.3s, 2m 5s, 1h 1m 5s)."""
    if seconds < 0:
        return "-"
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {seconds % 60:.0f}s"
    else:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m {((seconds % 3600) % 60):.0f}s"


def extract_json_from_result(raw_text: str) -> dict | None:
    """Extrai o dicionário JSON de um log de execução mesmo quando há linhas de texto/avisos antes do JSON."""
    if not raw_text:
        return None
    clean_res = re.sub(r"\[\s*⏱.*?Tempo de Execução.*?\]", "", str(raw_text)).strip()
    if not clean_res:
        return None
    try:
        parsed = json.loads(clean_res)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    for line in reversed(clean_res.splitlines()):
        line_str = line.strip()
        if line_str.startswith("{") and line_str.endswith("}"):
            try:
                parsed = json.loads(line_str)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return None


class AuditService:
    """Serviço de domínio para processamento de logs de auditoria e geração de relatórios GLPI."""

    def __init__(self, repository: Optional[ExecutionRepository] = None):
        self.repo = repository or ExecutionRepository()

    @staticmethod
    def parse_execution_metrics(start_time_raw: str, result_data: str) -> Dict[str, Any]:
        """Extrai horário inicial, final, duração formatada, segundos brutos e JSON de um log."""
        inicio_str = str(start_time_raw or "")[:19] if start_time_raw else "-"
        fim_str = "-"
        duracao_str = "-"
        raw_seconds = -1.0
        parsed_json = None

        if result_data:
            tempo_match = re.search(
                r"\[\s*⏱.*?Tempo de Execução.*?: ([\d\.]+) segundos\]",
                str(result_data),
            )
            if tempo_match:
                raw_seconds = float(tempo_match.group(1))
                duracao_str = format_duration(raw_seconds)

            parsed_json = extract_json_from_result(result_data)
            if parsed_json:
                if "Inicio" in parsed_json:
                    inicio_str = str(parsed_json["Inicio"])
                if "Fim" in parsed_json:
                    fim_str = str(parsed_json["Fim"])
                if "Inicio" in parsed_json and "Fim" in parsed_json:
                    try:
                        fmt = "%Y-%m-%d %H:%M:%S"
                        t_in = datetime.strptime(str(parsed_json["Inicio"]), fmt)
                        t_out = datetime.strptime(str(parsed_json["Fim"]), fmt)
                        raw_seconds = (t_out - t_in).total_seconds()
                        duracao_str = format_duration(raw_seconds)
                    except Exception:
                        pass

        return {
            "inicio": inicio_str,
            "fim": fim_str,
            "duracao": duracao_str,
            "seconds": raw_seconds,
            "json": parsed_json,
        }

    def generate_audit_report(self, execution_ids: List[int]) -> str:
        """Gera o texto completo do Relatório Oficial de Auditoria para anexar ao GLPI."""
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        lines = [
            "=" * 80,
            "                 SARCC - RELATÓRIO OFICIAL DE AUDITORIA E EXECUÇÃO",
            "=" * 80,
            f"Data de Geração do Relatório : {agora}",
            f"Total de Registros Exportados: {len(execution_ids)}",
            "=" * 80,
            "",
        ]

        for idx, log_id in enumerate(execution_ids, 1):
            row = self.repo.get_by_id(log_id)
            if not row:
                continue

            data_bruta, pc, script, status, res_data, tech, mod = row
            metrics = self.parse_execution_metrics(data_bruta, res_data)
            inicio_str = metrics["inicio"]
            fim_str = metrics["fim"] if metrics["fim"] != "-" else "N/A"
            duracao_str = metrics["duracao"] if metrics["duracao"] != "-" else "N/A"
            js = metrics["json"]

            detalhes = ""
            if js:
                msg = js.get("Mensagem", "")
                if msg:
                    detalhes += f">> MENSAGEM DO SISTEMA:\n{fix_mojibake(str(msg))}\n\n"
                if "Detalhes" in js:
                    detalhes += ">> DETALHES TÉCNICOS:\n"
                    if isinstance(js["Detalhes"], list):
                        for linha in js["Detalhes"]:
                            detalhes += f"  {fix_mojibake(str(linha))}\n"
                    else:
                        detalhes += f"  {fix_mojibake(str(js['Detalhes']))}\n"
            elif res_data:
                detalhes = f">> RAW OUTPUT:\n{fix_mojibake(str(res_data))}"

            bloco = (
                f"[ REGISTRO #{idx} - ID BD: {log_id} ] ".ljust(80, "-") + "\n"
                f"COMPUTADOR ALVO  : {pc}\n"
                f"TÉCNICO EXECUTOR : {tech}\n"
                f"MÓDULO DE ORIGEM : {mod}\n"
                f"SCRIPT / AÇÃO    : {script}\n"
                f"STATUS FINAL     : {status}\n"
                f"INÍCIO DA AÇÃO   : {inicio_str}\n"
                f"TÉRMINO DA AÇÃO  : {fim_str}\n"
                f"TEMPO DE EXECUÇÃO: {duracao_str}\n\n"
                f"{detalhes}\n"
                + ("-" * 80) + "\n"
            )
            lines.append(bloco)

        return "\n".join(lines)
