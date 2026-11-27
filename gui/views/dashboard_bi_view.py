from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QCompleter, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from gui.views.base_view import BaseView
from gui.widgets.bi_charts import BarChartWidget, DonutChartWidget
from infrastructure.repositories.execution_repository import ExecutionRepository


class DashboardBIView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.repo = ExecutionRepository()
        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Cabeçalho
        header_layout = QHBoxLayout()
        title = QLabel("Painel de Indicadores (BI)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Filtro de Período Padronizado
        header_layout.addWidget(QLabel("Período:"))
        self.cmb_period = QComboBox()
        self.cmb_period.setFixedHeight(32)
        self.cmb_period.addItems([
            "Todo o período",
            "Hoje",
            "Últimos 7 dias",
            "Últimos 30 dias"
        ])
        self.cmb_period.currentIndexChanged.connect(self.refresh_data)
        header_layout.addWidget(self.cmb_period)

        # Filtro por Alvo com Autocomplete
        header_layout.addWidget(QLabel("Filtrar por Alvo:"))
        self.inp_target_filter = QLineEdit()
        self.inp_target_filter.setFixedHeight(32)
        self.inp_target_filter.setPlaceholderText("Ex: HUL-WK-... ou 192.168....")
        self.inp_target_filter.setFixedWidth(250)
        self.inp_target_filter.textChanged.connect(self.refresh_data)

        self.target_completer = QCompleter([])
        self.target_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.target_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.inp_target_filter.setCompleter(self.target_completer)

        header_layout.addWidget(self.inp_target_filter)

        self.btn_refresh = QPushButton("↻ Atualizar")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("background-color: #666; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.refresh_data)
        header_layout.addWidget(self.btn_refresh)

        layout.addLayout(header_layout)

        # Cards de KPI
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(15)

        self.lbl_total_exec, self.lbl_val_total_exec = self._create_kpi_card("Total de Execuções", "0", "#4a90e2")
        self.lbl_taxa_sucesso, self.lbl_val_taxa_sucesso = self._create_kpi_card("Taxa de Sucesso", "0%", "#4CAF50")
        self.lbl_total_maquinas, self.lbl_val_total_maquinas = self._create_kpi_card("Máquinas Atendidas", "0", "#f0ad4e")

        kpi_layout.addWidget(self.lbl_total_exec)
        kpi_layout.addWidget(self.lbl_taxa_sucesso)
        kpi_layout.addWidget(self.lbl_total_maquinas)
        layout.addLayout(kpi_layout)

        # Área de Gráficos
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(15)

        self.donut_chart = DonutChartWidget()
        charts_layout.addWidget(self.donut_chart, stretch=1)

        self.bar_chart = BarChartWidget()
        charts_layout.addWidget(self.bar_chart, stretch=1)

        layout.addLayout(charts_layout, stretch=1)

    def _create_kpi_card(self, title, value, color):
        card = QGroupBox(title)
        card.setStyleSheet("QGroupBox { border: 1px solid #444; border-radius: 6px; font-weight: bold; color: #aaa; }")
        card_layout = QVBoxLayout(card)

        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {color};")
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lbl_val)

        return card, lbl_val

    def refresh_data(self):
        # Atualiza as sugestões de alvos no autocomplete
        targets = self.repo.get_unique_targets()
        self.target_completer.model().setStringList(targets)

        # Traduz a seleção do combo para dias (usado pelo SQLite)
        period_text = self.cmb_period.currentText()
        if period_text == "Todo o período":
            days = 0
        elif period_text == "Hoje":
            days = 1
        elif period_text == "Últimos 7 dias":
            days = 7
        elif period_text == "Últimos 30 dias":
            days = 30
        else:
            days = 0

        target_filter = self.inp_target_filter.text().strip()

        # 1. Métricas de Status
        metrics = self.repo.get_bi_metrics(days, target_filter)
        self.donut_chart.set_data(metrics["SUCESSO"], metrics["ALERTA"], metrics["FALHA"])

        total = sum(metrics.values())
        sucesso = metrics["SUCESSO"]
        taxa = (sucesso / total * 100) if total > 0 else 0

        # 2. Top Scripts
        top_scripts = self.repo.get_top_scripts(days, target_filter)
        self.bar_chart.set_data(top_scripts)

        # 3. Contador de máquinas
        maquinas = self.repo.get_unique_machines_count(days, target_filter)

        # Atualiza os valores nos Cards de KPI
        self.lbl_val_total_exec.setText(str(total))
        self.lbl_val_taxa_sucesso.setText(f"{taxa:.1f}%")
        self.lbl_val_total_maquinas.setText(str(maquinas))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_data()
