"""
<summary>余白をゼロに追い込んだアイコンスロット</summary>
"""
import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from backend.config.constants import Config


class PokemonSlotWidget(QWidget):
    """左クリック: ポケ徹URL。右クリック: 任意で手動追加メニュー（親が有効化）。"""

    clicked_with_name = Signal(str)
    party_manual_append_requested = Signal(str)
    selection_manual_pick_requested = Signal()

    def __init__(self, slot_number=None, parent=None):
        super().__init__(parent)
        self.slot_number = slot_number
        self._pokemon_name = None
        self._party_context_manual = False
        self._selection_context_manual = False
        self.init_ui()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def set_party_context_manual(self, enabled: bool):
        """敵6体列: 右クリックで「選出に手動追加」。"""
        self._party_context_manual = bool(enabled)

    def set_selection_context_manual(self, enabled: bool):
        """敵選出3枠: 右クリックで「リストから手動追加」。"""
        self._selection_context_manual = bool(enabled)

    def init_ui(self):
        layout = QVBoxLayout(self)
        # 余白と間隔を完全に0にする
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.icon_label = QLabel()
        # 親のサイズに合わせて伸縮させるため固定サイズを撤廃、または最小サイズ設定
        self.icon_label.setMinimumSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background-color: #cccccc; border: none;")
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.icon_label)
        # スロット自体の背景と枠
        self.setStyleSheet("border: 1px solid #333; background: #262626;")

    def update_pokemon(self, name):
        if not name or name == "Empty":
            self._pokemon_name = None
            self.icon_label.clear()
            return

        self._pokemon_name = name
        icon_path = os.path.join(Config.ICON_DIR, f"{name}.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            # ラベルの現在のサイズに合わせてスケーリング
            self.icon_label.setPixmap(pixmap.scaled(
                self.icon_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.icon_label.clear()
            self.icon_label.setText("?")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._pokemon_name:
            self.clicked_with_name.emit(self._pokemon_name)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        if not self._party_context_manual and not self._selection_context_manual:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        act_open = None
        if self._pokemon_name:
            act_open = menu.addAction("ポケ徹で開く")
        act_manual_party = None
        act_manual_pick = None
        if self._party_context_manual and self._pokemon_name:
            act_manual_party = menu.addAction("対面選出に手動で追加")
        if self._selection_context_manual:
            act_manual_pick = menu.addAction("選出リストから手動で追加…")
        if menu.actions():
            chosen = menu.exec(event.globalPos())
            if chosen is None:
                return
            if act_open and chosen == act_open and self._pokemon_name:
                self.clicked_with_name.emit(self._pokemon_name)
            elif act_manual_party and chosen == act_manual_party and self._pokemon_name:
                self.party_manual_append_requested.emit(self._pokemon_name)
            elif act_manual_pick and chosen == act_manual_pick:
                self.selection_manual_pick_requested.emit()
        else:
            super().contextMenuEvent(event)