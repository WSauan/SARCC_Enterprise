import os
import json
import re
import subprocess
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QComboBox,
    QMessageBox,
    QCheckBox,
    QAbstractItemView,
    QTabWidget,
    QDialog,
    QInputDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from gui.dialogs import CredentialDialog
from core.credential_store import CredentialStore
from core.remote_connection import RemoteConnectionManager
from core.task_queue import TaskQueueManager
from gui.views.base_view import BaseView
from core.logger import get_logger

log = get_logger(__name__)


class OnlineSearchDialog(QDialog):
    def __init__(self, engine="Winget", parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle(f"Pesquisar Pacotes Online ({self.engine})")
        self.resize(650, 450)
        self.selected_packages = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        search_layout = QHBoxLayout()
        self.inp_search = QLineEdit()
        self.inp_search.setFixedHeight(32)
        self.inp_search.setPlaceholderText(
            f"Digite o nome para buscar no {self.engine}..."
        )
        self.inp_search.setStyleSheet("padding: 0 10px;")
        self.inp_search.returnPressed.connect(self.search_packages)

        btn_search = QPushButton("🔍 Buscar")
        btn_search.setFixedHeight(32)
        btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_search.setStyleSheet(
            "background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        btn_search.clicked.connect(self.search_packages)

        search_layout.addWidget(self.inp_search)
        search_layout.addWidget(btn_search)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID do Pacote", "Nome", "Versão"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        lbl_aviso = QLabel(
            f"<i>Requisito: O {self.engine} deve estar instalado nesta máquina local.</i>"
        )
        lbl_aviso.setStyleSheet("color: #888;")
        btn_layout.addWidget(lbl_aviso)
        btn_layout.addStretch()

        btn_add = QPushButton("➕ Adicionar Selecionados")
        btn_add.setFixedHeight(32)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            "background-color: #1e8a5e; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        btn_add.clicked.connect(self.add_selected)
        btn_layout.addWidget(btn_add)
        layout.addLayout(btn_layout)

    def search_packages(self):
        term = self.inp_search.text().strip()
        if not term:
            return

        self.table.setRowCount(0)
        titulo_original = self.windowTitle()
        self.setWindowTitle(f"Buscando '{term}' no {self.engine}... Aguarde.")

        try:
            if self.engine == "Chocolatey":
                choco_path = r"C:\\ProgramData\\chocolatey\\bin\\choco.exe"
                comando = f'"{choco_path}" search "{term}" -r'
                result = subprocess.run(
                    comando,
                    capture_output=True,
                    text=False,
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self._parse_chocolatey(self._smart_decode(result.stdout))
            else:
                comando = f'winget search "{term}" --accept-source-agreements --disable-interactivity'
                result = subprocess.run(
                    comando,
                    capture_output=True,
                    text=False,
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                stdout = self._smart_decode(result.stdout)
                stderr = self._smart_decode(result.stderr)

                if not stdout.strip():
                    self._show_winget_diagnostic(stderr, result.returncode)
                    return

                self._parse_winget(stdout)
        finally:
            self.setWindowTitle(titulo_original)

    @staticmethod
    def _smart_decode(raw_bytes) -> str:
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

    def _show_winget_diagnostic(self, stderr: str, returncode: int):
        """Mensagem clara quando Winget retorna vazio."""
        low = (stderr or "").lower()
        if (
            "não reconhecido" in low
            or "not recognized" in low
            or "não pode ser encontrado" in low
        ):
            QMessageBox.critical(
                self,
                "Winget não instalado",
                "O Winget não foi encontrado no PATH desta máquina.\n\n"
                "Instale o 'App Installer' pela Microsoft Store\n"
                "ou baixe em: https://aka.ms/winget-cli",
            )
        elif "internet" in low or "network" in low or "0x8a150014" in low:
            QMessageBox.critical(
                self,
                "Sem acesso à internet",
                "O Winget não conseguiu alcançar os servidores da Microsoft.\n\n"
                "Verifique proxy/firewall desta máquina local (onde o SARCC roda).",
            )
        else:
            QMessageBox.warning(
                self,
                "Winget não retornou dados",
                f"Winget executou mas não retornou saída.\n\n"
                f"Código de saída: {returncode}\n"
                f"stderr: {stderr[:500] if stderr else '(vazio)'}",
            )

    def _parse_chocolatey(self, stdout):
        if not stdout.strip():
            QMessageBox.information(
                self, "Busca", "Nenhum pacote encontrado no Chocolatey."
            )
            return

        linhas = stdout.split("\n")
        encontrou = False
        for linha in linhas:
            linha = linha.strip()
            if "|" in linha:
                partes = linha.split("|")
                if len(partes) >= 2:
                    encontrou = True
                    row_pos = self.table.rowCount()
                    self.table.insertRow(row_pos)
                    self.table.setItem(row_pos, 0, QTableWidgetItem(partes[0].strip()))
                    self.table.setItem(row_pos, 1, QTableWidgetItem(partes[0].strip()))
                    self.table.setItem(row_pos, 2, QTableWidgetItem(partes[1].strip()))
        if not encontrou:
            QMessageBox.information(
                self, "Busca", "Nenhum pacote encontrado no Chocolatey."
            )

    def _parse_winget(self, stdout: str):
        """Parser de tabela do winget search (JSON não é suportado nesse comando)."""
        linhas = stdout.splitlines()

        # Localizar linha de separador (--- ou ───)
        start_idx = -1
        for i, l in enumerate(linhas):
            if re.match(r"^[-─]{3,}", l.strip()):
                start_idx = i + 1
                break

        # Fallback: procurar cabeçalho
        if start_idx == -1:
            for i, l in enumerate(linhas):
                if re.search(r"\b(Id|Nome|Name|Versão|Version)\b", l) and "  " in l:
                    start_idx = i + 2
                    break

        if start_idx == -1 or start_idx >= len(linhas):
            if re.search(r"(Nenhum|No package|Não foram|no packages)", stdout, re.I):
                QMessageBox.information(
                    self, "Busca", "Nenhum pacote encontrado no Winget."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Formato inesperado",
                    "Não foi possível interpretar a saída do Winget.\n\n"
                    f"Saída bruta (até 500 chars):\n{stdout[:500]}",
                )
            return

        encontrou = False
        for l in linhas[start_idx:]:
            stripped = l.strip()
            if not stripped or stripped.startswith("-"):
                continue
            # Separador: 2+ espaços OU pipe/barra vertical de tabela unicode
            partes = re.split(r"\s{2,}", stripped)
            if len(partes) < 3:
                partes = [p.strip() for p in re.split(r"[|│]", stripped) if p.strip()]
            if len(partes) >= 3:
                encontrou = True
                nome = partes[0]
                pkg_id = partes[1]
                versao = partes[2]
                row_pos = self.table.rowCount()
                self.table.insertRow(row_pos)
                self.table.setItem(row_pos, 0, QTableWidgetItem(pkg_id))
                self.table.setItem(row_pos, 1, QTableWidgetItem(nome))
                self.table.setItem(row_pos, 2, QTableWidgetItem(versao))

        if not encontrou:
            QMessageBox.warning(
                self,
                "Sem resultados",
                f"Winget retornou dados, mas nenhuma linha foi parseada.\n\n"
                f"Saída bruta (até 500 chars):\n{stdout[:500]}",
            )

    def add_selected(self):
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        for row in selected_rows:
            pkg_id = self.table.item(row, 0).text()
            self.selected_packages.append(pkg_id)
        if self.selected_packages:
            self.accept()
        else:
            QMessageBox.warning(
                self, "Aviso", "Selecione pelo menos um pacote na tabela."
            )


class FetchSoftwareWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, target_pc, engine):
        super().__init__()
        self.target_pc = target_pc
        self.engine = engine

    def run(self):
        try:
            conn = RemoteConnectionManager()
            ps_script = f"""
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8
            $ErrorActionPreference = 'SilentlyContinue'

            $Engine = "{self.engine}"
            $allSoftware = @()

            if ($Engine -eq "Chocolatey") {{
                $choco = "C:\\ProgramData\\chocolatey\\bin\\choco.exe"
                if (Test-Path $choco) {{
                    $clist = & $choco list -lo -r 2>$null
                    if ($null -ne $clist) {{
                        foreach ($c in $clist) {{
                            if ([string]::IsNullOrWhiteSpace($c)) {{ continue }}
                            $p = $c.Split('|')
                            if ($p.Length -ge 2) {{
                                $allSoftware += [PSCustomObject]@{{ Id = $p[0].Trim(); Name = $p[0].Trim(); Version = $p[1].Trim(); Origin = "Chocolatey" }}
                            }}
                        }}
                    }}
                }}
            }} else {{
                # ==============================================================
                # WINGET — Inventário forçando --source winget
                # (evita consulta automática ao msstore, que falha por proxy)
                # ==============================================================
                $wingetCmd = $null
                $cmd = Get-Command winget -ErrorAction SilentlyContinue
                if ($cmd) {{ $wingetCmd = $cmd.Source }}

                if (-not $wingetCmd) {{
                    $candidate = "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\winget.exe"
                    if (Test-Path $candidate) {{ $wingetCmd = $candidate }}
                }}

                if (-not $wingetCmd) {{
                    $appInst = Get-ChildItem "C:\\Program Files\\WindowsApps\\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\\winget.exe" -ErrorAction SilentlyContinue |
                               Sort-Object LastWriteTime -Descending | Select-Object -First 1
                    if ($appInst) {{ $wingetCmd = $appInst.FullName }}
                }}

                if ($wingetCmd -and (Test-Path $wingetCmd)) {{
                    # Captura direta: preserva o layout de colunas nativo
                    $out = @(& $wingetCmd list --source winget --nowarn --accept-source-agreements --disable-interactivity 2>$null)

                    $start = $false
                    $idPos = -1
                    $verPos = -1
                    foreach ($line in $out) {{
                        if ($null -eq $line) {{ continue }}
                        $lineStr = $line.ToString()
                        if ($lineStr -match '^Nome' -or $lineStr -match '^Name') {{
                            $idPos  = $lineStr.IndexOf("Id",   [System.StringComparison]::OrdinalIgnoreCase)
                            $verPos = $lineStr.IndexOf("Vers", [System.StringComparison]::OrdinalIgnoreCase)
                        }}
                        if ($lineStr -match '^---') {{ $start = $true; continue }}
                        if ($start -and -not [string]::IsNullOrWhiteSpace($lineStr) -and $idPos -gt 0 -and $verPos -gt $idPos) {{
                            $name = $lineStr.Substring(0, $idPos).Trim()
                            $id = $lineStr.Substring($idPos, $verPos - $idPos).Trim()
                            $verRest = $lineStr.Substring($verPos).Trim()
                            $parts = $verRest -split '\\s+', 2
                            $ver = if ($parts.Count -ge 1) {{ $parts[0] }} else {{ "" }}
                            $disp = if ($parts.Count -ge 2) {{ $parts[1].Trim() }} else {{ "" }}
                            if ($name -and $id) {{
                                $allSoftware += [PSCustomObject]@{{ Id = $id; Name = $name; Version = $ver; Available = $disp; Origin = "Winget" }}
                            }}
                        }}
                    }}

                    # Auto-diag: se zero pacotes, cria uma linha com info do primeiro array
                    if ($allSoftware.Count -eq 0 -and $out.Count -gt 0) {{
                        $primeira = if ($out[0]) {{ $out[0].ToString() }} else {{ "" }}
                        if ($primeira.Length -gt 100) {{ $primeira = $primeira.Substring(0, 100) }}
                        $allSoftware += [PSCustomObject]@{{
                            Id = "_DIAG_"
                            Name = "0 pacotes. Total linhas: $($out.Count). Primeira: $primeira"
                            Version = "-"
                            Origin = "Debug"
                        }}
                    }}
                }}

                # Fallback final: Registro (só se nada funcionou)
                if ($allSoftware.Count -eq 0) {{
                    $paths = @("HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*", "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*")
                    $reg = Get-ItemProperty $paths -ErrorAction SilentlyContinue | Where-Object DisplayName | Sort-Object DisplayName -Unique
                    foreach ($item in $reg) {{
                        if ($item.DisplayName) {{
                            $ver = if ($item.DisplayVersion) {{ $item.DisplayVersion }} else {{ "-" }}
                            $allSoftware += [PSCustomObject]@{{ Id = $item.DisplayName; Name = $item.DisplayName; Version = $ver; Origin = "Windows Registry" }}
                        }}
                    }}
                }}
            }}

            if ($allSoftware.Count -eq 0) {{
                $allSoftware += [PSCustomObject]@{{ Id="Nenhum"; Name="Nenhum software encontrado"; Version="-"; Origin="-" }}
            }}

            $finalList = $allSoftware | Sort-Object Name -Unique
            @{{ Pacotes = @($finalList) }} | ConvertTo-Json -Depth 5 -Compress
            """

            res = conn.execute_script(self.target_pc, ps_script)

            if res["status"] == "Sucesso" and res.get("json_data"):
                json_data = res["json_data"]
                if (
                    isinstance(json_data, dict)
                    and json_data.get("StatusFinal") == "ERRO FATAL"
                ):
                    self.error.emit("Erro Crítico no script remoto. Tente novamente.")
                    return
                pacotes = (
                    json_data.get("Pacotes", []) if isinstance(json_data, dict) else []
                )
                if not isinstance(pacotes, list):
                    pacotes = [pacotes]
                self.finished.emit(pacotes)
            else:
                self.error.emit(
                    res.get("log_saida", "Erro de comunicação ao listar inventário.")
                )
        except Exception as e:
            self.error.emit(str(e))


class CheckUpdatesWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, target_pc, engine):
        super().__init__()
        self.target_pc = target_pc
        self.engine = engine

    def run(self):
        try:
            conn = RemoteConnectionManager()
            ps_script = f"""
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8
            $ErrorActionPreference = 'SilentlyContinue'

            $outdatedPkgs = @{{}}
            $Engine = "{self.engine}"

            if ($Engine -eq "Chocolatey") {{
                $choco = "C:\\ProgramData\\chocolatey\\bin\\choco.exe"
                if (Test-Path $choco) {{
                    $cout = & $choco outdated -r 2>$null
                    if ($null -ne $cout) {{
                        foreach ($c in $cout) {{
                            if ([string]::IsNullOrWhiteSpace($c)) {{ continue }}
                            $p = $c.Split('|')
                            if ($p.Length -ge 3) {{ $outdatedPkgs[$p[0]] = $p[2].Trim() }}
                        }}
                    }}
                }}
                        }} else {{
                # ==============================================================
                # WINGET — Verificar atualizações via captura direta
                # (Start-Process -Wait travava em alguns ambientes)
                # ==============================================================
                $wingetCmd = $null
                $cmd = Get-Command winget -ErrorAction SilentlyContinue
                if ($cmd) {{ $wingetCmd = $cmd.Source }}

                if (-not $wingetCmd) {{
                    $candidate = "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\winget.exe"
                    if (Test-Path $candidate) {{ $wingetCmd = $candidate }}
                }}

                if (-not $wingetCmd) {{
                    $appInst = Get-ChildItem "C:\\Program Files\\WindowsApps\\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\\winget.exe" -ErrorAction SilentlyContinue |
                               Sort-Object LastWriteTime -Descending | Select-Object -First 1
                    if ($appInst) {{ $wingetCmd = $appInst.FullName }}
                }}

                if ($wingetCmd -and (Test-Path $wingetCmd)) {{
                    # Captura direta (sem arquivo, sem BOM, sem Out-String)
                    $cout = @(& $wingetCmd upgrade --source winget --nowarn --accept-source-agreements --disable-interactivity 2>$null)

                    $start = $false
                    $idPos = -1
                    $verPos = -1
                    $availPos = -1
                    foreach ($line in $cout) {{
                        if ($null -eq $line) {{ continue }}
                        $lineStr = $line.ToString()
                        if ($lineStr -match '^Nome' -or $lineStr -match '^Name') {{
                            $idPos    = $lineStr.IndexOf("Id",    [System.StringComparison]::OrdinalIgnoreCase)
                            $verPos   = $lineStr.IndexOf("Vers",  [System.StringComparison]::OrdinalIgnoreCase)
                            $availPos = $lineStr.IndexOf("Disp",  [System.StringComparison]::OrdinalIgnoreCase)
                            if ($availPos -eq -1) {{ $availPos = $lineStr.IndexOf("Avail", [System.StringComparison]::OrdinalIgnoreCase) }}
                        }}
                        if ($lineStr -match '^---') {{ $start = $true; continue }}
                        if ($start -and -not [string]::IsNullOrWhiteSpace($lineStr) -and $idPos -gt 0 -and $verPos -gt $idPos) {{
                            $id = $lineStr.Substring($idPos, $verPos - $idPos).Trim()
                            if ($availPos -gt $verPos) {{
                                $rest = $lineStr.Substring($availPos).Trim()
                                $avail = if ($rest) {{ $rest.Split(' ')[0] }} else {{ "" }}
                            }} else {{
                                $rest = $lineStr.Substring($verPos).Trim()
                                $parts = $rest -split '\\s+', 2
                                $avail = if ($parts.Count -ge 2) {{ $parts[1].Trim() }} else {{ "" }}
                            }}
                            if ($id -and $avail) {{ $outdatedPkgs[$id] = $avail }}
                        }}
                    }}
                }}
            }}

            @{{ Atualizacoes = $outdatedPkgs }} | ConvertTo-Json -Depth 5 -Compress
            """

            res = conn.execute_script(self.target_pc, ps_script)

            if res["status"] == "Sucesso" and res.get("json_data"):
                self.finished.emit(res["json_data"].get("Atualizacoes", {}))
            else:
                self.error.emit(
                    res.get("log_saida", "Falha ao analisar as atualizações.")
                )
        except Exception as e:
            self.error.emit(str(e))


class PreCheckDriverWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, target_pc, category):
        super().__init__()
        self.target_pc = target_pc
        self.category = category

    def run(self):
        try:
            conn = RemoteConnectionManager()
            ps_script = f"""
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $OutputEncoding = [System.Text.Encoding]::UTF8
            $ErrorActionPreference = 'Stop'

            try {{
                $Sys = Get-CimInstance -ClassName Win32_ComputerSystem
                $Manuf = $Sys.Manufacturer.Trim()
                $Model = $Sys.Model.Trim()
                
                $Drivers = Get-WindowsDriver -Online
                if ("{self.category}" -eq "Todos") {{
                    $Drivers = $Drivers | Where-Object {{ $_.ClassName -in @("Net", "Display", "Media", "Bluetooth", "Image", "Camera") }}
                }} elseif ("{self.category}" -eq "Camera_Image") {{
                    $Drivers = $Drivers | Where-Object {{ $_.ClassName -in @("Camera", "Image") }}
                }} else {{
                    $Drivers = $Drivers | Where-Object {{ $_.ClassName -eq "{self.category}" }}
                }}
                $Count = @($Drivers).Count
                
                @{{
                    Status = "OK"
                    Manuf = $Manuf
                    Model = $Model
                    Count = $Count
                }} | ConvertTo-Json -Compress
            }} catch {{
                @{{
                    Status = "ERRO"
                    Msg = $_.Exception.Message
                }} | ConvertTo-Json -Compress
            }}
            """

            res = conn.execute_script(self.target_pc, ps_script)
            if res["status"] == "Sucesso" and res.get("json_data"):
                if (
                    isinstance(res["json_data"], dict)
                    and res["json_data"].get("Status") == "OK"
                ):
                    self.finished.emit(res["json_data"])
                else:
                    err = (
                        res["json_data"].get("Msg")
                        if isinstance(res["json_data"], dict)
                        else "Erro ao analisar o hardware."
                    )
                    self.error.emit(err)
            else:
                self.error.emit(
                    res.get("log_saida", "Falha ao aceder à máquina alvo para cálculo.")
                )
        except Exception as e:
            self.error.emit(str(e))


class SoftwareView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(
            main_window_ref, "queue_manager", None
        ) or TaskQueueManager(max_threads=5)

        try:
            from core.database import DatabaseManager

            self.db = DatabaseManager()
        except Exception as e:
            log.warning(f"Falha ao inicializar DatabaseManager: {e}")
            self.db = None

        self.network_software_path = r"\\hul-vp-imagem-cc\netshared\Softwares"
        self.network_drivers_path = r"\\hul-vp-imagem-cc\netshared\Drivers"
        # --- Constantes de caminho para injeção em scripts PowerShell ---
        self.SHARE_ROOT = r"\\hul-vp-imagem-cc\netshared"
        self.SHARE_WINGET = r"\\hul-vp-imagem-cc\netshared\Winget"

        self.cat_map = {
            "Todos Essenciais (Vídeo, Rede, Áudio, BT, Cam)": "Todos",
            "Vídeo (Display)": "Display",
            "Rede (Net)": "Net",
            "Áudio (Media)": "Media",
            "Bluetooth": "Bluetooth",
            "Câmaras (Camera/Image)": "Camera_Image",
        }

        self._current_coleta_target = ""
        self._current_coleta_cat_nome = ""
        self._current_coleta_cat_class = ""

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Gestão e Inventário de Softwares e Drivers")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        target_group = QGroupBox("1. Controle de Endpoint e Motor de Gestão")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(15, 20, 15, 15)

        self.inp_target = QLineEdit()
        self.inp_target.setFixedHeight(32)
        self.inp_target.setPlaceholderText("Ex: HUL-WK-244377E ou 10.8.128.14")
        self.inp_target.setStyleSheet("padding: 0 10px;")
        self.inp_target.textChanged.connect(self._force_uppercase)

        self.cmb_engine = QComboBox()
        self.cmb_engine.setFixedHeight(32)
        self.cmb_engine.addItems(["Winget", "Chocolatey"])
        self.cmb_engine.setStyleSheet("padding: 0 10px; font-weight: bold;")
        self.cmb_engine.currentTextChanged.connect(self.clear_table_on_engine_change)

        self.lbl_motor = QLabel(" Motor:")

        self.btn_fetch = QPushButton("🔄 Listar Softwares (Inventário)")
        self.btn_fetch.setFixedHeight(32)
        self.btn_fetch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fetch.setStyleSheet(
            "background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_fetch.clicked.connect(self.fetch_software)

        self.btn_check_updates = QPushButton("🔎 Verificar Atualizações")
        self.btn_check_updates.setFixedHeight(32)
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_updates.setStyleSheet(
            "background-color: #f0ad4e; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_check_updates.clicked.connect(self.check_updates)

        target_layout.addWidget(QLabel("Alvo:"))
        target_layout.addWidget(self.inp_target)
        target_layout.addWidget(self.lbl_motor)
        target_layout.addWidget(self.cmb_engine)
        target_layout.addWidget(self.btn_fetch)
        target_layout.addWidget(self.btn_check_updates)
        layout.addWidget(target_group)

        self.tabs = QTabWidget()
        self._build_aba_inventario()
        self._build_aba_instalacao()
        self._build_aba_drivers()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tabs, stretch=1)

        status_group = QGroupBox("Acompanhamento de Execução Remota")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(10, 15, 10, 10)

        header_lote = QHBoxLayout()
        header_lote.addStretch()
        self.btn_clear_table = QPushButton("🧹 Limpar Lista")
        self.btn_clear_table.setFixedHeight(28)
        self.btn_clear_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_table.setStyleSheet(
            "padding: 0 15px; background-color: #666; color: white; font-weight: bold; border-radius: 4px;"
        )
        self.btn_clear_table.clicked.connect(lambda: self.status_table.setRowCount(0))
        header_lote.addWidget(self.btn_clear_table)
        status_layout.addLayout(header_lote)

        self.status_table = QTableWidget(0, 6)
        self.status_table.setHorizontalHeaderLabels(
            [
                "Computador Alvo",
                "Operação",
                "Início",
                "Fim",
                "Status Atual",
                "Resumo da Execução",
            ]
        )
        self.status_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        self.status_table.setColumnWidth(0, 130)
        self.status_table.setColumnWidth(1, 150)
        self.status_table.setColumnWidth(2, 70)
        self.status_table.setColumnWidth(3, 70)
        self.status_table.setColumnWidth(4, 110)
        self.status_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch
        )

        self.status_table.setWordWrap(True)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.status_table.setMaximumHeight(160)
        status_layout.addWidget(self.status_table)
        layout.addWidget(status_group)

    def on_tab_changed(self, index):
        show_engine = index in [0, 1]
        self.cmb_engine.setVisible(show_engine)
        self.lbl_motor.setVisible(show_engine)

        is_inv_tab = index == 0
        self.btn_fetch.setVisible(is_inv_tab)
        self.btn_check_updates.setVisible(is_inv_tab)

    def _build_aba_inventario(self):
        tab_inv = QWidget()
        inv_layout = QVBoxLayout(tab_inv)

        actions_layout = QHBoxLayout()
        self.btn_upgrade = QPushButton("⭐ Atualizar Selecionados")
        self.btn_upgrade.setFixedHeight(32)
        self.btn_upgrade.setStyleSheet(
            "background-color: #1e8a5e; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_upgrade.clicked.connect(lambda: self.execute_action("upgrade"))

        self.btn_force = QPushButton("♻️ Forçar Instalação")
        self.btn_force.setFixedHeight(32)
        self.btn_force.setStyleSheet(
            "background-color: #5bc0de; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_force.clicked.connect(lambda: self.execute_action("force"))

        self.btn_uninstall = QPushButton("🗑 Desinstalar Selecionados")
        self.btn_uninstall.setFixedHeight(32)
        self.btn_uninstall.setStyleSheet(
            "background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_uninstall.clicked.connect(lambda: self.execute_action("uninstall"))

        actions_layout.addWidget(self.btn_upgrade)
        actions_layout.addWidget(self.btn_force)
        actions_layout.addWidget(self.btn_uninstall)
        actions_layout.addStretch()
        inv_layout.addLayout(actions_layout)

        filter_layout = QHBoxLayout()
        self.chk_select_all = QCheckBox("Selecionar / Desmarcar Todos (Visíveis)")
        self.chk_select_all.setStyleSheet("font-weight: bold; color: #4a90e2;")
        self.chk_select_all.stateChanged.connect(self.toggle_select_all)
        filter_layout.addWidget(self.chk_select_all)

        # --- Opt-in: força fechamento de apps durante upgrades ---
        self.chk_force_close = QCheckBox("🔪 Fechar apps antes de atualizar")
        self.chk_force_close.setStyleSheet(
            "font-weight: bold; color: #d9534f; margin-left: 15px;"
        )
        self.chk_force_close.setToolTip(
            "Se marcado, usa 'winget upgrade --force' durante Atualizações,\n"
            "que fecha automaticamente processos em execução.\n"
            "AVISO: pode causar perda de dados não salvos no app do usuário."
        )
        self.chk_force_close.setChecked(False)  # default: seguro
        filter_layout.addWidget(self.chk_force_close)

        filter_layout.addStretch()

        # --- Filtro rápido: só pacotes com atualização disponível ---
        self.chk_only_updates = QCheckBox("⬆️ Só com atualização")
        self.chk_only_updates.setStyleSheet(
            "font-weight: bold; color: #f0ad4e; margin-right: 10px;"
        )
        self.chk_only_updates.setToolTip(
            "Mostra apenas pacotes que têm uma nova versão disponível.\n"
            "Combina com o filtro de texto ao lado."
        )
        self.chk_only_updates.setChecked(False)
        self.chk_only_updates.stateChanged.connect(self.apply_filters)  # aplica na hora
        filter_layout.addWidget(self.chk_only_updates)

        filter_layout.addWidget(QLabel("🔍 Filtrar:"))

        self.inp_filter = QLineEdit()
        self.inp_filter.setFixedHeight(32)
        self.inp_filter.setPlaceholderText("Buscar por Nome ou ID...")
        self.inp_filter.setFixedWidth(250)
        self.inp_filter.setStyleSheet("padding: 0 10px;")
        self.inp_filter.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.inp_filter)
        inv_layout.addLayout(filter_layout)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                "[ ]",
                "ID do Pacote",
                "Nome do Software",
                "Versão Instalada",
                "Nova Versão",
                "Origem",
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 110)
        header.setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        inv_layout.addWidget(self.table)

        self.tabs.addTab(tab_inv, "1. Inventário e Desinstalação")

    def _build_aba_instalacao(self):
        tab_inst = QWidget()
        inst_layout = QVBoxLayout(tab_inst)

        split_layout = QHBoxLayout()

        frame_rede = QGroupBox("Instaladores na Rede (Offline)")
        rede_layout = QVBoxLayout(frame_rede)

        header_rede = QHBoxLayout()
        self.btn_load_net = QPushButton("↻ Buscar no Compartilhamento")
        self.btn_load_net.setFixedHeight(32)
        self.btn_load_net.setStyleSheet(
            "padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_load_net.clicked.connect(self.carregar_softwares_da_rede)
        header_rede.addWidget(self.btn_load_net)
        header_rede.addStretch()
        rede_layout.addLayout(header_rede)

        self.tbl_offline = QTableWidget(0, 2)
        self.tbl_offline.setHorizontalHeaderLabels(["Instalador na Rede", "Tamanho"])
        self.tbl_offline.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_offline.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_offline.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_offline.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_offline.verticalHeader().setVisible(False)
        rede_layout.addWidget(self.tbl_offline)
        split_layout.addWidget(frame_rede)

        frame_winget = QGroupBox("Instalação Online (Nuvem)")
        winget_layout = QVBoxLayout(frame_winget)

        pesquisa_layout = QHBoxLayout()
        self.inp_custom_soft = QLineEdit()
        self.inp_custom_soft.setFixedHeight(32)
        self.inp_custom_soft.setStyleSheet("padding: 0 10px;")
        self.inp_custom_soft.setPlaceholderText(
            "IDs do pacote separados por vírgula..."
        )
        self.btn_search_online = QPushButton("🔍 Pesquisar ID")
        self.btn_search_online.setFixedHeight(32)
        self.btn_search_online.setStyleSheet(
            "padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_search_online.clicked.connect(self.open_search_dialog)
        pesquisa_layout.addWidget(self.inp_custom_soft)
        pesquisa_layout.addWidget(self.btn_search_online)
        winget_layout.addLayout(pesquisa_layout)
        winget_layout.addWidget(
            QLabel(
                "<i>Aviso: O endpoint precisa ter acesso à internet para o Winget/Choco.</i>"
            )
        )
        winget_layout.addStretch()
        split_layout.addWidget(frame_winget)

        inst_layout.addLayout(split_layout)

        self.btn_install = QPushButton("▶ Instalar Softwares Selecionados")
        self.btn_install.setFixedHeight(36)
        self.btn_install.setStyleSheet(
            "background-color: #1e8a5e; color: white; font-weight: bold; border-radius: 4px;"
        )
        self.btn_install.clicked.connect(self.start_software_install)
        inst_layout.addWidget(self.btn_install)

        self.tabs.addTab(tab_inst, "2. Nova Instalação (Rede/Nuvem)")

    def _build_aba_drivers(self):
        tab_drv = QWidget()
        drv_layout = QHBoxLayout(tab_drv)

        frame_backup = QGroupBox("📥 Coleta Inteligente (Backup para Rede)")
        bkp_layout = QVBoxLayout(frame_backup)
        bkp_layout.setSpacing(15)

        lbl_info_coleta = QLabel(
            "Calcula a estimativa e depois extrai os drivers\nde terceiros comparando com a rede."
        )
        lbl_info_coleta.setStyleSheet("color: #888; font-style: italic;")
        bkp_layout.addWidget(lbl_info_coleta)

        self.cmb_coleta_cat = QComboBox()
        self.cmb_coleta_cat.addItems(list(self.cat_map.keys()))
        bkp_layout.addWidget(QLabel("O que deseja extrair?"))
        bkp_layout.addWidget(self.cmb_coleta_cat)

        bkp_layout.addStretch()
        self.btn_coleta = QPushButton("⬇️ Iniciar Extração Inteligente")
        self.btn_coleta.setFixedHeight(36)
        self.btn_coleta.setStyleSheet(
            "background-color: #2a7de1; color: white; font-weight: bold; border-radius: 4px;"
        )
        self.btn_coleta.clicked.connect(self.coletar_drivers)
        bkp_layout.addWidget(self.btn_coleta)
        drv_layout.addWidget(frame_backup)

        frame_deploy = QGroupBox("📤 Instalação (Deploy Offline Automático)")
        dep_layout = QVBoxLayout(frame_deploy)
        dep_layout.setSpacing(15)

        lbl_info_deploy = QLabel(
            "O SARCC vai detetar automaticamente a marca/modelo\nda máquina alvo e instalar o driver da rede."
        )
        lbl_info_deploy.setStyleSheet("color: #888; font-style: italic;")
        dep_layout.addWidget(lbl_info_deploy)

        self.cmb_install_cat = QComboBox()
        self.cmb_install_cat.addItems(list(self.cat_map.keys()))
        dep_layout.addWidget(QLabel("O que deseja instalar nesta máquina?"))
        dep_layout.addWidget(self.cmb_install_cat)

        dep_layout.addStretch()
        self.btn_deploy = QPushButton("▶ Instalar no Alvo Automático")
        self.btn_deploy.setFixedHeight(36)
        self.btn_deploy.setStyleSheet(
            "background-color: #1e8a5e; color: white; font-weight: bold; border-radius: 4px;"
        )
        self.btn_deploy.clicked.connect(self.instalar_drivers)
        dep_layout.addWidget(self.btn_deploy)
        drv_layout.addWidget(frame_deploy)

        self.tabs.addTab(tab_drv, "3. Gestão de Drivers (Offline)")

    def coletar_drivers(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(
                self, "Aviso", "Informe o computador alvo no painel superior."
            )
            self.inp_target.setFocus()
            return

        cat_nome = self.cmb_coleta_cat.currentText()
        cat_class = self.cat_map[cat_nome]

        self.btn_coleta.setEnabled(False)
        self.btn_coleta.setText("A calcular estimativa...")

        self._current_coleta_target = target
        self._current_coleta_cat_nome = cat_nome
        self._current_coleta_cat_class = cat_class

        self.worker_pre = PreCheckDriverWorker(target, cat_class)
        self.worker_pre.finished.connect(self._on_pre_check_finished)
        self.worker_pre.error.connect(self._on_pre_check_error)
        self.worker_pre.start()

    @pyqtSlot(dict)
    def _on_pre_check_finished(self, data):
        self.btn_coleta.setEnabled(True)
        self.btn_coleta.setText("⬇️️ Iniciar Extração Inteligente")

        count = data.get("Count", 0)
        manuf = data.get("Manuf", "Desconhecido")
        model = data.get("Model", "Desconhecido")

        if count == 0:
            QMessageBox.information(
                self,
                "Coleta Finalizada",
                f"Nenhum driver de terceiros compatível encontrado para a categoria '{self._current_coleta_cat_nome}'.",
            )
            return

        est_mins = max(1, (count * 2) // 60)

        msg = f"Máquina Alvo: {manuf} {model}\n"
        msg += f"Categoria Selecionada: {self._current_coleta_cat_nome}\n"
        msg += f"Drivers Encontrados: {count}\n"
        msg += f"Tempo Estimado: Processo Rápido ({est_mins} min)\n\n"
        msg += "Deseja disparar a extração remota no computador?"

        reply = QMessageBox.question(
            self,
            "Estimativa de Coleta",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_coleta_direta(
                self._current_coleta_target, self._current_coleta_cat_class
            )

    @pyqtSlot(str)
    def _on_pre_check_error(self, err):
        self.btn_coleta.setEnabled(True)
        self.btn_coleta.setText("⬇️ Iniciar Extração Inteligente")
        QMessageBox.critical(
            self,
            "Erro",
            f"Não foi possível calcular os drivers do alvo.\nDetalhe: {err}",
        )

    def _start_coleta_direta(self, target, cat_class):
        core_script = f"""
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        $Categoria = "{cat_class}"
        $ShareServerPath = "{self.SHARE_ROOT}"
        
        $LogData = @{{
            Script = "Coleta Inteligente Direta ($Categoria)"
            Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            Computador = $env:COMPUTERNAME
            StatusFinal = "SUCESSO"
            Detalhes = @()
        }}
        
        try {{
            if (-not (Test-Path $ShareServerPath)) {{ throw "Acesso a rede negado." }}
            
            $Sys = Get-CimInstance -ClassName Win32_ComputerSystem
            $Manuf = $Sys.Manufacturer.Trim() -replace '[^a-zA-Z0-9]', '_'
            $Model = $Sys.Model.Trim() -replace '[^a-zA-Z0-9]', '_'
            
            $Destino = "$ShareServerPath\\Drivers\\COLETAS\\$Manuf\\$Model"
            if (-not (Test-Path $Destino)) {{ $null = New-Item -ItemType Directory -Force -Path $Destino }}
            
            $Drivers = Get-WindowsDriver -Online
            if ($Categoria -eq "Todos") {{
                $Drivers = $Drivers | Where-Object {{ $_.ClassName -in @("Net", "Display", "Media", "Bluetooth", "Image", "Camera") }}
            }} elseif ($Categoria -eq "Camera_Image") {{
                $Drivers = $Drivers | Where-Object {{ $_.ClassName -in @("Camera", "Image") }}
            }} else {{
                $Drivers = $Drivers | Where-Object {{ $_.ClassName -eq $Categoria }}
            }}
            
            $CountCopiados = 0
            $CountIgnorados = 0
            $ListaCopiados = @()
            $ListaMantidos = @()
            
            foreach ($drv in $Drivers) {{
                $InfPath = $drv.OriginalFileName
                $PastaOriginalDriver = Split-Path $InfPath -Parent
                $InfName = Split-Path $InfPath -Leaf
                $PastaRealDriver = $InfName -replace '\\.inf$', ''
                $CaminhoDestinoFinal = Join-Path $Destino $PastaRealDriver
                
                $ClassName = $drv.ClassName
                $Provider = $drv.ProviderName
                if ([string]::IsNullOrWhiteSpace($Provider)) {{ $Provider = "Desconhecido" }}
                $DrvLabel = "[$ClassName] $Provider ($InfName)"
                
                $Atualizar = $false
                $infRede = Get-ChildItem -Path $Destino -Filter $InfName -Recurse | Select-Object -First 1
                
                if ($infRede) {{
                    $expVerMatch = Select-String -Path $InfPath -Pattern 'DriverVer\\s*=\\s*(.*)' | Select-Object -First 1
                    $redeVerMatch = Select-String -Path $infRede.FullName -Pattern 'DriverVer\\s*=\\s*(.*)' | Select-Object -First 1
                    
                    if ($expVerMatch -and $redeVerMatch) {{
                        $expVerStr = $expVerMatch.Matches.Groups[1].Value.Trim()
                        $redeVerStr = $redeVerMatch.Matches.Groups[1].Value.Trim()
                        
                        try {{
                            $expDate = [datetime]($expVerStr -split ',')[0].Trim()
                            $redeDate = [datetime]($redeVerStr -split ',')[0].Trim()
                            
                            if ($expDate -gt $redeDate) {{
                                $Atualizar = $true
                            }} elseif ($expDate -eq $redeDate) {{
                                $expV = [version]($expVerStr -split ',')[1].Trim()
                                $redeV = [version]($redeVerStr -split ',')[1].Trim()
                                if ($expV -gt $redeV) {{ $Atualizar = $true }}
                            }}
                        }} catch {{
                            if ($expVerStr -ne $redeVerStr) {{ $Atualizar = $true }}
                        }}
                    }} else {{
                        $Atualizar = $true
                    }}
                }} else {{
                    $Atualizar = $true
                }}
                
                if ($Atualizar) {{
                    if ($infRede) {{ $null = Remove-Item -Path $infRede.Directory.FullName -Recurse -Force }}
                    if (Test-Path $CaminhoDestinoFinal) {{ $null = Remove-Item -Path $CaminhoDestinoFinal -Recurse -Force }}
                    
                    $null = Copy-Item -Path $PastaOriginalDriver -Destination $CaminhoDestinoFinal -Recurse -Force
                    $CountCopiados++
                    $ListaCopiados += "-> TRANSFERIDO: $DrvLabel"
                }} else {{
                    $CountIgnorados++
                    $ListaMantidos += "- MANTIDO (Ja atualizado): $DrvLabel"
                }}
            }}
            
            $LogData.Detalhes += "=== RESUMO DA COLETA ==="
            if ($CountCopiados -gt 0) {{ $LogData.Detalhes += $ListaCopiados }} else {{ $LogData.Detalhes += "Nenhum driver novo transferido." }}
            $LogData.Detalhes += "---"
            if ($CountIgnorados -gt 0) {{ $LogData.Detalhes += $ListaMantidos }}
        }} catch {{
            $LogData.StatusFinal = "ERRO"
            $LogData.Detalhes += "Falha: $($_.Exception.Message)"
        }} finally {{
            $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
        }}
        """
        self._enqueue_task(target, f"Backup Inteligente ({cat_class})", core_script)

    def instalar_drivers(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(
                self, "Aviso", "Informe o computador alvo no painel superior."
            )
            self.inp_target.setFocus()
            return

        cat_nome = self.cmb_install_cat.currentText()
        cat_class = self.cat_map[cat_nome]

        core_script = f"""
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        $Categoria = "{cat_class}"
        $ShareServerPath = "{self.SHARE_ROOT}"
        
        $LogData = @{{
            Script = "Deploy Auto ($Categoria)"
            Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            Computador = $env:COMPUTERNAME
            StatusFinal = "SUCESSO"
            Detalhes = @()
        }}
        
        try {{
            if (-not (Test-Path $ShareServerPath)) {{ throw "Acesso a rede negado. O SYSTEM tem acesso a $ShareServerPath?" }}

            $Sys = Get-CimInstance -ClassName Win32_ComputerSystem
            $Manuf = $Sys.Manufacturer.Trim() -replace '[^a-zA-Z0-9]', '_'
            $Model = $Sys.Model.Trim() -replace '[^a-zA-Z0-9]', '_'
            $CaminhoRede = "$ShareServerPath\\Drivers\\COLETAS\\$Manuf\\$Model"
            
            if (-not (Test-Path $CaminhoRede)) {{ throw "Nenhum backup encontrado na rede para: $Manuf $Model." }}
            
            $Infs = Get-ChildItem -Path $CaminhoRede -Filter "*.inf" -Recurse
            $CountSucesso = 0
            $CountFalha = 0
            
            $LogData.Detalhes += "=== RELATÓRIO DE INSTALAÇÃO ==="
            
            foreach ($inf in $Infs) {{
                $content = Get-Content $inf.FullName -TotalCount 35 -ErrorAction SilentlyContinue
                $ClassName = "Desconhecido"
                $LineMatch = $content -match "Class\\s*=\\s*([a-zA-Z0-9_]+)" | Select-Object -First 1
                if ($LineMatch -match "Class\\s*=\\s*([a-zA-Z0-9_]+)") {{
                    $ClassName = $matches[1]
                }}
                
                $Match = $false
                if ($Categoria -eq "Todos") {{
                    if ($ClassName -match "(?i)^(Net|Display|Media|Bluetooth|Image|Camera)$") {{ $Match = $true }}
                }} elseif ($Categoria -eq "Camera_Image") {{
                    if ($ClassName -match "(?i)^(Camera|Image)$") {{ $Match = $true }}
                }} else {{
                    if ($ClassName -match "(?i)^$Categoria$") {{ $Match = $true }}
                }}
                
                if ($Match) {{
                    $out = pnputil.exe /add-driver $inf.FullName /install 2>&1
                    $outStr = $out -join " "
                    
                    if ($outStr -match "Successfully" -or $outStr -match "êxito" -or $LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 3010 -or $LASTEXITCODE -eq 259) {{
                        $LogData.Detalhes += "-> INSTALADO: [$ClassName] $($inf.Name)"
                        $CountSucesso++
                    }} else {{
                        $LogData.Detalhes += "-> FALHA: [$ClassName] $($inf.Name) | Detalhe: $outStr"
                        $CountFalha++
                    }}
                }}
            }}
            
            $LogData.Detalhes += "---"
            $LogData.Detalhes += "Deploy concluido. $CountSucesso instalados, $CountFalha falhas."
        }} catch {{
            $LogData.StatusFinal = "ERRO"
            $LogData.Detalhes += "Falha: $($_.Exception.Message)"
        }} finally {{
            $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
        }}
        """

        reply = QMessageBox.question(
            self,
            "Deploy Automático",
            f"O sistema irá detetar a marca e instalar os drivers de {cat_nome}.\n\nDeseja prosseguir no computador {target}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._enqueue_task(
                target, f"Instalação Automática ({cat_class})", core_script
            )

    def _enqueue_task(self, target, title, ps_script, credentials=None):
        row_pos = self.status_table.rowCount()
        self.status_table.insertRow(row_pos)

        t_inicio = datetime.now().strftime("%H:%M:%S")

        item_target = QTableWidgetItem(target)
        item_title = QTableWidgetItem(title)
        item_inicio = QTableWidgetItem(t_inicio)
        item_fim = QTableWidgetItem("-")
        item_status = QTableWidgetItem("Pendente (Na fila)...")
        item_resume = QTableWidgetItem("Aguardando processo...")

        item_inicio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_fim.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_table.setItem(row_pos, 0, item_target)
        self.status_table.setItem(row_pos, 1, item_title)
        self.status_table.setItem(row_pos, 2, item_inicio)
        self.status_table.setItem(row_pos, 3, item_fim)
        self.status_table.setItem(row_pos, 4, item_status)
        self.status_table.setItem(row_pos, 5, item_resume)

        self.queue_manager.add_task(
            target_pc=target,
            script_name=title,
            script_content=ps_script,
            module_name="Gestão de Software/Drivers",
            credentials=credentials,
            on_start=lambda t, st=item_status, rs=item_resume: self.update_status_start(t, st, rs),
            on_finish=lambda t, s, d, st=item_status, rs=item_resume, fi=item_fim: self.update_status_finish(t, s, d, st, rs, fi),
            on_error=lambda t, e, st=item_status, rs=item_resume, fi=item_fim: self.update_status_error(t, e, st, rs, fi)
        )

    def open_search_dialog(self):
        engine = self.cmb_engine.currentText()
        dialog = OnlineSearchDialog(engine=engine, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            novos_pacotes = dialog.selected_packages
            texto_atual = self.inp_custom_soft.text().strip()
            lista_atual = [p.strip() for p in texto_atual.split(",") if p.strip()]
            lista_atual.extend(novos_pacotes)
            lista_final = list(dict.fromkeys(lista_atual))
            self.inp_custom_soft.setText(", ".join(lista_final))

    def carregar_softwares_da_rede(self):
        self.tbl_offline.setRowCount(0)
        try:
            if not os.path.exists(self.network_software_path):
                QMessageBox.warning(
                    self,
                    "Aviso de Rede",
                    f"Caminho inacessível:\n{self.network_software_path}",
                )
                return
            arquivos = [
                f
                for f in os.listdir(self.network_software_path)
                if f.lower().endswith((".msi", ".exe"))
            ]
            if not arquivos:
                QMessageBox.information(
                    self, "Pasta Vazia", "Nenhum instalador (.exe, .msi) encontrado."
                )
                return
            for arq in sorted(arquivos):
                row = self.tbl_offline.rowCount()
                self.tbl_offline.insertRow(row)
                full_path = os.path.join(self.network_software_path, arq)
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                item_name = QTableWidgetItem(arq)
                item_name.setFlags(item_name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item_name.setCheckState(Qt.CheckState.Unchecked)
                item_size = QTableWidgetItem(f"{size_mb:.1f} MB")
                item_size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_offline.setItem(row, 0, item_name)
                self.tbl_offline.setItem(row, 1, item_size)
        except Exception as e:
            QMessageBox.critical(
                self, "Erro", f"Falha ao ler o diretório da rede:\n{e}"
            )
    def _get_credentials(self):
        """Retorna credenciais — cache → disco (DPAPI) → popup."""
        # 1) Cache de sessão em memória
        cached = getattr(self.main_window, 'get_cached_credentials', None)
        if cached:
            creds = cached()
            if creds:
                return creds

        # 2) Arquivo em disco (DPAPI, mesma máquina + mesmo usuário)
        saved = CredentialStore.load()
        if saved:
            setter = getattr(self.main_window, 'set_cached_credentials', None)
            if setter:
                setter(saved["user"], saved["pass"])
            return saved

        # 3) Popup
        dominio = os.environ.get("USERDOMAIN", "")
        usuario = os.environ.get("USERNAME", "")
        user_str = f"{dominio}\\{usuario}"

        dlg = CredentialDialog(user_display=user_str, has_saved=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        senha = dlg.password
        if not senha:
            return None

        # 4) Se marcou "lembrar", salva em disco (DPAPI)
        if dlg.remember:
            CredentialStore.save(user_str, senha)

        # 5) Guarda no cache de sessão
        setter = getattr(self.main_window, 'set_cached_credentials', None)
        if setter:
            setter(user_str, senha)

        return {"user": user_str, "pass": senha, "vnc_pass": senha}
    
    def start_software_install(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        offline_softwares = []
        for row in range(self.tbl_offline.rowCount()):
            item = self.tbl_offline.item(row, 0)
            if item.checkState() == Qt.CheckState.Checked:
                offline_softwares.append(item.text())

        online_softwares = []
        custom_text = self.inp_custom_soft.text().strip()
        if custom_text:
            online_softwares.extend(
                [s.strip() for s in custom_text.split(",") if s.strip()]
            )

        if not offline_softwares and not online_softwares:
            QMessageBox.warning(
                self, "Aviso", "Selecione um pacote da rede ou adicione um ID online."
            )
            return

        engine = self.cmb_engine.currentText()

        # Winget também precisa de credencial para o bootstrap via rede (Kerberos double-hop)
        needs_creds = bool(offline_softwares) or (
            engine == "Winget" and bool(online_softwares)
        )

        cred_completa = ""
        senha_safe = ""
        if needs_creds:
            creds = self._get_credentials()
            if creds is None:
                return
            cred_completa = creds["user"]
            senha_safe = creds["pass"]
        ps_offline = ", ".join(f"'{pkg}'" for pkg in offline_softwares)
        ps_online = ", ".join(f"'{pkg}'" for pkg in online_softwares)
        ps_array_offline = f"@({ps_offline})" if offline_softwares else "@()"
        ps_array_online = f"@({ps_online})" if online_softwares else "@()"

        core_script = f"""
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        $PacotesOffline = {ps_array_offline}
        $PacotesOnline  = {ps_array_online}
        $Engine = "{engine}"

        $LogData = @{{
            Script      = "Instalação Multi-Engine ($Engine)"
            Inicio      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            Computador  = $env:COMPUTERNAME
            StatusFinal = "SUCESSO"
            PacotesProcessados = @()
            Detalhes    = @()
        }}

        $driveCreated = $false

        try {{
            # ============================================================
            # PARTE 1 — Instalação ONLINE (Winget / Chocolatey)
            # ============================================================
            if ($PacotesOnline.Count -gt 0) {{
                # ==============================================================
                # RESOLUÇÃO DINÂMICA DO WINGET (com bootstrap se ausente)
                # ==============================================================
                if ($Engine -eq "Winget") {{
                    $LogData.Detalhes += "[Bootstrap] Verificando disponibilidade do Winget..."

                    $wingetExe = $null
                    $cmd = Get-Command winget -ErrorAction SilentlyContinue
                    if ($cmd) {{ $wingetExe = $cmd.Source }}

                    if (-not $wingetExe) {{
                        $candidate = "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\winget.exe"
                        if (Test-Path $candidate) {{ $wingetExe = $candidate }}
                    }}

                    if (-not $wingetExe) {{
                        $appInst = Get-ChildItem "C:\\Program Files\\WindowsApps\\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\\winget.exe" -ErrorAction SilentlyContinue |
                                   Sort-Object LastWriteTime -Descending |
                                   Select-Object -First 1
                        if ($appInst) {{ $wingetExe = $appInst.FullName }}
                    }}

                    # ------------------------------------------------------------
                    # Bootstrap: instala App Installer a partir da pasta de rede
                    # (usa PSDrive com credencial para contornar Double Hop)
                    # ------------------------------------------------------------
                    if (-not $wingetExe) {{
                        $LogData.Detalhes += "[Bootstrap] Winget ausente. Iniciando instalacao via rede..."

                        $wingetRoot  = "{self.SHARE_ROOT}"
                        $wingetDrive = "W"
                        $localTemp   = "C:\\Windows\\Temp"

                        # --- Montar PSDrive com credencial ---
                        if (Get-PSDrive -Name $wingetDrive -ErrorAction SilentlyContinue) {{
                            Remove-PSDrive -Name $wingetDrive -Force -ErrorAction SilentlyContinue
                        }}

                        try {{
                            $secPass = ConvertTo-SecureString '[[ADMIN_PASS]]' -AsPlainText -Force
                            $cred    = New-Object System.Management.Automation.PSCredential('[[ADMIN_USER]]', $secPass)
                            $null = New-PSDrive -Name $wingetDrive -PSProvider FileSystem -Root $wingetRoot -Credential $cred -Scope Global -ErrorAction Stop
                            $LogData.Detalhes += "[Bootstrap] PSDrive W: montado com credencial."
                        }} catch {{
                            $LogData.Detalhes += "[Bootstrap] Falha ao montar PSDrive: $($_.Exception.Message)"
                        }}

                        $wingetShare = "${{wingetDrive}}:\\Winget"
                        $LogData.Detalhes += "[Bootstrap] Caminho a usar: $wingetShare"
                        $LogData.Detalhes += "[Bootstrap] Test-Path: $(Test-Path $wingetShare)"

                        # --- Localizar arquivos por wildcard (version-agnostic) ---
                        $vcLibsBase    = Get-ChildItem $wingetShare -Filter "Microsoft.VCLibs.140.00_*.appx"          -ErrorAction SilentlyContinue | Select-Object -First 1
                        $vcLibsDesktop = Get-ChildItem $wingetShare -Filter "Microsoft.VCLibs.140.00.UWPDesktop_*.appx" -ErrorAction SilentlyContinue | Select-Object -First 1
                        $winAppRT      = Get-ChildItem $wingetShare -Filter "Microsoft.WindowsAppRuntime.*.appx"        -ErrorAction SilentlyContinue | Select-Object -First 1
                        $msixBundle    = Get-ChildItem $wingetShare -Filter "Microsoft.DesktopAppInstaller_*.msixbundle" -ErrorAction SilentlyContinue | Select-Object -First 1

                        if (-not $msixBundle) {{
                            $LogData.Detalhes += "[Bootstrap] ERRO: bundle do Winget nao encontrado em $wingetShare"
                        }} else {{
                            try {{
                                # Instalar dependencias (se presentes) em ordem
                                $depsToInstall = @($vcLibsBase, $vcLibsDesktop, $winAppRT) | Where-Object {{ $_ -ne $null }}
                                foreach ($dep in $depsToInstall) {{
                                    $depLocal = Join-Path $localTemp ("sarcc_" + $dep.Name)
                                    Copy-Item $dep.FullName -Destination $depLocal -Force -ErrorAction Stop
                                    try {{
                                        Add-AppxPackage -Path $depLocal -ErrorAction Stop
                                        $LogData.Detalhes += "[Bootstrap] Dependencia instalada: $($dep.Name)"
                                    }} catch {{
                                        # Se ja estiver instalada, nao e fatal
                                        $LogData.Detalhes += "[Bootstrap] Aviso em $($dep.Name): $($_.Exception.Message)"
                                    }}
                                    Remove-Item $depLocal -Force -ErrorAction SilentlyContinue
                                }}

                                # Instalar bundle principal
                                $msixLocal = Join-Path $localTemp "sarcc_winget.msixbundle"
                                Copy-Item $msixBundle.FullName -Destination $msixLocal -Force -ErrorAction Stop
                                Add-AppxPackage -Path $msixLocal -ErrorAction Stop
                                $LogData.Detalhes += "[Bootstrap] App Installer (Winget) instalado."
                                Remove-Item $msixLocal -Force -ErrorAction SilentlyContinue

                                Start-Sleep -Seconds 5

                                # Re-resolver caminho
                                $candidate = "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\winget.exe"
                                if (Test-Path $candidate) {{
                                    $wingetExe = $candidate
                                }} else {{
                                    $appInst = Get-ChildItem "C:\\Program Files\\WindowsApps\\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\\winget.exe" -ErrorAction SilentlyContinue |
                                               Sort-Object LastWriteTime -Descending |
                                               Select-Object -First 1
                                    if ($appInst) {{ $wingetExe = $appInst.FullName }}
                                }}

                                if ($wingetExe) {{
                                    $LogData.Detalhes += "[Bootstrap] Winget disponivel em: $wingetExe"
                                }} else {{
                                    $LogData.Detalhes += "[Bootstrap] Instalacao concluida mas winget.exe nao localizado."
                                }}
                            }} catch {{
                                $LogData.Detalhes += "[Bootstrap] ERRO: $($_.Exception.Message)"
                            }} finally {{
                                # Cleanup do PSDrive
                                if (Get-PSDrive -Name $wingetDrive -ErrorAction SilentlyContinue) {{
                                    Remove-PSDrive -Name $wingetDrive -Force -ErrorAction SilentlyContinue
                                }}
                            }}
                        }}
                    }} else {{
                        $LogData.Detalhes += "[Bootstrap] Winget ja presente em: $wingetExe"
                    }}

                    # ------------------------------------------------------------
                    # Execução dos pacotes
                    # ------------------------------------------------------------
                    if (-not $wingetExe) {{
                        foreach ($sw in $PacotesOnline) {{
                            $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Winget indisponivel no alvo e bootstrap falhou." }}
                        }}
                        $LogData.StatusFinal = "ALERTA/ERRO"
                    }} else {{
                        # --- Validar/Reparar sources do Winget antes de usar ---
                        $LogData.Detalhes += "[Winget] Verificando integridade das sources..."
                        try {{
                            $srcCheck = & $wingetExe source list 2>&1 | Out-String
                            if ($srcCheck -match "Nenhuma|No sources|corrupt|invalid" -or $LASTEXITCODE -ne 0) {{
                                $LogData.Detalhes += "[Winget] Sources suspeitas. Executando 'source reset --force'..."
                                & $wingetExe source reset --force 2>&1 | Out-Null
                                Start-Sleep -Seconds 3
                                & $wingetExe source update 2>&1 | Out-Null
                                $LogData.Detalhes += "[Winget] Sources restauradas."
                            }} else {{
                                $LogData.Detalhes += "[Winget] Sources OK."
                            }}
                        }} catch {{
                            $LogData.Detalhes += "[Winget] Aviso na validacao: $($_.Exception.Message)"
                        }}

                        foreach ($sw in $PacotesOnline) {{
                            $LogData.Detalhes += "Instalando: $sw"
                            # --source winget força uso APENAS do CDN público (evita msstore corporativo bloqueado)
                            $out = & $wingetExe install --id "$sw" -e --silent --accept-package-agreements --accept-source-agreements --scope machine --source winget 2>&1
                            $outText = ($out | Out-String).Trim()

                            # --- Auto-recovery para source corrompida ---
                            if ($outText -match "Falha ao abrir a origem|source reset|0x8A15000B") {{
                                $LogData.Detalhes += "[Winget] Source corrompida detectada. Executando reset e tentando novamente..."
                                & $wingetExe source reset --force 2>&1 | Out-Null
                                Start-Sleep -Seconds 3
                                & $wingetExe source update 2>&1 | Out-Null
                                Start-Sleep -Seconds 2
                                $out = & $wingetExe install --id "$sw" -e --silent --accept-package-agreements --accept-source-agreements --scope machine --source winget 2>&1
                                $outText = ($out | Out-String).Trim()
                            }}

                            $LogData.Detalhes += "--- SAIDA Winget ($sw) ---"
                            $LogData.Detalhes += $outText

                            # Códigos Winget:
                            #   0, 19, 3010 = sucesso
                            #   -1978335189 (0x8A15002B) = UPDATE_NOT_APPLICABLE (já instalado)
                            #   -1978335212 (0x8A150054) = PACKAGE_ALREADY_INSTALLED
                            #   -1978335211 (0x8A150055) = NO_APPLICABLE_INSTALLER
                            $jaInstalado = ($LASTEXITCODE -in @(-1978335189, -1978335212, -1978335211)) `
                                           -or $outText -match "pacote existente já instalado|already installed|Nenhuma atualização disponível|No applicable"

                            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 19 -or $LASTEXITCODE -eq 3010 `
                                -or $outText -match "Successfully|exito|installed|Sucesso" `
                                -or $jaInstalado) {{
                                if ($jaInstalado -and $LASTEXITCODE -notin @(0, 19, 3010)) {{
                                    $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Já instalado (sem atualização pendente)." }}
                                }} else {{
                                    $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Sucesso (Winget)." }}
                                }}
                            }} else {{
                                $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Falha (Cod $LASTEXITCODE)." }}
                                $LogData.StatusFinal = "ALERTA/ERRO"
                            }}
                        }}
                    }}
                }} else {{
                    # Chocolatey: fluxo normal
                    foreach ($sw in $PacotesOnline) {{
                        $LogData.Detalhes += "Instalando via Chocolatey: $sw"
                        $chocoExe = "C:\\ProgramData\\chocolatey\\bin\\choco.exe"
                        if (-not (Test-Path $chocoExe)) {{
                            $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Chocolatey NAO instalado no alvo." }}
                            $LogData.StatusFinal = "ALERTA/ERRO"
                            continue
                        }}
                        $out = & $chocoExe install $sw -y --no-progress 2>&1
                        $outText = ($out | Out-String).Trim()
                        $LogData.Detalhes += "--- SAIDA Chocolatey ($sw) ---"
                        $LogData.Detalhes += $outText

                        if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 3010 -or $outText -match "Successfully|exito|installed") {{
                            $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Sucesso (Chocolatey)." }}
                        }} else {{
                            $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Falha (Cod $LASTEXITCODE)." }}
                            $LogData.StatusFinal = "ALERTA/ERRO"
                        }}
                    }}
                }}
            }}

            # ============================================================
            # PARTE 2 — Instalação OFFLINE (rede SMB com PSDrive seguro)
            # ============================================================
            if ($PacotesOffline.Count -gt 0) {{
                $ShareServerPath = "{self.SHARE_ROOT}"
                $DriveLetter     = "Z"
                $LocalTempDir    = "C:\\Windows\\Temp"

                # Montar drive com credencial segura (sem net use em cmdline)
                if (Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue) {{
                    Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
                }}

                try {{
                            $secPass = ConvertTo-SecureString '[[ADMIN_PASS]]' -AsPlainText -Force
                            $cred    = New-Object System.Management.Automation.PSCredential('[[ADMIN_USER]]', $secPass)
                    $null = New-PSDrive -Name $DriveLetter -PSProvider FileSystem `
                                        -Root $ShareServerPath -Credential $cred `
                                        -Scope Global -ErrorAction Stop
                    $driveCreated = $true
                    $LogData.Detalhes += "[+] PSDrive Z: montado com credencial segura."
                }} catch {{
                    $LogData.PacotesProcessados += @{{ Software = "Rede"; Log = "Falha no mapeamento: $($_.Exception.Message)" }}
                    throw "Falha no mapeamento via New-PSDrive: $($_.Exception.Message)"
                }}

                $shareRoot = "${{DriveLetter}}:"

                foreach ($sw in $PacotesOffline) {{
                    $remoteInstaller = Join-Path $shareRoot "Softwares\\$sw"
                    if (-not (Test-Path -LiteralPath $remoteInstaller)) {{
                        $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Arquivo não encontrado na rede" }}
                        $LogData.StatusFinal = "ALERTA/ERRO"
                        continue
                    }}

                    # Copiar para temp local antes de instalar (evita erro 1603 em MSI)
                    $localInstaller = Join-Path $LocalTempDir "SARCC_$sw"
                    try {{
                        Copy-Item -LiteralPath $remoteInstaller -Destination $localInstaller -Force -ErrorAction Stop
                    }} catch {{
                        $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Falha ao copiar: $($_.Exception.Message)" }}
                        $LogData.StatusFinal = "ALERTA/ERRO"
                        continue
                    }}

                    # Executar instalador do disco local
                    try {{
                        if ($sw -match '\\.msi$') {{
                            $msiLog = Join-Path $LocalTempDir "SARCC_$sw.log"
                            $args = "/i `"$localInstaller`" /qn /norestart /l*v `"$msiLog`" ALLUSERS=1"
                            $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $args -Wait -PassThru -NoNewWindow
                        }} else {{
                            $args = "/S /silent /quiet /qn"
                            $proc = Start-Process -FilePath $localInstaller -ArgumentList $args -Wait -PassThru -NoNewWindow
                        }}

                        if ($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 3010) {{
                            $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Sucesso (Offline, código $($proc.ExitCode))" }}
                        }} else {{
                            $LogData.PacotesProcessados += @{{ Software = $sw; Log = "Erro (Código $($proc.ExitCode))" }}
                            $LogData.StatusFinal = "ALERTA/ERRO"
                        }}
                    }} finally {{
                        Remove-Item -LiteralPath $localInstaller -Force -ErrorAction SilentlyContinue
                    }}
                }}
            }}
        }} catch {{
            $LogData.StatusFinal = "ERRO FATAL"
            $LogData.Detalhes += $_.Exception.Message
        }} finally {{
            if ($driveCreated) {{
                Remove-PSDrive -Name $DriveLetter -Force -ErrorAction SilentlyContinue
            }}
            $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            $LogData | ConvertTo-Json -Depth 4 -Compress | Write-Output
        }}
        """

        # Credenciais vão para o TaskWorker (ponto único de injeção)
        credentials = None
        if needs_creds:
            credentials = {
                "user": cred_completa,
                "pass": senha_safe,
                "vnc_pass": senha_safe,
            }

        self._enqueue_task(target, "Instalação Multi-Engine", core_script, credentials=credentials)

    def clear_table_on_engine_change(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.chk_select_all.setChecked(False)
        self.inp_filter.clear()
        self.table.setSortingEnabled(True)

    def apply_filters(self, *args):
        """Filtro unificado: texto (ID + Nome) AND (opcional) só com atualização."""
        search_term = self.inp_filter.text().lower().strip()
        only_updates = self.chk_only_updates.isChecked()

        for row in range(self.table.rowCount()):
            # Critério 1: texto (busca em ID e Nome)
            match = not search_term
            if search_term:
                id_item = self.table.item(row, 1)
                name_item = self.table.item(row, 2)
                if id_item and search_term in id_item.text().lower():
                    match = True
                elif name_item and search_term in name_item.text().lower():
                    match = True

            # Critério 2: só com atualização disponível
            if match and only_updates:
                avail_item = self.table.item(row, 4)
                avail_text = (avail_item.text() if avail_item else "").strip()
                # "-", "" ou "Nenhuma" não têm update
                if not avail_text or avail_text == "-":
                    match = False

            self.table.setRowHidden(row, not match)

        # Atualiza contador visual no checkbox (opcional, mas útil)
        if only_updates:
            total_visiveis = sum(
                1 for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)
            )
            self.chk_only_updates.setText(f"⬆️ Só com atualização ({total_visiveis})")
        else:
            self.chk_only_updates.setText("⬆️ Só com atualização")

    def fetch_software(self):
        target = self.inp_target.text().strip()
        engine = self.cmb_engine.currentText()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return
        self.btn_fetch.setEnabled(False)
        self.btn_check_updates.setEnabled(False)
        self.btn_fetch.setText(f"Lendo {engine}...")
        self.clear_table_on_engine_change()

        self.worker_fetch = FetchSoftwareWorker(target, engine)
        self.worker_fetch.finished.connect(self.populate_table)
        self.worker_fetch.error.connect(self.show_error)
        self.worker_fetch.start()

    def populate_table(self, pkgs_list):
        self.table.setSortingEnabled(False)
        achou_software_real = False

        for pkg in pkgs_list:
            if not isinstance(pkg, dict):
                continue
            pkg_id = pkg.get("Id", "-")
            name = pkg.get("Name", "Desconhecido")
            if name == "Nenhum software encontrado":
                continue

            achou_software_real = True
            ver = pkg.get("Version", "-")
            orig = pkg.get("Origin", "Winget")

            row_pos = self.table.rowCount()
            self.table.insertRow(row_pos)

            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_box = QCheckBox()
            chk_layout.addWidget(chk_box)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)

            self.table.setItem(row_pos, 0, QTableWidgetItem(""))
            self.table.setCellWidget(row_pos, 0, chk_widget)
            self.table.setItem(row_pos, 1, QTableWidgetItem(pkg_id))
            self.table.setItem(row_pos, 2, QTableWidgetItem(name))
            self.table.setItem(row_pos, 3, QTableWidgetItem(ver))
            available = (pkg.get("Available", "") or "").strip()
            item_avail = QTableWidgetItem(available if available else "-")
            if available:
                item_avail.setForeground(Qt.GlobalColor.green)
            self.table.setItem(row_pos, 4, item_avail)

            item_orig = QTableWidgetItem(orig)
            if orig == "Chocolatey":
                item_orig.setForeground(Qt.GlobalColor.cyan)
            elif orig == "Windows Registry":
                item_orig.setForeground(Qt.GlobalColor.yellow)
            else:
                item_orig.setForeground(Qt.GlobalColor.green)
            self.table.setItem(row_pos, 5, item_orig)

        self.table.setSortingEnabled(True)
        self.btn_fetch.setEnabled(True)
        self.btn_check_updates.setEnabled(True)
        self.btn_fetch.setText("🔄 Listar Softwares (Inventário)")
        self.apply_filters()

        if not achou_software_real:
            QMessageBox.information(
                self,
                "Inventário Vazio",
                f"A varredura foi concluída, mas nenhum pacote foi retornado pelo motor '{self.cmb_engine.currentText()}'.\nO computador alvo pode não ter este gerenciador instalado.",
            )

    def check_updates(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Liste os softwares primeiro.")
            return
        target = self.inp_target.text().strip()
        engine = self.cmb_engine.currentText()

        self.btn_fetch.setEnabled(False)
        self.btn_check_updates.setEnabled(False)
        self.btn_check_updates.setText(f"Buscando no {engine}...")

        self.worker_upd = CheckUpdatesWorker(target, engine)
        self.worker_upd.finished.connect(self.apply_updates_to_table)
        self.worker_upd.error.connect(self.show_error)
        self.worker_upd.start()

    def apply_updates_to_table(self, updates_dict):
        self.table.setSortingEnabled(False)
        self.btn_fetch.setEnabled(True)
        self.btn_check_updates.setEnabled(True)
        self.btn_check_updates.setText("🔎 Verificar Atualizações")

        if not updates_dict:
            QMessageBox.information(
                self,
                "Atualizações",
                "Nenhuma atualização encontrada para os pacotes deste motor.",
            )
            self.table.setSortingEnabled(True)
            return

        updates_lower = {k.lower(): v for k, v in updates_dict.items()}
        achou_alguma = False

        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 1)
            if id_item:
                pkg_id = id_item.text().lower()
                if pkg_id in updates_lower:
                    new_ver = updates_lower[pkg_id]
                    item_update = QTableWidgetItem(new_ver)
                    item_update.setForeground(Qt.GlobalColor.green)
                    self.table.setItem(row, 4, item_update)
                    achou_alguma = True

        self.table.setSortingEnabled(True)
        if achou_alguma:
            QMessageBox.information(
                self,
                "Sucesso",
                "Atualizações encontradas! Clique no cabeçalho 'Nova Versão'.",
            )

    def show_error(self, err):
        self.btn_fetch.setEnabled(True)
        self.btn_check_updates.setEnabled(True)
        self.btn_fetch.setText("🔄 Listar Softwares (Inventário)")
        self.btn_check_updates.setText("🔎 Verificar Atualizações")
        QMessageBox.critical(self, "Erro", f"Falha na comunicação:\n{err}")

    def toggle_select_all(self, state):
        is_checked = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            chk_widget = self.table.cellWidget(row, 0)
            if chk_widget:
                checkbox = chk_widget.findChild(QCheckBox)
                if checkbox:
                    if self.table.isRowHidden(row):
                        checkbox.setChecked(False)  # força limpar os escondidos
                    else:
                        checkbox.setChecked(is_checked)

    def execute_action(self, action):
        target = self.inp_target.text().strip()
        engine = self.cmb_engine.currentText()
        if not target:
            self.inp_target.setFocus()
            return

        selected_pkgs = []
        for row in range(self.table.rowCount()):
            chk_widget = self.table.cellWidget(row, 0)
            if chk_widget:
                checkbox = chk_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    pkg_id = self.table.item(row, 1).text()
                    selected_pkgs.append(f"'{pkg_id}'")

        if not selected_pkgs:
            QMessageBox.warning(
                self, "Aviso", "Selecione pelo menos um pacote na tabela."
            )
            return

        use_force = self.chk_force_close.isChecked() and action == "upgrade"
        force_flag = "--force" if use_force else ""
        pkgs_array_str = ", ".join(selected_pkgs)
        script_title = f"{action.capitalize()} ({engine})"

        core_script = f"""
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8

        $Pacotes = @({pkgs_array_str})
        $Engine = "{engine}"
        $LogData = @{{
            Script = "{script_title}"
            Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            Computador = $env:COMPUTERNAME
            StatusFinal = "SUCESSO"
            PacotesProcessados = @()
            Detalhes = @()
        }}

        try {{
            $wingetPath = (Get-Command winget -ErrorAction SilentlyContinue).Source
            if (-not $wingetPath -or -not (Test-Path $wingetPath)) {{
                $wingetPath = "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\winget.exe"
                if (-not (Test-Path $wingetPath)) {{
                    $appInst = Get-ChildItem -Path "C:\\Program Files\\WindowsApps\\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\\winget.exe" -ErrorAction SilentlyContinue |
                               Sort-Object LastWriteTime -Descending |
                               Select-Object -First 1
                    if ($appInst) {{ $wingetPath = $appInst.FullName }}
                }}
            }}

            foreach ($p in $Pacotes) {{
                $LogData.Detalhes += "Processando ID: $p ($Engine)"
                
                if ($Engine -eq "Winget") {{
                    if (-not $wingetPath -or -not (Test-Path $wingetPath)) {{
                        $LogData.PacotesProcessados += @{{ Software = $p; Log = "Falha: Winget não localizado no alvo." }}
                        $LogData.StatusFinal = "ALERTA/ERRO"
                        continue
                    }}
                    
                    if ("{action}" -eq "uninstall") {{
                        $out = & $wingetPath uninstall --id "$p" --exact --silent --accept-source-agreements --source winget 2>&1
                        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 19 -and $LASTEXITCODE -ne 3010) {{
                            $LogData.Detalhes += "Tentando fallback por nome flexível..."
                            $out = & $wingetPath uninstall "$p" --silent --all-versions --accept-source-agreements --source winget 2>&1
                            if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 19 -and $LASTEXITCODE -ne 3010) {{
                                $LogData.Detalhes += "Tentando fallback via WMI (Silencioso)..."
                                $wmi = Get-CimInstance Win32_Product -Filter "Name LIKE '%$p%'" -ErrorAction SilentlyContinue
                                if ($wmi) {{
                                    $null = Invoke-CimMethod -InputObject $wmi -MethodName Uninstall
                                    $out = "Desinstalado com sucesso via WMI."
                                    $LASTEXITCODE = 0
                                }}
                            }}
                        }}
                    }} elseif ("{action}" -eq "upgrade") {{
                        $forceFlag = "{force_flag}"
                        $out = & $wingetPath upgrade --id "$p" --exact --silent $forceFlag --accept-package-agreements --accept-source-agreements --scope machine --source winget 2>&1
                        $outTmp = ($out | Out-String)
                        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 19 -and $LASTEXITCODE -ne 3010 -and $outTmp -notmatch "Nenhuma atualização|No applicable|already installed") {{
                            $out = & $wingetPath upgrade "$p" --silent --accept-package-agreements --accept-source-agreements --scope machine --source winget 2>&1
                        }}
                    }} else {{
                        $out = & $wingetPath install --id "$p" --exact --force --silent --accept-package-agreements --accept-source-agreements --scope machine --source winget 2>&1
                        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 19 -and $LASTEXITCODE -ne 3010) {{
                            $out = & $wingetPath install "$p" --force --silent --accept-package-agreements --accept-source-agreements --scope machine --source winget 2>&1
                        }}
                    }}
                }} else {{
                    if ("{action}" -eq "uninstall") {{
                        $out = choco uninstall "$p" -y --no-progress 2>&1
                    }} elseif ("{action}" -eq "upgrade") {{
                        $out = choco upgrade "$p" -y --no-progress 2>&1
                    }} else {{
                        $out = choco install "$p" -y --force --no-progress 2>&1
                    }}
                }}
                
                $outText = $out -join " "
                $jaInstalado = ($LASTEXITCODE -in @(-1978335189, -1978335212, -1978335211)) `
                               -or $outText -match "pacote existente já instalado|already installed|Nenhuma atualização|No applicable"
                                $isSharingViolation = ($LASTEXITCODE -eq -2147024864) -or ($outText -match "0x80070020|being used by another process|usado por outro processo")
                if ($isSharingViolation) {{
                    $LogData.PacotesProcessados += @{{ Software = $p; Log = "Falha: app em execucao no alvo. Use 'Fechar apps antes de atualizar' ou peca ao usuario para fechar." }}
                    $LogData.StatusFinal = "ALERTA/ERRO"
                    $LogData.Detalhes += $outText
                    continue
                }}
                if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 19 -or $LASTEXITCODE -eq 3010 `
                    -or $outText -match "Successfully|êxito|WMI|Sucesso" `
                    -or $jaInstalado) {{
                    if ($jaInstalado -and $LASTEXITCODE -notin @(0, 19, 3010)) {{
                        $LogData.PacotesProcessados += @{{ Software = $p; Log = "Já instalado (sem atualização)." }}
                    }} else {{
                        $LogData.PacotesProcessados += @{{ Software = $p; Log = "Sucesso." }}
                    }}
                }} else {{
                    $LogData.PacotesProcessados += @{{ Software = $p; Log = "Falha (Cód $LASTEXITCODE). Ver Detalhes." }}
                    $LogData.StatusFinal = "ALERTA/ERRO"
                }}
                $LogData.Detalhes += $outText
            }}
        }} catch {{
            $LogData.StatusFinal = "ERRO FATAL"
            $LogData.Detalhes += $_.Exception.Message
        }} finally {{
            $LogData.Fim = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            $LogData | ConvertTo-Json -Depth 3 -Compress | Write-Output
        }}
        """

        reply = QMessageBox.question(
            self,
            "Ação",
            f"Executar {action} via {engine} em {len(selected_pkgs)} pacote(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._enqueue_task(target, script_title, core_script)
            self.chk_select_all.setChecked(False)

    @pyqtSlot(str, object, object)
    def update_status_start(self, target_pc, item_status, item_resume):
        try:
            item_status.setText("A Executar...")
            item_resume.setText("Aguarde a conclusão da operação...")
        except RuntimeError:
            pass

    @pyqtSlot(str, str, dict, object, object, object)
    def update_status_finish(
        self, target_pc, status, json_data, item_status, item_resume, item_fim
    ):
        try:
            item_status.setText(status)
            item_fim.setText(datetime.now().strftime("%H:%M:%S"))

            if "SUCESSO" in status.upper() or json_data.get("StatusFinal") == "SUCESSO":
                item_status.setForeground(Qt.GlobalColor.green)
            elif (
                "ERRO" in status.upper()
                or "FALHA" in status.upper()
                or "ALERTA" in status.upper()
            ):
                item_status.setForeground(Qt.GlobalColor.red)
            else:
                item_status.setForeground(Qt.GlobalColor.darkYellow)

            resumo = f"Status: {json_data.get('StatusFinal', 'Concluído')}"
            if "PacotesProcessados" in json_data:
                for pct in json_data.get("PacotesProcessados", []):
                    resumo += f"\n- {pct.get('Software', '')}: {pct.get('Log', '')}"
            if "Detalhes" in json_data:
                detalhes = json_data.get("Detalhes")
                if isinstance(detalhes, list):
                    resumo += "\n" + "\n".join(detalhes)
                elif isinstance(detalhes, str):
                    resumo += f"\n{detalhes}"

            item_resume.setText(resumo)
            row = item_status.row()
            if row >= 0:
                self.status_table.resizeRowToContents(row)
        except RuntimeError:
            pass

    @pyqtSlot(str, str, object, object, object)
    def update_status_error(
        self, target_pc, error_msg, item_status, item_resume, item_fim
    ):
        try:
            item_status.setText("Erro de Execução")
            item_status.setForeground(Qt.GlobalColor.red)
            item_resume.setText(error_msg)

            item_fim.setText(datetime.now().strftime("%H:%M:%S"))

            row = item_status.row()
            if row >= 0:
                self.status_table.resizeRowToContents(row)
        except RuntimeError:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()
