"""
見せ合いで確定済みの敵パーティ名（最大6）だけを候補に、
ROI画像と描画した名前のエッジを突き合わせて最も近い1体を選ぶ。
HUDフォントと完全一致しないため閾値はやや低め想定。
"""
from __future__ import annotations

import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.config.constants import Config


def _edge_like(gray_u8: np.ndarray) -> np.ndarray:
    g = cv2.resize(gray_u8, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return cv2.Canny(g, 40, 100)


def _roi_edges(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return _edge_like(gray)


def _pick_font_path() -> str:
    override = getattr(Config, "OPP_ACTIVE_NAME_FONT_PATH", "") or ""
    if override and os.path.isfile(override):
        return override
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("meiryo.ttc", "YuGothM.ttc", "msgothic.ttc", "yugothic.ttf"):
        p = os.path.join(windir, "Fonts", name)
        if os.path.isfile(p):
            return p
    return ""


def render_match_best_party(roi_bgr: np.ndarray, party_names: list[str]) -> tuple[str, float]:
    """
    party_names のみを候補にテンプレート照合。
    戻り値: (パーティ表記の名前 or "Empty", 最高スコア)
    """
    if roi_bgr is None or roi_bgr.size == 0 or not party_names:
        return "Empty", -1.0
    font_path = _pick_font_path()
    if not font_path:
        return "Empty", -1.0

    proc = _roi_edges(roi_bgr)
    h, w = proc.shape[:2]
    thresh = float(getattr(Config, "OPP_ACTIVE_NAME_RENDER_THRESHOLD", 0.18))

    best_name, best_score = "Empty", -1.0
    for name in party_names:
        if not name or name == "Empty":
            continue
        local_best = -1.0
        for fs in range(10, 40, 2):
            try:
                img = Image.new("L", (max(w, 64), max(h, 24)), 0)
                dr = ImageDraw.Draw(img)
                font = ImageFont.truetype(font_path, fs)
                bbox = dr.textbbox((0, 0), name, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if tw <= 0 or th <= 0:
                    continue
                img = Image.new("L", (w, h), 0)
                dr = ImageDraw.Draw(img)
                tx = max(0, (w - tw) // 2)
                ty = max(0, (h - th) // 2)
                dr.text((tx, ty), name, font=font, fill=255)
                arr = np.array(img, dtype=np.uint8)
                e = _edge_like(arr)
                if e.shape != proc.shape:
                    e = cv2.resize(e, (w, h), interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(proc, e, cv2.TM_CCOEFF_NORMED)
                _, sc, _, _ = cv2.minMaxLoc(res)
                local_best = max(local_best, float(sc))
            except Exception:
                continue
        if local_best > best_score:
            best_score, best_name = local_best, name

    if best_score < thresh:
        return "Empty", best_score
    return best_name, best_score
