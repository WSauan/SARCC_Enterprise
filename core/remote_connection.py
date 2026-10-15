import json
import subprocess
import base64
import socket
import os
import uuid
import time
from typing import Dict, Any
from core.logger import get_logger

log = get_logger(__name__)

class RemoteConnectionManager:
    def __init__(self):
        pass 

    def _is_port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
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

    def execute_script(self, target_pc: str, script_content: str) -> Dict[str, Any]:
        start_time = time.time()
        
        script_seguro = (
            "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
            + script_content
        )

        is_local = target_pc.lower() in ['localhost', '127.0.0.1', '::1', socket.gethostname().lower()]

        if is_local:
            result = self._run_local(script_seguro)
        elif self._is_port_open(target_pc, 5985):
            try:
                result = self._run_native_remoting(target_pc, script_seguro)
            except Exception as e_native:
                result = self._run_wmi(target_pc, script_seguro, str(e_native))
        else:
            result = self._run_wmi(target_pc, script_seguro, "A porta WinRM (5985) está fechada/bloqueada pelo Firewall.")

        elapsed = time.time() - start_time
        result["log_saida"] += f"\n\n[⏱️ Tempo de Execução da Conexão: {elapsed:.2f} segundos]"
        return result

    def _run_local(self, script_content: str) -> Dict[str, Any]:
        b64 = base64.b64encode(script_content.encode('utf-16-le')).decode('utf-8')
        result = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64],
            capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return self._process_output(self._smart_decode(result.stdout), self._smart_decode(result.stderr), result.returncode)

    def _run_native_remoting(self, target_pc: str, script_content: str) -> Dict[str, Any]:
        b64_script = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
        
        local_dir = os.path.join(os.environ.get('TEMP', 'C:\\Windows\\Temp'), 'SARCC_Cache')
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
            with open(local_wrapper, 'w', encoding='utf-8') as f:
                f.write(ps_wrapper)
                
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", local_wrapper],
                capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW
            )
            
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

    def _run_wmi(self, target_pc: str, script_content: str, previous_error: str) -> Dict[str, Any]:
        b64_script = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
        
        local_dir = os.path.join(os.environ.get('TEMP', 'C:\\Windows\\Temp'), 'SARCC_Cache')
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
            
            # TIMEOUT AUMENTADO PARA 8 HORAS (28800 SEGS) PARA PERMITIR EXPURGOS DE DEZENAS/CENTENAS DE PERFIS
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
            with open(local_wrapper, 'w', encoding='utf-8') as f:
                f.write(wmi_wrapper)
                
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-NoProfile", "-NonInteractive", "-File", local_wrapper],
                capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            out = self._smart_decode(result.stdout)
            err = self._smart_decode(result.stderr)
            
            if "SARCC_WMI_ERROR" in out or result.returncode != 0:
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
        if not raw_bytes: return ""
        try:
            text = raw_bytes.decode('utf-8')
            if '' in text: raise ValueError("Corrompido")
            return text.strip()
        except (UnicodeDecodeError, ValueError):
            return raw_bytes.decode('cp850', errors='replace').strip()

    def _process_output(self, stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
        json_data = {}
        full_log = (stdout + "\n" + stderr).strip()
        
        for line in reversed(full_log.splitlines()):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    json_data = json.loads(line)
                    break 
                except json.JSONDecodeError: continue
                    
        if not json_data:
            json_data = {
                "Mensagem": "A execução ocorreu, mas não foi possível ler o pacote de dados formatados.", 
                "StatusFinal": "ERRO FATAL", 
                "Detalhes": [full_log]
            }
            
        json_data["log_bruto"] = full_log
        return {"status": "Sucesso" if exit_code == 0 else "Falha", "log_saida": full_log, "json_data": json_data}
    
    def abrir_acesso_remoto(self, ip_alvo: str):
        """
        Inicia a sessão do UltraVNC Viewer apontando para o IP alvo.
        """
        viewer_path = r"C:\Program Files\uvnc bvba\UltraVNC\vncviewer.exe"
        
        if not os.path.exists(viewer_path):
            viewer_path = os.path.join(os.getcwd(), "vncviewer.exe")
            
        if not os.path.exists(viewer_path):
            raise Exception("Arquivo vncviewer.exe não encontrado! Instale o UltraVNC ou copie o .exe para a raiz do SARCC.")
            
        try:
            subprocess.Popen([viewer_path, ip_alvo])
        except Exception as e:
            log.error(f"Falha ao iniciar VNC Viewer para {ip_alvo}: {e}", exc_info=True)
            raise Exception(f"Falha ao iniciar o processo do VNC: {str(e)}")