"""
<summary>OCR（時間判定）と画像認識（選出完了判定）を使い分けるハイブリッド判定ロジック</summary>
"""
import cv2
import numpy as np
import os
import pytesseract
from backend.config.constants import Config
from backend.logic.opponent_name_render_match import render_match_best_party
from backend.logic.team_analyzer import TeamAnalyzer

# Tesseractのパス設定
pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

_NAME_OCR_EMPTY_LOGGED = False


def _tessdata_dir_config_suffix():
    """語データ(.traineddata)が存在するときだけ --tessdata-dir を付与する。"""
    tess_dir = os.path.join(Config.RESOURCES_DIR, "Tesseract-OCR", "tessdata")
    if not os.path.isdir(tess_dir):
        return ""
    try:
        names = os.listdir(tess_dir)
    except OSError:
        return ""
    if not any(n.endswith(".traineddata") for n in names):
        return ""
    return f' --tessdata-dir "{tess_dir}"'


def _opponent_name_binary_variants(crop_bgr):
    """HUDの差に耐える複数二値化パターン。"""
    gray0 = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    variants = []
    for scale in (2.5, 3.5):
        gray = cv2.resize(
            gray0, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
        m = float(gray.mean())
        if m < 128.0:
            _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(t)
        _, t2 = cv2.threshold(255 - gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        variants.append(t2)

    g3 = cv2.resize(gray0, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(g3)
    _, tc = cv2.threshold(cl, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(tc)
    _, tci = cv2.threshold(cl, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    variants.append(tci)
    _, tw = cv2.threshold(g3, 185, 255, cv2.THRESH_BINARY)
    variants.append(tw)
    _, tfix = cv2.threshold(g3, 150, 255, cv2.THRESH_BINARY_INV)
    variants.append(tfix)
    return variants


def _tesseract_collect_strings(img_bin, suffix, langs, psms):
    found = []
    for psm in psms:
        base = f"--psm {psm}"
        cfg = f"{base} {suffix}".strip() if suffix else base
        for lang in langs:
            try:
                t = pytesseract.image_to_string(img_bin, lang=lang, config=cfg).strip()
                if t:
                    found.append(t)
            except Exception:
                continue
    return found


class OcrProcessor:
    def __init__(self):
        """<summary>初期化時に1回だけトリガー画像をロードする</summary>"""
        self.trigger_templates = []
        self.num_templates = {}
        self.turn_start_template = None
        self.battle_end_template = None
        self._load_trigger_templates()
        self._load_turn_start_template()
        self._load_battle_end_template()

        self._load_num_templates()

    def _load_trigger_templates(self):
        """<summary>選出完了トリガー画像を複数読み込む（背景差分対策）</summary>"""
        for path in Config.TRIGGER_IMAGE_PATHS:
            if not os.path.exists(path):
                print(f"DEBUG: Trigger image NOT FOUND: {path}")
                continue
            try:
                img_array = np.fromfile(path, dtype=np.uint8)
                color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if color is None:
                    print(f"DEBUG: Trigger image load failed: {path}")
                    continue
                gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
                edge = cv2.Canny(gray, 40, 120)
                self.trigger_templates.append({"gray": gray, "edge": edge, "path": path})
                print(f"DEBUG: Trigger image loaded: {path}")
            except Exception as e:
                print(f"DEBUG: Failed to load trigger image: {e}")

    def _load_num_templates(self):
        """<summary>自選出番号(1/2/3)のテンプレート画像を読み込む</summary>"""
        for num, path in Config.NUM_TEMPLATE_PATHS.items():
            if not os.path.exists(path):
                print(f"DEBUG: Number template NOT FOUND: {path}")
                continue
            try:
                img_array = np.fromfile(path, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    print(f"DEBUG: Number template load failed: {path}")
                    continue
                _, img_bin = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY_INV)
                self.num_templates[num] = {
                    "gray": img,
                    "bin": img_bin
                }
                print(f"DEBUG: Number template loaded: {num} => {path}")
            except Exception as e:
                print(f"DEBUG: Number template exception ({num}): {e}")

    def _load_turn_start_template(self):
        """<summary>ターン開始トリガー画像を読み込む</summary>"""
        path = Config.TURN_START_IMAGE_PATH
        if not os.path.exists(path):
            print(f"DEBUG: Turn start image NOT FOUND: {path}")
            return
        try:
            img_array = np.fromfile(path, dtype=np.uint8)
            color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if color is None:
                print(f"DEBUG: Turn start image load failed: {path}")
                return
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            edge = cv2.Canny(gray, 40, 120)
            self.turn_start_template = {"gray": gray, "edge": edge}
            print(f"DEBUG: Turn start image loaded: {path}")
        except Exception as e:
            print(f"DEBUG: Failed to load turn start image: {e}")

    def _load_battle_end_template(self):
        """<summary>戦いの終了トリガー画像を読み込む</summary>"""
        path = Config.BATTLE_END_IMAGE_PATH
        if not os.path.exists(path):
            print(f"DEBUG: Battle end image NOT FOUND: {path}")
            return
        try:
            img_array = np.fromfile(path, dtype=np.uint8)
            color = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if color is None:
                print(f"DEBUG: Battle end image load failed: {path}")
                return
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            edge = cv2.Canny(gray, 40, 120)
            self.battle_end_template = {"gray": gray, "edge": edge}
            print(f"DEBUG: Battle end image loaded: {path}")
        except Exception as e:
            print(f"DEBUG: Failed to load battle end image: {e}")

    @staticmethod
    def read_text(frame, roi, lang='eng'):
        """<summary>指定ROIから文字を読み取る（主に時間表示用）</summary>"""
        x, y, w, h = roi
        crop = frame[y:y+h, x:x+w]
        
        # 以前の判定精度を維持する前処理
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
        
        config = "--psm 7"
        try:
            return pytesseract.image_to_string(thresh, lang=lang, config=config).strip()
        except:
            return ""

    @staticmethod
    def read_opponent_name_text(frame, roi=None, party_hints=None):
        """
        対面表示名の取得。ROIは Config.OPP_ACTIVE_NAME_ROI が既定。
        1) Tesseract 多段 OCR 2) 失敗時は敵6体名のみを候補に描画テンプレ照合（辞書照合）
        party_hints があれば OCR 候補の選別にも使う。
        """
        global _NAME_OCR_EMPTY_LOGGED
        r = roi if roi is not None else Config.OPP_ACTIVE_NAME_ROI
        x, y, w, h = r
        crop = frame[y : y + h, x : x + w]
        if crop is None or crop.size == 0:
            return ""
        suffix = _tessdata_dir_config_suffix()
        lang_pref = getattr(Config, "OPP_ACTIVE_NAME_OCR_LANG", "jpn")
        langs = [lang_pref, "jpn", "eng"]
        langs = list(dict.fromkeys(langs))
        psms = (7, 6, 13)

        candidates = []
        for img in _opponent_name_binary_variants(crop):
            candidates.extend(_tesseract_collect_strings(img, suffix, langs, psms))

        uniq = []
        for t in candidates:
            s = t.strip()
            if s and s not in uniq:
                uniq.append(s)

        ocr_choice = ""
        if uniq:
            if party_hints:
                best = ""
                best_key = (-1, -1)
                for c in uniq:
                    resolved = TeamAnalyzer.resolve_ocr_label_to_party(c, party_hints)
                    hit = 1 if resolved != "Empty" else 0
                    key = (hit, len(c.strip()))
                    if key > best_key:
                        best_key, best = key, c
                ocr_choice = best if best_key[0] == 1 else max(uniq, key=lambda s: len(s.strip()))
            else:
                ocr_choice = max(uniq, key=lambda s: len(s.strip()))

        ocr_resolved = (
            TeamAnalyzer.resolve_ocr_label_to_party(ocr_choice, party_hints)
            if (party_hints and ocr_choice)
            else ("Empty" if party_hints else "")
        )
        if party_hints and ocr_resolved != "Empty":
            return ocr_choice

        if party_hints:
            render_name, render_sc = render_match_best_party(crop, party_hints)
            if render_name != "Empty":
                return render_name

        if ocr_choice:
            return ocr_choice

        if not _NAME_OCR_EMPTY_LOGGED:
            _NAME_OCR_EMPTY_LOGGED = True
            td = os.path.join(Config.RESOURCES_DIR, "Tesseract-OCR", "tessdata")
            has_td = os.path.isdir(td) and any(
                n.endswith(".traineddata") for n in os.listdir(td)
            )
            print(
                "[OCR-NAME] OCRも辞書照合も失敗。確認: (1)ROI (2)jpn.traineddata "
                f"(3)同梱tessdataに語データあり={has_td} "
                "(4)OPP_ACTIVE_NAME_RENDER_THRESHOLD をやや下げる / OPP_ACTIVE_NAME_FONT_PATH でフォント指定"
            )
        return ""

    def is_target_time(self, frame, target="01:30"):
        """<summary>1:30判定（OCR）</summary>"""
        text = self.read_text(frame, Config.TIME_ROI)
        # 読めた時間はログに出す（デバッグ用）
        return target in text, text

    def is_waiting(self, frame):
        """<summary>画像マッチングによる選出完了判定</summary>"""
        if not self.trigger_templates:
            return False

        x, y, w, h = Config.TRIGGER_ROI
        roi = frame[y:y+h, x:x+w]
        if roi is None or roi.size == 0:
            return False

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_edge = cv2.Canny(roi_gray, 40, 120)
        best_score = -1.0

        for tpl in self.trigger_templates:
            tpl_gray = cv2.resize(tpl["gray"], (w, h), interpolation=cv2.INTER_AREA)
            tpl_edge = cv2.resize(tpl["edge"], (w, h), interpolation=cv2.INTER_AREA)

            res_gray = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            _, score_gray, _, _ = cv2.minMaxLoc(res_gray)

            res_edge = cv2.matchTemplate(roi_edge, tpl_edge, cv2.TM_CCOEFF_NORMED)
            _, score_edge, _, _ = cv2.minMaxLoc(res_edge)

            score = max(score_gray, score_edge)
            if score > best_score:
                best_score = score

        return best_score >= Config.TRIGGER_MATCH_THRESHOLD

    def detect_selection_number(self, frame, roi):
        """<summary>ROI内の選出番号(1/2/3)をテンプレートマッチングで判定する</summary>"""
        num, _ = self.detect_selection_number_with_score(frame, roi)
        return num

    def detect_selection_number_with_score(self, frame, roi):
        """<summary>ROI内の選出番号(1/2/3)と一致スコアを返す</summary>"""
        if not self.num_templates:
            return "", -1.0

        x, y, w, h = roi
        crop = frame[y:y+h, x:x+w]
        if crop is None or crop.size == 0:
            return "", -1.0

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, crop_bin = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

        best_num = ""
        best_score = -1.0
        score_map = {}

        for num, template_pack in self.num_templates.items():
            template_gray = cv2.resize(template_pack["gray"], (w, h), interpolation=cv2.INTER_AREA)
            template_bin = cv2.resize(template_pack["bin"], (w, h), interpolation=cv2.INTER_AREA)

            res_gray = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, score_gray, _, _ = cv2.minMaxLoc(res_gray)

            res_bin = cv2.matchTemplate(crop_bin, template_bin, cv2.TM_CCOEFF_NORMED)
            _, score_bin, _, _ = cv2.minMaxLoc(res_bin)

            score = max(score_gray, score_bin)
            score_map[num] = score
            if score > best_score:
                best_score = score
                best_num = num

        # スコアが低すぎる原因切り分けのために常時ログを残す
        print(
            f"[MY-SCORE] roi={roi} "
            f"1={score_map.get('1', -1):.3f} "
            f"2={score_map.get('2', -1):.3f} "
            f"3={score_map.get('3', -1):.3f} "
            f"best={best_num}:{best_score:.3f} th={Config.NUM_MATCH_THRESHOLD:.2f}"
        )

        if best_score >= Config.NUM_MATCH_THRESHOLD:
            return best_num, best_score
        return "", best_score

    def is_turn_start(self, frame):
        """<summary>ターン開始トリガーを画像マッチングで判定する</summary>"""
        is_match, _ = self.is_turn_start_with_score(frame)
        return is_match

    def is_turn_start_with_score(self, frame):
        """<summary>ターン開始トリガーの判定結果とスコアを返す</summary>"""
        if self.turn_start_template is None:
            return False, -1.0
        x, y, w, h = Config.TURN_START_ROI
        roi = frame[y:y+h, x:x+w]
        if roi is None or roi.size == 0:
            return False, -1.0

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_edge = cv2.Canny(roi_gray, 40, 120)

        tpl_gray = cv2.resize(self.turn_start_template["gray"], (w, h), interpolation=cv2.INTER_AREA)
        tpl_edge = cv2.resize(self.turn_start_template["edge"], (w, h), interpolation=cv2.INTER_AREA)

        res_gray = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, score_gray, _, _ = cv2.minMaxLoc(res_gray)
        res_edge = cv2.matchTemplate(roi_edge, tpl_edge, cv2.TM_CCOEFF_NORMED)
        _, score_edge, _, _ = cv2.minMaxLoc(res_edge)
        score = max(score_gray, score_edge)
        return score >= Config.TURN_START_MATCH_THRESHOLD, score

    def is_battle_end_with_score(self, frame):
        """<summary>戦いの終了トリガーの判定結果とスコアを返す</summary>"""
        if self.battle_end_template is None:
            return False, -1.0
        x, y, w, h = Config.BATTLE_END_ROI
        roi = frame[y:y+h, x:x+w]
        if roi is None or roi.size == 0:
            return False, -1.0

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_edge = cv2.Canny(roi_gray, 40, 120)

        tpl_gray = cv2.resize(self.battle_end_template["gray"], (w, h), interpolation=cv2.INTER_AREA)
        tpl_edge = cv2.resize(self.battle_end_template["edge"], (w, h), interpolation=cv2.INTER_AREA)

        res_gray = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, score_gray, _, _ = cv2.minMaxLoc(res_gray)
        res_edge = cv2.matchTemplate(roi_edge, tpl_edge, cv2.TM_CCOEFF_NORMED)
        _, score_edge, _, _ = cv2.minMaxLoc(res_edge)
        score = max(score_gray, score_edge)
        return score >= Config.BATTLE_END_MATCH_THRESHOLD, score