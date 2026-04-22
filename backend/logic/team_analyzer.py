"""
<summary>以前の成功していたアルゴリズムを完全再現した形状認識モジュール</summary>
"""
import re
import cv2
import os
import glob
import numpy as np
from backend.config.constants import Config


def _normalize_ocr_label(text: str) -> str:
    if not text:
        return ""
    s = text.replace("\n", "").replace("\r", "").strip()
    s = re.sub(r"[\s|｜「」『』]+", "", s)
    return s


class TeamAnalyzer:
    def __init__(self):
        self.kernel = np.ones((2, 2), np.uint8)
        self.templates = {}
        self._load_templates()

    def _load_templates(self):
        """<summary>アイコンを一度75x75の低解像度にしてからエッジ抽出を行いキャッシュする</summary>"""
        if not os.path.exists(Config.ICON_DIR): return
        
        files = glob.glob(os.path.join(Config.ICON_DIR, "*.png"))
        for path in files:
            name = os.path.splitext(os.path.basename(path))[0]
            try:
                img_array = np.fromfile(path, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img is not None:
                    # 重要：一度 75x75 にリサイズしてゲーム画面の粗さに合わせる
                    img_res = cv2.resize(img, (75, 75))
                    self.templates[name] = self._preprocess_shape_only(img_res)
            except: continue

    def _preprocess_shape_only(self, image):
        """<summary>以前の成功ロジック：2倍拡大 -> グレースケール -> 鮮鋭化 -> エッジ -> 膨張</summary>"""
        scaled = cv2.resize(image, (150, 150), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
        
        # 鮮鋭化
        sharp_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(gray, -1, sharp_kernel)
        
        # Cannyエッジ抽出
        edges = cv2.Canny(sharpened, 30, 100)
        
        # 膨張
        dilated = cv2.dilate(edges, self.kernel, iterations=1)
        return dilated

    def identify_pokemon(self, frame, rois, candidate_names=None):
        results = []
        candidate_set = set(candidate_names) if candidate_names else None
        for x, y, w, h in rois:
            roi = frame[y:y+h, x:x+w]
            processed_roi = self._preprocess_shape_only(roi)

            best_match, max_score = "Empty", -1
            for name, template_edge in self.templates.items():
                if candidate_set is not None and name not in candidate_set:
                    continue
                res = cv2.matchTemplate(processed_roi, template_edge, cv2.TM_CCOEFF_NORMED)
                _, score, _, _ = cv2.minMaxLoc(res)
                if score > max_score:
                    max_score, best_match = score, name

            if max_score < Config.MATCH_THRESHOLD:
                best_match = "Empty"
            results.append(best_match)
        return results

    @staticmethod
    def resolve_ocr_label_to_party(ocr_label: str, party: list[str]) -> str:
        """
        OCRで得た表示名を、見せ合いで確定済みのパーティ表記（アイコン由来の日本語名）に寄せる。
        例: 画面が「ロトム」でも、パーティに「ロトム ウォッシュロトム」だけがいればそれを採用する。
        """
        if not party:
            return "Empty"
        ocr = _normalize_ocr_label(ocr_label)
        if not ocr:
            return "Empty"
        for p in party:
            if not p or p == "Empty":
                continue
            pn = _normalize_ocr_label(p)
            if pn == ocr:
                return p
        matches = []
        for p in party:
            if not p or p == "Empty":
                continue
            pn = _normalize_ocr_label(p)
            if not pn:
                continue
            if ocr in pn:
                matches.append(p)
            elif pn in ocr:
                matches.append(p)
        if not matches:
            return "Empty"
        if len(matches) == 1:
            return matches[0]
        uniq = list(dict.fromkeys(matches))

        def _rank(m: str) -> tuple:
            try:
                pi = party.index(m)
            except ValueError:
                pi = 999
            return (-len(m), pi)

        uniq.sort(key=_rank)
        return uniq[0]

    def identify_best_among_candidates(self, frame, roi, candidate_names, min_score, min_margin):
        """<summary>候補限定で最高スコアを取り、2位との差が足りなければ Empty</summary>"""
        if not candidate_names:
            return "Empty", -1.0, -1.0
        x, y, w, h = roi
        roi_img = frame[y:y+h, x:x+w]
        if roi_img is None or roi_img.size == 0:
            return "Empty", -1.0, -1.0
        processed_roi = self._preprocess_shape_only(roi_img)

        scored = []
        for name in candidate_names:
            template_edge = self.templates.get(name)
            if template_edge is None:
                continue
            res = cv2.matchTemplate(processed_roi, template_edge, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(res)
            scored.append((name, float(score)))

        if not scored:
            return "Empty", -1.0, -1.0
        scored.sort(key=lambda t: t[1], reverse=True)
        best_name, best_s = scored[0]
        second_s = scored[1][1] if len(scored) > 1 else -1.0
        margin = best_s - second_s
        if best_s < min_score or margin < min_margin:
            return "Empty", best_s, second_s
        return best_name, best_s, second_s

    def _majority_vote(self, results):
        if not results: return []
        final_list = []
        num_slots = len(results[0])
        from collections import Counter
        for i in range(num_slots):
            slot_candidates = [r[i] for r in results if i < len(r)]
            counts = Counter(slot_candidates)
            winner = counts.most_common(1)[0][0] if counts else "Empty"
            final_list.append(winner)
        return final_list