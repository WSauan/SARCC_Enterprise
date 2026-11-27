from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget


class DonutChartWidget(QWidget):
    def __init__(self, title="Status das Execuções", parent=None):
        super().__init__(parent)
        self.title = title
        self.data = {"SUCESSO": 0, "ALERTA": 0, "FALHA": 0}
        self.colors = {"SUCESSO": QColor("#4CAF50"), "ALERTA": QColor("#f0ad4e"), "FALHA": QColor("#d9534f")}
        self.setMinimumSize(350, 350)

    def set_data(self, success, alert, fail):
        self.data["SUCESSO"] = success
        self.data["ALERTA"] = alert
        self.data["FALHA"] = fail
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(self.data.values())

        painter.setPen(QColor("#e0e0e0"))
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.drawText(0, 10, self.width(), 30, Qt.AlignmentFlag.AlignCenter, self.title)

        if total == 0:
            painter.setPen(QColor("#888"))
            painter.drawText(0, 0, self.width(), self.height(), Qt.AlignmentFlag.AlignCenter, "Nenhum dado no período")
            return

        rect = QRectF(75, 50, 200, 200)
        start_angle = 90 * 16

        for key in ["SUCESSO", "ALERTA", "FALHA"]:
            count = self.data[key]
            if count == 0:
                continue

            span_angle = int((count / total) * 360 * 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.colors[key]))
            painter.drawPie(rect, start_angle, -span_angle)
            start_angle -= span_angle

        painter.setBrush(QBrush(QColor("#1e1e1e")))
        painter.drawEllipse(QRectF(115, 90, 120, 120))

        painter.setPen(QColor("#e0e0e0"))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        painter.drawText(QRectF(115, 90, 120, 120), Qt.AlignmentFlag.AlignCenter, str(total))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRectF(115, 120, 120, 120), Qt.AlignmentFlag.AlignCenter, "Execuções")

        # --- Legenda Vertical ---
        start_x = 120
        start_y = 260
        espacamento_y = 25

        for i, key in enumerate(["SUCESSO", "ALERTA", "FALHA"]):
            y = start_y + (i * espacamento_y)
            painter.setBrush(QBrush(self.colors[key]))
            painter.drawRect(start_x, y, 15, 15)
            painter.setPen(QColor("#e0e0e0"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(start_x + 25, y + 12, f"{key.capitalize()} ({self.data[key]})")


class BarChartWidget(QWidget):
    def __init__(self, title="Top 5 Scripts Mais Executados", parent=None):
        super().__init__(parent)
        self.title = title
        self.data = []
        self.setMinimumSize(400, 250)

    def set_data(self, data_list):
        self.data = data_list[:5]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Título
        painter.setPen(QColor("#e0e0e0"))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 20, self.width(), 30, Qt.AlignmentFlag.AlignCenter, self.title)

        if not self.data:
            painter.setPen(QColor("#888"))
            painter.drawText(0, 0, self.width(), self.height(), Qt.AlignmentFlag.AlignCenter, "Nenhum dado no período")
            return

        max_val = max([d[1] for d in self.data]) if self.data else 1
        bar_height = 25
        spacing = 15
        start_y = 60
        label_width = 200

        for i, (name, count) in enumerate(self.data):
            y = start_y + i * (bar_height + spacing)

            # 1. Desenha o Nome
            painter.setPen(QColor("#e0e0e0"))
            painter.setFont(QFont("Arial", 10))
            metrics = painter.fontMetrics()
            elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, label_width - 10)
            painter.drawText(10, y, label_width, bar_height, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_name)

            # 2. Desenha o Fundo da Barra
            bar_max_width = self.width() - label_width - 60
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#333333")))
            painter.drawRoundedRect(label_width + 10, y, bar_max_width, bar_height, 4, 4)

            # 3. Desenha o Preenchimento da Barra
            fill_width = int((count / max_val) * bar_max_width)
            if fill_width > 0:
                painter.setBrush(QBrush(QColor("#2a7de1")))
                painter.drawRoundedRect(label_width + 10, y, fill_width, bar_height, 4, 4)

            # 4. Desenha o Número (Sempre no final da barra, em branco)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))

            # A posição X é calculada com base no final da barra (label_width + 10 + bar_max_width)
            # O "- 25" é a margem para o texto não colar na borda
            text_x = label_width + 10 + bar_max_width - 25
            painter.drawText(text_x, y, 20, bar_height, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(count))
