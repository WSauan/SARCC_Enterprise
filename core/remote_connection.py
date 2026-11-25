import base64
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Dict, List, Optional

from core.logger import get_logger

log = get_logger(__name__)


def resolve_target_hostname(target: str, timeout: float = 0.8) -> str:
    """Se target for um IP válido, tenta resolver o hostname; se falhar, retorna o IP."""
    cleaned = str(target or "").strip().upper()
    if not cleaned:
        return ""
    try:
        ipaddress.ip_address(cleaned)
    except ValueError:
        return cleaned

    def _lookup() -> str:
        fqdn = socket.gethostbyaddr(cleaned)[0]
        short_name = fqdn.split(".")[0].strip().upper()
        return short_name if short_name else cleaned

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_lookup)
            return future.result(timeout=timeout)
    except (socket.herror, socket.gaierror, OSError, FutureTimeoutError, Exception):
        return cleaned


class RemoteConnectionManager:
    def __init__(self):
        pass

    def _is_port_open(self, host: str, port: int, timeout: float = 0.8) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception as e:
            log.debug(f"Porta {port} em {host} fechada/filtrada: {e}")
            return False
        finally:
            s.close()

    def ping_host(self, host: str, timeout_ms: int = 500) -> bool:
        """Verifica resposta ICMP (Ping) em um único host."""
        target = str(host or "").strip()
        if not target:
            return False
        if target.lower() in ("localhost", "127.0.0.1", "::1", socket.gethostname().lower()):
            return True
        try:
            res = subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout_ms), target],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            out_low = (res.stdout or "").lower()
            return res.returncode == 0 and ("ttl=" in out_low or "time<" in out_low or "tempo<" in out_low)
        except Exception:
            return False

    def probe_host(self, target_pc: str, port_timeout: float = 0.8) -> Dict[str, Any]:
        """
        Sonda em paralelo WinRM (5985) e SMB/WMI (445) com timeout curto.
        Só executa Ping caso ambas as portas estejam fechadas, evitando falso negativo
        quando o ICMP está bloqueado no firewall mas o gerenciamento está ativo.
        """
        host = str(target_pc or "").strip()
        if not host:
            return {"reachable": False, "winrm_open": False, "smb_open": False, "ping_ok": False, "reason": "Alvo vazio."}

        if host.lower() in ("localhost", "127.0.0.1", "::1", socket.gethostname().lower()):
            return {"reachable": True, "winrm_open": True, "smb_open": True, "ping_ok": True, "reason": "Local"}

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_5985 = pool.submit(self._is_port_open, host, 5985, port_timeout)
            f_445 = pool.submit(self._is_port_open, host, 445, port_timeout)
            winrm_open = f_5985.result()
            smb_open = f_445.result()

        if winrm_open or smb_open:
            return {
                "reachable": True,
                "winrm_open": winrm_open,
                "smb_open": smb_open,
                "ping_ok": True,
                "reason": "OK"
            }

        ping_ok = self.ping_host(host, timeout_ms=500)
        if ping_ok:
            reason = (
                f"Estação '{host}' responde a Ping, mas as portas WinRM (5985) e SMB (445) "
                "estão fechadas ou bloqueadas pelo Firewall."
            )
        else:
            reason = (
                f"Estação '{host}' offline ou inacessível na rede "
                "(sem resposta de Ping e portas 5985/445 fechadas)."
            )

        return {
            "reachable": False,
            "winrm_open": False,
            "smb_open": False,
            "ping_ok": ping_ok,
            "reason": reason
        }

    def execute_script(self, target_pc: str, script_content: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        start_time = time.time()
        resolved_target = resolve_target_hostname(target_pc) or str(target_pc or "").strip()

        script_seguro = (
            "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
            + script_content
        )

        is_local = resolved_target.strip().lower() in [
            "localhost", "127.0.0.1", "::1", socket.gethostname().lower()
        ]

        if is_local:
            result = self._run_local(script_seguro, timeout_seconds=timeout_seconds)
        else:
            probe = self.probe_host(resolved_target, port_timeout=0.8)
            if not probe["reachable"]:
                elapsed = time.time() - start_time
                return {
                    "status": "Erro Fatal",
                    "log_saida": f"{probe['reason']}\n\n[⏱️ Tempo de Execução da Conexão: {elapsed:.2f} segundos]",
                    "json_data": {}
                }

            if probe["winrm_open"]:
                try:
                    result = self._run_native_remoting(resolved_target, script_seguro, timeout_seconds=timeout_seconds)
                except Exception as e_native:
                    result = self._run_wmi(resolved_target, script_seguro, str(e_native), timeout_seconds=timeout_seconds)
            else:
                result = self._run_wmi(
                    resolved_target,
                    script_seguro,
                    "A porta WinRM (5985) está fechada/bloqueada pelo Firewall.",
                    timeout_seconds=timeout_seconds
                )

        elapsed = time.time() - start_time
        result["log_saida"] += f"\n\n[⏱️ Tempo de Execução da Conexão: {elapsed:.2f} segundos]"
        return result

    def _run_local(self, script_content: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        local_dir = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "SARCC_Cache")
        os.makedirs(local_dir, exist_ok=True)
        script_id = uuid.uuid4().hex[:8]
        local_script = os.path.join(local_dir, f"local_{script_id}.ps1")

        try:
            with open(local_script, "w", encoding="utf-8-sig") as f:
                f.write(script_content)

            try:
                result = subprocess.run(
                    [
                        "powershell.exe", "-ExecutionPolicy", "Bypass",
                        "-NoProfile", "-NonInteractive", "-File", local_script
                    ],
                    capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=timeout_seconds
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "Erro Fatal",
                    "log_saida": f"Tempo limite de execução local excedido ({timeout_seconds}s). O processo foi abortado.",
                    "json_data": {}
                }
            return self._process_output(
                self._smart_decode(result.stdout),
                self._smart_decode(result.stderr),
                result.returncode
            )
        finally:
            try:
                os.remove(local_script)
            except OSError as e:
                log.debug(f"Falha ao remover script local temporário: {e}")

    def _run_native_remoting(self, target_pc: str, script_content: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        b64_script = base64.b64encode(script_content.encode("utf-8")).decode("utf-8")

        local_dir = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "SARCC_Cache")
        os.makedirs(local_dir, exist_ok=True)
        script_id = uuid.uuid4().hex[:8]
        local_wrapper = os.path.join(local_dir, f"winrm_{script_id}.ps1")

        ps_wrapper = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            $b64 = "{b64_script}"
            $DecodedScript = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))
            $ScriptBlock = [scriptblock]::Create($DecodedScript)

            $opt = New-PSSessionOption -SkipCACheck -SkipCNCheck -SkipRevocationCheck
            Invoke-Command -ComputerName '{target_pc}' -SessionOption $opt -ScriptBlock $ScriptBlock
        }} catch {{
            Write-Output "SARCC_WINRM_ERROR: $($_.Exception.Message)"
            exit 1
        }}
        """

        try:
            with open(local_wrapper, "w", encoding="utf-8") as f:
                f.write(ps_wrapper)

            try:
                result = subprocess.run(
                    [
                        "powershell.exe", "-ExecutionPolicy", "Bypass",
                        "-NoProfile", "-NonInteractive", "-File", local_wrapper
                    ],
                    capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=timeout_seconds
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "Erro Fatal",
                    "log_saida": f"Tempo limite do WinRM excedido ({timeout_seconds}s). O comando pode estar travado no alvo.",
                    "json_data": {}
                }

            out = self._smart_decode(result.stdout)
            err = self._smart_decode(result.stderr)

            if "SARCC_WINRM_ERROR" in out or result.returncode != 0:
                raise Exception(out.replace("SARCC_WINRM_ERROR: ", "").strip() if out else err)

            return self._process_output(out, err, result.returncode)
        finally:
            try:
                os.remove(local_wrapper)
            except OSError as e:
                log.debug(f"Falha ao remover wrapper WinRM temporário: {e}")

    def _run_wmi(self, target_pc: str, script_content: str, previous_error: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        b64_script = base64.b64encode(script_content.encode("utf-8")).decode("utf-8")

        local_dir = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "SARCC_Cache")
        os.makedirs(local_dir, exist_ok=True)
        script_id = uuid.uuid4().hex[:8]
        local_wrapper = os.path.join(local_dir, f"wmi_{script_id}.ps1")

        remote_ps1 = rf"C:\Windows\Temp\s_{script_id}.ps1"
        remote_json = rf"C:\Windows\Temp\o_{script_id}.json"
        unc_ps1 = rf"\\{target_pc}\C$\Windows\Temp\s_{script_id}.ps1"
        unc_json = rf"\\{target_pc}\C$\Windows\Temp\o_{script_id}.json"

        wmi_wrapper = f"""
        $ErrorActionPreference = 'Stop'
        try {{
            & cmd.exe /c "net use \\\\{target_pc}\\C$ /delete /y >nul 2>&1"

            $netUseOut = & cmd.exe /c "net use \\\\{target_pc}\\C$ 2>&1"
            if ($LASTEXITCODE -ne 0) {{ throw "Acesso Negado ou Disco C$ inacessível via SMB (445)." }}

            $b64 = "{b64_script}"
            $DecodedScript = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))
            $WmiRunner = "try {{ & {{ $DecodedScript }} | Out-File '{remote_json}' -Encoding UTF8 -Force }} catch {{ `$_.Exception.Message | Out-File '{remote_json}' -Encoding UTF8 -Force }}; Remove-Item `$PSCommandPath -Force -ErrorAction SilentlyContinue"

            [IO.File]::WriteAllText('{unc_ps1}', $WmiRunner, [System.Text.Encoding]::UTF8)

            $cmd = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -NoProfile -File {remote_ps1}"
            Invoke-WmiMethod -Path "Win32_Process" -Name "Create" -ArgumentList $cmd -ComputerName '{target_pc}' | Out-Null

            $timeout = 28800
            $elapsed = 0
            $result = ""
            while ($elapsed -lt $timeout) {{
                if (Test-Path '{unc_json}') {{
                    Start-Sleep -Milliseconds 500
                    try {{
                        $result = [IO.File]::ReadAllText('{unc_json}', [System.Text.Encoding]::UTF8)
                        Remove-Item '{unc_json}' -Force -ErrorAction SilentlyContinue
                        Remove-Item '{unc_ps1}' -Force -ErrorAction SilentlyContinue
                        break
                    }} catch {{ }}
                }}
                Start-Sleep -Seconds 1
                $elapsed++
            }}

            & cmd.exe /c "net use \\\\{target_pc}\\C$ /delete /y >nul 2>&1"

            if ($result) {{ Write-Output $result }}
            else {{ throw "WMI demorou mais de 8 Horas para responder. A execucao pode ter travado ou ainda esta rodando no alvo." }}

        }} catch {{
            $errMsg = $_.Exception.Message
            & cmd.exe /c "net use \\\\{target_pc}\\C$ /delete /y >nul 2>&1"
            Write-Output "SARCC_WMI_ERROR: $errMsg"
            exit 1
        }}
        """

        try:
            with open(local_wrapper, "w", encoding="utf-8") as f:
                f.write(wmi_wrapper)

            try:
                result = subprocess.run(
                    [
                        "powershell.exe", "-ExecutionPolicy", "Bypass",
                        "-NoProfile", "-NonInteractive", "-File", local_wrapper
                    ],
                    capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=timeout_seconds
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "Erro Fatal",
                    "log_saida": f"Tempo limite do WMI excedido ({timeout_seconds}s). O comando pode estar travado no alvo.",
                    "json_data": {}
                }

            out = self._smart_decode(result.stdout)
            err = self._smart_decode(result.stderr)

            if "SARCC_WINRM_ERROR" in out or "SARCC_WMI_ERROR" in out or result.returncode != 0:
                raise Exception(out.replace("SARCC_WMI_ERROR: ", "").strip() if out else err)

            return self._process_output(out, "", 0)
        except Exception as e:
            erro_limpo = str(e).strip()
            log.error(
                f"Falha total em {target_pc} (WinRM: {previous_error} | WMI: {erro_limpo})",
                exc_info=True,
            )
            return {
                "status": "Erro Fatal",
                "log_saida": f"WinRM (Primário): {previous_error}\n\nWMI (Secundário): {erro_limpo}",
                "json_data": {}
            }
        finally:
            try:
                os.remove(local_wrapper)
            except OSError as e:
                log.debug(f"Falha ao remover wrapper WMI temporário: {e}")

    def _smart_decode(self, raw_bytes: bytes) -> str:
        if not raw_bytes:
            return ""
        if isinstance(raw_bytes, str):
            return raw_bytes.strip()
        try:
            text = raw_bytes.decode("utf-8")
            if "\ufffd" in text:
                raise ValueError("Corrompido")
            return text.strip()
        except (UnicodeDecodeError, ValueError):
            return raw_bytes.decode("cp850", errors="replace").strip()

    def _process_output(self, stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
        json_data = {}
        full_log = (stdout + "\n" + stderr).strip()

        for line in reversed(full_log.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    json_data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if not json_data:
            json_data = {
                "Mensagem": "A execução ocorreu, mas não foi possível ler o pacote de dados formatados.",
                "StatusFinal": "ERRO FATAL",
                "Detalhes": [full_log]
            }

        json_data["log_bruto"] = full_log
        return {
            "status": "Sucesso" if exit_code == 0 else "Falha",
            "log_saida": full_log,
            "json_data": json_data
        }

    @staticmethod
    def _get_search_dirs() -> List[str]:
        """Retorna os diretórios base do SARCC (suporta execução via código-fonte e via PyInstaller .exe)."""
        dirs = []
        if getattr(sys, "frozen", False):
            dirs.append(os.path.dirname(sys.executable))
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                dirs.append(meipass)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        dirs.append(project_root)
        dirs.append(os.getcwd())
        return list(dict.fromkeys(dirs))

    def localizar_vnc_viewer(self) -> Optional[str]:
        """Localiza o executável do VNC Viewer nos diretórios portáteis do SARCC ou instalações padrão."""
        candidates = []
        for d in self._get_search_dirs():
            candidates.append(os.path.join(d, "vncviewer.exe"))

        candidates.extend([
            r"C:\Program Files\uvnc bvba\UltraVNC\vncviewer.exe",
            r"C:\Program Files (x86)\uvnc bvba\UltraVNC\vncviewer.exe",
            r"C:\Program Files\TightVNC\tvnviewer.exe",
            r"C:\Program Files (x86)\TightVNC\tvnviewer.exe",
        ])

        for path in candidates:
            if os.path.exists(path):
                return path

        return shutil.which("vncviewer")

    def localizar_anydesk(self) -> Optional[str]:
        """Localiza o executável do AnyDesk nos diretórios portáteis, Program Files ou PATH."""
        candidates = []
        for d in self._get_search_dirs():
            candidates.append(os.path.join(d, "AnyDesk.exe"))

        candidates.extend([
            r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
            r"C:\Program Files\AnyDesk\AnyDesk.exe",
            os.path.expandvars(r"%PROGRAMDATA%\AnyDesk\AnyDesk.exe"),
            os.path.expandvars(r"%APPDATA%\AnyDesk\AnyDesk.exe"),
        ])

        for path in candidates:
            if os.path.exists(path):
                return path

        return shutil.which("anydesk")

    def abrir_acesso_remoto(self, ip_alvo: str):
        """Inicia a sessão do UltraVNC Viewer apontando para o IP/Host alvo."""
        viewer_path = self.localizar_vnc_viewer()
        if not viewer_path:
            raise FileNotFoundError(
                "Arquivo vncviewer.exe não encontrado! Instale o UltraVNC ou mantenha o vncviewer.exe junto ao executável do SARCC."
            )

        args = [viewer_path, ip_alvo]
        for d in self._get_search_dirs():
            opt_file = os.path.join(d, "options.vnc")
            if os.path.exists(opt_file):
                args.extend(["-config", opt_file])
                break

        try:
            subprocess.Popen(args)
        except Exception as e:
            log.error(f"Falha ao iniciar VNC Viewer para {ip_alvo}: {e}", exc_info=True)
            raise RuntimeError(f"Falha ao iniciar o processo do VNC: {str(e)}")

    def abrir_anydesk(self, alvo: str):
        """Inicia o AnyDesk apontando para o ID ou Hostname alvo."""
        anydesk_path = self.localizar_anydesk()
        if not anydesk_path:
            raise FileNotFoundError(
                "AnyDesk.exe não encontrado nesta estação! Instale o AnyDesk ou coloque o AnyDesk.exe na pasta do SARCC."
            )
        try:
            subprocess.Popen([anydesk_path, alvo])
        except Exception as e:
            log.error(f"Falha ao iniciar AnyDesk para {alvo}: {e}", exc_info=True)
            raise RuntimeError(f"Falha ao iniciar o AnyDesk: {str(e)}")
