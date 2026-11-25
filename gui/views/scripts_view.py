from PyQt6.QtCore import QRegularExpression, Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.logger import get_logger
from domain.services.script_service import ScriptService
from gui.views.base_view import BaseView, sanitize_filename
from gui.widgets.code_editor import CodeEditorWidget
from infrastructure.repositories.script_repository import ScriptRepository

log = get_logger(__name__)


class PowerShellHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.highlightingRules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#ff79c6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "\\bif\\b", "\\belse\\b", "\\belseif\\b", "\\bforeach\\b",
            "\\bfor\\b", "\\bwhile\\b", "\\bdo\\b", "\\buntil\\b",
            "\\btry\\b", "\\bcatch\\b", "\\bfinally\\b", "\\bthrow\\b",
            "\\breturn\\b", "\\bbreak\\b", "\\bcontinue\\b", "\\bswitch\\b",
            "\\bfunction\\b", "\\bfilter\\b", "\\bworkflow\\b", "\\bclass\\b"
        ]
        for word in keywords:
            pattern = QRegularExpression(word, QRegularExpression.PatternOption.CaseInsensitiveOption)
            self.highlightingRules.append((pattern, keyword_format))

        variable_format = QTextCharFormat()
        variable_format.setForeground(QColor("#8be9fd"))
        pattern = QRegularExpression("\\$[a-zA-Z0-9_:]+")
        self.highlightingRules.append((pattern, variable_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#f1fa8c"))
        pattern = QRegularExpression("\".*\"|'.*'")
        pattern.setPatternOptions(QRegularExpression.PatternOption.InvertedGreedinessOption)
        self.highlightingRules.append((pattern, string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#50fa7b"))
        pattern = QRegularExpression("#[^\n]*")
        self.highlightingRules.append((pattern, comment_format))

        self.multi_line_comment_format = QTextCharFormat()
        self.multi_line_comment_format.setForeground(QColor("#50fa7b"))
        self.comment_start_expression = QRegularExpression("<#")
        self.comment_end_expression = QRegularExpression("#>")

    def highlightBlock(self, text):
        for pattern, fmt in self.highlightingRules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        self.setCurrentBlockState(0)
        startIndex = 0
        if self.previousBlockState() != 1:
            startIndex = text.find("<#")

        while startIndex >= 0:
            match = self.comment_end_expression.match(text, startIndex)
            endIndex = match.capturedStart()
            if endIndex == -1:
                self.setCurrentBlockState(1)
                commentLength = len(text) - startIndex
            else:
                commentLength = endIndex - startIndex + match.capturedLength()
            self.setFormat(startIndex, commentLength, self.multi_line_comment_format)
            startIndex = text.find("<#", startIndex + commentLength)


class ScriptsView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.repo = ScriptRepository()
        self.service = ScriptService(self.repo)
        self.current_script_id = None
        self._setup_ui()
        self.load_scripts_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Gestor de Scripts Automáticos")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2; margin-bottom: 10px;")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lib_group = QGroupBox("Biblioteca de Scripts")
        lib_layout = QVBoxLayout(lib_group)
        lib_layout.setContentsMargins(15, 20, 15, 15)

        self.inp_search = QLineEdit()
        self.inp_search.setFixedHeight(32)
        self.inp_search.setPlaceholderText("🔍 Buscar script...")
        self.inp_search.setStyleSheet("padding: 0 10px; border-radius: 4px;")
        self.inp_search.textChanged.connect(self.filter_scripts)
        lib_layout.addWidget(self.inp_search)

        self.tree_scripts = QTreeWidget()
        self.tree_scripts.setHeaderHidden(True)
        self.tree_scripts.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_scripts.setStyleSheet("""
            QTreeWidget { font-size: 14px; padding: 5px; border: 1px solid #444; border-radius: 4px; }
            QTreeWidget::item { padding: 4px; }
        """)
        self.tree_scripts.itemClicked.connect(self.on_script_selected)
        lib_layout.addWidget(self.tree_scripts)

        lib_buttons_layout = QHBoxLayout()

        btn_novo = QPushButton("➕ Novo Script")
        btn_novo.setFixedHeight(32)
        btn_novo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_novo.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 10px; font-weight: bold; border-radius: 4px;")
        btn_novo.clicked.connect(self.prepare_new_script)

        btn_importar = QPushButton("📥 Importar Arquivos")
        btn_importar.setFixedHeight(32)
        btn_importar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_importar.setStyleSheet("background-color: #5bc0de; color: black; padding: 0 10px; font-weight: bold; border-radius: 4px;")
        btn_importar.clicked.connect(self.import_script)

        lib_buttons_layout.addWidget(btn_novo)
        lib_buttons_layout.addWidget(btn_importar)
        lib_layout.addLayout(lib_buttons_layout)

        splitter.addWidget(lib_group)

        editor_group = QGroupBox("Editor de Código (PowerShell)")
        editor_layout = QVBoxLayout(editor_group)
        editor_layout.setContentsMargins(15, 20, 15, 15)

        row1_layout = QHBoxLayout()
        self.inp_nome = QLineEdit()
        self.inp_nome.setFixedHeight(32)
        self.inp_nome.setPlaceholderText("Nome do Script (ex: Limpar Temp)")
        self.inp_nome.setStyleSheet("padding: 0 10px; font-size: 14px; font-weight: bold;")

        self.cmb_categoria = QComboBox()
        self.cmb_categoria.setFixedHeight(32)
        self.cmb_categoria.addItems(["Manutenção", "Rede", "Segurança", "Instalação", "Diagnóstico", "Outros"])
        self.cmb_categoria.setStyleSheet("padding: 0 10px;")

        row1_layout.addWidget(QLabel("Nome:"))
        row1_layout.addWidget(self.inp_nome, stretch=2)
        row1_layout.addWidget(QLabel("Categoria:"))
        row1_layout.addWidget(self.cmb_categoria, stretch=1)
        editor_layout.addLayout(row1_layout)

        row2_layout = QHBoxLayout()
        self.inp_descricao = QLineEdit()
        self.inp_descricao.setFixedHeight(32)
        self.inp_descricao.setPlaceholderText("Descreva o que este script faz...")
        self.inp_descricao.setStyleSheet("padding: 0 10px;")
        row2_layout.addWidget(QLabel("Descrição:"))
        row2_layout.addWidget(self.inp_descricao)
        editor_layout.addLayout(row2_layout)

        self.txt_codigo = CodeEditorWidget()
        self.txt_codigo.editor.setPlaceholderText("# Escreva seu código PowerShell aqui...\n\nWrite-Output 'Olá, SARCC!'")

        self.highlighter = PowerShellHighlighter(self.txt_codigo.editor.document())
        editor_layout.addWidget(self.txt_codigo)

        action_layout = QHBoxLayout()

        self.btn_exportar = QPushButton("📤 Exportar")
        self.btn_exportar.setFixedHeight(32)
        self.btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_exportar.setStyleSheet("background-color: #666666; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_exportar.clicked.connect(self.export_script)
        self.btn_exportar.setToolTip("Exporta o script atual ou todos os selecionados na lista")

        self.btn_excluir = QPushButton("🗑️ Excluir")
        self.btn_excluir.setFixedHeight(32)
        self.btn_excluir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_excluir.setStyleSheet("background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_excluir.clicked.connect(self.delete_script)
        self.btn_excluir.setEnabled(False)

        self.btn_salvar = QPushButton("💾 Salvar Script")
        self.btn_salvar.setFixedHeight(32)
        self.btn_salvar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salvar.setStyleSheet("background-color: #1e8a5e; color: white; padding: 0 20px; font-weight: bold; border-radius: 4px;")
        self.btn_salvar.clicked.connect(self.save_script)

        action_layout.addStretch()
        action_layout.addWidget(self.btn_exportar)
        action_layout.addWidget(self.btn_excluir)
        action_layout.addWidget(self.btn_salvar)
        editor_layout.addLayout(action_layout)

        splitter.addWidget(editor_group)
        splitter.setSizes([350, 650])
        layout.addWidget(splitter)

    def load_scripts_list(self):
        self.tree_scripts.clear()
        scripts = self.repo.list_all()

        categorias_dict = {}
        for s in scripts:
            cat = s[3] if s[3] else "Outros"
            if cat not in categorias_dict:
                categorias_dict[cat] = []
            categorias_dict[cat].append(s)

        for cat in sorted(categorias_dict.keys()):
            cat_item = QTreeWidgetItem(self.tree_scripts, [f"📁 {cat}"])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            cat_item.setForeground(0, Qt.GlobalColor.gray)
            cat_item.setExpanded(True)

            for s in sorted(categorias_dict[cat], key=lambda x: x[1].lower()):
                script_id, nome, descricao, categoria, conteudo = s
                child_item = QTreeWidgetItem(cat_item, [f"📄 {nome}"])
                child_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "id": script_id,
                    "nome": nome,
                    "descricao": descricao,
                    "categoria": categoria,
                    "conteudo": conteudo
                })

        if self.inp_search.text().strip():
            self.filter_scripts(self.inp_search.text())

    def filter_scripts(self, text):
        search_text = text.lower().strip()
        for i in range(self.tree_scripts.topLevelItemCount()):
            cat_item = self.tree_scripts.topLevelItem(i)
            cat_has_visible_child = False

            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                script_name = child.text(0).lower()

                if search_text in script_name:
                    child.setHidden(False)
                    cat_has_visible_child = True
                else:
                    child.setHidden(True)

            cat_item.setHidden(not cat_has_visible_child)

    def prepare_new_script(self):
        self.current_script_id = None
        self.inp_nome.clear()
        self.inp_descricao.clear()
        self.cmb_categoria.setCurrentIndex(0)
        self.txt_codigo.setPlainText("")
        self.btn_excluir.setEnabled(False)
        self.tree_scripts.clearSelection()
        self.inp_nome.setFocus()

    def on_script_selected(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        self.current_script_id = data["id"]
        self.inp_nome.setText(data["nome"])
        self.inp_descricao.setText(data["descricao"] if data["descricao"] else "")

        cat = data.get("categoria") or "Outros"
        index = self.cmb_categoria.findText(cat)
        if index >= 0:
            self.cmb_categoria.setCurrentIndex(index)
        else:
            outros_idx = self.cmb_categoria.findText("Outros")
            if outros_idx >= 0:
                self.cmb_categoria.setCurrentIndex(outros_idx)

        self.txt_codigo.setPlainText(data["conteudo"] if data["conteudo"] else "")
        self.btn_excluir.setEnabled(True)

    def import_script(self):
        arquivos, _ = QFileDialog.getOpenFileNames(
            self, "Importar Scripts", "",
            "Arquivos Suportados (*.ps1 *.txt);;Todos os Arquivos (*.*)"
        )
        if not arquivos:
            return

        try:
            importados, atualizados = self.service.import_files(arquivos)
        except Exception as e:
            log.error(f"Falha ao importar scripts em lote: {e}", exc_info=True)
            QMessageBox.critical(self, "Erro na Importação", f"Ocorreu um erro durante a importação:\n{e}")
            return

        if importados > 0 or atualizados > 0:
            log.info(f"Importação concluída: {importados} novos, {atualizados} atualizados.")
            QMessageBox.information(
                self, "Importação Concluída",
                f"Processamento finalizado:\n• Novos importados: {importados}\n• Atualizados: {atualizados}"
            )
            self.load_scripts_list()
            self.prepare_new_script()

    def export_script(self):
        selected_items = self.tree_scripts.selectedItems()
        script_items = [item.data(0, Qt.ItemDataRole.UserRole) for item in selected_items if item.data(0, Qt.ItemDataRole.UserRole)]

        if len(script_items) > 1:
            pasta_destino = QFileDialog.getExistingDirectory(self, "Selecione a Pasta de Destino para os Scripts")
            if not pasta_destino:
                return

            try:
                sucesso = self.service.export_to_directory(script_items, pasta_destino)
                QMessageBox.information(self, "Exportação em Lote", f"{sucesso} arquivo(s) gerados na pasta selecionada!")
            except Exception as e:
                log.error(f"Falha na exportação em lote: {e}", exc_info=True)
                QMessageBox.critical(self, "Erro na Exportação", f"Falha ao exportar scripts:\n{e}")
        else:
            conteudo = self.txt_codigo.toPlainText().strip()
            if not conteudo:
                QMessageBox.warning(self, "Aviso", "Não há código no editor para ser exportado.")
                return

            nome_sugerido = sanitize_filename(self.inp_nome.text().strip(), default="Script_SARCC")
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Exportar Script", f"{nome_sugerido}.ps1",
                "PowerShell Script (*.ps1);;Arquivo de Texto (*.txt)"
            )

            if file_path:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(conteudo)
                    QMessageBox.information(self, "Sucesso", "Script exportado e salvo com sucesso!")
                except Exception as e:
                    log.error(f"Falha ao salvar arquivo exportado em '{file_path}': {e}", exc_info=True)
                    QMessageBox.critical(self, "Erro na Exportação", f"Falha ao salvar o arquivo:\n{e}")

    def save_script(self):
        nome = self.inp_nome.text().strip()
        descricao = self.inp_descricao.text().strip()
        categoria = self.cmb_categoria.currentText()
        conteudo = self.txt_codigo.toPlainText().strip()

        if not nome:
            QMessageBox.warning(self, "Aviso", "O nome do script é obrigatório.")
            return
        if not conteudo:
            QMessageBox.warning(self, "Aviso", "O código do script não pode estar vazio.")
            return

        try:
            if self.current_script_id is None:
                self.repo.create(nome, descricao, categoria, conteudo)
                log.info(f"Novo script criado: '{nome}' (categoria: {categoria})")
                QMessageBox.information(self, "Sucesso", "Novo script criado com sucesso!")
            else:
                self.repo.update(self.current_script_id, nome, descricao, categoria, conteudo)
                log.info(f"Script atualizado: '{nome}' (id={self.current_script_id})")
                QMessageBox.information(self, "Sucesso", "Script atualizado com sucesso!")
        except Exception as e:
            log.error(f"Falha ao salvar script '{nome}': {e}", exc_info=True)
            QMessageBox.critical(self, "Erro ao Salvar", f"Não foi possível salvar o script (verifique se o nome já existe):\n{e}")
            return

        self.load_scripts_list()

        for i in range(self.tree_scripts.topLevelItemCount()):
            cat_item = self.tree_scripts.topLevelItem(i)
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole)["nome"] == nome:
                    self.tree_scripts.setCurrentItem(child)
                    self.on_script_selected(child, 0)
                    break

    def delete_script(self):
        if self.current_script_id is None:
            return

        reply = QMessageBox.question(
            self, "Excluir",
            "Tem certeza que deseja excluir este script permanentemente?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                script_id = self.current_script_id
                self.repo.delete(script_id)
                log.info(f"Script excluído: id={script_id}")
                QMessageBox.information(self, "Excluído", "Script removido do banco de dados.")
                self.prepare_new_script()
                self.load_scripts_list()
            except Exception as e:
                log.error(f"Falha ao excluir script id={self.current_script_id}: {e}", exc_info=True)
                QMessageBox.critical(self, "Erro ao Excluir", f"Não foi possível remover o script:\n{e}")

    def showEvent(self, event):
        super().showEvent(event)
        self.load_scripts_list()
