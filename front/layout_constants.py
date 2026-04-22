"""
画面レイアウトの調整用定数です。見た目を変えたい場合は主にここの数値を編集してください。

- LEFT_SIDEBAR_MIN_WIDTH_PX … 左「対面サポート統計」パネルの最小幅
- TOP_ROW_OPP_PARTY_WIDTH_NUM / _DEN … 上段（映像の右）の「敵PT＋統計ラベル」列が
  ウィンドウ幅に対して占める割合（例: 3/20 ≒ 15%）。分子を大きくすると敵列が広がります。
- OPP_PARTY_ICON_CELL_MIN_WIDTH_PX … 敵PT1枠（アイコン）側の最小幅の目安
- OPP_PARTY_STAT_LABEL_MIN_WIDTH_PX … アイコン右の累計統計ラベル列の最小幅の目安
- WINDOW_DEFAULT_WIDTH_PX / WINDOW_DEFAULT_HEIGHT_PX … メインウィンドウ起動時のサイズ
- opp_column_outer_width() … 上記 NUM/DEN に基づく列幅。上段・下段で同じ関数を使うとリサイズ時も揃う
"""
from __future__ import annotations

WINDOW_DEFAULT_WIDTH_PX = 1920
WINDOW_DEFAULT_HEIGHT_PX = 1080

LEFT_SIDEBAR_MIN_WIDTH_PX = 280

TOP_ROW_OPP_PARTY_WIDTH_NUM = 4
TOP_ROW_OPP_PARTY_WIDTH_DEN = 20

OPP_PARTY_ICON_CELL_MIN_WIDTH_PX = 108
OPP_PARTY_STAT_LABEL_MIN_WIDTH_PX = 108


def opp_column_outer_width(
    panel_width: int,
    *,
    num: int | None = None,
    den: int | None = None,
) -> int:
    """上段の敵PT列・下段のカウントダウン列など、右パネル内で同じ幅に揃える列の幅（px）。"""
    n = TOP_ROW_OPP_PARTY_WIDTH_NUM if num is None else int(num)
    d = TOP_ROW_OPP_PARTY_WIDTH_DEN if den is None else int(den)
    n = max(1, n)
    d = max(n + 1, d)
    w = max(0, int(panel_width))
    return max(1, int(round(w * n / d)))
