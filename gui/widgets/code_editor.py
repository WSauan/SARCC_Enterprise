from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QTextFormat, QTextDocument, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QPlainTextEdit, QTextEdit, QHBoxLayout,
    QLineEdit, QPushButton, QVBoxLayout, QLabel
)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNbrAreaWidth(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNbrAreaPaintEvent(event)


class InternalCodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.find_bar_ref = None

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()
        self.setFont(QFont("Consolas", 11))

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #282a36;
                color: #f8f8f2;
                border: none;
            }
        """)

    def lineNbrAreaWidth(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        space = 15 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNbrAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNbrAreaWidth(), cr.height()))

    def lineNbrAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#282a36"))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QColor("#6272a4"))
                painter.drawText(
                    0, top, self.lineNumberArea.width() - 8, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor("#44475a")
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            if self.find_bar_ref:
                self.find_bar_ref.toggle_view()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self.find_bar_ref and self.find_bar_ref.find_widget.isVisible():
            self.find_bar_ref.close_find_bar()
            event.accept()
        else:
            super().keyPressEvent(event)


class CodeEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.total_matches = 0
        self.current_match = 0

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(0)

        self.setStyleSheet("""
            CodeEditorWidget {
                border: 1px solid #444;
                border-radius: 4px;
                background-color: #282a36;
            }
        """)

        self.editor = InternalCodeEditor()
        main_layout.addWidget(self.editor)

        self.find_widget = QWidget()
        self.find_widget.setStyleSheet("""
            QWidget {
                background-color: #21222c;
                border-top: 1px solid #44475a;
                border-bottom: none; border-left: none; border-right: none;
            }
            QLabel { color: #f8f8f2; border: none; }
            QLineEdit {
                background-color: #282a36;
                color: #f8f8f2;
                border: 1px solid #6272a4;
                padding: 4px;
                border-radius: 2px;
            }
            QPushButton {
                background-color: transparent;
                color: #f8f8f2;
                border: none;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover { 
                background-color: #44475a; 
                border-radius: 2px;
            }
        """)

        find_layout = QHBoxLayout(self.find_widget)
        find_layout.setContentsMargins(8, 4, 8, 4)

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Localizar...")
        self.find_input.textChanged.connect(self.update_count)
        self.find_input.returnPressed.connect(self.find_next)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #6272a4; margin-right: 10px;")

        btn_prev = QPushButton("↑")
        btn_prev.setToolTip("Anterior")
        btn_prev.clicked.connect(self.find_prev)

        btn_next = QPushButton("↓")
        btn_next.setToolTip("Próximo")
        btn_next.clicked.connect(self.find_next)

        btn_close = QPushButton("✕")
        btn_close.clicked.connect(self.close_find_bar)

        find_layout.addWidget(self.find_input)
        find_layout.addWidget(self.lbl_count)
        find_layout.addWidget(btn_prev)
        find_layout.addWidget(btn_next)
        find_layout.addWidget(btn_close)

        self.find_widget.setLayout(find_layout)
        self.find_widget.hide()
        main_layout.addWidget(self.find_widget)

        self.editor.find_bar_ref = self

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.find_widget.isVisible():
            self.close_find_bar()
            event.accept()
        else:
            super().keyPressEvent(event)

    def close_find_bar(self):
        self.find_widget.hide()
        self.editor.setFocus()

    def toggle_view(self):
        if self.find_widget.isVisible():
            self.close_find_bar()
        else:
            self.find_widget.show()
            self.find_input.setFocus()
            self.find_input.selectAll()
            self.update_count(self.find_input.text())

    def update_count(self, text):
        if not text:
            self.lbl_count.setText("")
            self.total_matches = 0
            self.current_match = 0
            return

        content = self.editor.toPlainText().lower()
        search_term = text.lower()
        self.total_matches = content.count(search_term)
        self.current_match = 0

        if self.total_matches > 0:
            self.lbl_count.setText(f"0 de {self.total_matches}")
        else:
            self.lbl_count.setText("Sem resultados")

    def update_label_position(self):
        if self.total_matches > 0:
            self.lbl_count.setText(f"{self.current_match} de {self.total_matches}")

    def find_next(self):
        text = self.find_input.text()
        if not text:
            return

        found = self.editor.find(text)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text)

        if found and self.total_matches > 0:
            self.current_match = (self.current_match % self.total_matches) + 1
            self.update_label_position()

    def find_prev(self):
        text = self.find_input.text()
        if not text:
            return

        found = self.editor.find(text, QTextDocument.FindFlag.FindBackward)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text, QTextDocument.FindFlag.FindBackward)

        if found and self.total_matches > 0:
            self.current_match = self.total_matches if self.current_match <= 1 else self.current_match - 1
            self.update_label_position()

    def setPlainText(self, text):
        self.editor.setPlainText(text)
        self.update_count(self.find_input.text())

    def toPlainText(self):
        return self.editor.toPlainText()