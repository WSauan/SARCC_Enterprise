import os
import re
import json
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QGroupBox, 
                             QMessageBox, QInputDialog, QTextEdit, QFileDialog, 
                             QSizePolicy, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QDialog  # (já existe no import? confirme)
from gui.dialogs import CredentialDialog
from core.credential_store import CredentialStore
from core.task_queue import TaskQueueManager
from core.database import DatabaseManager
from gui.views.base_view import BaseView

class ExecutionView(BaseView):
    
    def _get_credentials(self):
        """Retorna credenciais — cache → disco (DPAPI) → popup."""
        # 1) Cache de sessão em memória
        cached = getattr(self.main_window, 'get_cached_credentials', None)
        if cached:
            creds = cached()
            if creds:
                return creds

        # 2) Arquivo em disco (DPAPI, mesma máquina + mesmo usuário)
        saved = CredentialStore.load()
        if saved:
            setter = getattr(self.main_window, 'set_cached_credentials', None)
            if setter:
                setter(saved["user"], saved["pass"])
            return saved

        # 3) Popup
        dominio = os.environ.get("USERDOMAIN", "")
        usuario = os.environ.get("USERNAME", "")
        user_str = f"{dominio}\\{usuario}"

        dlg = CredentialDialog(user_display=user_str, has_saved=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        senha = dlg.password
        if not senha:
            return None

        # 4) Se marcou "lembrar", salva em disco (DPAPI)
        if dlg.remember:
            CredentialStore.save(user_str, senha)

        # 5) Guarda no cache de sessão
        setter = getattr(self.main_window, 'set_cached_credentials', None)
        if setter:
            setter(user_str, senha)

        return {"user": user_str, "pass": senha, "vnc_pass": senha}

    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(main_window_ref, 'queue_manager', None) or TaskQueueManager(max_threads=10)
        self.db = DatabaseManager()
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        title = QLabel("Central de Comando Remoto (Lote de Scripts)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        main_layout.addWidget(title)
        
        target_group = QGroupBox("1. Computadores Alvo")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(15, 20, 15, 15)
        
        self.target_input = QLineEdit()
        self.target_input.setFixedHeight(32)
        self.target_input.setPlaceholderText("Ex: localhost, 10.8.128.14, HUL-WK-244377E...")
        self.target_input.setStyleSheet("padding: 0 10px;")
        self.target_input.textChanged.connect(self._force_uppercase)
        
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
        target_layout.addWidget(self.btn_import_targets)
        target_layout.addWidget(self.btn_clear_targets)
        
        target_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        main_layout.addWidget(target_group)
        
        script_group = QGroupBox("2. Execução de Scripts (Biblioteca)")
        script_vlayout = QVBoxLayout(script_group)
        script_vlayout.setContentsMargins(15, 20, 15, 15)
        script_vlayout.setSpacing(10)

        # --- Linha 1: filtro + ações de biblioteca ---
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        self.inp_filter_scripts = QLineEdit()
        self.inp_filter_scripts.setFixedHeight(32)
        self.inp_filter_scripts.setPlaceholderText("🔍 Filtrar scripts por nome...")
        self.inp_filter_scripts.setStyleSheet("padding: 0 10px;")
        self.inp_filter_scripts.textChanged.connect(self._filtrar_scripts)
        row1.addWidget(self.inp_filter_scripts, stretch=1)

        self.btn_select_all_scripts = QPushButton("☑ Marcar Visíveis")
        self.btn_select_all_scripts.setFixedHeight(32)
        self.btn_select_all_scripts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all_scripts.setStyleSheet(
            "padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_select_all_scripts.clicked.connect(lambda: self._toggle_all_scripts(True))
        row1.addWidget(self.btn_select_all_scripts)

        self.btn_clear_scripts = QPushButton("☐ Desmarcar Todos")
        self.btn_clear_scripts.setFixedHeight(32)
        self.btn_clear_scripts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_scripts.setStyleSheet(
            "padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_clear_scripts.clicked.connect(lambda: self._toggle_all_scripts(False))
        row1.addWidget(self.btn_clear_scripts)

        self.btn_reload = QPushButton("↻ Recarregar")
        self.btn_reload.setFixedHeight(32)
        self.btn_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reload.setStyleSheet(
            "padding: 0 15px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_reload.clicked.connect(self.carregar_scripts_do_banco)
        row1.addWidget(self.btn_reload)

        script_vlayout.addLayout(row1)

        # --- Linha 2: lista com checkboxes ---
        self.list_scripts = QListWidget()
        self.list_scripts.setMinimumHeight(140)
        self.list_scripts.setMaximumHeight(220)
        self.list_scripts.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_scripts.setStyleSheet(
            "QListWidget { "
            "  font-size: 13px; padding: 4px; "
            "  border: 1px solid #444; border-radius: 4px; "
            "} "
            "QListWidget::item { padding: 4px 6px; } "
            "QListWidget::item:hover { background-color: rgba(74, 144, 226, 0.1); }"
        )
        self.list_scripts.itemChanged.connect(self._atualizar_contador_scripts)
        script_vlayout.addWidget(self.list_scripts)

        # --- Linha 3: contador + botão executar ---
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

    def import_targets_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Importar Lista de Computadores", "", "Text Files (*.txt);;CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                raw_targets = re.split(r'[\n,;]+', content)
                clean_targets = [t.strip() for t in raw_targets if t.strip()]
                if not clean_targets:
                    QMessageBox.warning(self, "Aviso", "Nenhum alvo válido encontrado no arquivo selecionado.")
                    return
                current_text = self.target_input.text().strip()
                if current_text:
                    existing = [t.strip() for t in current_text.split(",") if t.strip()]
                    clean_targets = existing + clean_targets
                unique_targets = list(dict.fromkeys(clean_targets))
                self.target_input.setText(", ".join(unique_targets))
                QMessageBox.information(self, "Sucesso", f"{len(unique_targets)} computador(es) carregado(s) na fila com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro na Importação", f"Falha ao processar o arquivo:\n{e}")

    def format_html(self, text, color="#cccccc"):
        safe_text = str(text).replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
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
            for item in selected_items: rows_to_clear.add(item.row())
        else:
            for i in range(self.table.rowCount()): rows_to_clear.add(i)
            
        for r in rows_to_clear:
            item = self.table.item(r, 0)
            if item: item.setData(Qt.ItemDataRole.UserRole, "")
            
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
            status_text = self.table.item(r, 4).text().lower()
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
        # Preserva o que já estava marcado (se for recarregar)
        marcados_antes = self._get_selected_script_names()

        self.list_scripts.blockSignals(True)
        self.list_scripts.clear()

        scripts = self.db.get_all_scripts()
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
            # Re-marca se estava marcado antes
            if nome in marcados_antes:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            # Guarda os metadados necessários
            item.setData(Qt.ItemDataRole.UserRole, {
                "id": script_id,
                "nome": nome,
                "descricao": descricao,
                "categoria": categoria,
                "conteudo": conteudo,
            })
            # Tooltip mostra categoria + descrição
            tooltip = f"[{categoria or 'Sem categoria'}]"
            if descricao:
                tooltip += f"\n{descricao}"
            item.setToolTip(tooltip)

            self.list_scripts.addItem(item)

        self.list_scripts.blockSignals(False)
        self._atualizar_contador_scripts()

    def get_targets(self):
        targets_text = self.target_input.text().strip()
        if not targets_text:
            QMessageBox.warning(self, "Aviso", "Por favor, insira pelo menos um IP ou Hostname na caixa ou faça a importação de uma lista (.txt).")
            return []
        return [t.strip() for t in targets_text.split(",") if t.strip()]

    def start_script_execution(self):
        """Dispara todos os scripts marcados para todos os alvos listados."""
        targets = self.get_targets()
        if not targets:
            return

        # Coleta todos os scripts marcados
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

        # --- Detecção de credenciais (se QUALQUER script precisar) ---
        credentials = None
        needs_creds = any(
            any(ph in s["conteudo"] for ph in ("[[ADMIN_PASS]]", "[[VNC_PASS]]", "[[ADMIN_USER]]"))
            for s in scripts_selecionados
        )

        if needs_creds:
            credentials = self._get_credentials()
            if credentials is None:
                return

        # --- Confirmação com contagem ---
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

        # Enfileira: para cada script, todos os targets
        for script in scripts_selecionados:
            self.disparar_fila(
                targets,
                script["nome"],
                script["conteudo"],
                credentials=credentials,
            )
    def _get_selected_script_names(self) -> set:
        """Retorna o conjunto de nomes dos scripts marcados."""
        nomes = set()
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    nomes.add(data["nome"])
        return nomes

    def _atualizar_contador_scripts(self, *args):
        """Atualiza o label 'X script(s) selecionado(s)'."""
        total = self.list_scripts.count()
        marcados = 0
        for i in range(total):
            item = self.list_scripts.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                marcados += 1

        if total == 0:
            self.lbl_scripts_count.setText("0 script(s) selecionado(s)")
        else:
            self.lbl_scripts_count.setText(
                f"{marcados} de {total} script(s) selecionado(s)"
            )

    def _toggle_all_scripts(self, marcar: bool):
        """Marca ou desmarca todos os scripts visíveis (respeitando filtro)."""
        state = Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
        self.list_scripts.blockSignals(True)
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            if not item.isHidden():
                item.setCheckState(state)
        self.list_scripts.blockSignals(False)
        self._atualizar_contador_scripts()

    def _filtrar_scripts(self, text: str):
        """Esconde itens que não casam com o filtro."""
        termo = text.strip().lower()
        for i in range(self.list_scripts.count()):
            item = self.list_scripts.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data:
                continue
            # Busca em nome + descrição + categoria
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
            
            # Formatação base da linha
            for item in [item_target, item_action, item_inicio, item_fim, item_status, item_resume]:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
            # Ancorando o log inicial dentro da célula do alvo
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

    @pyqtSlot(str, object, object, object)
    def update_status_start(self, target_pc, item_status, item_resume, item_inicio):
        try:
            item_status.setText("Executando...")
            item_resume.setText("Processando...")
            item_inicio.setText(datetime.now().strftime("%H:%M:%S"))
        except RuntimeError: pass 

    @pyqtSlot(str, str, dict, object, object, object, object)
    def update_status_finish(self, target_pc, status, json_data, item_target, item_status, item_resume, item_fim):
        try:
            item_status.setText(status)
            item_fim.setText(datetime.now().strftime("%H:%M:%S"))
            
            if "SUCESSO" in status.upper() or json_data.get("StatusFinal") == "SUCESSO": 
                item_status.setForeground(Qt.GlobalColor.green)
                sucesso = True
            elif "ERRO" in status.upper() or "FALHA" in status.upper() or "ALERTA" in status.upper(): 
                item_status.setForeground(Qt.GlobalColor.red)
                sucesso = False
            else: 
                item_status.setForeground(Qt.GlobalColor.darkYellow)
                sucesso = False
                
            resumo = json_data.get("Mensagem", "Operação concluída.")
            if "Detalhes" in json_data and json_data["Detalhes"]:
                if isinstance(json_data["Detalhes"], list):
                    linhas = [str(x).strip() for x in json_data["Detalhes"] if str(x).strip()]
                    if linhas: resumo = " | ".join(linhas)[:150] + "..."
                else: resumo = str(json_data["Detalhes"])[:150] + "..."

            item_resume.setText(str(resumo).strip())
            row = item_status.row()
            if row >= 0: self.table.resizeRowToContents(row)
        except RuntimeError: pass

        linhas_console = []
        script_name = json_data.get("Script", "Ação Remota")
        linhas_console.append("="*80)
        linhas_console.append(f" [ SARCC ] RELATÓRIO DE EXECUÇÃO - ALVO: {target_pc} ")
        linhas_console.append("="*80)
        linhas_console.append(f" SCRIPT/AÇÃO   : {script_name}")
        linhas_console.append(f" STATUS FINAL  : {json_data.get('StatusFinal', status.upper())}")
        if "Inicio" in json_data: linhas_console.append(f" INÍCIO        : {json_data['Inicio']}")
        if "Fim" in json_data:    linhas_console.append(f" TÉRMINO       : {json_data['Fim']}")
        linhas_console.append("-" * 80)
        
        if "Mensagem" in json_data and json_data["Mensagem"]:
            linhas_console.append(f" RESUMO: {json_data['Mensagem']}")
            linhas_console.append("-" * 80)
            
        if "Detalhes" in json_data and json_data["Detalhes"]:
            if isinstance(json_data["Detalhes"], list):
                for d in json_data["Detalhes"]: linhas_console.append(f"  {d}")
            else: linhas_console.append(f"  {json_data['Detalhes']}")
                
        linhas_console.append("="*80 + "\n")
        
        relatorio_str = "\n".join(linhas_console)
        html_to_add = self.format_html(relatorio_str, "#4CAF50" if sucesso else "#f0ad4e")
        
        current_html = item_target.data(Qt.ItemDataRole.UserRole) or ""
        item_target.setData(Qt.ItemDataRole.UserRole, current_html + html_to_add)
        self.refresh_console()
            
    @pyqtSlot(str, str, object, object, object, object)
    def update_status_error(self, target_pc, error_msg, item_target, item_status, item_resume, item_fim):
        try:
            item_status.setText("Erro Fatal")
            item_status.setForeground(Qt.GlobalColor.red)
            item_fim.setText(datetime.now().strftime("%H:%M:%S"))
            item_resume.setText("Falha Crítica. Verifique o console abaixo.")
            row = item_status.row()
            if row >= 0: self.table.resizeRowToContents(row)
        except RuntimeError: pass
            
        linhas_erro = [
            "=" * 80,
            f" [ SARCC ] ERRO CRÍTICO / FALHA DE CONEXÃO - ALVO: {target_pc}",
            "=" * 80,
            str(error_msg).strip(),
            "=" * 80 + "\n"
        ]
        relatorio_str = "\n".join(linhas_erro)
        html_to_add = self.format_html(relatorio_str, "#d9534f")
        
        current_html = item_target.data(Qt.ItemDataRole.UserRole) or ""
        item_target.setData(Qt.ItemDataRole.UserRole, current_html + html_to_add)
        self.refresh_console()