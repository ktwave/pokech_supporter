from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def _table_style() -> str:
    return (
        "QTableWidget { background: #2a2a2a; color: #e8e8e8; gridline-color: #444; "
        "font-size: 11px; border: 1px solid #444; border-radius: 4px; }"
        "QHeaderView::section { background: #353535; color: #ccc; padding: 4px; "
        "border: 1px solid #444; font-weight: bold; }"
    )


class OpponentStatsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("opponentStatsPanel")
        self.setStyleSheet("#opponentStatsPanel { background: transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._title = QLabel("対面サポート統計")
        self._title.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
        lay.addWidget(self._title)

        self._message_browser = QTextBrowser()
        self._message_browser.setOpenExternalLinks(False)
        self._message_browser.setStyleSheet(
            "QTextBrowser { background: #2a2a2a; color: #ddd; border: 1px solid #444; "
            "border-radius: 4px; font-size: 12px; }"
        )
        lay.addWidget(self._message_browser, 1)

        self._stats_scroll = QScrollArea()
        self._stats_scroll.setWidgetResizable(True)
        self._stats_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stats_scroll.hide()

        self._stats_inner = QWidget()
        inner = QVBoxLayout(self._stats_inner)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(4)

        self._poke_name_label = QLabel("")
        self._poke_name_label.setStyleSheet(
            "color: #f0f0f0; font-size: 13px; font-weight: bold; margin-bottom: 4px;"
        )
        inner.addWidget(self._poke_name_label)

        self._section_tables: dict[str, QTableWidget] = {}
        for key, title in (
            ("わざ", "わざ"),
            ("もちもの", "もちもの"),
            ("とくせい", "とくせい"),
            ("せいかく", "せいかく"),
        ):
            st = QLabel(title)
            st.setStyleSheet(
                "color: #ccc; font-size: 12px; font-weight: bold; margin-top: 6px;"
            )
            inner.addWidget(st)
            tb = QTableWidget(0, 2)
            tb.setHorizontalHeaderLabels(["名前", "採用率"])
            tb.setAlternatingRowColors(True)
            tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tb.setSelectionMode(QAbstractItemView.NoSelection)
            tb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tb.verticalHeader().setVisible(False)
            tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            tb.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            tb.setMaximumHeight(160)
            tb.setStyleSheet(_table_style())
            tb.hide()
            inner.addWidget(tb)
            self._section_tables[key] = tb

        ev_title = QLabel("能力ポイント配分")
        ev_title.setStyleSheet(
            "color: #ccc; font-size: 12px; font-weight: bold; margin-top: 8px;"
        )
        inner.addWidget(ev_title)

        self._ev_table = QTableWidget(0, 7)
        self._ev_table.setHorizontalHeaderLabels(
            ["H", "A", "B", "C", "D", "S", "採用率"]
        )
        self._ev_table.setAlternatingRowColors(True)
        self._ev_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._ev_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._ev_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ev_table.verticalHeader().setVisible(False)
        self._ev_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._ev_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self._ev_table.setMaximumHeight(260)
        self._ev_table.setStyleSheet(_table_style())
        self._ev_table.hide()
        inner.addWidget(self._ev_table)

        inner.addStretch(1)
        self._stats_scroll.setWidget(self._stats_inner)
        lay.addWidget(self._stats_scroll, 1)

    @staticmethod
    def _fill_name_rate_table(table: QTableWidget, rows: list[dict], max_rows: int = 14):
        table.setRowCount(0)
        if not rows:
            table.insertRow(0)
            na = QTableWidgetItem("—")
            nb = QTableWidgetItem("データなし")
            for it in (na, nb):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(0, 0, na)
            table.setItem(0, 1, nb)
            table.show()
            return
        for i, r in enumerate(rows[:max_rows]):
            table.insertRow(i)
            n = QTableWidgetItem(str(r.get("名前", "")))
            p = QTableWidgetItem(str(r.get("採用率", "")))
            for it in (n, p):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            n.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
            table.setItem(i, 0, n)
            table.setItem(i, 1, p)
        table.resizeRowsToContents()
        table.show()

    def _clear_stat_sections(self):
        self._poke_name_label.clear()
        for tb in self._section_tables.values():
            tb.setRowCount(0)
            tb.hide()
        self._ev_table.setRowCount(0)
        self._ev_table.hide()

    def _fill_ev_table(self, rows: list[dict]):
        self._ev_table.setRowCount(0)
        if not rows:
            self._ev_table.hide()
            return
        self._ev_table.show()
        for i, r in enumerate(rows[:10]):
            self._ev_table.insertRow(i)
            vals = [
                r.get("H", ""),
                r.get("A", ""),
                r.get("B", ""),
                r.get("C", ""),
                r.get("D", ""),
                r.get("S", ""),
                r.get("採用率", ""),
            ]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                self._ev_table.setItem(i, col, it)
        self._ev_table.resizeRowsToContents()

    def show_idle(self, message: str = "バトル中に対面が判明すると表示されます。"):
        self._clear_stat_sections()
        self._stats_scroll.hide()
        self._message_browser.setHtml(f"<p style='color:#888'>{escape(message)}</p>")
        self._message_browser.show()

    def show_loading(self, name: str):
        self._clear_stat_sections()
        self._stats_scroll.hide()
        self._message_browser.setHtml(
            f"<p style='color:#aaa'>読み込み中… <b>{escape(name)}</b></p>"
        )
        self._message_browser.show()

    def show_error(self, name: str, err: str):
        self._clear_stat_sections()
        self._stats_scroll.hide()
        self._message_browser.setHtml(
            f"<p style='color:#f88'><b>{escape(name)}</b><br/>{escape(err)}</p>"
        )
        self._message_browser.show()

    def show_stats(self, data: dict):
        self._message_browser.hide()
        self._poke_name_label.setText(data.get("ポケモン名") or "")
        for key in ("わざ", "もちもの", "とくせい", "せいかく"):
            self._fill_name_rate_table(
                self._section_tables[key], data.get(key) or []
            )
        self._fill_ev_table(data.get("能力ポイント配分") or [])
        self._stats_scroll.show()
