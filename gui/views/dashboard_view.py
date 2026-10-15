import os
import json
import subprocess
import socket
import time
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QGroupBox, 
                             QGridLayout, QTextEdit, QComboBox, QMessageBox, QProgressBar, QScrollArea, QInputDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.remote_connection import RemoteConnectionManager
from core.task_queue import TaskQueueManager
from core.database import DatabaseManager
from core.ps_loader import load_ps_template, PsTemplateError
from gui.views.base_view import BaseView

class PingTrackerWorker(QThread):
    success = pyqtSignal(str)
    timeout = pyqtSignal(str)

    def __init__(self, target_pc):
        super().__init__()
        self.target_pc = target_pc

    def run(self):
        for _ in range(60):
            res = subprocess.run(f"ping -n 1 -w 1000 {self.target_pc}", capture_output=True, text=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if "TTL=" in res.stdout:
                self.success.emit(self.target_pc)
                return
            time.sleep(5)
        self.timeout.emit(self.target_pc)

class TelemetryWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, target_pc):
        super().__init__()
        self.target_pc = target_pc

    def run(self):
        try:
            try:
                ps_script = load_ps_template("dashboard", "telemetry")
            except PsTemplateError as e:
                self.error.emit(f"Erro de configuração interna: {e}")
                return

            conn = RemoteConnectionManager()
            res = conn.execute_script(self.target_pc, ps_script)

            if res["status"] == "Sucesso" and res.get("json_data"):
                self.finished.emit(res["json_data"])
            elif "WMI Assíncrono" in res["status"]:
                self.error.emit("A máquina alvo bloqueou o WinRM. O comando WMI disparou em 2º plano.")
            else:
                self.error.emit(res.get("log_saida", "Erro crítico na coleta."))
        except Exception as e:
            self.error.emit(str(e))

class DashboardView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(main_window_ref, 'queue_manager', None) or TaskQueueManager(max_threads=5)
        self.db = DatabaseManager()
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Dashboard & Diagnóstico Operacional")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        main_layout.addWidget(title)

        target_group = QGroupBox("Computador Alvo (Telemetria)")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(15, 20, 15, 15)
        
        self.inp_target = QLineEdit()
        self.inp_target.setFixedHeight(32)
        self.inp_target.setPlaceholderText("Ex: HUL-WK-244377E ou 10.8.128.14")
        self.inp_target.setStyleSheet("padding: 0 10px;")
        self.inp_target.textChanged.connect(self._force_uppercase)
        
        self.btn_fetch = QPushButton("🔄 Carregar Telemetria")
        self.btn_fetch.setFixedHeight(32)
        self.btn_fetch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fetch.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_fetch.clicked.connect(self.fetch_telemetry)

        self.lbl_last_sync = QLabel(" Última atualização: -")
        self.lbl_last_sync.setStyleSheet("color: #888; font-style: italic; font-weight: bold;")

        target_layout.addWidget(QLabel("Alvo:"))
        target_layout.addWidget(self.inp_target)
        target_layout.addWidget(self.btn_fetch)
        target_layout.addWidget(self.lbl_last_sync)
        main_layout.addWidget(target_group)

        action_group = QGroupBox("⚡ Ações Rápidas & Acesso Remoto")
        action_layout = QHBoxLayout(action_group)
        action_layout.setContentsMargins(15, 20, 15, 15)
        action_layout.setSpacing(10)
        
        self.cmb_remote = QComboBox()
        self.cmb_remote.setFixedHeight(32)
        self.cmb_remote.addItems(["RDP (Windows)", "VNC Viewer", "AnyDesk", "Assistência Rápida"])
        self.cmb_remote.setStyleSheet("padding: 0 10px; font-weight: bold;")
        
        self.btn_connect = QPushButton("▶ Conectar")
        self.btn_connect.setFixedHeight(32)
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setStyleSheet("background-color: #0275d8; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_connect.clicked.connect(self.action_connect)

        self.btn_wol = QPushButton("📡 Wake-on-LAN")
        self.btn_wol.setFixedHeight(32)
        self.btn_wol.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_wol.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_wol.clicked.connect(self.action_wol)
        
        self.btn_logoff = QPushButton("👤 Forçar Logoff")
        self.btn_logoff.setFixedHeight(32)
        self.btn_logoff.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logoff.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_logoff.clicked.connect(lambda: self.action_power("logoff"))
        
        self.btn_restart = QPushButton("🔄 Reiniciar")
        self.btn_restart.setFixedHeight(32)
        self.btn_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restart.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_restart.clicked.connect(lambda: self.action_power("restart"))
        
        self.btn_shutdown = QPushButton("🔌 Desligar")
        self.btn_shutdown.setFixedHeight(32)
        self.btn_shutdown.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shutdown.setStyleSheet("background-color: #292b2c; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_shutdown.clicked.connect(lambda: self.action_power("shutdown"))
        
        action_layout.addWidget(self.cmb_remote)
        action_layout.addWidget(self.btn_connect)
        action_layout.addWidget(self.btn_wol)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_logoff)
        action_layout.addWidget(self.btn_restart)
        action_layout.addWidget(self.btn_shutdown)
        
        main_layout.addWidget(action_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        grid_cards = QGridLayout()
        grid_cards.setSpacing(15)
        grid_cards.setColumnStretch(0, 1)
        grid_cards.setColumnStretch(1, 1)

        self.card_sys = QGroupBox("🌐 Informações do Sistema")
        sys_layout = QVBoxLayout(self.card_sys)
        sys_layout.setContentsMargins(15, 20, 15, 15)
        
        sys_grid = QGridLayout()
        sys_grid.setSpacing(8)
        
        self.lbl_hostname = QLabel("Hostname: -")
        self.lbl_os = QLabel("SO: -")
        self.lbl_uptime = QLabel("Uptime: -") 
        self.lbl_ip = QLabel("IP (Ethernet/Wi-Fi): -")
        self.lbl_mac = QLabel("MAC Address: -")
        self.lbl_av = QLabel("Antivírus: -")
        
        self.lbl_rdp = QLabel("RDP: -")
        self.lbl_vnc = QLabel("VNC: -")
        self.lbl_anydesk = QLabel("AnyDesk ID: -")
        self.lbl_wol = QLabel("WoL (OS): -")
        self.lbl_zabbix = QLabel("Zabbix: -")
        self.lbl_glpi = QLabel("GLPI: -")
        self.lbl_desktopinfo = QLabel("Desktop Info: -")
        self.lbl_winget = QLabel("Winget: -")
        self.lbl_reboot = QLabel("Reboot: -")

        # Permite selecionar e copiar texto (Ctrl+C) em todos os rótulos de informação
        for lbl in [self.lbl_hostname, self.lbl_os, self.lbl_uptime, self.lbl_ip, self.lbl_mac, 
                    self.lbl_av, self.lbl_rdp, self.lbl_vnc, self.lbl_anydesk, self.lbl_wol, 
                    self.lbl_zabbix, self.lbl_glpi, self.lbl_desktopinfo, self.lbl_winget, self.lbl_reboot]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        sys_grid.addWidget(self.lbl_hostname, 0, 0)
        sys_grid.addWidget(self.lbl_os, 1, 0)
        sys_grid.addWidget(self.lbl_uptime, 2, 0)
        sys_grid.addWidget(self.lbl_ip, 3, 0)
        sys_grid.addWidget(self.lbl_mac, 4, 0)
        sys_grid.addWidget(self.lbl_av, 5, 0)
        sys_grid.addWidget(self.lbl_winget, 6, 0)
        sys_grid.addWidget(self.lbl_reboot, 7, 0)

        sys_grid.addWidget(self.lbl_rdp, 0, 1)
        sys_grid.addWidget(self.lbl_vnc, 1, 1)
        sys_grid.addWidget(self.lbl_anydesk, 2, 1)
        sys_grid.addWidget(self.lbl_wol, 3, 1)
        sys_grid.addWidget(self.lbl_zabbix, 4, 1)
        sys_grid.addWidget(self.lbl_glpi, 5, 1)
        sys_grid.addWidget(self.lbl_desktopinfo, 6, 1) 
        
        sys_layout.addLayout(sys_grid)
        grid_cards.addWidget(self.card_sys, 0, 0)

        self.card_profiles = QGroupBox("👥 Sessões e Perfis de Usuários")
        p_layout = QHBoxLayout(self.card_profiles)
        p_layout.setContentsMargins(15, 20, 15, 15)
        
        v_prof = QVBoxLayout()
        self.lbl_profiles_count = QLabel("-")
        self.lbl_profiles_count.setStyleSheet("font-size: 26px; font-weight: bold; color: #2a7de1;")
        self.lbl_profiles_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_prof.addWidget(self.lbl_profiles_count)
        v_prof.addWidget(QLabel("Perfis na Máquina", alignment=Qt.AlignmentFlag.AlignCenter))
        
        v_log = QVBoxLayout()
        self.lbl_logged_count = QLabel("-")
        self.lbl_logged_count.setStyleSheet("font-size: 26px; font-weight: bold; color: #f0ad4e;")
        self.lbl_logged_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_log.addWidget(self.lbl_logged_count)
        v_log.addWidget(QLabel("Usuários Logados", alignment=Qt.AlignmentFlag.AlignCenter))
        
        p_layout.addLayout(v_prof)
        p_layout.addLayout(v_log)
        grid_cards.addWidget(self.card_profiles, 0, 1)

        content_layout.addLayout(grid_cards)

        bottom_panels = QHBoxLayout()
        bottom_panels.setSpacing(15)

        self.card_resources = QGroupBox("⚙️ Recursos do Sistema (Disco, CPU, RAM)")
        res_layout = QVBoxLayout(self.card_resources)
        res_layout.setContentsMargins(15, 20, 15, 15)
        
        self.lbl_storage_info = QLabel("Disco C:: Aguardando leitura...")
        self.prog_storage = QProgressBar()
        self.prog_storage.setValue(0)
        self.prog_storage.setStyleSheet(self._get_bar_style(0))
        
        self.lbl_cpu_info = QLabel("CPU: Aguardando leitura...")
        self.prog_cpu = QProgressBar()
        self.prog_cpu.setValue(0)
        self.prog_cpu.setStyleSheet(self._get_bar_style(0))

        self.lbl_temp_info = QLabel("Temperatura CPU: Aguardando leitura...")
        self.prog_temp = QProgressBar()
        self.prog_temp.setValue(0)
        self.prog_temp.setStyleSheet(self._get_bar_style(0, is_temp=True))
        
        self.lbl_ram_info = QLabel("RAM: Aguardando leitura...")
        self.prog_ram = QProgressBar()
        self.prog_ram.setValue(0)
        self.prog_ram.setStyleSheet(self._get_bar_style(0))

        res_layout.addWidget(self.lbl_storage_info)
        res_layout.addWidget(self.prog_storage)
        res_layout.addSpacing(10)
        
        cpu_horiz = QHBoxLayout()
        cpu_horiz.setSpacing(15)
        
        v_cpu = QVBoxLayout()
        v_cpu.setSpacing(5)
        v_cpu.addWidget(self.lbl_cpu_info)
        v_cpu.addWidget(self.prog_cpu)
        
        v_temp = QVBoxLayout()
        v_temp.setSpacing(5)
        v_temp.addWidget(self.lbl_temp_info)
        v_temp.addWidget(self.prog_temp)
        
        cpu_horiz.addLayout(v_cpu, stretch=1)
        cpu_horiz.addLayout(v_temp, stretch=1)
        res_layout.addLayout(cpu_horiz)
        
        res_layout.addSpacing(10)
        res_layout.addWidget(self.lbl_ram_info)
        res_layout.addWidget(self.prog_ram)
        
        bottom_panels.addWidget(self.card_resources, stretch=65)

        lic_group = QGroupBox("🔑 Gestão de Versão do Windows")
        lic_layout = QVBoxLayout(lic_group)
        lic_layout.setContentsMargins(15, 20, 15, 15)
        
        self.lbl_activation = QLabel("Status Atual: -")
        self.lbl_activation.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        lic_layout.addWidget(self.lbl_activation)

        self.cmb_license = QComboBox()
        self.cmb_license.setFixedHeight(32)
        self.cmb_license.addItem("Windows 10 Education", "NW6C2-QMPVW-D7KKK-3GKT6-VCFB2")
        self.cmb_license.addItem("Windows 10 Pro Education", "6TP4R-GNPTD-KYYHQ-7B7DP-J447Y")
        self.cmb_license.addItem("Windows 10 Enterprise", "NPPR9-FWDCX-D2C8J-H872K-2YT43")
        self.cmb_license.addItem("Windows 10 Pro", "W269N-WFGWX-YVC9B-4J6C9-T83GX")
        self.cmb_license.setStyleSheet("padding: 0 10px;")
        lic_layout.addWidget(self.cmb_license)
        
        lbl_info = QLabel("<i>Altera a versão do SO em background.</i>")
        lbl_info.setStyleSheet("color: gray; margin-top: 5px;")
        lic_layout.addWidget(lbl_info)
        
        lic_layout.addStretch()
        
        self.btn_apply_key = QPushButton("⚙️ Injetar Chave KMS")
        self.btn_apply_key.setFixedHeight(32)
        self.btn_apply_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_key.setStyleSheet("background-color: #f0ad4e; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_apply_key.clicked.connect(self.change_windows_key)
        lic_layout.addWidget(self.btn_apply_key)

        bottom_panels.addWidget(lic_group, stretch=35)
        content_layout.addLayout(bottom_panels)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _get_bar_style(self, val, is_temp=False, disabled=False):
        if disabled:
            color = "#666666" 
        elif is_temp:
            if val >= 85: color = "#d9534f" 
            elif val >= 70: color = "#f0ad4e" 
            else: color = "#1e8a5e" 
        else:
            if val >= 90: color = "#d9534f" 
            elif val >= 75: color = "#f0ad4e" 
            else: color = "#1e8a5e" 
            
        return f"QProgressBar {{ border: 1px solid #444; color: white; font-weight: bold; border-radius: 4px; text-align: center; height: 16px; }} QProgressBar::chunk {{ background-color: {color}; }}"

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()

    def action_connect(self):
        target = self.inp_target.text().strip()
        tool = self.cmb_remote.currentText()
        executor = os.environ.get("USERNAME", "Desconhecido")
        
        if tool != "Assistência Rápida" and not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo para conectar.")
            self.inp_target.setFocus()
            return
            
        try:
            if tool == "RDP (Windows)":
                subprocess.Popen(["mstsc", f"/v:{target}"])
            elif tool == "VNC Viewer":
                RemoteConnectionManager().abrir_acesso_remoto(target)
            elif tool == "AnyDesk":
                subprocess.Popen(["anydesk", target])
            elif tool == "Assistência Rápida":
                subprocess.Popen("start quickassist", shell=True)
                
            self.db.save_execution(
                target_pc=target if target else "Sessão Local", 
                script_name=f"Acesso Remoto ({tool})", 
                status="SUCESSO", 
                result_data="Conexão solicitada via interface gráfica.", 
                technician=executor, 
                module="[Dashboard] Conexão"
            )
        except Exception as e:
            self.db.save_execution(
                target_pc=target if target else "Sessão Local", 
                script_name=f"Acesso Remoto ({tool})", 
                status="ERRO", 
                result_data=str(e), 
                technician=executor, 
                module="[Dashboard] Conexão"
            )
            QMessageBox.warning(self, "Erro", f"O executável para '{tool}' não foi encontrado ou falhou ao iniciar.\nDetalhe: {e}")

    def on_wol_success(self, target):
        self.btn_wol.setText("📡 Wake-on-LAN")
        self.btn_wol.setEnabled(True)
        QMessageBox.information(self, "Máquina Online!", f"O computador {target} já está ligado e respondendo a PING na rede!\n\nVocê já pode iniciar o Acesso Remoto.")

    def on_wol_timeout(self, target):
        self.btn_wol.setText("📡 Wake-on-LAN")
        self.btn_wol.setEnabled(True)
        QMessageBox.warning(self, "Tempo Esgotado", f"O pacote mágico foi enviado, mas o computador {target} não respondeu a ping após 5 minutos.\n\nVerifique se ele possui cabo de energia conectado ou se o WoL está habilitado na BIOS.")

    def action_wol(self):
        mac_text = self.lbl_mac.text().replace("MAC Address: ", "").strip()
        alvo_text = self.inp_target.text().strip()
        executor = os.environ.get("USERNAME", "Desconhecido")

        if not mac_text or mac_text == "-" or mac_text == "N/A":
            if alvo_text.count(":") == 5 or alvo_text.count("-") == 5:
                mac_text = alvo_text
            else:
                mac_text, ok = QInputDialog.getText(self, "Wake-on-LAN", 
                                                    "A máquina está offline e sem telemetria.\n\nCole o MAC Address (Ex: 00:11:22:33:44:55):")
                if not ok or not mac_text:
                    return

        mac_clean = mac_text.replace(':', '').replace('-', '').replace('.', '').upper()
        
        if len(mac_clean) != 12:
            QMessageBox.warning(self, "Erro", f"O formato do MAC Address fornecido parece inválido: {mac_text}")
            return
            
        try:
            data = bytes.fromhex('FF' * 6 + mac_clean * 16)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(data, ('255.255.255.255', 9))
            sock.sendto(data, ('255.255.255.255', 7))
            sock.close()
            
            target_log = alvo_text if alvo_text else mac_clean
            self.db.save_execution(
                target_pc=target_log, 
                script_name="Wake-on-LAN", 
                status="SUCESSO", 
                result_data=f"Pacote Mágico disparado na rede para o MAC {mac_clean}", 
                technician=executor, 
                module="[Dashboard] Energia"
            )
            
            if alvo_text and (alvo_text.count(".") == 3 or not alvo_text.count(":")):
                self.btn_wol.setText("⏳ Aguardando...")
                self.btn_wol.setEnabled(False)
                self.ping_worker = PingTrackerWorker(alvo_text)
                self.ping_worker.success.connect(self.on_wol_success)
                self.ping_worker.timeout.connect(self.on_wol_timeout)
                self.ping_worker.start()
                QMessageBox.information(self, "Wake-on-LAN Disparado", f"O Pacote Mágico foi enviado.\n\nO SARCC continuará testando a conectividade em segundo plano e te avisará assim que a máquina ligar.")
            else:
                QMessageBox.information(self, "Wake-on-LAN Disparado", f"O Pacote Mágico foi enviado com sucesso para o MAC:\n{mac_text}")
                
        except Exception as e:
            target_log = alvo_text if alvo_text else mac_clean
            self.db.save_execution(
                target_pc=target_log, 
                script_name="Wake-on-LAN", 
                status="ERRO", 
                result_data=str(e), 
                technician=executor, 
                module="[Dashboard] Energia"
            )
            QMessageBox.critical(self, "Erro Crítico", f"Falha ao enviar o pacote Wake-on-LAN:\n{e}")

    def action_power(self, action_type):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        # Mapeamento ação → (rótulo PT-BR, nome do template .ps1)
        # Cada ação tem seu próprio arquivo para evitar escapes complexos de
        # aspas duplas em strings PS passadas como variável.
        acoes = {
            "restart":  ("Reiniciar",       "power_restart"),
            "shutdown": ("Desligar",        "power_shutdown"),
            "logoff":   ("Forçar Logoff",   "power_logoff"),
        }

        nome_acao, template_name = acoes[action_type]

        reply = QMessageBox.question(self, 'Confirmação Crítica',
                                     f'ATENÇÃO: Você está prestes a {nome_acao} o computador {target}.\n\nDeseja realmente prosseguir com esta ação disruptiva?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ps_script = load_ps_template("dashboard", template_name)
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro interno", f"Template ausente: {e}")
            return

        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Power: {nome_acao}",
            script_content=ps_script,
            module_name="[Dashboard] Energia",
            on_start=lambda t: None,
            on_finish=lambda t, s, d: None,
            on_error=lambda t, e: QMessageBox.critical(self, "Falha de Conexão", f"Não foi possível enviar o comando para {t}:\n{e}")
        )
        QMessageBox.information(self, "Comando Despachado", f"O comando de {nome_acao} foi enfileirado para envio a {target}.\n\nVocê pode conferir o resultado final na aba Histórico de Logs.")

    def fetch_telemetry(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("Coletando...")
        agora = datetime.now().strftime('%H:%M:%S')
        self.lbl_last_sync.setText(f" Iniciado às: {agora}...")

        self.worker = TelemetryWorker(target)
        self.worker.finished.connect(self.update_telemetry_ui)
        self.worker.error.connect(self.show_telemetry_error)
        self.worker.start()

    def update_telemetry_ui(self, data):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("🔄 Carregar Telemetria")
        agora = datetime.now().strftime('%H:%M:%S')
        self.lbl_last_sync.setText(f" Última atualização: {agora}")

        pct = data.get("DiskPct", 0)
        free = data.get("DiskFree", 0)
        total = data.get("DiskTotal", 0)
        self.prog_storage.setValue(int(pct))
        self.prog_storage.setStyleSheet(self._get_bar_style(pct))
        self.prog_storage.setFormat("%p%")
        self.lbl_storage_info.setText(f"Disco C:: Usado {pct}% ({free} GB livres de {total} GB)")
        
        cpuModel = data.get("CPUModel", "N/A")
        cpuUsage = data.get("CPUUsage", 0)
        self.prog_cpu.setValue(int(cpuUsage))
        self.prog_cpu.setStyleSheet(self._get_bar_style(cpuUsage))
        self.prog_cpu.setFormat("%p%")
        self.lbl_cpu_info.setText(f"CPU: {cpuModel}")
        
        tempVal = data.get("CPUTemp", "N/A")
        
        if tempVal != "N/A":
            tempVal = str(tempVal).replace(",", ".")

        if tempVal == "N/A" or float(tempVal) <= 0:
            self.prog_temp.setValue(0)
            self.prog_temp.setStyleSheet(self._get_bar_style(0, disabled=True))
            self.prog_temp.setFormat("N/A")
            self.lbl_temp_info.setText("Temperatura CPU: Sensor não suportado")
        else:
            t = float(tempVal)
            self.prog_temp.setValue(int(t))
            self.prog_temp.setStyleSheet(self._get_bar_style(t, is_temp=True))
            self.prog_temp.setFormat("%v°C")
            self.lbl_temp_info.setText("Temperatura CPU:")

        totalRam = data.get("TotalRAM", 0)
        usedRam = data.get("UsedRAM", 0)
        ramPct = data.get("RAMPct", 0)
        self.prog_ram.setValue(int(ramPct))
        self.prog_ram.setStyleSheet(self._get_bar_style(ramPct))
        self.prog_ram.setFormat("%p%")
        self.lbl_ram_info.setText(f"RAM: Usando {usedRam} GB de {totalRam} GB")

        self.lbl_profiles_count.setText(str(data.get("ProfilesCount", 0)))
        self.lbl_logged_count.setText(str(data.get("LoggedUsers", 0)))

        self.lbl_hostname.setText(f"Hostname: {data.get('HostName', 'N/A')}")
        self.lbl_os.setText(f"SO: {data.get('OSVersion', 'N/A')}")
        self.lbl_uptime.setText(f"Uptime: {data.get('Uptime', 'N/A')}") 
        self.lbl_ip.setText(f"IP: {data.get('IP', 'N/A')}")
        self.lbl_mac.setText(f"MAC: {data.get('MAC', 'N/A')}")
        
        av = data.get('AVProduct', 'N/A')
        self.lbl_av.setText(f"Antivírus: <span style='color: #4CAF50; font-weight: bold;'>{av}</span>")
        
        activation = data.get('Activation', 'N/A')
        if "Ativado" in activation:
            self.lbl_activation.setText(f"Status Atual: <span style='color: #4CAF50;'>{activation}</span>")
        else:
            self.lbl_activation.setText(f"Status Atual: <span style='color: #f44336;'>{activation}</span>")
            
        rdp = data.get('RDP', 'N/A')
        if rdp == "Ativado":
            self.lbl_rdp.setText(f"RDP: <span style='color: #4CAF50; font-weight: bold;'>{rdp}</span>")
        else:
            self.lbl_rdp.setText(f"RDP: <span style='color: #f44336; font-weight: bold;'>{rdp}</span>")

        vnc = data.get('VNC', 'N/A')
        if "Ativo" in vnc:
            self.lbl_vnc.setText(f"VNC: <span style='color: #4CAF50; font-weight: bold;'>{vnc}</span>")
        elif "Parado" in vnc:
            self.lbl_vnc.setText(f"VNC: <span style='color: #f44336; font-weight: bold;'>{vnc}</span>")
        else:
            self.lbl_vnc.setText(f"VNC: <span style='color: #888888; font-weight: bold;'>{vnc}</span>")

        anydesk = data.get('AnyDesk', 'N/A')
        if anydesk != "Não Instalado":
            self.lbl_anydesk.setText(f"AnyDesk ID: <span style='color: #4CAF50; font-weight: bold;'>{anydesk}</span>")
        else:
            self.lbl_anydesk.setText(f"AnyDesk ID: <span style='color: #888888; font-weight: bold;'>{anydesk}</span>")

        wol = data.get('WOL', 'N/A')
        if "Ativado" in wol:
            self.lbl_wol.setText(f"WoL (OS): <span style='color: #4CAF50; font-weight: bold;'>{wol}</span>")
        else:
            self.lbl_wol.setText(f"WoL (OS): <span style='color: #f44336; font-weight: bold;'>{wol}</span>")

        zabbix = data.get('Zabbix', 'N/A')
        if "Ativo" in zabbix:
            self.lbl_zabbix.setText(f"Zabbix: <span style='color: #4CAF50; font-weight: bold;'>{zabbix}</span>")
        elif "Parado" in zabbix:
            self.lbl_zabbix.setText(f"Zabbix: <span style='color: #f44336; font-weight: bold;'>{zabbix}</span>")
        else:
            self.lbl_zabbix.setText(f"Zabbix: <span style='color: #888888; font-weight: bold;'>{zabbix}</span>")

        glpi = data.get('GLPI', 'N/A')
        if "Ativo" in glpi:
            self.lbl_glpi.setText(f"GLPI: <span style='color: #4CAF50; font-weight: bold;'>{glpi}</span>")
        elif "Parado" in glpi:
            self.lbl_glpi.setText(f"GLPI: <span style='color: #f44336; font-weight: bold;'>{glpi}</span>")
        else:
            self.lbl_glpi.setText(f"GLPI: <span style='color: #888888; font-weight: bold;'>{glpi}</span>")

        dinfo = data.get('DesktopInfo', 'N/A')
        if "Ativo" in dinfo:
            self.lbl_desktopinfo.setText(f"Desktop Info: <span style='color: #4CAF50; font-weight: bold;'>{dinfo}</span>")
        else:
            self.lbl_desktopinfo.setText(f"Desktop Info: <span style='color: #888888; font-weight: bold;'>{dinfo}</span>")
        
        wg = data.get('Winget', 'N/A')
        if "Instalado" in wg and "Não" not in wg:
            self.lbl_winget.setText(f"Winget: <span style='color: #4CAF50; font-weight: bold;'>{wg}</span>")
        else:
            self.lbl_winget.setText(f"Winget: <span style='color: #f44336; font-weight: bold;'>{wg}</span>")

        reboot = data.get('RebootPending', 'N/A')
        if "Pendente" in reboot:
            self.lbl_reboot.setText(
                f"Reboot: <span style='color: #f0ad4e; font-weight: bold;'>⚠️ {reboot}</span>"
            )
        elif reboot == "OK":
            self.lbl_reboot.setText(
                f"Reboot: <span style='color: #4CAF50; font-weight: bold;'>{reboot}</span>"
            )
        else:
            self.lbl_reboot.setText(
                f"Reboot: <span style='color: #888888; font-weight: bold;'>{reboot}</span>"
            )

    def show_telemetry_error(self, err):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("🔄 Carregar Telemetria")
        agora = datetime.now().strftime('%H:%M:%S')
        self.lbl_last_sync.setText(f" Última atualização: Falha às {agora}")
        QMessageBox.warning(self, "Aviso Operacional", f"{err}")

    def change_windows_key(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        version_name = self.cmb_license.currentText()
        gblk_key = self.cmb_license.currentData()

        reply = QMessageBox.question(self, 'Confirmação', f'Alterar a versão do Windows em {target} para {version_name}?\n\nChave GVLK: {gblk_key}', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return

        try:
            ps_script = load_ps_template(
                "dashboard", "change_windows_key",
                gblk_key=gblk_key,
                version_name=version_name,
            )
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro interno", f"Template ausente: {e}")
            return

        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Licença {version_name}",
            script_content=ps_script,
            module_name="[Dashboard] Licenciamento",
            on_start=lambda t: None,
            on_finish=lambda t, s, d: None,
            on_error=lambda t, e: QMessageBox.critical(self, "Erro", f"Falha na injeção da chave:\n{e}")
        )
        QMessageBox.information(self, "Ação Iniciada", "A chave está sendo processada em segundo plano. Verifique o Histórico de Logs em alguns instantes.")