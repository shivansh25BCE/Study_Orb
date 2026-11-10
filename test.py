import sys
import math
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPolygon

class PropShowcaseBot(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(140, 130) 
        
        self.tick_counter = 0
        self.prop_index = 0
        self.prop_names = ["Ceramic Tea", "Sekiro Katana", "ESP32 Antenna", "Fabric Grass Block"]
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(30)

    def update_animation(self):
        self.tick_counter += 1
        self.update()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.prop_index = (self.prop_index + 1) % len(self.prop_names)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw current prop name text
        painter.setPen(QColor(169, 177, 214))
        font = painter.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 115, self.width(), 15, Qt.AlignmentFlag.AlignCenter, f"Prop: {self.prop_names[self.prop_index]}")
        
        bob_y = int(math.sin(self.tick_counter * 0.15) * 2)
        
        # Center the bot and shift down for head clearance
        painter.translate(25, 30)
        
        # Base Bot Drawing
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 30, 35)))
        painter.drawRoundedRect(15, 54, 18, 18, 4, 4)
        painter.drawRoundedRect(57, 54, 18, 18, 4, 4)
        
        painter.setBrush(QBrush(QColor(136, 163, 140)))
        painter.drawRoundedRect(9, 12, 72, 48, 12, 12)
        
        painter.setBrush(QBrush(QColor(10, 10, 15)))
        painter.drawRoundedRect(16, 18, 57, 36, 7, 7)
        
        painter.setPen(QColor(16, 185, 129))
        font.setPointSize(18)
        painter.setFont(font)
        
        painter.save()
        painter.translate(0, bob_y)
        painter.drawText(16, 18, 57, 36, Qt.AlignmentFlag.AlignCenter, "U_U")
        painter.restore()
        
        # Prop Coordinate Base
        px, py = 45, 12 
        
        painter.setPen(Qt.PenStyle.NoPen)
        
        if self.prop_index == 0: # Tea
            cup_x = px - 10
            cup_y = py - 10
            steam_y = (self.tick_counter % 60) * 0.3
            steam_alpha = max(0, 200 - int((steam_y / 18.0) * 200))
            painter.setPen(QPen(QColor(255, 255, 255, steam_alpha), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            steam_offset = math.sin(self.tick_counter * 0.1) * 3
            painter.drawArc(int(cup_x + 6 + steam_offset), int(cup_y - 5 - steam_y), 8, 10, 90 * 16, 180 * 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(240, 235, 225)))
            painter.drawRoundedRect(cup_x, cup_y, 20, 14, 3, 3)
            painter.setBrush(QBrush(QColor(40, 20, 10)))
            painter.drawEllipse(cup_x + 2, cup_y - 2, 16, 4)
            
        elif self.prop_index == 1: # Sekiro Katana with Sakura
            # Blade
            painter.setBrush(QBrush(QColor(200, 200, 205)))
            painter.drawRect(px - 10, py - 5, 55, 4)
            # Handle wrapping
            painter.setBrush(QBrush(QColor(40, 40, 45)))
            painter.drawRect(px - 40, py - 5, 30, 4)
            # Crossguard
            painter.setBrush(QBrush(QColor(218, 165, 32)))
            painter.drawRect(px - 12, py - 9, 3, 12)
            # Pommel accent
            painter.setBrush(QBrush(QColor(218, 165, 32)))
            painter.drawRect(px - 42, py - 5, 2, 4)
            
            # Tiny Sakura resting on the blade
            sx, sy = px + 10, py - 7
            painter.setBrush(QBrush(QColor(255, 183, 197))) # Soft Pink
            painter.drawEllipse(sx - 3, sy - 3, 5, 5) # Top-left petal
            painter.drawEllipse(sx + 1, sy - 3, 5, 5) # Top-right petal
            painter.drawEllipse(sx - 3, sy + 1, 5, 5) # Bottom-left petal
            painter.drawEllipse(sx + 1, sy + 1, 5, 5) # Bottom-right petal
            painter.setBrush(QBrush(QColor(255, 255, 255))) # White center
            painter.drawEllipse(sx - 1, sy - 1, 3, 3)
            
        elif self.prop_index == 2: # ESP32 Antenna
            painter.setBrush(QBrush(QColor(46, 139, 87))) # PCB Green
            painter.drawRect(px - 8, py - 10, 16, 10)
            painter.setPen(QPen(QColor(150, 150, 150), 2))
            painter.drawLine(px, py - 10, px, py - 24)
            # Blinking TX/RX LED
            if self.tick_counter % 20 < 10:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 50, 50)))
                painter.drawEllipse(px - 2, py - 26, 4, 4)
                
        elif self.prop_index == 3: # Grass Block
            painter.setBrush(QBrush(QColor(101, 67, 33))) # Dirt
            painter.drawRect(px - 10, py - 18, 20, 18)
            painter.setBrush(QBrush(QColor(113, 175, 71))) # Grass top
            painter.drawRect(px - 10, py - 18, 20, 6)
            painter.drawRect(px - 10, py - 12, 4, 3) # Grass overhang
            painter.drawRect(px + 4, py - 12, 5, 4)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = PropShowcaseBot()
    w.show()
    sys.exit(app.exec())