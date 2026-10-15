import qdarktheme
import os
from PyQt6.QtGui import QPixmap
from core.resources import resource_path
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QWidget, QHBoxLayout, QVBoxLayout, 
                             QPushButton, QStackedWidget, QLabel, QApplication)
from PyQt6.QtCore import Qt

from core.database import DatabaseManager
from core.task_queue import TaskQueueManager

# Importando todas as 8 Views do SARCC v2.0
from gui.views.dashboard_view import DashboardView
from gui.views.shell_view import ShellView
from gui.views.system_manager_view import SystemManagerView
from gui.views.execution_view import ExecutionView
from gui.views.software_view import SoftwareView
from gui.views.scheduler_view import SchedulerView
from gui.views.scripts_view import ScriptsView
from gui.views.history_view import HistoryView
from gui.views.help_view import HelpView

def _get_max_threads(default: int = 12) -> int:
    """Lê SARCC_MAX_THREADS do ambiente. Cai para `default` se inválido/ausente.

    Exemplos:
        default (sem variável)     -> 12
        SARCC_MAX_THREADS=20       -> 20
        SARCC_MAX_THREADS=0        -> 12  (inválido, cai para default)
        SARCC_MAX_THREADS=abc      -> 12  (inválido, cai para default)
        SARCC_MAX_THREADS=999      -> 999 (aceita, técnico sabe o que faz)
    """
    raw = os.environ.get("SARCC_MAX_THREADS", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        if value < 1:
            return default
        return value
    except ValueError:
        return default
    
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SARCC - SysAdmin Remote Command Center")
        self.resize(1150, 750) 

        # Cache de credenciais em memória (apenas durante esta sessão).
        # Elimina o popup repetitivo quando múltiplos scripts precisam de
        # acesso a rede. NUNCA é salvo em disco.
        self._credentials_cache = None
                # Tenta carregar credenciais salvas em disco (DPAPI)
        try:
            from core.credential_store import CredentialStore
            saved = CredentialStore.load()
            if saved:
                self._credentials_cache = {
                    "user": saved["user"],
                    "pass": saved["pass"],
                    "vnc_pass": saved.get("vnc_pass", saved["pass"]),
                }
        except Exception as e:
            from core.logger import get_logger
            get_logger(__name__).warning(f"Falha ao carregar credenciais salvas: {e}")

        # Pool único de execução remota compartilhado por TODAS as views.
        # N de threads = SARCC_MAX_THREADS (env) ou 12 (default).
        _max_threads = _get_max_threads(12)
        self.queue_manager = TaskQueueManager(max_threads=_max_threads)

        from core.logger import get_logger
        get_logger(__name__).info(
            f"TaskQueueManager inicializado com {_max_threads} thread(s)"
        )

        self.is_dark_theme = True
        self._setup_ui()
        self.apply_theme()  # Aciona o motor de temas na inicialização

    def _setup_ui(self):
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        
        main_layout = QHBoxLayout(self.main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- BARRA LATERAL (Sidebar) ---
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setObjectName("Sidebar")
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(10)
        
        # --- Cabeçalho: ícone + nome ---
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 0, 8, 0)
        header_layout.setSpacing(10)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon_path = resource_path("logo.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(
                36, 36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(36, 36)
        header_layout.addWidget(icon_label)

        self.title_label = QLabel("SARCC")
        self.title_label.setObjectName("MainTitle")
        header_layout.addWidget(self.title_label)

        sidebar_layout.addWidget(header_widget)
        sidebar_layout.addSpacing(20)
        
        self.btn_dashboard = QPushButton("Dashboard")
        self.btn_shell = QPushButton("Terminal Interativo")
        self.btn_sysman = QPushButton("Gerenciador do Sistema")
        self.btn_execution = QPushButton("Execução Remota")
        self.btn_software = QPushButton("Gestão de Softwares")
        self.btn_scheduler = QPushButton("Automação (Agendador)")
        self.btn_scripts = QPushButton("Gestor de Scripts")
        self.btn_history = QPushButton("Histórico de Logs")
        self.btn_help = QPushButton("Sobre & Documentação")
        
        self.menu_buttons = [self.btn_dashboard, self.btn_shell, self.btn_sysman, 
                             self.btn_execution, self.btn_software, self.btn_scheduler, 
                             self.btn_scripts, self.btn_history, self.btn_help]
        
        for i, btn in enumerate(self.menu_buttons):
            btn.setObjectName("MenuBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True) # Essencial para manter o botão marcado
            sidebar_layout.addWidget(btn)
            
        sidebar_layout.addStretch()

        self.btn_clear_creds = QPushButton("🔒 Esquecer senha")
        self.btn_clear_creds.setObjectName("MenuBtn")
        self.btn_clear_creds.setCursor(Qt.CursorShape.PointingHandCursor)

        # Tooltip com caminho real do arquivo de credenciais (DPAPI)
        from core.credential_store import CredentialStore
        self.btn_clear_creds.setToolTip(
            "Limpa a senha salva em memória e no disco.\n"
            f"Arquivo: {CredentialStore.location()}"
        )
        self.btn_clear_creds.clicked.connect(self._on_clear_creds_clicked)
        sidebar_layout.addWidget(self.btn_clear_creds)
        self.btn_theme_toggle = QPushButton("☀️ Tema Claro")
        self.btn_theme_toggle.setObjectName("MenuBtn")
        self.btn_theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme_toggle)
        
        main_layout.addWidget(self.sidebar)
        
        # --- ÁREA CENTRAL (Stacked Widget) ---
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)
        
        self.dashboard_view = DashboardView(main_window_ref=self)
        self.shell_view = ShellView(main_window_ref=self)
        self.sysman_view = SystemManagerView(main_window_ref=self)
        self.execution_view = ExecutionView(main_window_ref=self)
        self.software_view = SoftwareView(main_window_ref=self)
        self.scheduler_view = SchedulerView(main_window_ref=self)
        self.scripts_view = ScriptsView()
        self.history_view = HistoryView()
        self.help_view = HelpView(main_window_ref=self)
        
        self.stacked_widget.addWidget(self.dashboard_view) # 0
        self.stacked_widget.addWidget(self.shell_view)     # 1
        self.stacked_widget.addWidget(self.sysman_view)    # 2
        self.stacked_widget.addWidget(self.execution_view) # 3
        self.stacked_widget.addWidget(self.software_view)  # 4
        self.stacked_widget.addWidget(self.scheduler_view) # 5
        self.stacked_widget.addWidget(self.scripts_view)   # 6
        self.stacked_widget.addWidget(self.history_view)   # 7
        self.stacked_widget.addWidget(self.help_view)      # 8

        # Conexões seguras usando argumento 'checked' para evitar KeyboardInterrupt/TypeError
        self.btn_dashboard.clicked.connect(lambda checked, i=0: self.set_active_menu(i))
        self.btn_shell.clicked.connect(lambda checked, i=1: self.set_active_menu(i))
        self.btn_sysman.clicked.connect(lambda checked, i=2: self.set_active_menu(i))
        self.btn_execution.clicked.connect(lambda checked, i=3: self.set_active_menu(i))
        self.btn_software.clicked.connect(lambda checked, i=4: self.set_active_menu(i))
        self.btn_scheduler.clicked.connect(lambda checked, i=5: self.set_active_menu(i))
        self.btn_scripts.clicked.connect(lambda checked, i=6: self.set_active_menu(i))
        self.btn_history.clicked.connect(lambda checked, i=7: self.set_active_menu(i))
        self.btn_help.clicked.connect(lambda checked, i=8: self.set_active_menu(i))
        
        self.set_active_menu(0)

    def _on_clear_creds_clicked(self):
        from core.credential_store import CredentialStore
        had_memory = self._credentials_cache is not None
        had_disk = CredentialStore.exists()

        if not had_memory and not had_disk:
            QMessageBox.information(self, "Cache", "Nenhuma senha salva para esquecer.")
            return

        self.clear_cached_credentials()
        CredentialStore.clear()
        QMessageBox.information(
            self,
            "Senha Esquecida",
            "A senha em memória e no disco foi removida.\n"
            "Você será solicitado novamente na próxima execução."
        )
        
    def set_active_menu(self, index):
        for i, btn in enumerate(self.menu_buttons):
            btn.setChecked(i == index)
        self.stacked_widget.setCurrentIndex(index)

    def toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        self.apply_theme()

        # Recarrega o changelog com as novas cores (o QTextDocument não segue QSS)
        try:
            if hasattr(self, "help_view") and hasattr(self.help_view, "reload_changelog"):
                self.help_view.reload_changelog()
        except Exception as e:
            from core.logger import get_logger
            get_logger(__name__).debug(f"Falha ao recarregar changelog: {e}")

    def apply_theme(self):
        theme = "dark" if self.is_dark_theme else "light"
        primary_blue = "#4a90e2"
        
        if self.is_dark_theme:
            self.btn_theme_toggle.setText("☀️ Tema Claro")
            sidebar_bg = "#161616"
            border_color = "#333333"
            group_border = "#444444"
            text_menu = "#e0e0e0"
            hover_menu = "rgba(74, 144, 226, 0.15)"
            input_bg = "#1e1e1e"
        else:
            self.btn_theme_toggle.setText("🌙 Tema Escuro")
            sidebar_bg = "#f0f2f5" 
            border_color = "#d1d5db"
            group_border = "#c2c7d0"
            text_menu = "#202124"
            hover_menu = "rgba(74, 144, 226, 0.2)"
            input_bg = "#ffffff"

        # Correção visual robusta e padronização global de inputs
        custom_css = f"""
        QWidget#Sidebar {{ background-color: {sidebar_bg}; border-right: 1px solid {border_color}; }}
        QLabel#MainTitle {{ font-size: 22px; font-weight: bold; color: {primary_blue}; }}
        QPushButton#MenuBtn {{ text-align: left; padding: 12px 15px; font-size: 14px; font-weight: 500; background-color: transparent; border: none; border-radius: 6px; color: {text_menu}; }}
        QPushButton#MenuBtn:hover {{ background-color: {hover_menu}; color: {primary_blue}; }}
        QPushButton#MenuBtn:checked {{ background-color: {hover_menu}; color: {primary_blue}; font-weight: bold; border-left: 4px solid {primary_blue}; border-radius: 4px; }}
        QGroupBox {{ border: 1px solid {group_border}; border-radius: 6px; margin-top: 15px; padding-top: 15px; font-weight: bold; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 15px; padding: 0 5px; color: {primary_blue}; }}
        QHeaderView::section {{ font-weight: bold; color: {primary_blue}; }}
        
        /* Padronização de Caixas de Texto e Combobox em todas as telas */
        QLineEdit, QComboBox {{ 
            min-height: 32px; 
            max-height: 32px;
            padding: 0 10px; 
            background-color: {input_bg}; 
            color: {text_menu}; 
            border: 1px solid {border_color}; 
            border-radius: 4px; 
        }}
        
        QTextEdit {{ background-color: {input_bg}; color: {text_menu}; border: 1px solid {border_color}; border-radius: 4px; }}
        QComboBox QAbstractItemView {{ background-color: {input_bg}; color: {text_menu}; border: 1px solid {border_color}; selection-background-color: {primary_blue}; selection-color: #ffffff; }}

        /* QTextBrowser (usado no HelpView/Novidades) — herda o tema */
        QTextBrowser {{
            background-color: {input_bg};
            color: {text_menu};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 12px;
            font-size: 14px;
            selection-background-color: {primary_blue};
            selection-color: #ffffff;
        }}
        """
        
        base_sheet = qdarktheme.load_stylesheet(theme)
        QApplication.instance().setStyleSheet(base_sheet + custom_css)
        
        titulos_conhecidos = [
            "Dashboard & Diagnóstico Operacional", 
            "Terminal Interativo Remoto (PowerShell)",
            "Gerenciador de Processos e Serviços do Sistema",
            "Central de Comando Remoto",
            "Gestão e Inventário de Softwares do Endpoint",
            "Agendador de Tarefas Remotas (Automação)",
            "Gestor de Scripts Automáticos",
            "Histórico de Execuções",
            "Lixeira (Logs Excluídos)"
        ]
        
        for label in self.findChildren(QLabel):
            if label.text() in titulos_conhecidos or "24px" in label.styleSheet():
                label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {primary_blue}; margin-bottom: 10px;")
    def get_cached_credentials(self):
        """Retorna dict {user, pass, vnc_pass} ou None."""
        return self._credentials_cache

    def set_cached_credentials(self, user: str, password: str):
        """Armazena credenciais em memória para a sessão atual."""
        self._credentials_cache = {
            "user": user,
            "pass": password,
            "vnc_pass": password,
        }

    def clear_cached_credentials(self):
        """Limpa o cache. Chamado pelo botão da sidebar."""
        self._credentials_cache = None

    def closeEvent(self, event):
        """Encerra os workers do TaskQueueManager ao fechar a janela."""
        try:
            self.queue_manager.shutdown()
        except Exception as e:
            # Se algo der errado, ainda deixa a janela fechar
            from core.logger import get_logger
            get_logger(__name__).warning(f"Falha no shutdown do TaskQueueManager: {e}")
        super().closeEvent(event)