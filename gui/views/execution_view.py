import ipaddress
import json
import os
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox,
    QMessageBox, QTextEdit, QFileDialog,
    QSizePolicy, QListWidget, QListWidgetItem, QDialog,
    QApplication, QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from gui.dialogs.dialogs import CredentialDialog
from core.credential_store import CredentialStore
from core.remote_connection import RemoteConnectionManager
from core.task_queue import TaskQueueManager
from infrastructure.repositories.script_repository import ScriptRepository
from domain.services.script_service import ScriptService
from gui.views.base_view import BaseView, read_text_file_safe
from gui.views.software_view import fix_mojibake


def parse_targets_string(raw_text: str) -> list[str]:
    """Separa IPs/Hostnames por vírgula, ponto e vírgula ou quebra de linha, limpa BOM e remove duplicados."""
    if not raw_text:
        return []
    cleaned = raw_text.lstrip("\ufeff")
    tokens = re.split(r"[\n,;]+", cleaned)
    valid = []
    for t in tokens:
        host = t.strip().upper()
        if host:
            valid.append(host)
    return list(dict.fromkeys(valid))


def expand_subnet_range(spec: str) -> list[str]:
    """Expande CIDR (ex: 10.8.128.0/28) ou intervalo curto (ex: 10.8.128.1-20) em lista de IPs."""
    raw = (spec or "").strip()
    if not raw:
        return []

    if "/" in raw:
        net = ipaddress.ip_network(raw, strict=False)
        return [str(ip) for ip in list(net.hosts())[:254]]

    m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){3})\s*-\s*(\d{1,3})$", raw)
    if m:
        base_ip = ipaddress.ip_address(m.group(1))
        end_octet = int(m.group(2))
        parts = str(base_ip).split(".")
        start_octet = int(parts[3])
        if 0 <= start_octet <= 254 and 0 <= end_octet <= 254 and start_octet <= end_octet:
            return [f"{parts[0]}.{parts[1]}.{parts[2]}.{i}" for i in range(start_octet, end_octet + 1)][:254]

    return []


def _resolve_hostname_for_ip(ip_str: str) -> str:
    """Resolve o nome do host a partir do IP (priorizando o nome curto), retornando o IP se não resolver."""
    try:
        fqdn = socket.gethostbyaddr(ip_str)[0]
        short_name = fqdn.split(".")[0].strip().upper()
        if short_name and short_name != ip_str:
            return short_name
    except Exception:
        pass
    return ip_str.strip().upper()


def _ip_in_subnet(ip_str: str, subnet_spec: str) -> bool:
    """Verifica se um IP pertence ao CIDR ou intervalo informado."""
    raw = (subnet_spec or "").strip()
    if not raw or not ip_str:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False

    if "/" in raw:
        try:
            net = ipaddress.ip_network(raw, strict=False)
            return ip_obj in net
        except ValueError:
            return False

    range_ips = expand_subnet_range(raw)
    return str(ip_obj) in set(range_ips)


class HostDiscoveryWorker(QThread):
    """Descobre hosts ativos na sub-rede, no AD ou combinando AD + Sub-rede, priorizando o nome do host."""
    finished = pyqtSignal(list, dict, str)

    def __init__(self, mode: str, query: str = "", subnet_filter: str = ""):
        super().__init__()
        self.mode = mode
        self.query = query
        self.subnet_filter = subnet_filter
        self.is_cancelled = False

    def _query_ad_computers(self, name_filter: str) -> list[dict]:
        """Consulta computadores no AD (Nome e, quando disponível, IPv4)."""
        filtro = (name_filter or "*").replace("'", "").strip()
        ps_cmd = (
            "try { "
            "  if (Get-Command Get-ADComputer -ErrorAction SilentlyContinue) { "
            f"    Get-ADComputer -Filter \"Name -like '{filtro}'\" -Properties IPv4Address | "
            "      Select-Object Name, IPv4Address | ConvertTo-Json -Compress "
            "  } else { "
            f"    & dsquery computer -name \"{filtro}\" -limit 200 2>$null | "
            "      ForEach-Object { [PSCustomObject]@{ Name = (($_ -split ',')[0] -replace '^\"CN=',''); IPv4Address = '' } } | "
            "      ConvertTo-Json -Compress "
            "  } "
            "} catch { '[]' }"
        )
        records = []
        try:
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if self.is_cancelled:
                return []
            raw_out = (proc.stdout or "").strip()
            if raw_out:
                parsed = json.loads(raw_out)
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict):
                        name = str(item.get("Name") or "").strip().upper()
                        ip = str(item.get("IPv4Address") or "").strip()
                        if name:
                            records.append({"name": name, "ip": ip})
        except Exception:
            pass
        return records

    def run(self):
        conn = RemoteConnectionManager()
        host_to_ip: dict[str, str] = {}
        ordered_targets: list[str] = []

        if self.mode == "subnet":
            ips = expand_subnet_range(self.query)
            if not ips:
                if not self.is_cancelled:
                    self.finished.emit([], {}, "Informe uma sub-rede válida (ex: 10.8.128.0/24 ou 10.8.128.1-30).")
                return

            def _probe_and_resolve(ip_str: str):
                if self.is_cancelled:
                    return None
                probe = conn.probe_host(ip_str, port_timeout=0.35)
                if self.is_cancelled:
                    return None
                if probe["reachable"] or probe["ping_ok"]:
                    resolved_name = _resolve_hostname_for_ip(ip_str)
                    return resolved_name, ip_str
                return None

            workers = min(24, max(4, len(ips)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for res in pool.map(_probe_and_resolve, ips):
                    if self.is_cancelled:
                        return
                    if res:
                        h_name, h_ip = res
                        host_to_ip[h_name] = h_ip
                        if h_name not in ordered_targets:
                            ordered_targets.append(h_name)

            if not self.is_cancelled:
                self.finished.emit(ordered_targets, host_to_ip, "")
            return

        ad_records = self._query_ad_computers(self.query or "*")
        if self.is_cancelled:
            return

        if self.mode == "ad_subnet":
            if not self.subnet_filter.strip():
                if not self.is_cancelled:
                    self.finished.emit([], {}, "Informe a sub-rede para filtrar os computadores do AD.")
                return

            def _match_ad_in_subnet(rec: dict):
                if self.is_cancelled:
                    return None
                name = rec["name"]
                ip = rec.get("ip", "")
                if not ip:
                    try:
                        ip = socket.gethostbyname(name)
                    except Exception:
                        ip = ""
                if ip and _ip_in_subnet(ip, self.subnet_filter):
                    return name, ip
                return None

            workers = min(16, max(2, len(ad_records)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for res in pool.map(_match_ad_in_subnet, ad_records):
                    if self.is_cancelled:
                        return
                    if res:
                        h_name, h_ip = res
                        host_to_ip[h_name] = h_ip
                        if h_name not in ordered_targets:
                            ordered_targets.append(h_name)

            if not self.is_cancelled:
                self.finished.emit(ordered_targets, host_to_ip, "")
            return

        for rec in ad_records:
            if self.is_cancelled:
                return
            h_name = rec["name"]
            if rec.get("ip"):
                host_to_ip[h_name] = rec["ip"]
            if h_name not in ordered_targets:
                ordered_targets.append(h_name)

        if not self.is_cancelled:
            self.finished.emit(ordered_targets, host_to_ip, "")


class BatchPingWorker(QThread):
    """Testa conectividade de múltiplos alvos em paralelo sem travar a interface."""
    finished = pyqtSignal(list, list)

    def __init__(self, targets: list[str]):
        super().__init__()
        self.targets = targets

    def run(self):
        conn = RemoteConnectionManager()

        def _check(host: str) -> tuple[str, bool]:
            probe = conn.probe_host(host, port_timeout=0.7)
            if probe["reachable"] or probe["ping_ok"]:
                return host, True
            return host, conn.ping_host(host, timeout_ms=500)

        online = []
        offline = []
        workers = min(16, max(2, len(self.targets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for host, is_up in pool.map(_check, self.targets):
                if is_up:
                    online.append(host)
                else:
                    offline.append(host)

        self.finished.emit(online, offline)


class ExecutionView(BaseView):

    def _get_credentials(self):
        """Retorna credenciais — cache → disco (DPAPI) → popup."""
        cached = getattr(self.main_window, "get_cached_credentials", None)
        if cached:
            creds = cached()
            if creds:
                return creds

        saved = CredentialStore.load()
        if saved:
            setter = getattr(self.main_window, "set_cached_credentials", None)
            if setter:
                setter(saved["user"], saved["pass"])
            return saved

        dominio = os.environ.get("USERDOMAIN", "")
        usuario = os.environ.get("USERNAME", "")
        user_str = f"{dominio}\\{usuario}"

        dlg = CredentialDialog(user_display=user_str, has_saved=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        senha = dlg.password
        if not senha:
            return None

        if dlg.remember:
            CredentialStore.save(user_str, senha)

        setter = getattr(self.main_window, "set_cached_credentials", None)
        if setter:
            setter(user_str, senha)

        return {"user": user_str, "pass": senha, "vnc_pass": senha}

    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(main_window_ref, "queue_manager", None) or TaskQueueManager(max_threads=10)
        self.script_repo = ScriptRepository()
        self.script_service = ScriptService(self.script_repo)
        self.discovered_host_ips: dict[str, str] = {}
        self.is_discovering = False
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Central de Comando Remoto (Lote de Scripts)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        main_layout.addWidget(title)

        target_group = QGroupBox("Computadores Alvo")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(15, 20, 15, 15)

        self.target_input = QLineEdit()
        self.target_input.setFixedHeight(32)
        self.target_input.setPlaceholderText("Ex: localhost, 10.8.128.14, HUL-WK-244377E...")
        self.target_input.setStyleSheet("padding: 0 10px;")
        self.target_input.textChanged.connect(self._force_uppercase)

        self.btn_discover_targets = QPushButton("🔎 Descobrir Alvos")
        self.btn_discover_targets.setFixedHeight(32)
        self.btn_discover_targets.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_discover_targets.setToolTip("Varre faixa de sub-rede, consulta AD ou combina AD + Sub-rede (priorizando o nome do host)")
        self.btn_discover_targets.setStyleSheet("background-color: #4a90e2; color: white; padding: 0 14px; font-weight: bold; border-radius: 4px;")
        self.btn_discover_targets.clicked.connect(self.discover_targets)

        self.btn_filter_online = QPushButton("📡 Filtrar Online (Ping)")
        self.btn_filter_online.setFixedHeight(32)
        self.btn_filter_online.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_online.setToolTip("Testa os alvos em paralelo e mantém apenas os que respondem na rede")
        self.btn_filter_online.setStyleSheet("background-color: #1e8a5e; color: white; padding: 0 14px; font-weight: bold; border-radius: 4px;")
        self.btn_filter_online.clicked.connect(self.filter_online_targets)

        self.btn_import_targets = QPushButton("📂 Importar Lista (.txt)")
        self.btn_import_targets.setFixedHeight(32)
        self.btn_import_targets.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_targets.setStyleSheet("background-color: #5bc0de; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_import_targets.clicked.connect(self.import_targets_from_file)

        self.btn_clear_targets = QPushButton("🗑️ Limpar Alvos")
        self.btn_clear_targets.setFixedHeight(32)
        self.btn_clear_targets.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_targets.setStyleSheet("background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_clear_targets.clicked.connect(self.target_input.clear)

        target_layout.addWidget(QLabel("IPs ou Hostnames:"))
        target_layout.addWidget(self.target_input, stretch=1)
        target_layout.addWidget(self.btn_discover_targets)
        target_layout.addWidget(self.btn_filter_online)
        target_layout.addWidget(self.btn_import_targets)
        target_layout.addWidget(self.btn_clear_targets)

        target_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        main_layout.addWidget(target_group)

        script_group = QGroupBox("Execução de Scripts (Biblioteca)")
        script_vlayout = QVBoxLayout(script_group)
        script_vlayout.setContentsMargins(15, 20, 15, 15)
        script_vlayout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        self.inp_filter_scripts = QLineEdit()
        self.inp_filter_scripts.setFixedHeight(32)
        self.inp_filter_scripts.setPlaceholderText("🔍 Filtrar scripts por nome...")
        self.inp_filter_scripts.setStyleSheet("padding: 0 10px;")
        self.inp_filter_scripts.textChanged.connect(lambda text: self._filtrar_scripts(self.inp_filter_scripts.text()))
        row1.addWidget(self.inp_filter_scripts, stretch=1)

        self.btn_select_all_scripts = QPushButton("☑ Marcar Visíveis")
        self.btn_select_all_scripts.setFixedHeight(32)
        self.btn_select_all_scripts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all_scripts.setStyleSheet("padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_select_all_scripts.clicked.connect(lambda: self._toggle_all_scripts(True))
        row1.addWidget(self.btn_select_all_scripts)

        self.btn_clear_scripts = QPushButton("☐ Desmarcar Todos")
        self.btn_clear_scripts.setFixedHeight(32)
        self.btn_clear_scripts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_scripts.setStyleSheet("padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_clear_scripts.clicked.connect(lambda: self._toggle_all_scripts(False))
        row1.addWidget(self.btn_clear_scripts)

        self.btn_reload = QPushButton("↻ Recarregar")
        self.btn_reload.setFixedHeight(32)
        self.btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reload.setStyleSheet("padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_reload.clicked.connect(self.carregar_scripts_do_banco)
        row1.addWidget(self.btn_reload)

        script_vlayout.addLayout(row1)

        self.list_scripts = QListWidget()
        self.list_scripts.setMinimumHeight(140)
        self.list_scripts.setMaximumHeight(220)
        self.list_scripts.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_scripts.setStyleSheet(
            "QListWidget { font-size: 13px; padding: 4px; border: 1px solid #444; border-radius: 4px; } "
            "QListWidget::item { padding: 4px 6px; } "
            "QListWidget::item:hover { background-color: rgba(74, 144, 226, 0.1); }"
        )
        self.list_scripts.itemChanged.connect(self._atualizar_contador_scripts)
        script_vlayout.addWidget(self.list_scripts)

        row3 = QHBoxLayout()
        row3.setSpacing(10)

        self.lbl_scripts_count = QLabel("0 script(s) selecionado(s)")
        self.lbl_scripts_count.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
        row3.addWidget(self.lbl_scripts_count)

        row3.addStretch()

        self.btn_execute = QPushButton("▶ Executar Selecionados")
        self.btn_execute.setFixedHeight(36)
        self.btn_execute.setMinimumWidth(220)
        self.btn_execute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_execute.setStyleSheet(
            "background-color: #2a7de1; color: white; padding: 0 20px; "
            "font-weight: bold; border-radius: 4px; font-size: 13px;"
        )
        self.btn_execute.clicked.connect(self.start_script_execution)
        row3.addWidget(self.btn_execute)

        script_vlayout.addLayout(row3)
        main_layout.addWidget(script_group)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)

        table_group = QGroupBox("Acompanhamento do Lote de Execuções")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(15, 20, 15, 15)

        header_lote = QHBoxLayout()
        header_lote.addStretch()

        self.btn_remove_selected = QPushButton("🗑️ Remover Selecionados")
        self.btn_remove_selected.setFixedHeight(32)
        self.btn_remove_selected.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_selected.setStyleSheet("padding: 0 15px; background-color: #d9534f; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_remove_selected.clicked.connect(self.remove_selected_rows)
        header_lote.addWidget(self.btn_remove_selected)

        self.btn_clear_table = QPushButton("🧹 Limpar Concluídos")
        self.btn_clear_table.setFixedHeight(32)
        self.btn_clear_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_table.setStyleSheet("padding: 0 15px; background-color: #666; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_clear_table.clicked.connect(self.clear_finished_rows)
        header_lote.addWidget(self.btn_clear_table)

        table_layout.addLayout(header_lote)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Computador Alvo", "Operação", "Início", "Fim", "Status Atual", "Resumo da Execução"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 110)
        self.table.setWordWrap(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.refresh_console)
        table_layout.addWidget(self.table)

        bottom_layout.addWidget(table_group, stretch=60)

        console_group = QGroupBox("Console de Saída Detalhada")
        console_layout = QVBoxLayout(console_group)
        console_layout.setContentsMargins(15, 20, 15, 15)

        self.txt_console = QTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setFont(QFont("Consolas", 10))
        self.txt_console.setStyleSheet("padding: 8px; border: 1px solid #444; border-radius: 4px; line-height: 1.2;")
        console_layout.addWidget(self.txt_console)

        btn_clear_console = QPushButton("🗑 Limpar Console Desta Seleção")
        btn_clear_console.setFixedHeight(32)
        btn_clear_console.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_console.setStyleSheet("padding: 0 15px; background-color: #d9534f; color: white; font-weight: bold; border-radius: 4px;")
        btn_clear_console.clicked.connect(self.clear_console_data)
        console_layout.addWidget(btn_clear_console, alignment=Qt.AlignmentFlag.AlignRight)

        bottom_layout.addWidget(console_group, stretch=40)
        main_layout.addLayout(bottom_layout, stretch=1)

    def _reset_discover_button(self):
        self.is_discovering = False
        try:
            QApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.btn_discover_targets.setEnabled(True)
        self.btn_discover_targets.setText("🔎 Descobrir Alvos")
        self.btn_discover_targets.setStyleSheet(
            "background-color: #4a90e2; color: white; padding: 0 14px; font-weight: bold; border-radius: 4px;"
        )

    def discover_targets(self):
        """Inicia ou cancela a descoberta por sub-rede, AD ou AD + Sub-rede."""
        if getattr(self, "is_discovering", False):
            worker = getattr(self, "_discovery_worker", None)
            if worker and worker.isRunning():
                worker.is_cancelled = True
            self._reset_discover_button()
            return

        opcoes = [
            "1. Consultar Active Directory (padrão ex: HUL-WK-* ou *)",
            "2. Varredura de Sub-rede (resolve nome do host quando possível)",
            "3. AD + Sub-rede (computadores do AD na sub-rede informada)"
        ]
        escolha, ok = QInputDialog.getItem(
            self, "Descobrir Computadores Alvo",
            "Selecione a origem de descoberta (prioriza o nome do host):",
            opcoes, 0, False
        )
        if not ok or not escolha:
            return

        subnet_filter = ""
        if escolha.startswith("1."):
            param, ok_p = QInputDialog.getText(
                self, "Filtro Active Directory",
                "Informe o padrão de nome do computador (ex: HUL-WK-* ou *):",
                QLineEdit.EchoMode.Normal, "HUL-WK-*"
            )
            mode = "ad"
        elif escolha.startswith("2."):
            param, ok_p = QInputDialog.getText(
                self, "Faixa de Sub-rede",
                "Informe CIDR (ex: 10.8.128.0/26) ou faixa final (ex: 10.8.128.1-40):",
                QLineEdit.EchoMode.Normal, "10.8.128.1-30"
            )
            mode = "subnet"
        else:
            param, ok_p = QInputDialog.getText(
                self, "Filtro Active Directory",
                "Informe o padrão de nome no AD (ex: HUL-WK-* ou *):",
                QLineEdit.EchoMode.Normal, "*"
            )
            if not ok_p:
                return
            sub_val, ok_s = QInputDialog.getText(
                self, "Sub-rede Alvo",
                "Informe a sub-rede (ex: 10.8.128.0/24 ou 10.8.128.1-254):",
                QLineEdit.EchoMode.Normal, "10.8.128.0/24"
            )
            if not ok_s:
                return
            subnet_filter = sub_val.strip()
            mode = "ad_subnet"

        if not ok_p or not param.strip():
            return

        self.is_discovering = True
        self.btn_discover_targets.setEnabled(True)
        self.btn_discover_targets.setText("⛔ Cancelar Descoberta")
        self.btn_discover_targets.setStyleSheet(
            "background-color: #d9534f; color: white; padding: 0 14px; font-weight: bold; border-radius: 4px;"
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._discovery_worker = HostDiscoveryWorker(
            mode=mode, query=param.strip(), subnet_filter=subnet_filter
        )
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.start()

    def _on_discovery_finished(self, found: list[str], host_ip_map: dict, err_msg: str):
        worker = getattr(self, "_discovery_worker", None)
        if worker and getattr(worker, "is_cancelled", False):
            self._reset_discover_button()
            return

        self._reset_discover_button()

        if err_msg:
            QMessageBox.warning(self, "Aviso", err_msg)
            return

        if not found:
            QMessageBox.information(self, "Descoberta de Alvos", "Nenhum computador encontrado para o critério informado.")
            return

        if isinstance(host_ip_map, dict):
            self.discovered_host_ips.update(host_ip_map)

        existing = parse_targets_string(self.target_input.text())
        merged = list(dict.fromkeys(existing + found))
        self.target_input.setText(", ".join(merged))
        QMessageBox.information(
            self, "Descoberta Concluída",
            f"{len(found)} host(s) adicionado(s) por nome (total: {len(merged)})."
        )

    def filter_online_targets(self):
        """Testa os alvos em paralelo e mantém no campo apenas os que respondem na rede."""
        targets = self.get_targets()
        if not targets:
            return

        self.btn_filter_online.setEnabled(False)
        self.btn_filter_online.setText("⏳ Testando...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._ping_worker = BatchPingWorker(targets)
        self._ping_worker.finished.connect(self._on_batch_ping_finished)
        self._ping_worker.start()

    def _on_batch_ping_finished(self, online: list[str], offline: list[str]):
        QApplication.restoreOverrideCursor()
        self.btn_filter_online.setEnabled(True)
        self.btn_filter_online.setText("📡 Filtrar Online (Ping)")

        self.target_input.setText(", ".join(online))

        if offline:
            copy_off = QMessageBox.question(
                self,
                "Filtro de Conectividade Concluído",
                f"Online ({len(online)}): {', '.join(online[:6]) if online else 'Nenhum'}"
                + (f" ... (+{len(online) - 6})" if len(online) > 6 else "")
                + f"\nOffline / Sem resposta ({len(offline)}): {', '.join(offline[:6])}"
                + (f" ... (+{len(offline) - 6})" if len(offline) > 6 else "")
                + "\n\nA lista de alvos foi mantida apenas com os hosts online.\n"
                "Deseja copiar a lista de hosts offline para a área de transferência?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if copy_off == QMessageBox.StandardButton.Yes:
                QApplication.clipboard().setText("\n".join(offline))
        else:
            QMessageBox.information(
                self,
                "Filtro de Conectividade Concluído",
                f"Todos os {len(online)} alvo(s) estão acessíveis na rede."
            )

    def import_targets_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Importar Lista de Computadores", "",
            "Text Files (*.txt);;CSV Files (*.csv)"
        )
        if file_path:
            try:
                content = read_text_file_safe(file_path)
                new_targets = parse_targets_string(content)
                if not new_targets:
                    QMessageBox.warning(self, "Aviso", "Nenhum alvo válido encontrado no arquivo selecionado.")
                    return

                existing = parse_targets_string(self.target_input.text())
                unique_targets = list(dict.fromkeys(existing + new_targets))
                self.target_input.setText(", ".join(unique_targets))
                QMessageBox.information(
                    self, "Sucesso",
                    f"{len(unique_targets)} computador(es) carregado(s) na fila com sucesso!"
                )
            except Exception as e:
                QMessageBox.critical(self, "Erro na Importação", f"Falha ao processar o arquivo:\n{e}")

    def format_html(self, text, color="#cccccc"):
        clean = fix_mojibake(str(text))
        safe_text = clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        return f"<span style='color: {color}; font-family: Consolas;'>{safe_text}</span><br>"

    def refresh_console(self):
        self.txt_console.clear()
        selected_items = self.table.selectedItems()

        rows_to_show = set()
        if selected_items:
            for item in selected_items:
                rows_to_show.add(item.row())
        else:
            for i in range(self.table.rowCount()):
                rows_to_show.add(i)

        html_content = ""
        for row in sorted(list(rows_to_show)):
            item = self.table.item(row, 0)
            if item:
                row_html = item.data(Qt.ItemDataRole.UserRole)
                if row_html:
                    html_content += row_html

        self.txt_console.insertHtml(html_content)
        self.txt_console.moveCursor(QTextCursor.MoveOperation.End)

    def clear_console_data(self):
        selected_items = self.table.selectedItems()
        rows_to_clear = set()
        if selected_items:
            for item in selected_items:
                rows_to_clear.add(item.row())
        else:
            for i in range(self.table.rowCount()):
                rows_to_clear.add(i)

        for r in rows_to_clear:
            item = self.table.item(r, 0)
            if item:
                item.setData(Qt.ItemDataRole.UserRole, "")

        self.refresh_console()

    def remove_selected_rows(self):
        rows = sorted(list(set(item.row() for item in self.table.selectedItems())), reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self.table.clearSelection()
        self.refresh_console()

    def clear_finished_rows(self):
        rows_to_remove = []
        for r in range(self.table.rowCount()):
            status_item = self.table.item(r, 4)
            status_text = status_item.text().lower() if status_item else ""
            if "executando" not in status_text and "pendente" not in status_text:
                rows_to_remove.append(r)

        for r in sorted(rows_to_remove, reverse=True):
            self.table.removeRow(r)
        self.table.clearSelection()
        self.refresh_console()

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_scripts_do_banco()
        self.target_input.setFocus()

    def carregar_scripts_do_banco(self):
        """Popula a lista de scripts com checkboxes preservando seleções anteriores."""
        marcados_antes = self._get_selected_script_names()

        self.list_scripts.blockSignals(True)
        self.list_scripts.clear()

        scripts = self.script_repo.list_all()
        if not scripts:
            item = QListWidgetItem("⚠️ Nenhum script na biblioteca.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.list_scripts.addItem(item)
            self.list_scripts.blockSignals(False)
            self._atualizar_contador_scripts()
            return

        for s in scripts:
            script_id, nome, descricao, categoria, conteudo = s
            item = QListWidgetItem(f"{nome}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if nome in marcados_antes:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, {
                "id": script_id,
                "nome": nome,
                "descricao": descricao,
                "categoria": categoria,
                "conteudo": conteudo,
            })
            tooltip = f"[{categoria or 'Sem categoria'}]"
            if descricao:
                tooltip += f"\n{descricao}"
            item.setToolTip(tooltip)

            self.list_scripts.addItem(item)

        self.list_scripts.blockSignals(False)
        self._atualizar_contador_scripts()
        if self.inp_filter_scripts.text().strip():
            self._filtrar_scripts(self.inp_filter_scripts.text())

    def get_targets(self) -> list[str]:
        targets = parse_targets_string(self.target_input.text())
        if not targets:
            QMessageBox.warning(
                self, "Aviso",
                "Por favor, insira pelo menos um IP ou Hostname na caixa ou faça a importação de uma lista (.txt)."
            )
            return []
        return targets

    def start_script_execution(self):
        """Dispara todos os scripts marcados para todos os alvos listados."""
        targets = self.get_targets()
        if not targets:
            return

        scripts_selecionados = []
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    scripts_selecionados.append(data)

        if not scripts_selecionados:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione pelo menos um script na lista (marque a checkbox)."
            )
            return

        credentials = None
        if self.script_service.any_requires_credentials(scripts_selecionados):
            credentials = self._get_credentials()
            if credentials is None:
                return

        total_tarefas = len(scripts_selecionados) * len(targets)
        nomes = "\n".join(f"  • {s['nome']}" for s in scripts_selecionados[:5])
        if len(scripts_selecionados) > 5:
            nomes += f"\n  ... e mais {len(scripts_selecionados) - 5}"

        reply = QMessageBox.question(
            self, "Confirmar Lote",
            f"Enfileirar {len(scripts_selecionados)} script(s) para {len(targets)} alvo(s)?\n"
            f"Total: {total_tarefas} tarefa(s).\n\n"
            f"Scripts:\n{nomes}\n\n"
            f"Alvos: {', '.join(targets[:5])}"
            + (f" ... (+{len(targets) - 5})" if len(targets) > 5 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for script in scripts_selecionados:
            self.disparar_fila(
                targets,
                script["nome"],
                script["conteudo"],
                credentials=credentials,
            )

    def _get_selected_script_names(self) -> set:
        nomes = set()
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    nomes.add(data["nome"])
        return nomes

    def _atualizar_contador_scripts(self, *args):
        total = self.list_scripts.count()
        marcados = 0
        for i in range(total):
            item = self.list_scripts.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                marcados += 1

        if total == 0:
            self.lbl_scripts_count.setText("0 script(s) selecionado(s)")
        else:
            self.lbl_scripts_count.setText(f"{marcados} de {total} script(s) selecionado(s)")

    def _toggle_all_scripts(self, marcar: bool):
        state = Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
        self.list_scripts.blockSignals(True)
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            if not item.isHidden() and (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                item.setCheckState(state)
        self.list_scripts.blockSignals(False)
        self._atualizar_contador_scripts()

    def _filtrar_scripts(self, text: str):
        termo = text.strip().lower()
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data:
                continue
            alvo = f"{data['nome']} {data.get('descricao', '')} {data.get('categoria', '')}".lower()
            item.setHidden(termo not in alvo)

    def disparar_fila(self, targets, nome_tarefa, script_content, credentials=None):
        self.table.setSortingEnabled(False)

        for target in targets:
            row_position = self.table.rowCount()
            self.table.insertRow(row_position)

            item_target = QTableWidgetItem(target)
            item_action = QTableWidgetItem(nome_tarefa)
            item_inicio = QTableWidgetItem("-")
            item_fim = QTableWidgetItem("-")
            item_status = QTableWidgetItem("Pendente (Na fila)")
            item_resume = QTableWidgetItem("Aguardando...")

            for item in [item_target, item_action, item_inicio, item_fim, item_status, item_resume]:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            log_inicial = self.format_html(f"[{nome_tarefa}] -> Despachando lote para alvo: {target}...\n", "#4a90e2")
            item_target.setData(Qt.ItemDataRole.UserRole, log_inicial)

            self.table.setItem(row_position, 0, item_target)
            self.table.setItem(row_position, 1, item_action)
            self.table.setItem(row_position, 2, item_inicio)
            self.table.setItem(row_position, 3, item_fim)
            self.table.setItem(row_position, 4, item_status)
            self.table.setItem(row_position, 5, item_resume)

            self.queue_manager.add_task(
                target_pc=target,
                script_name=nome_tarefa,
                script_content=script_content,
                module_name="[Execução] Lote",
                credentials=credentials,
                on_start=lambda t, st=item_status, rs=item_resume, ini=item_inicio: self.update_status_start(t, st, rs, ini),
                on_finish=lambda t, s, d, tgt=item_target, st=item_status, rs=item_resume, fi=item_fim: self.update_status_finish(t, s, d, tgt, st, rs, fi),
                on_error=lambda t, e, tgt=item_target, st=item_status, rs=item_resume, fi=item_fim: self.update_status_error(t, e, tgt, st, rs, fi)
            )

        self.table.setSortingEnabled(True)
        self.refresh_console()

    def update_status_start(self, target_pc, item_status, item_resume, item_inicio):
        try:
            self.table.setSortingEnabled(False)
            item_status.setText("Executando...")
            item_resume.setText("Processando...")
            item_inicio.setText(datetime.now().strftime("%H:%M:%S"))
            self.table.setSortingEnabled(True)
        except RuntimeError:
            pass

    def update_status_finish(self, target_pc, status, json_data, item_target, item_status, item_resume, item_fim):
        json_data = json_data if isinstance(json_data, dict) else {}
        sucesso = False
        try:
            self.table.setSortingEnabled(False)
            status_str = str(status or "Concluído")
            item_status.setText(status_str)
            item_fim.setText(datetime.now().strftime("%H:%M:%S"))

            if "SUCESSO" in status_str.upper() or json_data.get("StatusFinal") == "SUCESSO":
                item_status.setForeground(Qt.GlobalColor.green)
                sucesso = True
            elif "ERRO" in status_str.upper() or "FALHA" in status_str.upper() or "ALERTA" in status_str.upper():
                item_status.setForeground(Qt.GlobalColor.red)
                sucesso = False
            else:
                item_status.setForeground(Qt.GlobalColor.darkYellow)
                sucesso = False

            resumo = json_data.get("Mensagem", "Operação concluída.")
            if "Detalhes" in json_data and json_data["Detalhes"]:
                if isinstance(json_data["Detalhes"], list):
                    linhas = [fix_mojibake(str(x).strip()) for x in json_data["Detalhes"] if str(x).strip()]
                    if linhas:
                        resumo = " | ".join(linhas)[:150] + "..."
                else:
                    resumo = fix_mojibake(str(json_data["Detalhes"]))[:150] + "..."

            item_resume.setText(fix_mojibake(str(resumo).strip()))
            row = item_status.row()
            if row >= 0:
                self.table.resizeRowToContents(row)
            self.table.setSortingEnabled(True)
        except RuntimeError:
            return

        linhas_console = []
        script_name = json_data.get("Script", "Ação Remota")
        linhas_console.append("=" * 80)
        linhas_console.append(f" [ SARCC ] RELATÓRIO DE EXECUÇÃO - ALVO: {target_pc} ")
        linhas_console.append("=" * 80)
        linhas_console.append(f" SCRIPT/AÇÃO   : {script_name}")
        linhas_console.append(f" STATUS FINAL  : {json_data.get('StatusFinal', str(status).upper())}")
        if "Inicio" in json_data:
            linhas_console.append(f" INÍCIO        : {json_data['Inicio']}")
        if "Fim" in json_data:
            linhas_console.append(f" TÉRMINO       : {json_data['Fim']}")
        linhas_console.append("-" * 80)

        if "Mensagem" in json_data and json_data["Mensagem"]:
            linhas_console.append(f" RESUMO: {json_data['Mensagem']}")
            linhas_console.append("-" * 80)

        if "Detalhes" in json_data and json_data["Detalhes"]:
            if isinstance(json_data["Detalhes"], list):
                for d in json_data["Detalhes"]:
                    linhas_console.append(f"  {d}")
            else:
                linhas_console.append(f"  {json_data['Detalhes']}")

        linhas_console.append("=" * 80 + "\n")

        relatorio_str = "\n".join(linhas_console)
        html_to_add = self.format_html(relatorio_str, "#4CAF50" if sucesso else "#f0ad4e")

        try:
            current_html = item_target.data(Qt.ItemDataRole.UserRole) or ""
            item_target.setData(Qt.ItemDataRole.UserRole, current_html + html_to_add)
            self.refresh_console()
        except RuntimeError:
            pass

    def update_status_error(self, target_pc, error_msg, item_target, item_status, item_resume, item_fim):
        try:
            self.table.setSortingEnabled(False)
            item_status.setText("Erro Fatal")
            item_status.setForeground(Qt.GlobalColor.red)
            item_fim.setText(datetime.now().strftime("%H:%M:%S"))
            item_resume.setText("Falha Crítica. Verifique o console abaixo.")
            row = item_status.row()
            if row >= 0:
                self.table.resizeRowToContents(row)
            self.table.setSortingEnabled(True)
        except RuntimeError:
            return

        linhas_erro = [
            "=" * 80,
            f" [ SARCC ] ERRO CRÍTICO / FALHA DE CONEXÃO - ALVO: {target_pc}",
            "=" * 80,
            str(error_msg).strip(),
            "=" * 80 + "\n"
        ]
        relatorio_str = "\n".join(linhas_erro)
        html_to_add = self.format_html(relatorio_str, "#d9534f")

        try:
            current_html = item_target.data(Qt.ItemDataRole.UserRole) or ""
            item_target.setData(Qt.ItemDataRole.UserRole, current_html + html_to_add)
            self.refresh_console()
        except RuntimeError:
            pass