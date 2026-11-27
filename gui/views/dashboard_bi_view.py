from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

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

        header_layout.addWidget(QLabel("Período:"))
        self.cmb_period = QComboBox()
        self.cmb_period.addItem("Todo o período", 0)
        self.cmb_period.addItem("Hoje", 1)
        self.cmb_period.addItem("Últimos 7 dias", 7)
        self.cmb_period.addItem("Últimos 30 dias", 30)
        self.cmb_period.setFixedHeight(32)
        self.cmb_period.setFixedWidth(150)
        self.cmb_period.currentIndexChanged.connect(self.refresh_data)
        header_layout.addWidget(self.cmb_period)

        self.btn_refresh = QPushButton("↻ Atualizar")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("background-color: #666; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.refresh_data)
        header_layout.addWidget(self.btn_refresh)

        layout.addLayout(header_layout)

        # Cards de KPI (Totais)
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(15)

        self.lbl_total_exec = self._create_kpi_card("Total de Execuções", "0", "#4a90e2")
        self.lbl_taxa_sucesso = self._create_kpi_card("Taxa de Sucesso", "0%", "#4CAF50")
        self.lbl_total_maquinas = self._create_kpi_card("Máquinas Atendidas", "0", "#f0ad4e")

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
        return card # Retorna o widget, mas precisamos do Label interno, então faremos um hack rápido

    def refresh_data(self):
        days = self.cmb_period.currentData()

        # 1. Métricas de Status
        metrics = self.repo.get_bi_metrics(days)
        self.donut_chart.set_data(metrics["SUCESSO"], metrics["ALERTA"], metrics["FALHA"])

        total = sum(metrics.values())
        sucesso = metrics["SUCESSO"]
        taxa = (sucesso / total * 100) if total > 0 else 0

        # 2. Top Scripts
        top_scripts = self.repo.get_top_scripts(days)
        self.bar_chart.set_data(top_scripts)

        # 3. Contador de máquinas
        maquinas = self.repo.get_unique_machines_count(days)

        # Atualiza os KPIs (acessando o QLabel dentro do layout do QGroupBox)
        def update_card(card, val_str):
            lbl = card.layout().itemAt(0).widget()
            lbl.setText(val_str)

        update_card(self.lbl_total_exec, str(total))
        update_card(self.lbl_taxa_sucesso, f"{taxa:.1f}%")
        update_card(self.lbl_total_maquinas, str(maquinas))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_data()
