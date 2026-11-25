import base64

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.ps_loader import PsTemplateError, load_ps_template
from core.remote_connection import RemoteConnectionManager
from core.text_utils import fix_mojibake
from gui.views.base_view import BaseView

# Catálogo de atalhos de diagnóstico e reset de rede
NETWORK_SHORTCUTS = [
    ("Resetar Rede (DNS / ARP / NetBIOS)", "ipconfig /flushdns; arp -d *; nbtstat -R; nbtstat -RR; ipconfig /registerdns; Write-Output 'Cache DNS, ARP e NetBIOS resetados com sucesso.'"),
    ("Ping Rápido (4 pacotes)",              "ping -n 4 8.8.8.8"),
    ("Ping Contínuo (30 pacotes)",           "ping -n 30 8.8.8.8"),
    ("Ping no Gateway Padrão",               "$gw = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1).NextHop; if ($gw) { ping -n 4 $gw } else { Write-Output 'Gateway padrao nao encontrado' }"),
    ("Tracert (rota até 8.8.8.8)",            "tracert -d -h 15 8.8.8.8"),
    ("NSLookup (DNS A do alvo)",              "Resolve-DnsName -Name {target} -Type A -ErrorAction SilentlyContinue | Format-Table -AutoSize"),
    ("Reverso (PTR do alvo)",                 "Resolve-DnsName -Name {target} -Type PTR -ErrorAction SilentlyContinue | Format-Table -AutoSize"),
    ("Test-NetConnection (WinRM 5985)",       "Test-NetConnection -ComputerName localhost -Port 5985"),
    ("Test-NetConnection (RDP 3389)",         "Test-NetConnection -ComputerName localhost -Port 3389"),
    ("Config de Rede (IP/Gateway)",           "Get-NetIPConfiguration | Format-List"),
    ("Servidores DNS Configurados",           "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | Format-Table -AutoSize"),
    ("Tabela de Rotas",                       "Get-NetRoute -AddressFamily IPv4 | Sort-Object RouteMetric | Format-Table -AutoSize"),
    ("Conexões Ativas (ESTABLISHED)",         "netstat -ano | findstr ESTABLISHED | Select-Object -First 30"),
    ("Portas em Escuta (LISTENING)",          "netstat -ano | findstr LISTENING | Select-Object -First 30"),
    ("ARP (vizinhos de rede)",                "arp -a"),
    ("Cache DNS Local",                       "Get-DnsClientCache | Select-Object -First 30 | Format-Table -AutoSize"),
    ("Wi-Fi / Redes Visíveis",                "netsh wlan show networks mode=bssid 2>$null | Select-Object -First 40"),
    ("Firewall (Perfis)",                     "Get-NetFirewallProfile | Format-Table Name, Enabled, DefaultInboundAction -AutoSize"),
]


def format_console_html(raw_text: str) -> str:
    """Escapa caracteres HTML (<, >, &) e repara UTF-8 antes de converter quebras de linha em <br>."""
    cleaned = fix_mojibake(str(raw_text or ""))
    escaped = (
        cleaned.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    return escaped


class ShellWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, target_pc, command):
        super().__init__()
        self.target_pc = target_pc
        self.command = command

    def run(self):
        try:
            cmd_b64 = base64.b64encode(self.command.encode("utf-8")).decode("ascii")

            try:
                ps_script = load_ps_template("shell", "run_command", command_b64=cmd_b64)
            except PsTemplateError as e:
                self.finished.emit(f"[ERRO INTERNO] Falha ao carregar template: {e}")
                return

            conn = RemoteConnectionManager()
            res = conn.execute_script(self.target_pc, ps_script)

            saida = fix_mojibake(res.get("log_saida", "").strip())

            if "SARCC_SHELL_ERROR:" in saida:
                saida = f"[ERRO DE EXECUÇÃO NO POWERSHELL]\n{saida.replace('SARCC_SHELL_ERROR:', '').strip()}"
            elif not saida and res["status"] == "Sucesso":
                saida = "[Comando executado com sucesso sem retorno visual]"
            elif res["status"] != "Sucesso":
                saida = f"[ERRO DE CONEXÃO]\n{saida}"

            self.finished.emit(saida)
        except Exception as e:
            self.finished.emit(f"[FALHA CRÍTICA]\n{str(e)}")


class ShellView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Terminal Interativo Remoto (PowerShell)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        layout.addWidget(title)

        conn_group = QGroupBox("Estabelecer Sessão")
        conn_layout = QHBoxLayout()
        conn_layout.setContentsMargins(15, 20, 15, 15)

        self.inp_target = QLineEdit()
        self.inp_target.setFixedHeight(32)
        self.inp_target.setPlaceholderText("Ex: LOCALHOST, HUL-WK-001122E ou 192.168.0.2")
        self.inp_target.setStyleSheet("padding: 0 10px; font-weight: bold;")
        self.inp_target.textChanged.connect(self._force_uppercase)

        conn_layout.addWidget(QLabel("Computador Alvo:"))
        conn_layout.addWidget(self.inp_target)
        conn_layout.addStretch()
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        shortcut_group = QGroupBox("⚡ Atalhos de Diagnóstico e Rede")
        shortcut_layout = QHBoxLayout(shortcut_group)
        shortcut_layout.setContentsMargins(15, 20, 15, 15)
        shortcut_layout.setSpacing(10)

        self.cmb_shortcut = QComboBox()
        self.cmb_shortcut.setFixedHeight(32)
        self.cmb_shortcut.setStyleSheet("padding: 0 10px;")
        self.cmb_shortcut.addItem("— Selecione um atalho —", userData=None)
        for label, cmd in NETWORK_SHORTCUTS:
            self.cmb_shortcut.addItem(label, userData=cmd)
        shortcut_layout.addWidget(self.cmb_shortcut, stretch=1)

        self.btn_run_shortcut = QPushButton("⚡ Executar Atalho")
        self.btn_run_shortcut.setFixedHeight(32)
        self.btn_run_shortcut.setMinimumWidth(160)
        self.btn_run_shortcut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run_shortcut.setStyleSheet(
            "background-color: #5bc0de; color: black; padding: 0 15px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_run_shortcut.clicked.connect(self.run_shortcut)
        shortcut_layout.addWidget(self.btn_run_shortcut)

        layout.addWidget(shortcut_group)

        console_group = QGroupBox("Console de Saída")
        console_layout = QVBoxLayout(console_group)
        console_layout.setContentsMargins(15, 20, 15, 15)

        self.txt_console = QTextEdit()
        self.txt_console.setReadOnly(True)
        font = QFont("Consolas", 11)
        self.txt_console.setFont(font)
        self.txt_console.setStyleSheet(
            "font-family: Consolas, monospace; padding: 10px; "
            "background-color: #121212; color: #e0e0e0; border: 1px solid #444; border-radius: 4px;"
        )
        self.txt_console.setPlainText(
            "SARCC PowerShell Remote Host\n"
            "Digite um comando abaixo ou escolha um atalho de diagnóstico para iniciar...\n"
        )
        console_layout.addWidget(self.txt_console)
        layout.addWidget(console_group, stretch=1)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        lbl_prompt = QLabel("PS >")
        lbl_prompt.setStyleSheet(
            "font-weight: bold; font-family: Consolas; font-size: 14px; color: #4a90e2;"
        )
        input_layout.addWidget(lbl_prompt)

        self.inp_command = QLineEdit()
        self.inp_command.setFixedHeight(32)
        self.inp_command.setFont(font)
        self.inp_command.setStyleSheet(
            "padding: 0 10px; border: 1px solid #444; "
            "border-radius: 4px; background-color: #121212; color: #e0e0e0;"
        )
        self.inp_command.setPlaceholderText("Digite um comando (ex: Get-Process, ipconfig) e pressione Enter...")
        self.inp_command.returnPressed.connect(self.execute_command)
        input_layout.addWidget(self.inp_command)

        self.btn_send = QPushButton("Enviar")
        self.btn_send.setFixedHeight(32)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setStyleSheet(
            "background-color: #1e8a5e; color: white; padding: 0 20px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_send.clicked.connect(self.execute_command)
        input_layout.addWidget(self.btn_send)

        self.btn_clear = QPushButton("Limpar Tela")
        self.btn_clear.setFixedHeight(32)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(
            "background-color: #d9534f; color: white; padding: 0 15px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_clear.clicked.connect(
            lambda: self.txt_console.setPlainText("SARCC PowerShell Remote Host\n")
        )
        input_layout.addWidget(self.btn_clear)

        layout.addLayout(input_layout)

    def run_shortcut(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo antes de executar um atalho.")
            self.inp_target.setFocus()
            return

        cmd_template = self.cmb_shortcut.currentData()
        if not cmd_template:
            QMessageBox.information(self, "Atalho", "Selecione um atalho na lista antes de executar.")
            return

        comando = cmd_template.replace("{target}", target)
        self.inp_command.setText(comando)
        self.execute_command()

    def append_to_console(self, text: str, is_error: bool = False, is_prompt: bool = False):
        color_style = ""
        if is_error:
            color_style = "color: #d9534f;"
        elif is_prompt:
            color_style = "color: #e67e22;"

        safe_html = format_console_html(text)
        self.txt_console.moveCursor(QTextCursor.MoveOperation.End)
        if color_style:
            self.txt_console.insertHtml(
                f"<span style='{color_style} white-space: pre-wrap;'>{safe_html}</span><br>"
            )
        else:
            self.txt_console.insertHtml(
                f"<span style='white-space: pre-wrap;'>{safe_html}</span><br>"
            )
        self.txt_console.moveCursor(QTextCursor.MoveOperation.End)

    def execute_command(self):
        target = self.inp_target.text().strip()
        command = self.inp_command.text().strip()

        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo antes de enviar comandos.")
            self.inp_target.setFocus()
            return

        if not command:
            return

        self.append_to_console(f"\n[{target}] PS > {command}", is_prompt=True)

        self.inp_command.clear()
        self.inp_command.setEnabled(False)
        self.btn_send.setEnabled(False)
        self.btn_run_shortcut.setEnabled(False)
        self.inp_command.setPlaceholderText("Aguardando resposta do servidor...")

        self.worker = ShellWorker(target, command)
        self.worker.finished.connect(self.on_command_finished)
        self.worker.start()

    def on_command_finished(self, result_text: str):
        is_err = "[ERRO" in result_text or "[FALHA" in result_text
        self.append_to_console(result_text, is_error=is_err)

        self.inp_command.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.btn_run_shortcut.setEnabled(True)
        self.inp_command.setPlaceholderText("Digite um comando (ex: Get-Process, ipconfig) e pressione Enter...")
        self.inp_command.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()
