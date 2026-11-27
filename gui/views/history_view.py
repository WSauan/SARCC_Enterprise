import json
from datetime import datetime, timedelta

from PyQt6.QtCore import QDate, QDateTime, Qt, QTime
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.enums import ExecutionStatus
from core.text_utils import fix_mojibake
from domain.services.audit_service import AuditService, extract_json_from_result, format_duration
from gui.views.base_view import sanitize_filename
from infrastructure.repositories.execution_repository import ExecutionRepository


class LogTreeWidgetItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column in [0, 10]:
            column = 3

        if column == 2:
            try:
                return int(self.text(column)) < int(other.text(column))
            except ValueError:
                return self.text(column) < other.text(column)

        if column == 5:
            val1 = self.data(5, Qt.ItemDataRole.UserRole)
            val2 = other.data(5, Qt.ItemDataRole.UserRole)
            v1 = float(val1) if val1 is not None else -1.0
            v2 = float(val2) if val2 is not None else -1.0
            return v1 < v2

        return self.text(column) < other.text(column)


class JsonDetailDialog(QDialog):
    def __init__(self, json_string, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalhes da Execução (JSON)")
        self.resize(720, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 13px; "
            "background-color: #1e1e1e; color: #d4d4d4; padding: 10px; "
            "border-radius: 4px; border: 1px solid #444;"
        )

        parsed_json = extract_json_from_result(json_string)
        if parsed_json is not None:
            formatted_json = json.dumps(parsed_json, indent=4, ensure_ascii=False)
            text_edit.setPlainText(fix_mojibake(formatted_json))
        else:
            text_edit.setPlainText(fix_mojibake(str(json_string or "")))

        layout.addWidget(text_edit)

        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("background-color: #4a90e2; color: white; font-weight: bold; border-radius: 4px; padding: 0 20px;")
        btn_close.clicked.connect(self.close)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)


class HistoryView(QWidget):
    def __init__(self, main_window_ref=None):
        super().__init__()
        self.main_window = main_window_ref
        self.repo = ExecutionRepository()
        self.audit_service = AuditService(self.repo)
        self.view_mode = "ativos"
        self.sort_col = 3
        self.sort_order = Qt.SortOrder.DescendingOrder
        self._last_clicked_row = -1 # <--- NOVO: Variável para controlar o Shift+Click
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("Histórico e Auditoria por Máquina")
        self.lbl_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()

        self.btn_export = QPushButton("📄 Exportar Relatório")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setStyleSheet("background-color: #1e8a5e; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_export.clicked.connect(self.exportar_txt)
        header_layout.addWidget(self.btn_export)

        self.btn_batch_res = QPushButton("↩ Restaurar")
        self.btn_batch_res.setFixedHeight(32)
        self.btn_batch_res.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_batch_res.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_batch_res.clicked.connect(self.batch_restore)
        self.btn_batch_res.setVisible(False)
        header_layout.addWidget(self.btn_batch_res)

        self.btn_batch_del = QPushButton("🗑️ Excluir Selecionados")
        self.btn_batch_del.setFixedHeight(32)
        self.btn_batch_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_batch_del.setStyleSheet("background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_batch_del.clicked.connect(self.batch_delete)
        header_layout.addWidget(self.btn_batch_del)

        self.btn_empty_trash = QPushButton("💥 Esvaziar Lixeira")
        self.btn_empty_trash.setFixedHeight(32)
        self.btn_empty_trash.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_empty_trash.setStyleSheet("background-color: #000000; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px; border: 1px solid #d9534f;")
        self.btn_empty_trash.clicked.connect(self.empty_trash)
        self.btn_empty_trash.setVisible(False)
        header_layout.addWidget(self.btn_empty_trash)

        self.btn_toggle_view = QPushButton("🗑️ Ver Lixeira")
        self.btn_toggle_view.setFixedHeight(32)
        self.btn_toggle_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_view.setStyleSheet("background-color: #f0ad4e; color: black; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_toggle_view.clicked.connect(self.toggle_view)
        header_layout.addWidget(self.btn_toggle_view)

        self.btn_refresh = QPushButton("↻ Atualizar")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("background-color: #666; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.load_logs)
        header_layout.addWidget(self.btn_refresh)

        layout.addLayout(header_layout)

        filter_group = QGroupBox("Filtros de Pesquisa")
        control_bar = QHBoxLayout(filter_group)
        control_bar.setContentsMargins(15, 20, 15, 15)
        control_bar.setSpacing(10)

        self.chk_date_filter = QCheckBox("Data:")
        self.chk_date_filter.setFixedHeight(32)
        self.chk_date_filter.setStyleSheet("font-weight: bold; color: #4a90e2;")
        self.chk_date_filter.stateChanged.connect(self.apply_filters)
        control_bar.addWidget(self.chk_date_filter)

        self.cmb_date_mode = QComboBox()
        self.cmb_date_mode.setFixedHeight(32)
        self.cmb_date_mode.addItems([
            "Data exata",
            "Intervalo de data/hora (De / Até)",
            "Últimas 2 horas",
            "Últimas 12 horas",
            "Últimas 24 horas",
            "Últimos 7 dias",
            "Últimos 30 dias"
        ])
        self.cmb_date_mode.setEnabled(False)
        self.cmb_date_mode.currentTextChanged.connect(self._on_date_mode_changed)
        control_bar.addWidget(self.cmb_date_mode)

        self.dt_filter = QDateEdit(QDate.currentDate())
        self.dt_filter.setFixedHeight(32)
        self.dt_filter.setCalendarPopup(True)
        self.dt_filter.setDisplayFormat("dd/MM/yyyy")
        self.dt_filter.setStyleSheet("padding: 0 6px;")
        self.dt_filter.setEnabled(False)
        cal = self.dt_filter.calendarWidget()
        cal.setMinimumWidth(320)
        cal.setMinimumHeight(240)
        self.dt_filter.dateChanged.connect(self.apply_filters)
        control_bar.addWidget(self.dt_filter)

        self.lbl_from = QLabel("De:")
        self.lbl_from.setVisible(False)
        control_bar.addWidget(self.lbl_from)

        self.dt_filter_start = QDateTimeEdit(QDateTime(QDate.currentDate(), QTime(0, 0)))
        self.dt_filter_start.setFixedHeight(32)
        self.dt_filter_start.setCalendarPopup(True)
        self.dt_filter_start.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.dt_filter_start.setStyleSheet("padding: 0 6px;")
        self.dt_filter_start.setEnabled(False)
        self.dt_filter_start.setVisible(False)
        cal_start = self.dt_filter_start.calendarWidget()
        cal_start.setMinimumWidth(320)
        cal_start.setMinimumHeight(240)
        self.dt_filter_start.dateTimeChanged.connect(self.apply_filters)
        control_bar.addWidget(self.dt_filter_start)

        self.lbl_to = QLabel("Até:")
        self.lbl_to.setVisible(False)
        control_bar.addWidget(self.lbl_to)

        self.dt_filter_end = QDateTimeEdit(QDateTime(QDate.currentDate(), QTime(23, 59)))
        self.dt_filter_end.setFixedHeight(32)
        self.dt_filter_end.setCalendarPopup(True)
        self.dt_filter_end.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.dt_filter_end.setStyleSheet("padding: 0 6px;")
        self.dt_filter_end.setEnabled(False)
        self.dt_filter_end.setVisible(False)
        cal_end = self.dt_filter_end.calendarWidget()
        cal_end.setMinimumWidth(320)
        cal_end.setMinimumHeight(240)
        self.dt_filter_end.dateTimeChanged.connect(self.apply_filters)
        control_bar.addWidget(self.dt_filter_end)

        self.chk_date_filter.toggled.connect(self._on_date_filter_toggled)

        control_bar.addSpacing(10)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.setFixedHeight(32)
        self.cmb_filter_status.addItems([
            "Todos os Status",
            ExecutionStatus.SUCCESS.value,
            ExecutionStatus.ERROR.value,
            ExecutionStatus.WARNING.value,
            ExecutionStatus.PENDING.value
        ])
        self.cmb_filter_status.setStyleSheet("padding: 0 10px; font-weight: bold;")
        self.cmb_filter_status.currentTextChanged.connect(self.apply_filters)
        control_bar.addWidget(self.cmb_filter_status)

        self.inp_search = QLineEdit()
        self.inp_search.setFixedHeight(32)
        self.inp_search.setPlaceholderText("🔍 Buscar livre em texto...")
        self.inp_search.setStyleSheet("padding: 0 10px; font-size: 13px;")
        self.inp_search.textChanged.connect(self.apply_filters)
        control_bar.addWidget(self.inp_search, stretch=1)

        layout.addWidget(filter_group)

        selection_bar = QHBoxLayout()
        selection_bar.setContentsMargins(6, 0, 0, 0)
        self.chk_select_all = QCheckBox("Selecionar Todos (Visíveis)")
        self.chk_select_all.setFixedHeight(24)
        self.chk_select_all.setStyleSheet("font-weight: bold; color: #4a90e2;")
        self.chk_select_all.stateChanged.connect(self.toggle_select_all)
        selection_bar.addWidget(self.chk_select_all)

        selection_bar.addStretch()

        selection_bar.addWidget(QLabel("Exibir:"))
        self.cmb_limit = QComboBox()
        self.cmb_limit.setFixedHeight(24)
        self.cmb_limit.addItems(["10", "20", "50", "100", "Todos"])
        self.cmb_limit.setCurrentText("50")
        self.cmb_limit.setStyleSheet("padding: 0 5px;")
        self.cmb_limit.currentTextChanged.connect(self.load_logs)
        selection_bar.addWidget(self.cmb_limit)

        layout.addLayout(selection_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "[✓]", "Alvo (Computador)", "ID", "Início", "Fim", "Tempo",
            "Módulo", "Ação / Script", "Técnico", "Status", "Ações"
        ])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSortingEnabled(True)
        self.tree.setRootIsDecorated(False)

        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 38)
        header.resizeSection(1, 180)
        header.resizeSection(2, 50)
        header.resizeSection(3, 140)
        header.resizeSection(4, 140)
        header.resizeSection(5, 80)
        header.resizeSection(6, 120)
        header.resizeSection(7, 180)
        header.resizeSection(8, 100)
        header.resizeSection(9, 100)
        header.setStretchLastSection(True)

        self.tree.header().sectionClicked.connect(self.on_header_clicked)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemClicked.connect(self.on_item_clicked) # <--- NOVO: Intercepta o clique na linha
        layout.addWidget(self.tree)

    def on_item_clicked(self, item, column):
        """Lógica para Shift+Click no Checkbox"""
        current_row = self.tree.indexOfTopLevelItem(item)

        # O Qt não expõe o estado do Shift diretamente no evento itemClicked em todas as versões,
        # então verificamos via QApplication
        modifiers = QApplication.keyboardModifiers()

        # 1. Se for Shift+Click e já houver uma linha anterior clicada
        if modifiers == Qt.KeyboardModifier.ShiftModifier and self._last_clicked_row != -1:
            start_row = min(self._last_clicked_row, current_row)
            end_row = max(self._last_clicked_row, current_row)

            # Pega o estado da linha onde o Shift+Click começou
            start_item = self.tree.topLevelItem(self._last_clicked_row)
            state_to_apply = start_item.checkState(0)

            # Aplica o mesmo estado para todas as linhas no intervalo
            for r in range(start_row, end_row + 1):
                row_item = self.tree.topLevelItem(r)
                if row_item and not row_item.isHidden():
                    row_item.setCheckState(0, state_to_apply)
        else:
            # 2. Clique normal (sem shift): Alterna o checkbox da linha atual
            current_state = item.checkState(0)
            new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(0, new_state)

        # 3. Atualiza a última linha clicada (para o próximo Shift+Click)
        self._last_clicked_row = current_row

    def _on_date_filter_toggled(self, enabled: bool):
        self.cmb_date_mode.setEnabled(enabled)
        self._on_date_mode_changed(self.cmb_date_mode.currentText())

    def _on_date_mode_changed(self, mode: str):
        enabled = self.chk_date_filter.isChecked()
        is_exact = (not enabled) or (mode == "Data exata")
        is_range = enabled and (mode == "Intervalo de data/hora (De / Até)")

        self.dt_filter.setVisible(is_exact)
        self.dt_filter.setEnabled(enabled and mode == "Data exata")

        self.lbl_from.setVisible(is_range)
        self.dt_filter_start.setVisible(is_range)
        self.dt_filter_start.setEnabled(is_range)

        self.lbl_to.setVisible(is_range)
        self.dt_filter_end.setVisible(is_range)
        self.dt_filter_end.setEnabled(is_range)
        self.apply_filters()

    @staticmethod
    def _parse_log_datetime(raw_text: str):
        txt = (raw_text or "").strip()
        if not txt or txt == "-":
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(txt[:19], fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        return format_duration(seconds)

    def on_header_clicked(self, logical_index):
        if logical_index in [0, 10]:
            self.tree.sortItems(self.sort_col, self.sort_order)
            self.tree.header().setSortIndicator(self.sort_col, self.sort_order)
            return

        if self.sort_col == logical_index:
            self.sort_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.sort_col = logical_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        self.tree.sortItems(self.sort_col, self.sort_order)
        self.tree.header().setSortIndicator(self.sort_col, self.sort_order)

    def on_item_double_clicked(self, item, column):
        if item is not None and column != 0:
            json_data = item.data(10, Qt.ItemDataRole.UserRole)
            if json_data:
                self.show_details(json_data)

    def apply_filters(self):
        search_text = self.inp_search.text().lower().strip()
        status_filter = self.cmb_filter_status.currentText()
        use_date = self.chk_date_filter.isChecked()
        mode = self.cmb_date_mode.currentText()
        filter_date_str = self.dt_filter.date().toString("yyyy-MM-dd")
        dt_start = self.dt_filter_start.dateTime().toPyDateTime().replace(second=0, microsecond=0)
        dt_end = self.dt_filter_end.dateTime().toPyDateTime().replace(second=59, microsecond=999999)
        now = datetime.now()

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            match = True

            if status_filter != "Todos os Status":
                val = item.text(9)
                if val != status_filter:
                    match = False

            if match and search_text:
                row_text = f"{item.text(1)} {item.text(6)} {item.text(7)} {item.text(8)}".lower()
                if search_text not in row_text:
                    match = False

            if match and use_date:
                log_dt = self._parse_log_datetime(item.text(3))
                if mode == "Data exata":
                    if item.text(3)[:10] != filter_date_str:
                        match = False
                elif mode == "Intervalo de data/hora (De / Até)":
                    if not log_dt or not (dt_start <= log_dt <= dt_end):
                        match = False
                elif mode == "Últimas 2 horas":
                    if not log_dt or log_dt < (now - timedelta(hours=2)):
                        match = False
                elif mode == "Últimas 12 horas":
                    if not log_dt or log_dt < (now - timedelta(hours=12)):
                        match = False
                elif mode == "Últimas 24 horas":
                    if not log_dt or log_dt < (now - timedelta(hours=24)):
                        match = False
                elif mode == "Últimos 7 dias":
                    if not log_dt or log_dt < (now - timedelta(days=7)):
                        match = False
                elif mode == "Últimos 30 dias":
                    if not log_dt or log_dt < (now - timedelta(days=30)):
                        match = False

            item.setHidden(not match)

    def toggle_view(self):
        if self.view_mode == "ativos":
            self.view_mode = "lixeira"
            self.lbl_title.setText("Lixeira (Logs Excluídos)")
            self.btn_toggle_view.setText("↩ Voltar ao Histórico")
            self.btn_batch_del.setText("❌ Excluir Definitivamente")
            self.btn_batch_res.setVisible(True)
            self.btn_empty_trash.setVisible(True)
        else:
            self.view_mode = "ativos"
            self.lbl_title.setText("Histórico e Auditoria por Máquina")
            self.btn_toggle_view.setText("🗑️ Ver Lixeira")
            self.btn_batch_del.setText("🗑 Excluir Selecionados")
            self.btn_batch_res.setVisible(False)
            self.btn_empty_trash.setVisible(False)
        self.chk_select_all.setChecked(False)
        self.inp_search.clear()
        self.chk_date_filter.setChecked(False)
        self.load_logs()

    def toggle_select_all(self, state):
        is_checked = (state == Qt.CheckState.Checked.value)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item.isHidden():
                item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)

    def get_selected_ids(self):
        selected_ids = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item.isHidden() and item.checkState(0) == Qt.CheckState.Checked:
                selected_ids.append(int(item.text(2)))
        return selected_ids

    def batch_delete(self):
        ids = self.get_selected_ids()
        if not ids:
            QMessageBox.warning(self, "Aviso", "Marque o checkbox de pelo menos um log visível.")
            return

        if self.view_mode == "ativos":
            self.repo.soft_delete_many(ids)
        else:
            reply = QMessageBox.question(
                self, "Excluir Definitivamente",
                f"Deseja excluir permanentemente os {len(ids)} logs selecionados?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.repo.hard_delete_many(ids)

        self.chk_select_all.setChecked(False)
        self.load_logs()

    def batch_restore(self):
        ids = self.get_selected_ids()
        if not ids:
            return
        self.repo.restore_many(ids)
        self.chk_select_all.setChecked(False)
        self.load_logs()

    def empty_trash(self):
        reply = QMessageBox.question(
            self, "Esvaziar Lixeira",
            "Apagar TODOS os logs da lixeira definitivamente?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.repo.empty_trash()
            self.load_logs()

    def load_logs(self):
        self.tree.setSortingEnabled(False)
        self.tree.clear()

        # Reseta o controle de click
        self._last_clicked_row = -1

        limit_str = self.cmb_limit.currentText()
        limit = 10000 if limit_str == "Todos" else int(limit_str)

        rows = self.repo.list_executions(deleted=(self.view_mode == "lixeira"), limit=limit)

        for row in rows:
            log_id, start_time, target_pc, script_name, status, result_data = row[:6]
            pc = target_pc if target_pc else "Desconhecido"
            technician = row[6] if len(row) > 6 and row[6] else "N/A"
            module = row[7] if len(row) > 7 and row[7] else "Geral"

            metrics = self.audit_service.parse_execution_metrics(start_time, result_data)
            inicio_str = metrics["inicio"]
            fim_str = metrics["fim"]
            duracao_str = metrics["duracao"]
            raw_seconds = metrics["seconds"]

            status_clean = ExecutionStatus.normalize(status)

            child_item = LogTreeWidgetItem(self.tree, [
                "", f"🖥️ {pc}", str(log_id), inicio_str, fim_str, duracao_str,
                str(module), str(script_name), str(technician), status_clean, ""
            ])

            if status_clean == ExecutionStatus.SUCCESS.value:
                child_item.setForeground(9, Qt.GlobalColor.green)
            elif status_clean == ExecutionStatus.ERROR.value:
                child_item.setForeground(9, Qt.GlobalColor.red)
            elif status_clean == ExecutionStatus.WARNING.value:
                child_item.setForeground(9, Qt.GlobalColor.darkYellow)

            child_item.setCheckState(0, Qt.CheckState.Unchecked)
            child_item.setData(5, Qt.ItemDataRole.UserRole, raw_seconds)
            child_item.setData(10, Qt.ItemDataRole.UserRole, result_data)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)

            btn_view = QPushButton("📄 JSON")
            btn_view.setFixedHeight(24)
            btn_view.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_view.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 8px; font-weight: bold; border-radius: 4px;")
            btn_view.clicked.connect(lambda checked, js_str=result_data: self.show_details(js_str))

            action_layout.addWidget(btn_view)
            action_layout.addStretch()
            self.tree.setItemWidget(child_item, 10, action_widget)

        self.tree.setSortingEnabled(True)
        self.tree.sortItems(self.sort_col, self.sort_order)
        self.tree.header().setSortIndicator(self.sort_col, self.sort_order)
        self.apply_filters()

    def exportar_txt(self):
        ids = self.get_selected_ids()
        if not ids:
            QMessageBox.warning(self, "Aviso", "Marque o checkbox de pelo menos uma linha para exportar.")
            return

        conteudo_final = self.audit_service.generate_audit_report(ids)

        if len(ids) == 1:
            row = self.repo.get_by_id(ids[0])
            if row:
                data_bruta, pc, script = row[0], row[1], row[2]
                raw_name = f"{pc}_{str(data_bruta)[:19]}_{script}".replace(" ", "_")
                default_filename = f"{sanitize_filename(raw_name)}.txt"
            else:
                default_filename = "Relatorio_SARCC.txt"
        else:
            agora_safe = datetime.now().strftime("%Y%m%d_%H%M")
            default_filename = f"Lote_{len(ids)}_Registros_{agora_safe}.txt"

        file_path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório", default_filename, "Text Files (*.txt)")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(conteudo_final)
            QMessageBox.information(self, "Sucesso", "Relatório de Auditoria salvo!")

    def show_details(self, json_string):
        dialog = JsonDetailDialog(json_string, self)
        dialog.exec()

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_search.setFocus()
        self.load_logs()
