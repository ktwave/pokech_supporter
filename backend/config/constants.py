"""
<summary>アプリケーション全体で使用する定数管理クラス</summary>
"""
import os

class Config:
    # --- 既存のパス設定 ---
    BASE_DIR = os.getcwd()
    POKEMON_DATA_TSV_PATH = os.path.join(BASE_DIR, "database", "pokemons_data.tsv")
    PROFILE_STATS_DB_PATH = os.path.join(BASE_DIR, "database", "profile_stats.sqlite")
    RESOURCES_DIR = os.path.join(BASE_DIR, "resources")
    ICON_DIR = os.path.join(RESOURCES_DIR, "icons")
    FFMPEG_PATH = os.path.join(RESOURCES_DIR, "ffmpeg", "bin", "ffmpeg.exe")
    # Tesseractの実行ファイルパス
    TESSERACT_PATH = os.path.join(RESOURCES_DIR, "Tesseract-OCR", "tesseract.exe")

    # --- 映像設定 ---
    VIDEO_DEVICE = "AVerMedia HD Capture GC573 1"
    WIDTH = 1280
    HEIGHT = 720
    MATCH_THRESHOLD = 0.2

    # --- OCR・自動スキャン用座標 (x, y, w, h) ---
    # 1. 相手のパーティ（見せ合い6体）: 1列に縦並び
    OPPONENT_ROIS = [
        (1078, 103, 75, 75),
        (1078, 187, 75, 75),
        (1078, 271, 75, 75),
        (1078, 355, 75, 75),
        (1078, 439, 75, 75),
        (1078, 523, 75, 75)
    ]

    # 選出残時間 (01:30 判定用)
    TIME_ROI = (211, 26, 78, 20)
    
    # 自分の選出タイミング (「待機中」判定用)
    MY_STATUS_ROI = (270, 625, 52, 17)
    
    # 選出番号 (60, 126～551)
    MY_SELECT_NUM_ROIS = [
        (205, 125, 30, 36), 
        (205, 209, 30, 36), 
        (205, 293, 30, 36),
        (205, 377, 30, 36), 
        (205, 461, 30, 36), 
        (205, 545, 30, 36)
    ]
    # 選出完了後の最終判定で使う番号ROI（必要ならここだけ別座標に調整）
    MY_FINAL_SELECT_NUM_ROIS = MY_SELECT_NUM_ROIS

    # 自分のポケモンのアイコン座標 (330, 109～529)
    MY_POKEMON_ROIS = [
        (238, 105, 75, 75), 
        (238, 189, 75, 75), 
        (238, 273, 75, 75),
        (238, 357, 75, 75), 
        (238, 441, 75, 75), 
        (238, 525, 75, 75)
    ]

    # 自分の選出完了トリガー（画像判定用）
    TRIGGER_IMAGE_PATH = os.path.join(RESOURCES_DIR, "images", "my_selection.png")
    TRIGGER_ROI = (530, 75, 16, 16)
    # ルールや背景差分に対応するため、複数トリガーを許可する
    TRIGGER_IMAGE_PATHS = [
        TRIGGER_IMAGE_PATH,
        os.path.join(RESOURCES_DIR, "images", "my_selection_casual.png"),
    ]
    # エッジ判定も併用するため、従来より少し低めの値を採用
    TRIGGER_MATCH_THRESHOLD = 0.62
    TURN_START_IMAGE_PATH = os.path.join(RESOURCES_DIR, "images", "turn_start.png")
    TURN_START_ROI = (1144, 428, 95, 95)
    TURN_START_MATCH_THRESHOLD = 0.40
    BATTLE_END_IMAGE_PATH = os.path.join(RESOURCES_DIR, "images", "battle_end.png")
    BATTLE_END_ROI = (190, 645, 165, 35)
    BATTLE_END_MATCH_THRESHOLD = 0.35
    # 対面ポケモン名の表示テキスト領域（OCR）。環境に合わせて調整してください。
    OPP_ACTIVE_NAME_ROI = (1069, 38, 111, 21)
    # Tesseract の言語（日本語は jpn.traineddata。無い場合は eng も試行）
    # 同梱 tessdata に .traineddata が無いときは OS 既定の tessdata を使う（空読み防止）
    OPP_ACTIVE_NAME_OCR_LANG = "jpn"
    # OCRが空のとき、敵6体名のみを候補に描画＋エッジで照合する閾値（TM_CCOEFF_NORMED）
    OPP_ACTIVE_NAME_RENDER_THRESHOLD = 0.18
    # 空なら OS の日本語フォントを順に試す。明示したい場合は .ttc/.ttf の絶対パス
    OPP_ACTIVE_NAME_FONT_PATH = ""
    OPP_ACTIVE_CAPTURE_INTERVAL_SECONDS = 1
    # 旧: アイコン ROI でのテンプレート照合（参照用・現状は名前OCRを使用）
    OPP_ACTIVE_ROI = (990, 33, 75, 75)
    OPP_ACTIVE_MATCH_THRESHOLD = 0.24
    OPP_ACTIVE_SCORE_MARGIN = 0.05

    # 自分の選出番号テンプレート（画像判定用）
    NUM_TEMPLATE_PATHS = {
        "1": os.path.join(RESOURCES_DIR, "images", "num1.png"),
        "2": os.path.join(RESOURCES_DIR, "images", "num2.png"),
        "3": os.path.join(RESOURCES_DIR, "images", "num3.png"),
    }
    NUM_MATCH_THRESHOLD = 0.35
    # 選出完了後のバーストスキャン設定（0.1秒 x 10フレーム）
    MY_FINAL_SCAN_FRAMES = 10
    MY_FINAL_SCAN_INTERVAL_MS = 100

    # --- 相手の最終選出（空なら従来どおり「自選出ロック直後」にターン開始監視を許可）---
    # 相手側の選出番号 ROI（自チームの MY_SELECT_NUM_ROIS と同様の並び）。座標を入れると自選出ロック後に
    # バーストで相手の 1/2/3 を読み、終了後にのみターン開始（バトル開始）監視を開始する。
    OPP_FINAL_SELECT_NUM_ROIS = ()
    # 上記番号と対応する相手パーティアイコン ROI。空のときは OPPONENT_ROIS を使う。
    OPP_FINAL_PARTY_ROIS = ()
    OPP_FINAL_SCAN_FRAMES = 10
    OPP_FINAL_SCAN_INTERVAL_MS = 100
    # 相手選出ゲート(_ensure)通過後、初回ターン開始で戦闘トラッキングに入るまでの待ち秒。0 で無効。
    TURN_START_ARM_DELAY_SEC = 0.0