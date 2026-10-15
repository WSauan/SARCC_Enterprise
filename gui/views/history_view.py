from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTreeWidget, QTreeWidgetItem, 
                             QHeaderView, QDialog, QTextEdit, QMessageBox, QFileDialog, QCheckBox, QLineEdit, QComboBox, QDateEdit, QAbstractItemView, QGroupBox)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor
import json
import re
from datetime import datetime

from core.database import DatabaseManager

class LogTreeWidgetItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column in [1, 10]:
            column = 3
            
        if column == 2:
            try: return int(self.text(column)) < int(other.text(column))
            except ValueError: return self.text(column) < other.text(column)
                
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
        self.resize(700, 500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 13px; background-color: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 4px; border: 1px solid #444;")
        
        clean_json = re.sub(r'\[\s*⏱.*?Tempo de Execução.*?\]', '', json_string).strip()
        
        try:
            parsed_json = json.loads(clean_json)
            formatted_json = json.dumps(parsed_json, indent=4, ensure_ascii=False)
            text_edit.setPlainText(formatted_json)
        except Exception:
            text_edit.setPlainText(str(json_string))
            
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
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.view_mode = "ativos"
        self.sort_col = 3 
        self.sort_order = Qt.SortOrder.DescendingOrder
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

        filter_group = QGroupBox("Filtros de Pesquisa e Seleção")
        control_bar = QHBoxLayout(filter_group)
        control_bar.setContentsMargins(15, 20, 15, 15)
        control_bar.setSpacing(10)
        
        self.chk_date_filter = QCheckBox("Data:")
        self.chk_date_filter.setFixedHeight(32)
        self.chk_date_filter.setStyleSheet("font-weight: bold; color: #4a90e2;")
        self.chk_date_filter.stateChanged.connect(self.apply_filters)
        control_bar.addWidget(self.chk_date_filter)
        
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
        self.chk_date_filter.toggled.connect(self.dt_filter.setEnabled)
        control_bar.addWidget(self.dt_filter)
        
        control_bar.addSpacing(15)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.setFixedHeight(32)
        self.cmb_filter_status.addItems(["Todos os Status", "SUCESSO", "ERRO / FALHA", "PENDENTE"])
        self.cmb_filter_status.setStyleSheet("padding: 0 10px; font-weight: bold;")
        self.cmb_filter_status.currentTextChanged.connect(self.apply_filters)
        control_bar.addWidget(self.cmb_filter_status)

        self.inp_search = QLineEdit()
        self.inp_search.setFixedHeight(32)
        self.inp_search.setPlaceholderText("🔍 Buscar livre em texto...")
        self.inp_search.setStyleSheet("padding: 0 10px; font-size: 13px;")
        self.inp_search.textChanged.connect(self.apply_filters)
        control_bar.addWidget(self.inp_search, stretch=1)

        self.chk_select_all = QCheckBox("Selecionar Visíveis")
        self.chk_select_all.setFixedHeight(32)
        self.chk_select_all.setStyleSheet("font-weight: bold; color: #4a90e2; margin-left: 10px;")
        self.chk_select_all.stateChanged.connect(self.toggle_select_all)
        control_bar.addWidget(self.chk_select_all)
        
        layout.addWidget(filter_group)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Alvo (Computador)", "[✓]", "ID", "Início", "Fim", "Tempo", "Módulo", "Ação / Script", "Técnico", "Status", "Ações"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSortingEnabled(True)
        self.tree.setRootIsDecorated(False) 
        
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 180)
        header.resizeSection(1, 35)
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
        layout.addWidget(self.tree)

    def _format_duration(self, seconds):
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {seconds % 60:.0f}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m {((seconds % 3600) % 60):.0f}s"

    def on_header_clicked(self, logical_index):
        if logical_index in [1, 10]: return
        if self.sort_col == logical_index:
            self.sort_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.sort_col = logical_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        self.tree.sortItems(self.sort_col, self.sort_order)
        self.tree.header().setSortIndicator(self.sort_col, self.sort_order)

    def on_item_double_clicked(self, item, column):
        if item is not None:
            current_state = item.checkState(1)
            new_state = Qt.CheckState.Checked if current_state == Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
            item.setCheckState(1, new_state)
            
            json_data = item.data(10, Qt.ItemDataRole.UserRole)
            if json_data: self.show_details(json_data)

    def apply_filters(self):
        search_text = self.inp_search.text().lower()
        status_filter = self.cmb_filter_status.currentText()
        use_date = self.chk_date_filter.isChecked()
        filter_date_str = self.dt_filter.date().toString("yyyy-MM-dd")
        
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            match = True
            
            if status_filter != "Todos os Status":
                val = item.text(9).upper() 
                if status_filter == "SUCESSO" and "SUCESSO" not in val: match = False
                elif status_filter == "ERRO / FALHA" and not ("ERRO" in val or "FALHA" in val): match = False
                elif status_filter == "PENDENTE" and "PENDENTE" not in val: match = False
            
            if match and search_text:
                row_text = f"{item.text(0)} {item.text(6)} {item.text(7)} {item.text(8)}".lower() 
                if search_text not in row_text: match = False
                    
            if match and use_date:
                log_date = item.text(3)[:10] 
                if log_date != filter_date_str: match = False
                    
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
            self.btn_batch_del.setText("🗑️️ Excluir Selecionados")
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
                item.setCheckState(1, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)

    def get_selected_ids(self):
        selected_ids = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item.isHidden() and item.checkState(1) == Qt.CheckState.Checked:
                selected_ids.append(int(item.text(2)))
        return selected_ids

    def batch_delete(self):
        ids = self.get_selected_ids()
        if not ids:
            QMessageBox.warning(self, "Aviso", "Marque o checkbox de pelo menos um log visível.")
            return

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if self.view_mode == "ativos":
                cursor.executemany("UPDATE executions SET excluido = 1 WHERE id = ?", [(i,) for i in ids])
                conn.commit()
            else:
                reply = QMessageBox.question(self, 'Excluir Definitivamente', f'Deseja excluir permanentemente os {len(ids)} logs selecionados?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    cursor.executemany("DELETE FROM executions WHERE id = ?", [(i,) for i in ids])
                    conn.commit()

        self.chk_select_all.setChecked(False)
        self.load_logs()

    def batch_restore(self):
        ids = self.get_selected_ids()
        if not ids: return
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("UPDATE executions SET excluido = 0 WHERE id = ?", [(i,) for i in ids])
            conn.commit()
        self.chk_select_all.setChecked(False)
        self.load_logs()

    def empty_trash(self):
        reply = QMessageBox.question(self, 'Esvaziar Lixeira', 'Apagar TODOS os logs da lixeira definitivamente?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM executions WHERE excluido = 1")
                conn.commit()
            self.load_logs()

    def load_logs(self):
        self.tree.setSortingEnabled(False) 
        self.tree.clear()
        is_excluido = 1 if self.view_mode == "lixeira" else 0
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, start_time, target_pc, script_name, status, result_data, technician, module 
                FROM executions 
                WHERE excluido = ?
                ORDER BY start_time DESC LIMIT 1000
            ''', (is_excluido,))
            rows = cursor.fetchall()
            
        for log in rows:
            log_id, start_time, target_pc, script_name, status, result_data = log[:6]
            pc = target_pc if target_pc else "Desconhecido"
            technician = log[6] if len(log) > 6 and log[6] else "N/A"
            module = log[7] if len(log) > 7 and log[7] else "Geral"
            
            inicio_str = str(start_time)[:19]
            fim_str = "-"
            duracao_str = "-"
            raw_seconds = -1.0
            
            if result_data:
                tempo_match = re.search(r'\[\s*⏱.*?Tempo de Execução.*?: ([\d\.]+) segundos\]', str(result_data))
                if tempo_match:
                    raw_seconds = float(tempo_match.group(1))
                    duracao_str = self._format_duration(raw_seconds)
                    
                try:
                    clean_res = re.sub(r'\[\s*⏱.*?Tempo de Execução.*?\]', '', str(result_data)).strip()
                    js = json.loads(clean_res)
                    
                    if "Inicio" in js: inicio_str = js["Inicio"]
                    if "Fim" in js: fim_str = js["Fim"]
                        
                    if "Inicio" in js and "Fim" in js:
                        fmt = "%Y-%m-%d %H:%M:%S"
                        t_in = datetime.strptime(js["Inicio"], fmt)
                        t_out = datetime.strptime(js["Fim"], fmt)
                        raw_seconds = (t_out - t_in).total_seconds()
                        duracao_str = self._format_duration(raw_seconds)
                except: pass

            child_item = LogTreeWidgetItem(self.tree, [
                f"🖥️ {pc}", "", str(log_id), inicio_str, fim_str, duracao_str, str(module), str(script_name), str(technician), str(status), ""
            ])
            
            if "SUCESSO" in status.upper(): child_item.setForeground(9, Qt.GlobalColor.green)
            elif "ERRO" in status.upper() or "FALHA" in status.upper(): child_item.setForeground(9, Qt.GlobalColor.red)
            elif "ALERTA" in status.upper(): child_item.setForeground(9, Qt.GlobalColor.darkYellow)
            
            child_item.setCheckState(1, Qt.CheckState.Unchecked)
            child_item.setData(5, Qt.ItemDataRole.UserRole, raw_seconds)
            child_item.setData(10, Qt.ItemDataRole.UserRole, result_data)
            
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            
            btn_view = QPushButton("📄 JSON")
            btn_view.setFixedHeight(24)
            btn_view.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_view.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 8px; font-weight: bold; border-radius: 4px;")
            btn_view.clicked.connect(lambda checked, js=result_data: self.show_details(js))
            
            action_layout.addWidget(btn_view)
            action_layout.addStretch()
            self.tree.setItemWidget(child_item, 10, action_widget)
                
        self.tree.setSortingEnabled(True) 
        self.tree.sortItems(self.sort_col, self.sort_order)
        self.apply_filters()

    def exportar_txt(self):
        ids = self.get_selected_ids()
        if not ids:
            QMessageBox.warning(self, "Aviso", "Marque o checkbox de pelo menos uma linha para exportar.")
            return

        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        conteudo_final = (
            "================================================================================\n"
            "                 SARCC - RELATÓRIO OFICIAL DE AUDITORIA E EXECUÇÃO\n"
            "================================================================================\n"
            f"Data de Geração do Relatório : {agora}\n"
            f"Total de Registros Exportados: {len(ids)}\n"
            "================================================================================\n\n"
        )
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for idx, log_id in enumerate(ids, 1):
                cursor.execute("SELECT start_time, target_pc, script_name, status, result_data, technician, module FROM executions WHERE id = ?", (log_id,))
                row_data = cursor.fetchone()
                if not row_data: continue
                
                data_bruta, pc, script, status, res_data, tech, mod = row_data
                detalhes = ""
                
                inicio_str = str(data_bruta)[:19]
                fim_str = "N/A"
                duracao_str = "N/A"
                
                if res_data:
                    tempo_match = re.search(r'\[\s*⏱.*?Tempo de Execução.*?: ([\d\.]+) segundos\]', str(res_data))
                    if tempo_match:
                        duracao_str = self._format_duration(float(tempo_match.group(1)))
                        
                    try:
                        clean_res = re.sub(r'\[\s*⏱.*?Tempo de Execução.*?\]', '', str(res_data)).strip()
                        js = json.loads(clean_res)
                        
                        if "Inicio" in js: inicio_str = js["Inicio"]
                        if "Fim" in js: fim_str = js["Fim"]
                        if "Inicio" in js and "Fim" in js:
                            fmt = "%Y-%m-%d %H:%M:%S"
                            t_in = datetime.strptime(js["Inicio"], fmt)
                            t_out = datetime.strptime(js["Fim"], fmt)
                            duracao_str = self._format_duration((t_out - t_in).total_seconds())
                            
                        msg = js.get("Mensagem", "")
                        if msg: detalhes += f">> MENSAGEM DO SISTEMA:\n{msg}\n\n"
                        if "Detalhes" in js:
                            detalhes += ">> DETALHES TÉCNICOS:\n"
                            if isinstance(js["Detalhes"], list):
                                for linha in js["Detalhes"]: detalhes += f"  {linha}\n"
                            else: detalhes += f"  {js['Detalhes']}\n"
                    except:
                        detalhes = f">> RAW OUTPUT:\n{str(res_data)}"

                conteudo = (
                    f"[ REGISTRO #{idx} - ID BD: {log_id} ] ".ljust(80, "-") + "\n"
                    f"COMPUTADOR ALVO  : {pc}\n"
                    f"TÉCNICO EXECUTOR : {tech}\n"
                    f"MÓDULO DE ORIGEM : {mod}\n"
                    f"SCRIPT / AÇÃO    : {script}\n"
                    f"STATUS FINAL     : {status}\n"
                    f"INÍCIO DA AÇÃO   : {inicio_str}\n"
                    f"TÉRMINO DA AÇÃO  : {fim_str}\n"
                    f"TEMPO DE EXECUÇÃO: {duracao_str}\n\n"
                    f"{detalhes}\n"
                    f"{''.ljust(80, '-')}\n\n"
                )
                conteudo_final += conteudo

        if len(ids) == 1:
            data_safe = inicio_str.replace(":", "-").replace(" ", "_")
            script_safe = script.replace("/", "-").replace("\\", "-").replace(" ", "_")
            default_filename = f"{pc}_{data_safe}_{script_safe}.txt"
        else:
            agora_safe = datetime.now().strftime('%Y%m%d_%H%M')
            default_filename = f"Lote_{len(ids)}_Registros_{agora_safe}.txt"
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório", default_filename, "Text Files (*.txt)")
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f: f.write(conteudo_final)
            QMessageBox.information(self, "Sucesso", "Relatório de Auditoria salvo!")

    def show_details(self, json_string):
        dialog = JsonDetailDialog(json_string, self)
        dialog.exec()
        
    def showEvent(self, event):
        super().showEvent(event)
        self.inp_search.setFocus()
        self.load_logs()