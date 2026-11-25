import base64
import csv
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.credential_store import CredentialStore
from core.logger import get_logger
from core.ps_loader import PsTemplateError, load_ps_template
from core.remote_connection import RemoteConnectionManager
from core.task_queue import TaskQueueManager
from core.text_utils import fix_mojibake
from gui.dialogs.dialogs import CredentialDialog
from gui.views.base_view import BaseView

log = get_logger(__name__)


class ExecutionLogDialog(QDialog):
    """Janela modal para visualizar o log verbose completo de uma execução."""
    def __init__(self, target: str, operation: str, status: str, log_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Log Detalhado (Verbose) — {target}")
        self.resize(780, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        header = QLabel(f"<b>Alvo:</b> {target} &nbsp;|&nbsp; <b>Operação:</b> {operation} &nbsp;|&nbsp; <b>Status:</b> {status}")
        header.setStyleSheet("font-size: 13px; color: #4a90e2;")
        layout.addWidget(header)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setPlainText(fix_mojibake(log_text))
        self.txt_log.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background-color: #121212; color: #e0e0e0; padding: 10px; border: 1px solid #444;"
        )
        layout.addWidget(self.txt_log)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copiar Log Completo")
        btn_copy.setFixedHeight(32)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet("background-color: #5bc0de; color: black; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        btn_copy.clicked.connect(self._copy_log)
        btn_layout.addWidget(btn_copy)

        btn_layout.addStretch()

        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("background-color: #4a90e2; color: white; font-weight: bold; padding: 0 20px; border-radius: 4px;")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _copy_log(self):
        QApplication.clipboard().setText(self.txt_log.toPlainText())
        QMessageBox.information(self, "Copiado", "Log copiado para a área de transferência.")


class OnlineSearchDialog(QDialog):
    def __init__(self, engine="Winget", parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle(f"Pesquisar Pacotes Online ({self.engine})")
        self.resize(680, 470)
        self.selected_packages = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        search_layout = QHBoxLayout()
        self.inp_search = QLineEdit()
        self.inp_search.setFixedHeight(32)
        self.inp_search.setPlaceholderText(f"Digite o nome para buscar no {self.engine} (ex: brave, 7zip, vlc)...")
        self.inp_search.setStyleSheet("padding: 0 10px;")
        self.inp_search.returnPressed.connect(self.search_packages)

        btn_search = QPushButton("🔍 Buscar")
        btn_search.setFixedHeight(32)
        btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_search.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        btn_search.clicked.connect(self.search_packages)

        search_layout.addWidget(self.inp_search)
        search_layout.addWidget(btn_search)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID do Pacote", "Nome", "Versão"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.lbl_aviso = QLabel(f"<i>Motor selecionado: {self.engine} (Com fallback automático de nuvem).</i>")
        self.lbl_aviso.setStyleSheet("color: #888;")
        btn_layout.addWidget(self.lbl_aviso)
        btn_layout.addStretch()

        btn_add = QPushButton("➕ Adicionar Selecionados")
        btn_add.setFixedHeight(32)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet("background-color: #1e8a5e; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        btn_add.clicked.connect(self.add_selected)
        btn_layout.addWidget(btn_add)
        layout.addLayout(btn_layout)

    @staticmethod
    def _find_choco_exe() -> str | None:
        default_path = r"C:\ProgramData\chocolatey\bin\choco.exe"
        if os.path.exists(default_path):
            return default_path
        return shutil.which("choco")

    @staticmethod
    def _find_winget_exe() -> str | None:
        w = shutil.which("winget")
        if w:
            return w
        local_app = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe")
        if os.path.exists(local_app):
            return local_app
        return None

    def search_packages(self):
        term = self.inp_search.text().strip()
        if not term:
            return

        self.table.setRowCount(0)
        titulo_original = self.windowTitle()
        self.setWindowTitle(f"Buscando '{term}' no {self.engine}... Aguarde.")
        QApplication.processEvents()

        try:
            if self.engine == "Chocolatey":
                choco_exe = self._find_choco_exe()
                found_local = False

                if choco_exe:
                    result = subprocess.run(
                        [choco_exe, "search", term, "--limit-output"],
                        capture_output=True,
                        text=False,
                        shell=False,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    stdout = self._smart_decode(result.stdout)
                    found_local = self._parse_chocolatey(stdout, silent_if_empty=True)

                if not found_local:
                    self.lbl_aviso.setText("<i>🌐 Busca realizada via API Oficial do Chocolatey (Fallback Cloud ativo).</i>")
                    self._search_chocolatey_cloud_api(term)
                else:
                    self.lbl_aviso.setText("<i>✔ Busca realizada via motor Chocolatey local.</i>")
            else:
                winget_exe = self._find_winget_exe()
                if not winget_exe:
                    QMessageBox.critical(
                        self,
                        "Winget Ausente",
                        "O utilitário Winget (Instalador de Aplicativo da Microsoft) não foi encontrado na sua máquina local."
                    )
                    return

                result = subprocess.run(
                    [winget_exe, "search", term, "--source", "winget", "--accept-source-agreements", "--disable-interactivity"],
                    capture_output=True,
                    text=False,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                stdout = self._smart_decode(result.stdout)
                stderr = self._smart_decode(result.stderr)
                if not stdout.strip():
                    self._show_winget_diagnostic(stderr, result.returncode)
                    return
                self._parse_winget(stdout)
        finally:
            self.setWindowTitle(titulo_original)

    def _search_chocolatey_cloud_api(self, term: str):
        try:
            safe_term = urllib.parse.quote(term)
            url = (
                f"https://community.chocolatey.org/api/v2/Search()?"
                f"$filter=IsLatestVersion&searchTerm='{safe_term}'&targetFramework=''&includePrerelease=false&$skip=0&$top=40"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "SARCC-Enterprise/2.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_data = resp.read().decode("utf-8", errors="replace")

            root = ET.fromstring(xml_data)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
                "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
            }
            entries = root.findall("atom:entry", ns)
            encontrou = False

            for entry in entries:
                props = entry.find("m:properties", ns)
                if props is None:
                    continue
                pkg_id_el = props.find("d:Id", ns)
                title_el = props.find("d:Title", ns)
                ver_el = props.find("d:Version", ns)

                pkg_id = pkg_id_el.text.strip() if (pkg_id_el is not None and pkg_id_el.text) else ""
                title = title_el.text.strip() if (title_el is not None and title_el.text) else pkg_id
                ver = ver_el.text.strip() if (ver_el is not None and ver_el.text) else "-"

                if pkg_id:
                    encontrou = True
                    row_pos = self.table.rowCount()
                    self.table.insertRow(row_pos)
                    self.table.setItem(row_pos, 0, QTableWidgetItem(pkg_id))
                    self.table.setItem(row_pos, 1, QTableWidgetItem(title))
                    self.table.setItem(row_pos, 2, QTableWidgetItem(ver))

            if not encontrou:
                QMessageBox.information(self, "Busca", f"Nenhum pacote encontrado para '{term}' no repositório do Chocolatey.")
        except Exception as e:
            QMessageBox.warning(self, "Erro na Busca Online", f"Não foi possível consultar o repositório do Chocolatey:\n{e}")

    @staticmethod
    def _smart_decode(raw_bytes) -> str:
        if not raw_bytes:
            return ""
        if isinstance(raw_bytes, str):
            return fix_mojibake(raw_bytes.strip())
        try:
            return fix_mojibake(raw_bytes.decode("utf-8").strip())
        except (UnicodeDecodeError, ValueError):
            try:
                return fix_mojibake(raw_bytes.decode("cp850").strip())
            except (UnicodeDecodeError, ValueError):
                return fix_mojibake(raw_bytes.decode("utf-8", errors="replace").strip())

    def _show_winget_diagnostic(self, stderr: str, returncode: int):
        low = (stderr or "").lower()
        if "não reconhecido" in low or "not recognized" in low or "não pode ser encontrado" in low:
            QMessageBox.critical(self, "Winget não instalado", "O Winget não foi encontrado nesta máquina local.")
        elif "internet" in low or "network" in low or "0x8a150014" in low:
            QMessageBox.critical(self, "Sem acesso", "O Winget não conseguiu alcançar os servidores da Microsoft.")
        else:
            QMessageBox.warning(self, "Sem retorno", f"Código: {returncode}\nstderr: {stderr[:500] if stderr else '(vazio)'}")

    def _parse_chocolatey(self, stdout: str, silent_if_empty: bool = False) -> bool:
        if not stdout.strip():
            if not silent_if_empty:
                QMessageBox.information(self, "Busca", "Nenhum pacote encontrado.")
            return False
        linhas = stdout.splitlines()
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
        if not encontrou and not silent_if_empty:
            QMessageBox.information(self, "Busca", "Nenhum pacote encontrado.")
        return encontrou

    def _parse_winget(self, stdout: str):
        linhas = stdout.splitlines()
        start_idx = -1
        for i, linha in enumerate(linhas):
            if re.match(r"^[-─]{3,}", linha.strip()):
                start_idx = i + 1
                break
        if start_idx == -1:
            for i, linha in enumerate(linhas):
                if re.search(r"\b(Id|Nome|Name|Versão|Version)\b", linha) and "  " in linha:
                    start_idx = i + 2
                    break
        if start_idx == -1 or start_idx >= len(linhas):
            if re.search(r"(Nenhum|No package|Não foram|no packages)", stdout, re.I):
                QMessageBox.information(self, "Busca", "Nenhum pacote encontrado.")
            else:
                QMessageBox.warning(self, "Formato", f"Não foi possível interpretar a saída.\n{stdout[:500]}")
            return

        encontrou = False
        for linha in linhas[start_idx:]:
            stripped = linha.strip()
            if not stripped or stripped.startswith("-"):
                continue
            partes = re.split(r"\s{2,}", stripped)
            if len(partes) < 3:
                partes = [p.strip() for p in re.split(r"[|│]", stripped) if p.strip()]
            if len(partes) >= 3:
                encontrou = True
                row_pos = self.table.rowCount()
                self.table.insertRow(row_pos)
                self.table.setItem(row_pos, 0, QTableWidgetItem(partes[1]))
                self.table.setItem(row_pos, 1, QTableWidgetItem(fix_mojibake(partes[0])))
                self.table.setItem(row_pos, 2, QTableWidgetItem(partes[2]))
        if not encontrou:
            QMessageBox.warning(self, "Erro", "Nenhuma linha interpretada.")

    def add_selected(self):
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        for row in selected_rows:
            self.selected_packages.append(self.table.item(row, 0).text())
        if self.selected_packages:
            self.accept()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione um pacote.")


class FetchSoftwareWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, target_pc, engine):
        super().__init__()
        self.target_pc = target_pc
        self.engine = engine

    def run(self):
        try:
            try:
                ps_script = load_ps_template("software", "inventory", engine=self.engine)
            except PsTemplateError as e:
                self.error.emit(f"Erro interno: {e}")
                return
            conn = RemoteConnectionManager()
            res = conn.execute_script(self.target_pc, ps_script)

            if res["status"] == "Sucesso" and res.get("json_data"):
                json_data = res["json_data"]
                if isinstance(json_data, dict) and json_data.get("StatusFinal") == "ERRO FATAL":
                    self.error.emit("Erro Crítico remoto.")
                    return
                pacotes = json_data.get("Pacotes", []) if isinstance(json_data, dict) else []
                if not isinstance(pacotes, list):
                    pacotes = [pacotes]
                self.finished.emit(pacotes)
            else:
                self.error.emit(res.get("log_saida", "Erro de comunicação ao listar inventário."))
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
            try:
                ps_script = load_ps_template("software", "check_updates", engine=self.engine)
            except PsTemplateError as e:
                self.error.emit(f"Erro interno: {e}")
                return
            conn = RemoteConnectionManager()
            res = conn.execute_script(self.target_pc, ps_script)

            if res["status"] == "Sucesso" and res.get("json_data"):
                self.finished.emit(res["json_data"].get("Atualizacoes", {}))
            else:
                self.error.emit(res.get("log_saida", "Falha ao analisar as atualizações."))
        except Exception as e:
            self.error.emit(str(e))


class SoftwareView(BaseView):
    SYSTEM_APP_PATTERNS = (
        "msix\\",
        "microsoft.windows",
        "microsoft.zune",
        "microsoft.vp9",
        "microsoft.webmedia",
        "microsoft.webp",
        "microsoft.heif",
        "microsoft.screensketch",
        "microsoft.getstarted",
        "microsoft.bing",
        "microsoft.549981c3f5f10",
        "microsoft.xbox",
        "microsoft.gaming",
        "microsoft.yourphone",
        "microsoft.people",
        "microsoft.todos",
        "microsoft.powerautomate",
        "microsoft.paint",
        "microsoft.windowsalarms",
        "microsoft.windowscalculator",
        "microsoft.windowscamera",
        "microsoft.windowscommunicationsapps",
        "microsoft.windowsfeedbackhub",
        "microsoft.windowsmaps",
        "microsoft.windowsnotepad",
        "microsoft.windowssoundrecorder",
        "microsoft.windowsterminal",
    )

    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(main_window_ref, "queue_manager", None) or TaskQueueManager(max_threads=5)
        self.SHARE_ROOT = r"\\hul-vp-imagem-cc\netshared"
        self.network_software_path = r"\\hul-vp-imagem-cc\netshared\Softwares"
        self.cat_map = {
            "Todos Essenciais (Vídeo, Rede, Áudio, BT, Cam)": "Todos",
            "Vídeo (Display)": "Display",
            "Rede (Net)": "Net",
            "Áudio (Media)": "Media",
            "Bluetooth": "Bluetooth",
            "Câmaras (Camera/Image)": "Camera_Image",
        }
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Gestão e Inventário de Softwares e Drivers")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        target_group = QGroupBox("Controle de Endpoint e Motor de Gestão")
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
        self.btn_fetch.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_fetch.clicked.connect(self.fetch_software)

        self.btn_check_updates = QPushButton("🔎 Verificar Atualizações")
        self.btn_check_updates.setFixedHeight(32)
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_updates.setStyleSheet("background-color: #f0ad4e; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;")
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

        status_group = QGroupBox("Acompanhamento de Execução Remota (Duplo clique na linha para abrir Log Verbose)")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(10, 15, 10, 10)

        header_lote = QHBoxLayout()
        header_lote.addStretch()
        self.btn_clear_table = QPushButton("🧹 Limpar Lista")
        self.btn_clear_table.setFixedHeight(28)
        self.btn_clear_table.setStyleSheet("padding: 0 15px; background-color: #666; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_clear_table.clicked.connect(self._clear_status_table)
        header_lote.addWidget(self.btn_clear_table)
        status_layout.addLayout(header_lote)

        self.status_table = QTableWidget(0, 6)
        self.status_table.setHorizontalHeaderLabels(["Computador Alvo", "Operação", "Início", "Fim", "Status Atual", "Resumo da Execução"])
        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.status_table.setColumnWidth(0, 130)
        self.status_table.setColumnWidth(1, 200)
        self.status_table.setColumnWidth(2, 70)
        self.status_table.setColumnWidth(3, 70)
        self.status_table.setColumnWidth(4, 110)
        self.status_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.status_table.setWordWrap(True)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.status_table.setMaximumHeight(160)
        self.status_table.cellDoubleClicked.connect(self._open_verbose_log_dialog)
        status_layout.addWidget(self.status_table)
        layout.addWidget(status_group)

    def on_tab_changed(self, index):
        show_engine = index in [0, 1]
        self.cmb_engine.setVisible(show_engine)
        self.lbl_motor.setVisible(show_engine)
        self.btn_fetch.setVisible(index == 0)
        self.btn_check_updates.setVisible(index == 0)

    def _build_aba_inventario(self):
        tab_inv = QWidget()
        inv_layout = QVBoxLayout(tab_inv)

        actions_layout = QHBoxLayout()
        self.btn_upgrade = QPushButton("⭐ Atualizar Selecionados")
        self.btn_upgrade.setFixedHeight(32)
        self.btn_upgrade.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_upgrade.setStyleSheet("background-color: #1e8a5e; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_upgrade.clicked.connect(lambda: self.execute_action("upgrade"))

        self.btn_uninstall = QPushButton("🗑 Desinstalar Selecionados")
        self.btn_uninstall.setFixedHeight(32)
        self.btn_uninstall.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_uninstall.setStyleSheet("background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_uninstall.clicked.connect(lambda: self.execute_action("uninstall"))

        self.btn_export_inv = QPushButton("📥 Exportar Lista (CSV)")
        self.btn_export_inv.setFixedHeight(32)
        self.btn_export_inv.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_inv.setStyleSheet("background-color: #5bc0de; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_export_inv.clicked.connect(self.export_inventory_csv)

        actions_layout.addWidget(self.btn_upgrade)
        actions_layout.addWidget(self.btn_uninstall)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_export_inv)
        inv_layout.addLayout(actions_layout)

        filter_layout = QHBoxLayout()
        self.chk_select_all = QCheckBox("Selecionar / Desmarcar Todos")
        self.chk_select_all.setStyleSheet("font-weight: bold; color: #4a90e2;")
        self.chk_select_all.stateChanged.connect(self.toggle_select_all)
        filter_layout.addWidget(self.chk_select_all)

        self.chk_force_close = QCheckBox("🔪 Fechar apps antes de atualizar")
        self.chk_force_close.setStyleSheet("font-weight: bold; color: #d9534f; margin-left: 10px;")
        filter_layout.addWidget(self.chk_force_close)

        self.chk_hide_system = QCheckBox("🚫 Ocultar Apps do Sistema (MSIX/Windows)")
        self.chk_hide_system.setStyleSheet("font-weight: bold; color: #5bc0de; margin-left: 10px;")
        self.chk_hide_system.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.chk_hide_system)

        filter_layout.addStretch()

        self.chk_only_updates = QCheckBox("⬆️ Só com atualização")
        self.chk_only_updates.setStyleSheet("font-weight: bold; color: #f0ad4e; margin-right: 10px;")
        self.chk_only_updates.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.chk_only_updates)

        self.inp_filter = QLineEdit()
        self.inp_filter.setFixedHeight(32)
        self.inp_filter.setPlaceholderText("🔍 Filtrar por nome ou ID...")
        self.inp_filter.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.inp_filter)
        inv_layout.addLayout(filter_layout)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["[ ]", "ID do Pacote", "Nome do Software", "Versão", "Nova Versão", "Origem"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 260)
        self.table.horizontalHeader().setStretchLastSection(True)
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
        self.btn_load_net = QPushButton("↻ Buscar no Compartilhamento")
        self.btn_load_net.setFixedHeight(32)
        self.btn_load_net.clicked.connect(self.carregar_softwares_da_rede)
        rede_layout.addWidget(self.btn_load_net)

        self.tbl_offline = QTableWidget(0, 2)
        self.tbl_offline.setHorizontalHeaderLabels(["Instalador na Rede", "Tamanho"])
        self.tbl_offline.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_offline.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_offline.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_offline.verticalHeader().setVisible(False)
        rede_layout.addWidget(self.tbl_offline)
        split_layout.addWidget(frame_rede)

        frame_winget = QGroupBox("Instalação Online (Nuvem)")
        winget_layout = QVBoxLayout(frame_winget)
        self.inp_custom_soft = QLineEdit()
        self.inp_custom_soft.setFixedHeight(32)
        self.inp_custom_soft.setPlaceholderText("IDs separados por vírgula (ex: VideoLAN.VLC, Brave.Brave)...")

        self.btn_search_online = QPushButton("🔍 Pesquisar ID")
        self.btn_search_online.setFixedHeight(32)
        self.btn_search_online.clicked.connect(self.open_search_dialog)

        l_pesq = QHBoxLayout()
        l_pesq.addWidget(self.inp_custom_soft)
        l_pesq.addWidget(self.btn_search_online)
        winget_layout.addLayout(l_pesq)
        winget_layout.addStretch()
        split_layout.addWidget(frame_winget)

        inst_layout.addLayout(split_layout)

        self.btn_install = QPushButton("▶ Instalar Softwares Selecionados")
        self.btn_install.setFixedHeight(36)
        self.btn_install.setStyleSheet("background-color: #1e8a5e; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_install.clicked.connect(self.start_software_install)
        inst_layout.addWidget(self.btn_install)
        self.tabs.addTab(tab_inst, "2. Nova Instalação (Rede/Nuvem)")

    def _build_aba_drivers(self):
        tab_drv = QWidget()
        drv_layout = QHBoxLayout(tab_drv)

        frame_backup = QGroupBox("📥 Coleta Inteligente (Backup para Rede)")
        bkp_layout = QVBoxLayout(frame_backup)
        bkp_layout.addWidget(QLabel("Selecione as categorias que deseja extrair:"))

        self.list_coleta = QListWidget()
        self.list_coleta.setStyleSheet("background-color: transparent; border: 1px solid #444;")
        for name, cls in self.cat_map.items():
            if cls == "Todos":
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, cls)
            self.list_coleta.addItem(item)
        bkp_layout.addWidget(self.list_coleta)

        self.btn_coleta = QPushButton("⬇️ Iniciar Extração Inteligente")
        self.btn_coleta.setFixedHeight(36)
        self.btn_coleta.setStyleSheet("background-color: #2a7de1; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_coleta.clicked.connect(self.coletar_drivers)
        bkp_layout.addWidget(self.btn_coleta)
        drv_layout.addWidget(frame_backup)

        frame_deploy = QGroupBox("📤 Instalação (Deploy Offline Automático)")
        dep_layout = QVBoxLayout(frame_deploy)
        dep_layout.addWidget(QLabel("Selecione as categorias que deseja instalar:"))

        self.list_deploy = QListWidget()
        self.list_deploy.setStyleSheet("background-color: transparent; border: 1px solid #444;")
        for name, cls in self.cat_map.items():
            if cls == "Todos":
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, cls)
            self.list_deploy.addItem(item)
        dep_layout.addWidget(self.list_deploy)

        self.btn_deploy = QPushButton("▶ Instalar no Alvo Automático")
        self.btn_deploy.setFixedHeight(36)
        self.btn_deploy.setStyleSheet("background-color: #1e8a5e; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_deploy.clicked.connect(self.instalar_drivers)
        dep_layout.addWidget(self.btn_deploy)
        drv_layout.addWidget(frame_deploy)

        self.tabs.addTab(tab_drv, "3. Gestão de Drivers (Offline)")

    def export_inventory_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Liste o inventário de um computador antes de exportar.")
            return

        target = self.inp_target.text().strip() or "ENDPOINT"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Inventario_Softwares_{target}_{timestamp}.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Inventário de Softwares",
            default_name,
            "Arquivo CSV (*.csv);;Arquivo de Texto (*.txt)"
        )
        if not file_path:
            return

        try:
            count = 0
            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Computador", "ID do Pacote", "Nome do Software", "Versao Instalada", "Atualizacao Disponivel", "Motor/Origem"])

                for r in range(self.table.rowCount()):
                    if self.table.isRowHidden(r):
                        continue
                    pkg_id = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
                    name = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
                    ver = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
                    avail = self.table.item(r, 4).text() if self.table.item(r, 4) else ""
                    orig = self.table.item(r, 5).text() if self.table.item(r, 5) else ""
                    writer.writerow([target, pkg_id, name, ver, avail, orig])
                    count += 1

            QMessageBox.information(self, "Exportação Concluída", f"{count} software(s) exportado(s) com sucesso para:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Exportar", f"Falha ao salvar o arquivo:\n{e}")

    def _open_verbose_log_dialog(self, row, col):
        target = self.status_table.item(row, 0).text() if self.status_table.item(row, 0) else "N/A"
        op = self.status_table.item(row, 1).text() if self.status_table.item(row, 1) else "N/A"
        st = self.status_table.item(row, 4).text() if self.status_table.item(row, 4) else "N/A"
        resumo_item = self.status_table.item(row, 5)
        log_text = resumo_item.text() if resumo_item else "Sem detalhes registrados."
        ExecutionLogDialog(target, op, st, log_text, parent=self).exec()

    def coletar_drivers(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        categorias = []
        for i in range(self.list_coleta.count()):
            item = self.list_coleta.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                categorias.append(item.data(Qt.ItemDataRole.UserRole))

        if not categorias:
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos uma categoria.")
            return

        try:
            ps_script = load_ps_template("software", "drivers_collect", categories=",".join(categorias), share_root=self.SHARE_ROOT)
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro", f"Template ausente: {e}")
            return

        credentials = None
        if not self._is_local_target(target):
            credentials = self._get_credentials()
            if credentials is None:
                return

        reply = QMessageBox.question(self, "Confirmação", f"Coletar de {target}?")
        if reply == QMessageBox.StandardButton.Yes:
            self._enqueue_task(target, f"Backup Drivers ({len(categorias)} cats)", ps_script, credentials=credentials)

    def instalar_drivers(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        categorias = []
        for i in range(self.list_deploy.count()):
            item = self.list_deploy.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                categorias.append(item.data(Qt.ItemDataRole.UserRole))

        if not categorias:
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos uma categoria.")
            return

        try:
            ps_script = load_ps_template("software", "drivers_deploy", categories=",".join(categorias), share_root=self.SHARE_ROOT)
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro", f"Template ausente: {e}")
            return

        credentials = None
        if not self._is_local_target(target):
            credentials = self._get_credentials()
            if credentials is None:
                return

        reply = QMessageBox.question(self, "Confirmação", f"Instalar em {target}?")
        if reply == QMessageBox.StandardButton.Yes:
            self._enqueue_task(target, f"Deploy Drivers ({len(categorias)} cats)", ps_script, credentials=credentials)

    def _clear_status_table(self):
        linhas_para_remover = []
        for r in range(self.status_table.rowCount()):
            s = (self.status_table.item(r, 4).text().lower() if self.status_table.item(r, 4) else "")
            if not ("execut" in s or "pendente" in s or "aguard" in s):
                linhas_para_remover.append(r)
        for r in sorted(linhas_para_remover, reverse=True):
            self.status_table.removeRow(r)

    def _get_credentials(self):
        cached = getattr(self.main_window, 'get_cached_credentials', None)
        if cached:
            c = cached()
            if c:
                return c
        saved = CredentialStore.load()
        if saved:
            s = getattr(self.main_window, 'set_cached_credentials', None)
            if s:
                s(saved["user"], saved["pass"])
            return saved

        dominio, usuario = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")
        dlg = CredentialDialog(user_display=f"{dominio}\\{usuario}", has_saved=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.password:
            return None

        if dlg.remember:
            CredentialStore.save(f"{dominio}\\{usuario}", dlg.password)
        s = getattr(self.main_window, 'set_cached_credentials', None)
        if s:
            s(f"{dominio}\\{usuario}", dlg.password)
        return {"user": f"{dominio}\\{usuario}", "pass": dlg.password, "vnc_pass": dlg.password}

    @staticmethod
    def _is_local_target(target: str) -> bool:
        import socket
        t = (target or "").strip().lower()
        return t in ("localhost", "127.0.0.1", "::1", socket.gethostname().lower())

    def _b64(self, text):
        return base64.b64encode(str(text).encode('utf-8')).decode('ascii')

    def start_software_install(self):
        target = self.inp_target.text().strip()
        if not target:
            return self.inp_target.setFocus()

        engine = self.cmb_engine.currentText()
        offline = [
            self.tbl_offline.item(r, 0).text()
            for r in range(self.tbl_offline.rowCount())
            if self.tbl_offline.item(r, 0).checkState() == Qt.CheckState.Checked
        ]
        online = [s.strip() for s in self.inp_custom_soft.text().split(",") if s.strip()]

        if not offline and not online:
            return QMessageBox.warning(self, "Aviso", "Selecione pacotes para instalar.")

        try:
            pacotes_online_str = ",".join(online) if online else ""
            pacotes_offline_str = ",".join(offline) if offline else ""

            ps_script = load_ps_template(
                "software", "software_install",
                engine_b64=self._b64(engine),
                share_root_b64=self._b64(self.SHARE_ROOT),
                pacotes_online_b64=self._b64(pacotes_online_str),
                pacotes_offline_b64=self._b64(pacotes_offline_str)
            )
        except PsTemplateError as e:
            return QMessageBox.critical(self, "Erro", f"Template ausente: {e}")

        credentials = None
        if offline and not self._is_local_target(target):
            credentials = self._get_credentials()
            if credentials is None:
                return

        todos = offline + online
        sufixo = ", ".join(todos[:3]) + (f" (+{len(todos)-3})" if len(todos) > 3 else "")

        if offline and online:
            origem_lbl = f"Rede+{engine}"
        elif offline:
            origem_lbl = "Rede"
        else:
            origem_lbl = engine

        self._enqueue_task(target, f"Instalar ({origem_lbl}): {sufixo}", ps_script, credentials=credentials)

    def execute_action(self, action):
        target, engine = self.inp_target.text().strip(), self.cmb_engine.currentText()
        if not target:
            return self.inp_target.setFocus()

        pkgs = [
            self.table.item(r, 1).text()
            for r in range(self.table.rowCount())
            if self.table.cellWidget(r, 0) and self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
        ]
        if not pkgs:
            return QMessageBox.warning(self, "Aviso", "Selecione pacotes.")

        try:
            pacotes_str = ",".join(pkgs)
            force_flag = "--force" if (self.chk_force_close.isChecked() and action == "upgrade") else ""

            ps_script = load_ps_template(
                "software", "software_action",
                action_b64=self._b64(action),
                engine_b64=self._b64(engine),
                force_flag_b64=self._b64(force_flag),
                pacotes_b64=self._b64(pacotes_str)
            )
        except PsTemplateError as e:
            return QMessageBox.critical(self, "Erro", f"Template ausente: {e}")

        if QMessageBox.question(self, "Ação", f"Executar {action} em {len(pkgs)} pacote(s)?") == QMessageBox.StandardButton.Yes:
            self._enqueue_task(target, f"{action.capitalize()} ({engine})", ps_script, credentials=None)
            self.chk_select_all.setChecked(False)

    def _enqueue_task(self, target, title, ps_script, credentials=None):
        r = self.status_table.rowCount()
        self.status_table.insertRow(r)

        i_inicio = QTableWidgetItem(datetime.now().strftime("%H:%M:%S"))
        i_fim = QTableWidgetItem("-")
        i_inicio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        i_fim.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        i_status = QTableWidgetItem("Pendente (Na fila)...")
        i_resumo = QTableWidgetItem("Aguardando processo...")

        self.status_table.setItem(r, 0, QTableWidgetItem(target))
        self.status_table.setItem(r, 1, QTableWidgetItem(title))
        self.status_table.setItem(r, 2, i_inicio)
        self.status_table.setItem(r, 3, i_fim)
        self.status_table.setItem(r, 4, i_status)
        self.status_table.setItem(r, 5, i_resumo)

        self.queue_manager.add_task(
            target_pc=target, script_name=title, script_content=ps_script,
            module_name="Gestão de Software/Drivers", credentials=credentials,
            on_start=lambda t, s=i_status, rs=i_resumo: self.update_status_start(t, s, rs),
            on_finish=lambda t, st, d, s=i_status, rs=i_resumo, f=i_fim: self.update_status_finish(t, st, d, s, rs, f),
            on_error=lambda t, e, s=i_status, rs=i_resumo, f=i_fim: self.update_status_error(t, e, s, rs, f)
        )

    def clear_table_on_engine_change(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.chk_select_all.setChecked(False)
        self.inp_filter.clear()
        self.table.setSortingEnabled(True)

    def _is_system_app(self, pkg_id: str, pkg_name: str) -> bool:
        low_id = (pkg_id or "").lower()
        low_name = (pkg_name or "").lower()
        for pat in self.SYSTEM_APP_PATTERNS:
            if low_id.startswith(pat) or pat in low_id:
                return True
        if low_id.startswith("msix\\") or "redistributable" in low_name or "edge webview2" in low_name:
            return True
        return False

    def apply_filters(self, *args):
        t = self.inp_filter.text().lower().strip()
        only_upd = self.chk_only_updates.isChecked()
        hide_sys = self.chk_hide_system.isChecked()

        for r in range(self.table.rowCount()):
            id_item = self.table.item(r, 1)
            name_item = self.table.item(r, 2)
            id_txt = id_item.text() if id_item else ""
            name_txt = name_item.text() if name_item else ""

            match = True
            if t:
                match = (t in id_txt.lower()) or (t in name_txt.lower())

            if match and hide_sys:
                if self._is_system_app(id_txt, name_txt):
                    match = False

            if match and only_upd:
                av = self.table.item(r, 4)
                if not av or av.text().strip() in ["-", ""]:
                    match = False

            self.table.setRowHidden(r, not match)

        visible_count = sum(1 for r in range(self.table.rowCount()) if not self.table.isRowHidden(r))
        if only_upd:
            self.chk_only_updates.setText(f"⬆️ Só com atualização ({visible_count})")
        else:
            self.chk_only_updates.setText("⬆️ Só com atualização")

    def fetch_software(self):
        target, engine = self.inp_target.text().strip(), self.cmb_engine.currentText()
        if not target:
            return self.inp_target.setFocus()
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
        for pkg in pkgs_list:
            if not isinstance(pkg, dict) or pkg.get("Name") == "Nenhum software encontrado":
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)

            chk_w = QWidget()
            chk_l = QHBoxLayout(chk_w)
            chk_l.addWidget(QCheckBox())
            chk_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_l.setContentsMargins(0, 0, 0, 0)

            clean_id = fix_mojibake(str(pkg.get("Id", "-")))
            clean_name = fix_mojibake(str(pkg.get("Name", "Desconhecido")))

            self.table.setItem(r, 0, QTableWidgetItem(""))
            self.table.setCellWidget(r, 0, chk_w)
            self.table.setItem(r, 1, QTableWidgetItem(clean_id))
            self.table.setItem(r, 2, QTableWidgetItem(clean_name))
            self.table.setItem(r, 3, QTableWidgetItem(str(pkg.get("Version", "-"))))

            av = (pkg.get("Available", "") or "").strip()
            item_av = QTableWidgetItem(av if av else "-")
            if av:
                item_av.setForeground(Qt.GlobalColor.green)
            self.table.setItem(r, 4, item_av)

            orig = pkg.get("Origin", "Winget")
            item_orig = QTableWidgetItem(orig)
            item_orig.setForeground(
                Qt.GlobalColor.cyan if orig == "Chocolatey"
                else Qt.GlobalColor.yellow if orig == "Windows Registry"
                else Qt.GlobalColor.green
            )
            self.table.setItem(r, 5, item_orig)

        self.table.setSortingEnabled(True)
        self.btn_fetch.setEnabled(True)
        self.btn_check_updates.setEnabled(True)
        self.btn_fetch.setText("🔄 Listar Softwares (Inventário)")
        self.apply_filters()

    def check_updates(self):
        if self.table.rowCount() == 0:
            return QMessageBox.warning(self, "Aviso", "Liste os softwares primeiro.")
        self.btn_fetch.setEnabled(False)
        self.btn_check_updates.setEnabled(False)
        self.btn_check_updates.setText("Buscando...")
        self.worker_upd = CheckUpdatesWorker(self.inp_target.text().strip(), self.cmb_engine.currentText())
        self.worker_upd.finished.connect(self.apply_updates_to_table)
        self.worker_upd.error.connect(self.show_error)
        self.worker_upd.start()

    def apply_updates_to_table(self, updates_dict):
        self.table.setSortingEnabled(False)
        self.btn_fetch.setEnabled(True)
        self.btn_check_updates.setEnabled(True)
        self.btn_check_updates.setText("🔎 Verificar Atualizações")
        if not updates_dict:
            return QMessageBox.information(self, "Atualizações", "Nenhuma atualização encontrada.")

        upd_lower = {k.lower(): v for k, v in updates_dict.items()}
        for r in range(self.table.rowCount()):
            id_item = self.table.item(r, 1)
            if id_item and id_item.text().lower() in upd_lower:
                it = QTableWidgetItem(upd_lower[id_item.text().lower()])
                it.setForeground(Qt.GlobalColor.green)
                self.table.setItem(r, 4, it)
        self.table.setSortingEnabled(True)
        QMessageBox.information(self, "Sucesso", "Atualizações encontradas!")

    def show_error(self, err):
        self.btn_fetch.setEnabled(True)
        self.btn_check_updates.setEnabled(True)
        self.btn_fetch.setText("🔄 Listar Softwares (Inventário)")
        self.btn_check_updates.setText("🔎 Verificar Atualizações")
        QMessageBox.critical(self, "Erro", f"Falha na comunicação:\n{fix_mojibake(str(err))}")

    def toggle_select_all(self, state):
        c = state == Qt.CheckState.Checked.value
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w:
                chk = w.findChild(QCheckBox)
                if chk:
                    chk.setChecked(False if self.table.isRowHidden(r) else c)

    def update_status_start(self, t, st, rs):
        try:
            st.setText("A Executar...")
            rs.setText("Executando operação remota... Aguarde.")
        except Exception:
            pass

    def update_status_finish(self, t, s, j, st, rs, f):
        try:
            j = j if isinstance(j, dict) else {}
            status_final = str(j.get("StatusFinal", s or "Concluído"))
            st.setText(status_final)
            f.setText(datetime.now().strftime("%H:%M:%S"))

            st_upper = status_final.upper()
            if "SUCESSO" in st_upper:
                st.setForeground(Qt.GlobalColor.green)
            elif "ERRO" in st_upper or "FALHA" in st_upper:
                st.setForeground(Qt.GlobalColor.red)
            else:
                st.setForeground(Qt.GlobalColor.darkYellow)

            resumo = f"Status: {status_final}"
            if "PacotesProcessados" in j and isinstance(j["PacotesProcessados"], list):
                for pct in j["PacotesProcessados"]:
                    if isinstance(pct, dict):
                        log_txt = fix_mojibake(str(pct.get("Log", "")).strip())
                        software_txt = fix_mojibake(str(pct.get("Software", "")).strip())
                        resumo += f"\n- {software_txt}: {log_txt}"
            if "Detalhes" in j:
                d = j.get("Detalhes")
                det_str = "\n".join(fix_mojibake(str(item)) for item in d) if isinstance(d, list) else fix_mojibake(str(d))
                resumo += "\n" + det_str
            rs.setText(resumo)
            self.status_table.resizeRowToContents(st.row())
        except Exception as exc:
            log.error(f"Erro ao atualizar status_table: {exc}")

    def update_status_error(self, t, e, st, rs, f):
        try:
            st.setText("Erro de Execução")
            st.setForeground(Qt.GlobalColor.red)
            rs.setText(fix_mojibake(str(e)))
            f.setText(datetime.now().strftime("%H:%M:%S"))
            self.status_table.resizeRowToContents(st.row())
        except Exception as exc:
            log.error(f"Erro ao registrar falha na status_table: {exc}")

    def open_search_dialog(self):
        d = OnlineSearchDialog(engine=self.cmb_engine.currentText(), parent=self)
        if d.exec() == QDialog.DialogCode.Accepted:
            curr = [x.strip() for x in self.inp_custom_soft.text().split(",") if x.strip()]
            self.inp_custom_soft.setText(", ".join(list(dict.fromkeys(curr + d.selected_packages))))

    def carregar_softwares_da_rede(self):
        self.tbl_offline.setRowCount(0)
        try:
            if not os.path.exists(self.network_software_path):
                return QMessageBox.warning(self, "Aviso", "Caminho inacessível.")
            arqs = [f for f in os.listdir(self.network_software_path) if f.lower().endswith((".msi", ".exe"))]
            for a in sorted(arqs):
                r = self.tbl_offline.rowCount()
                self.tbl_offline.insertRow(r)
                it = QTableWidgetItem(a)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Unchecked)
                s = QTableWidgetItem(f"{os.path.getsize(os.path.join(self.network_software_path, a)) / (1024 * 1024):.1f} MB")
                s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_offline.setItem(r, 0, it)
                self.tbl_offline.setItem(r, 1, s)
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()
