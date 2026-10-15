import os
import re
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGroupBox, QScrollArea, QPushButton, QApplication,
                             QMessageBox, QTabWidget, QTextBrowser)
from PyQt6.QtCore import Qt
from gui.views.base_view import BaseView
from core.resources import resource_path
from core.logger import get_logger

log = get_logger(__name__)


APP_VERSION = "2.7.0"


class HelpView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Sobre & Documentação do Sistema")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        main_layout.addWidget(title)

        # --- Sistema de abas ---
        tabs = QTabWidget()
        tabs.addTab(self._build_about_tab(), "📖 Sobre & Firewall")
        tabs.addTab(self._build_changelog_tab(), "🆕 Novidades")
        main_layout.addWidget(tabs)

    # ------------------------------------------------------------------
    # ABA 1 — Sobre + Requisitos de Firewall
    # ------------------------------------------------------------------
    def _build_about_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(20)

        # 1. Informações de Autoria
        group_about = QGroupBox("Autoria e Licenciamento")
        layout_about = QVBoxLayout(group_about)
        layout_about.setContentsMargins(15, 20, 15, 15)

        lbl_about = QLabel(
            f"<b>SARCC - System Administration & Remote Command Center v{APP_VERSION}</b><br><br>"
            "Plataforma centralizada para gestão de endpoints, execução de scripts, automação de tarefas "
            "e telemetria em tempo real via arquitetura Agentless (WinRM/WMI).<br><br>"
            "<b>Desenvolvido por:</b> Welber Sauan dos Santos Souza<br>"
            "<b>Suporte e Contato:</b> <i>Welber.sauan123@gmail.com</i><br><br>"
            "<i>Este software é de uso restrito da equipe de Tecnologia da Informação. "
            "A reprodução, distribuição ou modificação não autorizada sem o consentimento "
            "do desenvolvedor original é estritamente proibida.</i>"
        )
        lbl_about.setWordWrap(True)
        lbl_about.setStyleSheet("font-size: 14px; line-height: 1.5;")
        lbl_about.setTextFormat(Qt.TextFormat.RichText)
        layout_about.addWidget(lbl_about)
        layout.addWidget(group_about)

        # 2. Requisitos de Firewall
        group_fw = QGroupBox("Requisitos de Infraestrutura (Regras de Firewall e Roteamento)")
        layout_fw = QVBoxLayout(group_fw)
        layout_fw.setContentsMargins(15, 20, 15, 15)

        self.firewall_text = (
            "Para garantir o pleno funcionamento do parque de funcionalidades e da arquitetura de "
            "gerenciamento remoto do SARCC, os seguintes serviços e portas devem estar liberados "
            "nos firewalls de rede e do Windows (Inbound/Outbound):<br><br>"

            "<b>• WinRM (Gerenciamento Remoto, Scripts e WMI)</b><br>"
            "<b>Portas:</b> 5985 (HTTP) e 5986 (HTTPS) | <b>Protocolo:</b> TCP<br>"
            "<b>Uso:</b> Canal principal do SARCC. Utilizado para conectar às estações via PowerShell "
            "Remoting, disparar scripts de deploy, coletar telemetria e gerenciar serviços.<br>"
            "<i>Nota de Segurança: Todas as consultas WMI/CIM são encapsuladas e processadas localmente "
            "através deste túnel, dispensando a liberação de portas DCOM/RPC vulneráveis (TCP 135) na rede.</i><br><br>"

            "<b>• SMB (Acesso a Compartilhamentos de Rede)</b><br>"
            "<b>Porta:</b> 445 | <b>Protocolo:</b> TCP<br>"
            "<b>Uso:</b> Necessária para que os scripts executados nas máquinas alvo consigam mapear a "
            "pasta compartilhada da TI (\\\\hul-vp-imagem-cc\\netshared) para puxar os instaladores "
            "(.exe/.msi), arquivos de configuração e chaves de segurança.<br><br>"

            "<b>• UltraVNC Server (Visualização de Tela e Suporte Remoto)</b><br>"
            "<b>Porta:</b> 5900 | <b>Protocolo:</b> TCP<br>"
            "<b>Uso:</b> Utilizada diretamente pelo VNC Viewer do operador de TI para estabelecer a "
            "conexão gráfica de controle remoto com a máquina do usuário final (e 5800 para acesso via Java/Web).<br><br>"

            "<b>• Wake-on-LAN & ICMP (Descoberta e Ativação de Hosts)</b><br>"
            "<b>Portas:</b> 9 | <b>Protocolo:</b> UDP & ICMP<br>"
            "<b>Uso:</b> Envio de Magic Packets para ligar máquinas desligadas e pacotes de Ping "
            "para checagem de status de conectividade no dashboard.<br><br>"

            "<b>• Remote Desktop Protocol - RDP (Microsoft)</b><br>"
            "<b>Porta:</b> 3389 | <b>Protocolo:</b> TCP e UDP<br>"
            "<b>Uso:</b> Utilizado para conexões nativas de área de trabalho remota. Para acessar "
            "estações de outras VLANs, o tráfego precisa ser permitido entre as sub-redes e nas GPOs.<br><br>"

            "<b>• AnyDesk (Acesso Nuvem)</b><br>"
            "<b>Portas:</b> 443 (HTTPS) e 6568 | <b>Protocolo:</b> TCP (Outbound)<br>"
            "<b>Uso:</b> Arquitetura baseada em nuvem operando de forma outbound. As estações não "
            "precisam de portas de entrada abertas, mas o firewall da instituição precisa permitir "
            "a saída para os servidores de revezamento (rendezvous servers)."
        )

        lbl_fw = QLabel(self.firewall_text)
        lbl_fw.setWordWrap(True)
        lbl_fw.setStyleSheet("font-size: 14px; line-height: 1.6;")
        lbl_fw.setTextFormat(Qt.TextFormat.RichText)
        layout_fw.addWidget(lbl_fw)

        btn_copy = QPushButton("📋 Copiar Requisitos de Firewall para a Área de Transferência")
        btn_copy.setFixedHeight(32)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(
            "background-color: #2a7de1; color: white; padding: 0 15px; "
            "font-weight: bold; border-radius: 4px; margin-top: 10px;"
        )
        btn_copy.clicked.connect(self.copy_to_clipboard)
        layout_fw.addWidget(btn_copy)

        layout.addWidget(group_fw)
        layout.addStretch()

        # Envolve em scroll para telas pequenas
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # ABA 2 — Novidades / Changelog
    # ------------------------------------------------------------------
    def _build_changelog_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)   # ← respiro em toda a aba
        layout.setSpacing(12)

        # Cabeçalho com versão atual
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)       # ← respiro vertical
        header.setSpacing(12)

        version_badge = QLabel(f"  v{APP_VERSION}  ")
        version_badge.setStyleSheet(
            "background-color: #1e8a5e; color: white; font-weight: bold; "
            "border-radius: 10px; padding: 4px 10px; font-size: 13px;"
        )
        header.addWidget(version_badge)

        lbl_titulo = QLabel("<b>O que há de novo nesta versão</b>")
        lbl_titulo.setStyleSheet("font-size: 14px;")
        header.addWidget(lbl_titulo)
        header.addStretch()

        btn_refresh = QPushButton("↻ Recarregar")
        btn_refresh.setFixedHeight(28)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(
            "padding: 0 15px; background-color: #666; color: white; "
            "font-weight: bold; border-radius: 4px;"
        )
        btn_refresh.clicked.connect(self.reload_changelog)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        # Visualizador de Markdown — estilos aplicados dinamicamente
        # por reload_changelog() conforme o tema atual.
        self.txt_changelog = QTextBrowser()
        self.txt_changelog.setOpenExternalLinks(True)
        self.txt_changelog.setFrameShape(QTextBrowser.Shape.NoFrame)
        layout.addWidget(self.txt_changelog)

        # Popula na primeira exibição
        self.reload_changelog()
        return container

    def reload_changelog(self):
        """Lê o CHANGELOG.md, renderiza em Markdown, e força cores temáticas."""
        path = resource_path("CHANGELOG.md")
        if not os.path.exists(path):
            self.txt_changelog.setPlainText(
                f"⚠️ Arquivo CHANGELOG.md não encontrado em:\n{path}"
            )
            log.warning(f"CHANGELOG.md não encontrado em {path}")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                conteudo = f.read()

                        # Detecta tema atual
            is_dark = getattr(self.main_window, "is_dark_theme", True)
            ACCENT = "#4a90e2"

            # Pega a cor de fundo REAL do container pai (QTabWidget pane)
            # — garante match perfeito com o tema atual, sem hardcode.
            parent_widget = self.txt_changelog.parent()
            if parent_widget is not None:
                body_bg = parent_widget.palette().color(QPalette.ColorRole.Window).name()
            else:
                body_bg = "#1e1e1e" if is_dark else "#ffffff"

            if is_dark:
                text_color = "#e0e0e0"
                heading_color = ACCENT
                link_color = ACCENT
                code_bg = "#2a2a2a"
                code_color = "#f1fa8c"
                hr_color = "#444444"
            else:
                text_color = "#202124"
                heading_color = ACCENT
                link_color = ACCENT
                code_bg = "#f0f2f5"
                code_color = "#c7254e"
                hr_color = "#d1d5db"

            # 1) CSS no documento — incluindo background explícito
            self.txt_changelog.document().setDefaultStyleSheet(f"""
                body {{ background-color: {body_bg}; color: {text_color}; font-size: 15px; }}
                p, li {{ color: {text_color}; }}
                h1, h2, h3, h4 {{ color: {heading_color}; font-weight: bold; }}
                h1 {{ border-bottom: 1px solid {hr_color}; padding-bottom: 4px; font-size: 24px; }}
                h2 {{ font-size: 20px; }}
                h3 {{ font-size: 17px; }}
                code {{ background-color: {code_bg}; color: {code_color};
                        padding: 1px 5px; border-radius: 3px;
                        font-family: Consolas, monospace; }}
                pre {{ background-color: {code_bg}; color: {code_color};
                       padding: 8px; border-radius: 4px; }}
                hr {{ border: none; border-top: 1px solid {hr_color}; }}
                blockquote {{ color: #888; border-left: 3px solid {hr_color};
                              padding-left: 10px; margin-left: 0; }}
            """)

            # 2) Aplica CSS ao widget E ao viewport interno
            #    (QTextBrowser herda de QAbstractScrollArea — o viewport
            #    interno não segue o QSS do widget pai; precisa ser
            #    estilizado separadamente)
            self.txt_changelog.setStyleSheet(
                f"QTextBrowser {{ "
                f"  background-color: {body_bg}; "
                f"  color: {text_color}; "
                f"  border: 1px solid {hr_color}; "
                f"  border-radius: 6px; "
                f"  padding: 12px; "
                f"}}"
            )
            # Alinha o viewport (área de rolagem interna) com o mesmo fundo
            self.txt_changelog.viewport().setStyleSheet(
                f"background-color: {body_bg};"
            )
            self.txt_changelog.viewport().setAutoFillBackground(True)

            # 3) Renderiza Markdown
            self.txt_changelog.setMarkdown(conteudo)

            # 4) Força a cor dos links
            self._force_link_color(link_color)

            log.info(
                f"Changelog carregado ({len(conteudo)} chars, "
                f"tema {'dark' if is_dark else 'light'})"
            )
        except Exception as e:
            self.txt_changelog.setPlainText(f"⚠️ Erro ao ler CHANGELOG.md:\n{e}")
            log.error(f"Falha ao ler CHANGELOG.md: {e}", exc_info=True)

    def _force_link_color(self, color_hex: str):
        """Força a cor de todos os links (<a>) no QTextDocument.

        Por que isso é necessário?
        O `setMarkdown()` do Qt aplica um formato de caractere embutido
        (via QTextCharFormat) em cada <a> com a cor padrão azul escuro do
        sistema. Nem QSS, nem QPalette, nem CSS no HTML sobrescrevem esse
        formato. A única forma é iterar fragmento por fragmento e
        reescrever o foreground diretamente.
        """
        doc = self.txt_changelog.document()
        color = QColor(color_hex)
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isAnchor():
                    fmt = frag.charFormat()
                    new_fmt = QTextCharFormat(fmt)
                    new_fmt.setForeground(color)
                    new_fmt.setAnchor(fmt.isAnchor())
                    new_fmt.setAnchorHref(fmt.anchorHref())

                    cursor = QTextCursor(doc)
                    cursor.setPosition(frag.position())
                    cursor.setPosition(
                        frag.position() + frag.length(),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    cursor.setCharFormat(new_fmt)
                it += 1
            block = block.next()

    def copy_to_clipboard(self):
        clean_text = (
            self.firewall_text
            .replace("<b>", "").replace("</b>", "")
            .replace("<br>", "\n")
            .replace("<i>", "").replace("</i>", "")
        )
        QApplication.clipboard().setText(clean_text)
        QMessageBox.information(
            self, "Copiado",
            "A documentação técnica foi copiada para a área de transferência."
        )
    def showEvent(self, event):
        """Reaplica o Markdown sempre que a aba ganha foco.

        Isso garante que ao trocar o tema, o conteúdo seja re-renderizado
        com as cores novas (o widget é restilizado pelo app_window, mas o
        documento interno precisa ser re-aplicado).
        """
        super().showEvent(event)
        if hasattr(self, "txt_changelog"):
            self.reload_changelog()