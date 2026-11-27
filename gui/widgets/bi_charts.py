from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget


class DonutChartWidget(QWidget):
    def __init__(self, title="Status das Execuções", parent=None):
        super().__init__(parent)
        self.title = title
        self.data = {"SUCESSO": 0, "ALERTA": 0, "FALHA": 0}
        self.setMinimumSize(300, 250)

    def set_data(self, success, alert, fail):
        self.data["SUCESSO"] = success
        self.data["ALERTA"] = alert
        self.data["FALHA"] = fail
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(self.data.values())

        # Desenha o Título
        painter.setPen(QColor("#e0e0e0"))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 20, self.width(), 30, Qt.AlignmentFlag.AlignCenter, self.title)

        if total == 0:
            painter.setPen(QColor("#888"))
            painter.drawText(0, 0, self.width(), self.height(), Qt.AlignmentFlag.AlignCenter, "Nenhum dado no período")
            return

        # Configurações do Donut
        rect = QRectF(50, 50, 200, 200)
        start_angle = 90 * 16  # Começa no topo (12h)

        colors = {
            "SUCESSO": QColor("#4CAF50"),
            "ALERTA": QColor("#f0ad4e"),
            "FALHA": QColor("#d9534f")
        }

        # Desenha as fatias
        for key in ["SUCESSO", "ALERTA", "FALHA"]:
            count = self.data[key]
            if count == 0:
                continue

            span_angle = int((count / total) * 360 * 16)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(colors[key]))
            painter.drawPie(rect, start_angle, -span_angle) # Negativo para sentido horário
            start_angle -= span_angle

        # Desenha o buraco do Donut
        painter.setBrush(QBrush(QColor("#1e1e1e"))) # Fundo igual ao tema
        painter.drawEllipse(QRectF(90, 90, 120, 120))

        # Desenha o Total no centro
        painter.setPen(QColor("#e0e0e0"))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        painter.drawText(QRectF(90, 90, 120, 120), Qt.AlignmentFlag.AlignCenter, str(total))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRectF(90, 120, 120, 120), Qt.AlignmentFlag.AlignCenter, "Execuções")


class BarChartWidget(QWidget):
    def __init__(self, title="Top 5 Scripts Mais Executados", parent=None):
        super().__init__(parent)
        self.title = title
        self.data = [] # Lista de tuplas (nome_script, quantidade)
        self.setMinimumSize(400, 250)

    def set_data(self, data_list):
        self.data = data_list[:5] # Pega apenas os top 5
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Desenha o Título
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
        label_width = 150

        for i, (name, count) in enumerate(self.data):
            y = start_y + i * (bar_height + spacing)

            # Desenha o nome do script (label)
            painter.setPen(QColor("#e0e0e0"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(10, y, label_width, bar_height, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

            # Desenha o fundo da barra
            bar_max_width = self.width() - label_width - 60
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#333333")))
            painter.drawRoundedRect(label_width + 10, y, bar_max_width, bar_height, 4, 4)

            # Desenha o preenchimento da barra
            fill_width = int((count / max_val) * bar_max_width)
            if fill_width > 0:
                painter.setBrush(QBrush(QColor("#2a7de1")))
                painter.drawRoundedRect(label_width + 10, y, fill_width, bar_height, 4, 4)

            # Desenha o número no final da barra
            painter.setPen(QColor("#e0e0e0"))
            painter.drawText(label_width + 15 + fill_width, y, 50, bar_height, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(count))
