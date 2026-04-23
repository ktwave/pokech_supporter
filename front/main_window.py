"""
<summary>インポートエラーを修正し、動画再生速度の同期精度を高めたメインウィンドウ</summary>
"""
import sys
import os
import cv2
import time
import subprocess
import threading
from collections import Counter
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QFrame,
    QSizePolicy,
    QInputDialog,
    QMessageBox,
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QUrl, QSize, QSettings
from PySide6.QtGui import (
    QAction,
    QImage,
    QPixmap,
    QDesktopServices,
    QShortcut,
    QKeySequence,
)

# インポート漏れを修正
from backend.config.constants import Config
from backend.service.capture_service import CaptureService
from backend.logic.pokemon_urls import (
    load_pokecham_battle_support_urls_by_japanese_name,
    load_yakkun_urls_by_japanese_name,
)
from front.layout_constants import (
    LEFT_SIDEBAR_MIN_WIDTH_PX,
    OPP_PARTY_ICON_CELL_MIN_WIDTH_PX,
    OPP_PARTY_STAT_LABEL_MIN_WIDTH_PX,
    TOP_ROW_OPP_PARTY_WIDTH_DEN,
    TOP_ROW_OPP_PARTY_WIDTH_NUM,
    WINDOW_DEFAULT_HEIGHT_PX,
    WINDOW_DEFAULT_WIDTH_PX,
    opp_column_outer_width,
)
from front.opponent_stats_panel import OpponentStatsPanel
from front.pokecham_fetch_thread import PokechamFetchThread
from front.pokemon_slot import PokemonSlotWidget
from backend.db.profile_stats_store import ProfileStatsStore


class Video16x9Pane(QWidget):
    """親が割り当てる矩形をそのまま 16:9 表示領域とする。ラベルは全面フィット。"""

    def __init__(self, video_label: QLabel, parent=None):
        super().__init__(parent)
        self._video_label = video_label
        video_label.setParent(self)
        video_label.setAlignment(Qt.AlignCenter)
        # キャプチャが 16:9 以外のときの余白は黒ではなくウィンドウ背景に近い色
        video_label.setStyleSheet("background-color: #1a1a1a;")
        self.setStyleSheet("background-color: #1a1a1a;")

    def resizeEvent(self, event):
        self._video_label.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)


class TopVideoPartyRow(QWidget):
    """上段: 左に 16:9 の映像、右に敵PT列（幅は front.layout_constants を参照）。"""

    _AR_NUM = 16
    _AR_DEN = 9

    def __init__(
        self,
        video_pane: Video16x9Pane,
        opp_widget: QWidget,
        parent=None,
        *,
        opp_width_num: int = TOP_ROW_OPP_PARTY_WIDTH_NUM,
        opp_width_den: int = TOP_ROW_OPP_PARTY_WIDTH_DEN,
    ):
        super().__init__(parent)
        self._opp_w_num = max(1, int(opp_width_num))
        self._opp_w_den = max(self._opp_w_num + 1, int(opp_width_den))
        self._video_pane = video_pane
        self._opp = opp_widget
        video_pane.setParent(self)
        opp_widget.setParent(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: #1a1a1a;")

    def resizeEvent(self, event):
        W, H = self.width(), self.height()
        if W > 0 and H > 0:
            ow = opp_column_outer_width(W, num=self._opp_w_num, den=self._opp_w_den)
            vw = W - ow
            ar = self._AR_NUM / self._AR_DEN
            if vw <= 0:
                self._video_pane.setGeometry(0, 0, 0, 0)
                self._opp.setGeometry(0, 0, ow, H)
            else:
                if vw / H > ar:
                    nh = H
                    nw = max(1, int(round(H * ar)))
                else:
                    nw = vw
                    nh = max(1, int(round(vw / ar)))
                x = (vw - nw) // 2
                y = (H - nh) // 2
                self._video_pane.setGeometry(x, y, nw, nh)
                self._opp.setGeometry(vw, 0, ow, H)
        super().resizeEvent(event)

    def sizeHint(self):
        return QSize(960, 400)


class BottomBarAlignedTimer(QWidget):
    """下段右のカウントダウン枠の幅を、上段の敵PT+統計列と同じ式（opp_column_outer_width）に合わせる。"""

    def __init__(
        self,
        my_w: QWidget,
        vs_label: QWidget,
        os_w: QWidget,
        timer_strip: QWidget,
        *,
        opp_width_num: int = TOP_ROW_OPP_PARTY_WIDTH_NUM,
        opp_width_den: int = TOP_ROW_OPP_PARTY_WIDTH_DEN,
        parent=None,
    ):
        super().__init__(parent)
        self._opp_w_num = max(1, int(opp_width_num))
        self._opp_w_den = max(self._opp_w_num + 1, int(opp_width_den))
        self._timer_strip = timer_strip
        timer_strip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(my_w, 8)
        lay.addWidget(vs_label, 0)
        lay.addWidget(os_w, 8)
        lay.addWidget(timer_strip, 0)

    def _sync_timer_strip_width(self):
        W = self.width()
        if W <= 0:
            return
        ow = opp_column_outer_width(W, num=self._opp_w_num, den=self._opp_w_den)
        self._timer_strip.setFixedWidth(ow)

    def resizeEvent(self, event):
        self._sync_timer_strip_width()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer_strip_width()


class SharedFrame:
    def __init__(self):
        self.frame = None
        self.lock = threading.Lock()

    def set_frame(self, frame):
        with self.lock:
            # 参照ではなくコピーを保持
            self.frame = frame.copy() if frame is not None else None

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

"""
敵PTスキャン後は _pre_battle_tick で「自選トリガー(is_waiting)」と「ターン開始」を並行監視する。
ターン開始が先に立った場合は自選バーストを行わずに戦闘トラッキングへ移る。
戦闘開始後は track_opponent_active のみ（バトル終了・対面監視）。
"""
class OcrThread(QThread):
    opp_party_signal = Signal(list)
    my_selection_signal = Signal(list)
    opp_selection_signal = Signal(list)
    opp_active_focus_signal = Signal(str)
    timer_update_signal = Signal(str)
    battle_timer_reset_signal = Signal()
    battle_started_signal = Signal()
    battle_stats_signal = Signal(list, list)
    battle_ended_signal = Signal()

    def __init__(self, shared_frame, service):
        super().__init__()
        self.shared_frame = shared_frame
        self.service = service
        self.is_opp_scanned = False
        self.is_my_selection_locked = False
        self.opp_party = []
        self.opp_party_scanned = []
        self.opp_selection = []
        self.is_opp_active_tracking = False
        self.last_opp_capture_time = 0.0
        self.last_turn_debug_time = 0.0
        self._last_stats_focus = None
        self._tick = 0
        self.is_opp_pick_confirmed = False
        self._opp_final_selection_scan_done = False
        self._opp_pick_confirmed_at = 0.0
        # 敵PTスキャン後〜初回ターン開始まで: 自選バーストは最大1回。ターン開始が先ならバーストは行わない。
        self._my_final_burst_ran = False

    def run(self):
        print("--- [OcrThread] Monitoring Started (Opponent + My Selection) ---")
        while not self.isInterruptionRequested():
            self._tick += 1
            frame = self.shared_frame.get_frame()
            if frame is not None:
                # --- 1. 時間監視 & 敵PT自動スキャン ---
                is_target, time_text = self.service.ocr.is_target_time(frame)
                if time_text:
                    self.timer_update_signal.emit(time_text)
                
                # 01:30～01:20の範囲で、まだスキャンしていないなら実行
                if is_target and not self.is_opp_scanned:
                    print(f"--- [EVENT] 01:30 Detected: Scanning Opponent Party ---")
                    # 連戦対策：新しい試合の開始時に表示状態を初期化
                    self.reset_match_state_for_new_battle()
                    self.battle_timer_reset_signal.emit()
                    # 以前の 10回多数決スキャンを呼び出す
                    self.perform_full_scan()
                    self.is_opp_scanned = True
                
                # 次の試合のためにリセット (01:50台などでフラグを戻す)
                if "01:5" in time_text:
                    self.is_opp_scanned = False
                    self.is_my_selection_locked = False
                    self.opp_party = []
                    self.opp_party_scanned = []
                    self.opp_selection = []
                    self.is_opp_active_tracking = False
                    self.last_opp_capture_time = 0.0
                    self.last_turn_debug_time = 0.0
                    self._last_stats_focus = None
                    self.is_opp_pick_confirmed = False
                    self._opp_final_selection_scan_done = False
                    self._opp_pick_confirmed_at = 0.0
                    self._my_final_burst_ran = False

                # --- 2. 敵PT後: 自選トリガーとターン開始を並行監視。ターン開始が先なら自選バーストはスキップ。---
                if self.is_opp_scanned:
                    if not self.is_opp_active_tracking:
                        self._pre_battle_tick(frame)
                    else:
                        self.track_opponent_active(frame)

                # 監視スパン：リアルタイム性を維持しつつ負荷を抑える
                self.msleep(300)
            else:
                self.msleep(100)

    def _enter_battle_tracking(self):
        """初回ターン開始を検知したらバトル中扱いにし、以降は自選バーストを行わない。"""
        if self.is_opp_active_tracking:
            return
        self.is_opp_active_tracking = True
        self._my_final_burst_ran = True
        self.last_opp_capture_time = 0.0
        print("[BATTLE] turn start → 戦闘中トラッキング開始（自選バーストは以降スキップ）")
        self.battle_started_signal.emit()

    def _pre_battle_tick(self, frame):
        """敵PT確定後〜初回ターン開始前。ターン開始を自選トリガーより優先する。"""
        now = time.time()
        is_ts, ts_score = self.service.ocr.is_turn_start_with_score(frame)

        if not self._my_final_burst_ran and self._tick % 10 == 0:
            print(
                f"[PRE-BATTLE] waiting_trigger={self.service.ocr.is_waiting(frame)} "
                f"turn_start={is_ts} score={ts_score:.3f}"
            )

        if is_ts:
            self._ensure_opponent_pick_gate()
            arm_delay = float(getattr(Config, "TURN_START_ARM_DELAY_SEC", 0.0) or 0.0)
            if (
                arm_delay > 0.0
                and self._opp_pick_confirmed_at > 0.0
                and (now - self._opp_pick_confirmed_at) < arm_delay
            ):
                return
            self._enter_battle_tracking()
            return

        if self._my_final_burst_ran:
            return
        if self.service.ocr.is_waiting(frame):
            print("!!! [LOCK] My Selection Confirmed !!! start final burst scan")
            self.perform_my_selection_final_scan()
            self._my_final_burst_ran = True
            self.is_my_selection_locked = True
            self._ensure_opponent_pick_gate()

    def perform_my_selection_final_scan(self):
        """<summary>選出完了後に0.1秒間隔で複数フレームを取得し、多数決で自選出を確定する</summary>"""
        print("--- [MY-FINAL] burst scan started ---")
        frame_results = []
        for i in range(Config.MY_FINAL_SCAN_FRAMES):
            frame = self.shared_frame.get_frame()
            if frame is None:
                self.msleep(Config.MY_FINAL_SCAN_INTERVAL_MS)
                continue

            picks = []
            rois = Config.MY_FINAL_SELECT_NUM_ROIS
            for slot_idx in range(min(6, len(rois))):
                num, score = self.service.ocr.detect_selection_number_with_score(frame, rois[slot_idx])
                if num in ["1", "2", "3"]:
                    p_name = self.service.analyzer.identify_pokemon(frame, [Config.MY_POKEMON_ROIS[slot_idx]])[0]
                    picks.append((num, p_name, score, slot_idx + 1))

            # 同一番号が複数スロットで出た場合、スコア最大の候補を採用する
            best_by_num = {}
            for num, name, score, slot in picks:
                prev = best_by_num.get(num)
                if prev is None or score > prev[1]:
                    best_by_num[num] = (name, score, slot)

            unique_picks = []
            for num in ["1", "2", "3"]:
                if num in best_by_num:
                    name, score, slot = best_by_num[num]
                    unique_picks.append((num, name))
                    print(f"[MY-FINAL] pick num={num} slot={slot} score={score:.3f} pokemon={name}")

            frame_results.append(unique_picks)
            print(f"[MY-FINAL] frame {i+1}/{Config.MY_FINAL_SCAN_FRAMES}: {unique_picks}")
            self.msleep(Config.MY_FINAL_SCAN_INTERVAL_MS)

        # 番号1/2/3ごとに多数決で最終確定
        final_selection = ["Empty"] * 3
        for target_num in ["1", "2", "3"]:
            candidates = []
            for picks in frame_results:
                for num, name in picks:
                    if num == target_num and name != "Empty":
                        candidates.append(name)
            if candidates:
                final_selection[int(target_num) - 1] = Counter(candidates).most_common(1)[0][0]

        print(f"--- [MY-FINAL] result: {final_selection} ---")
        if any(name != "Empty" for name in final_selection):
            self.my_selection_signal.emit(final_selection)

    def _ensure_opponent_pick_gate(self):
        """自選出ロック後、相手の選出を確定してからターン開始監視を許可する。"""
        if self.is_opp_pick_confirmed:
            return
        rois = getattr(Config, "OPP_FINAL_SELECT_NUM_ROIS", None) or ()
        if not rois:
            self.is_opp_pick_confirmed = True
            self._opp_pick_confirmed_at = time.time()
            return
        if self._opp_final_selection_scan_done:
            self.is_opp_pick_confirmed = True
            self._opp_pick_confirmed_at = time.time()
            return
        self._opp_final_selection_scan_done = True
        try:
            self.perform_opponent_final_selection_scan()
        except Exception as ex:
            print(f"[OPP-FINAL] scan error: {ex}")
        self.is_opp_pick_confirmed = True
        self._opp_pick_confirmed_at = time.time()

    def perform_opponent_final_selection_scan(self):
        """相手の選出番号 ROI から 1/2/3 を読み、多数決で確定する。"""
        print("--- [OPP-FINAL] burst scan started ---")
        num_rois = getattr(Config, "OPP_FINAL_SELECT_NUM_ROIS", None) or ()
        party_rois = getattr(Config, "OPP_FINAL_PARTY_ROIS", None) or ()
        if not party_rois:
            party_rois = Config.OPPONENT_ROIS
        n_frames = getattr(Config, "OPP_FINAL_SCAN_FRAMES", Config.MY_FINAL_SCAN_FRAMES)
        interval_ms = getattr(Config, "OPP_FINAL_SCAN_INTERVAL_MS", Config.MY_FINAL_SCAN_INTERVAL_MS)

        frame_results = []
        for i in range(n_frames):
            frame = self.shared_frame.get_frame()
            if frame is None:
                self.msleep(interval_ms)
                continue

            picks = []
            for slot_idx in range(min(6, len(num_rois))):
                num, score = self.service.ocr.detect_selection_number_with_score(
                    frame, num_rois[slot_idx]
                )
                if num in ["1", "2", "3"]:
                    p_name = self.service.analyzer.identify_pokemon(
                        frame, [party_rois[slot_idx]]
                    )[0]
                    picks.append((num, p_name, score, slot_idx + 1))

            best_by_num = {}
            for num, name, score, slot in picks:
                prev = best_by_num.get(num)
                if prev is None or score > prev[1]:
                    best_by_num[num] = (name, score, slot)

            unique_picks = []
            for num in ["1", "2", "3"]:
                if num in best_by_num:
                    name, score, slot = best_by_num[num]
                    unique_picks.append((num, name))
                    print(
                        f"[OPP-FINAL] pick num={num} slot={slot} score={score:.3f} pokemon={name}"
                    )

            frame_results.append(unique_picks)
            print(f"[OPP-FINAL] frame {i+1}/{n_frames}: {unique_picks}")
            self.msleep(interval_ms)

        final_selection = ["Empty"] * 3
        for target_num in ["1", "2", "3"]:
            candidates = []
            for picks in frame_results:
                for num, name in picks:
                    if num == target_num and name != "Empty":
                        candidates.append(name)
            if candidates:
                final_selection[int(target_num) - 1] = Counter(candidates).most_common(1)[0][0]

        print(f"--- [OPP-FINAL] result: {final_selection} ---")
        self.opp_selection = [n for n in final_selection if n and n != "Empty"]
        self.opp_selection_signal.emit(list(final_selection))

    def perform_full_scan(self):
        """<summary>敵PTを10回サンプリングして高精度に特定する</summary>"""
        results = []
        for i in range(10):
            f = self.shared_frame.get_frame()
            if f is not None:
                # 敵側の座標リストを渡して判定
                res = self.service.recognize_party(f, is_opponent=True)
                results.append(res)
                print(f"  Opponent Scan: {i+1}/10...")
            self.msleep(50)
        
        if results:
            final = self.service.analyzer._majority_vote(results)
            self.opp_party_scanned = list(final)
            self.opp_party = [p for p in final if p != "Empty"]
            self.opp_selection = []
            self.is_opp_active_tracking = False
            self.last_opp_capture_time = 0.0
            self._last_stats_focus = None
            print(f"--- OPPONENT PARTY SCANNED: {final} ---")
            self.opp_party_signal.emit(final)
            self.is_opp_pick_confirmed = False
            self._opp_final_selection_scan_done = False
            self._opp_pick_confirmed_at = 0.0
            self._my_final_burst_ran = False
            self.is_my_selection_locked = False

    def reset_match_state_for_new_battle(self):
        self.opp_party = []
        self.opp_party_scanned = []
        self.opp_selection = []
        self.is_opp_active_tracking = False
        self.last_opp_capture_time = 0.0
        self._last_stats_focus = None
        self.is_opp_pick_confirmed = False
        self._opp_final_selection_scan_done = False
        self._opp_pick_confirmed_at = 0.0
        self._my_final_burst_ran = False
        self.is_my_selection_locked = False
        self.my_selection_signal.emit(["Empty", "Empty", "Empty"])
        self.opp_selection_signal.emit(["Empty", "Empty", "Empty"])

    def track_opponent_active(self, frame):
        now = time.time()
        is_battle_end, end_score = False, -1.0
        if self.is_opp_active_tracking:
            is_battle_end, end_score = self.service.ocr.is_battle_end_with_score(frame)
        if now - self.last_turn_debug_time >= 1.0:
            print(
                f"[BATTLE] battle_end match={is_battle_end} "
                f"score={end_score:.3f} th={Config.BATTLE_END_MATCH_THRESHOLD:.2f}"
            )
            self.last_turn_debug_time = now

        if self.is_opp_active_tracking and is_battle_end:
            self.is_opp_active_tracking = False
            self.last_opp_capture_time = 0.0
            self.is_opp_scanned = False
            self.is_my_selection_locked = False
            self._last_stats_focus = None
            self.is_opp_pick_confirmed = False
            self._opp_final_selection_scan_done = False
            self._opp_pick_confirmed_at = 0.0
            self._my_final_burst_ran = False
            print("[OPP-ACTIVE] battle end detected: stop capture loop and return to 01:30 watch")
            self.battle_stats_signal.emit(
                list(self.opp_party_scanned), list(self.opp_selection)
            )
            self.battle_ended_signal.emit()
            return

        if not self.opp_party:
            print("[OPP-ACTIVE] skip: opponent party is empty")
            return

        if now - self.last_opp_capture_time < Config.OPP_ACTIVE_CAPTURE_INTERVAL_SECONDS:
            return
        self.last_opp_capture_time = now

        active, best_s, second_s = self.service.analyzer.identify_best_among_candidates(
            frame,
            Config.OPP_ACTIVE_ROI,
            self.opp_party,
            Config.OPP_ACTIVE_MATCH_THRESHOLD,
            Config.OPP_ACTIVE_SCORE_MARGIN,
        )
        print(
            f"[OPP-ACTIVE] detected={active} "
            f"best={best_s:.3f} second={second_s:.3f} "
            f"th={Config.OPP_ACTIVE_MATCH_THRESHOLD:.2f} margin>={Config.OPP_ACTIVE_SCORE_MARGIN:.2f} "
            f"party={self.opp_party}"
        )
        if active == "Empty":
            return
        if active not in self.opp_selection and len(self.opp_selection) < 3:
            self.opp_selection.append(active)
            print(f"[OPP-ACTIVE] append enemy_selection={self.opp_selection}")
            self.opp_selection_signal.emit(self.opp_selection.copy())

        if active != "Empty" and active != self._last_stats_focus:
            self._last_stats_focus = active
            self.opp_active_focus_signal.emit(active)

    def manual_append_opponent_selection(self, name: str):
        """対面選出に手動で1体追加（最大3）。既にいる場合は左統計のフォーカスのみ更新。"""
        if not name or name == "Empty":
            return
        if name not in self.opp_party:
            print(f"[MANUAL-OPP] skip: {name!r} は見せ合い6体に含まれません")
            return
        if name in self.opp_selection:
            if name != self._last_stats_focus:
                self._last_stats_focus = name
                self.opp_active_focus_signal.emit(name)
            return
        if len(self.opp_selection) >= 3:
            print("[MANUAL-OPP] 選出は既に3体です")
            return
        self.opp_selection.append(name)
        print(f"[MANUAL-OPP] append enemy_selection={self.opp_selection}")
        self.opp_selection_signal.emit(self.opp_selection.copy())
        if name != self._last_stats_focus:
            self._last_stats_focus = name
            self.opp_active_focus_signal.emit(name)

class VideoThread(QThread):
    change_pixmap_signal = Signal(QImage)

    def __init__(self, mode="device", video_path=None, shared_frame=None):
        super().__init__()
        self.mode = mode
        self.video_path = video_path
        self.shared_frame = shared_frame
        self.service = CaptureService(mode=mode, video_path=video_path)

    def run(self):
        self.service.start_capture()
        
        # 動画再生速度の調整用
        target_fps = 60
        frame_time = 1.0 / target_fps
        
        while not self.isInterruptionRequested():
            start_time = time.time()
            
            frame = self.service.get_frame()
            if frame is None:
                self.msleep(1)
                continue

            # 表示
            h, w, ch = frame.shape
            self.change_pixmap_signal.emit(QImage(frame.data, w, h, ch * w, QImage.Format_BGR888))

            # OCRスレッドへ共有
            if self.shared_frame:
                self.shared_frame.set_frame(frame)

            # 速度制御
            if self.mode == "device":
                self.msleep(1)
            else:
                # 処理にかかった時間を引いて、待機時間を計算
                elapsed = time.time() - start_time
                wait_time = max(0, frame_time - elapsed)
                time.sleep(wait_time)

        self.service.stop_capture()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._media_recording = False
        self.resize(WINDOW_DEFAULT_WIDTH_PX, WINDOW_DEFAULT_HEIGHT_PX)
        self.setAcceptDrops(True)
        self.battle_seconds_left = 20 * 60
        self.battle_timer_running = False
        self.battle_timer = QTimer(self)
        self.battle_timer.timeout.connect(self._tick_battle_timer)
        self.shared_frame = SharedFrame()
        self._pokemon_url_by_jp = load_yakkun_urls_by_japanese_name(Config.POKEMON_DATA_TSV_PATH)
        self._pokecham_url_by_jp = load_pokecham_battle_support_urls_by_japanese_name(
            Config.POKEMON_DATA_TSV_PATH
        )
        self._battle_stats_cache = {}
        self._stats_in_flight = set()
        self._stats_done_failed = {}
        self._current_stats_focus = None
        self._prev_opp_selection_padded = ["Empty", "Empty", "Empty"]
        self._stats_threads = []
        self._stats_battle_generation = 0
        self._profile_store = ProfileStatsStore()
        self._profile_settings = QSettings("PokeChSupporter", "PokeChSupporter")
        self._active_profile_id = self._resolve_active_profile_id()
        self._in_battle = False
        self._menu_profile = None
        self._sub_profile_switch = None
        self._init_ui()
        self._init_profile_menu()
        self._sync_window_title()
        self._wire_pokemon_url_clicks()
        self._install_media_seek_shortcuts()
        self._reset_battle_timer_display()
        self._start_threads("device")

    def _init_ui(self):
        # 左サイドバー幅・敵PT列・起動時ウィンドウサイズは front/layout_constants.py を編集してください。
        central = QWidget()
        central.setStyleSheet("background-color: #1a1a1a;")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.left_sidebar = QFrame()
        self.left_sidebar.setObjectName("leftSidebar")
        self.left_sidebar.setMinimumWidth(LEFT_SIDEBAR_MIN_WIDTH_PX)
        self.left_sidebar.setStyleSheet(
            "#leftSidebar { background-color: #222222; border-right: 1px solid #3a3a3a; }"
        )
        self.left_sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_lay = QVBoxLayout(self.left_sidebar)
        left_lay.setContentsMargins(12, 16, 12, 16)
        left_lay.setSpacing(8)
        self._opp_stats_panel = OpponentStatsPanel(self.left_sidebar)
        self._opp_stats_panel.show_idle()
        left_lay.addWidget(self._opp_stats_panel, 1)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.image_label = QLabel()
        self._video_pane = Video16x9Pane(self.image_label)

        self.opp_slots = [PokemonSlotWidget(i + 1) for i in range(6)]
        self._opp_party_stat_labels: list[QLabel] = []
        opp_w = QWidget()
        opp_v = QVBoxLayout(opp_w)
        opp_v.setContentsMargins(0, 0, 0, 0)
        opp_v.setSpacing(0)
        for s in self.opp_slots:
            s.setToolTip("左クリック: ポケ徹\n右クリック: メニュー（選出に手動追加など）")
            s.setFixedWidth(OPP_PARTY_ICON_CELL_MIN_WIDTH_PX)
            row = QWidget()
            row_h = QHBoxLayout(row)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(4)
            lab = QLabel("")
            lab.setWordWrap(True)
            lab.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            lab.setMinimumWidth(OPP_PARTY_STAT_LABEL_MIN_WIDTH_PX)
            lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lab.setStyleSheet(
                "color: #c8c8c8; font-size: 10px; background: transparent; padding: 2px;"
            )
            row_h.addWidget(s, 0)
            row_h.addWidget(lab, 1)
            self._opp_party_stat_labels.append(lab)
            opp_v.addWidget(row)

        self.top_capture_row = TopVideoPartyRow(
            self._video_pane,
            opp_w,
            opp_width_num=TOP_ROW_OPP_PARTY_WIDTH_NUM,
            opp_width_den=TOP_ROW_OPP_PARTY_WIDTH_DEN,
        )

        self.my_slots = [PokemonSlotWidget() for _ in range(3)]
        my_w = QWidget()
        my_h = QHBoxLayout(my_w)
        my_h.setContentsMargins(0, 0, 0, 0)
        my_h.setSpacing(0)
        for s in self.my_slots:
            my_h.addWidget(s)

        self.vs_label = QLabel("VS")
        self.vs_label.setAlignment(Qt.AlignCenter)
        self.vs_label.setMinimumWidth(56)
        self.vs_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.vs_label.setStyleSheet(
            "color: #ffffff; font-size: 28px; font-weight: bold; background: #1a1a1a;"
        )

        self.opp_sel_slots = [PokemonSlotWidget() for _ in range(3)]
        os_w = QWidget()
        os_h = QHBoxLayout(os_w)
        os_h.setContentsMargins(0, 0, 0, 0)
        os_h.setSpacing(0)
        for s in self.opp_sel_slots:
            s.setToolTip("左クリック: ポケ徹\n右クリック: 未選出をリストから手動追加")
            os_h.addWidget(s)

        timer_wrap = QWidget()
        timer_wrap.setStyleSheet("background-color: #262626;")
        timer_layout = QVBoxLayout(timer_wrap)
        timer_layout.setContentsMargins(4, 2, 4, 2)
        timer_layout.setSpacing(0)
        timer_layout.addStretch(1)
        self.battle_timer_label = QLabel("20:00")
        self.battle_timer_label.setAlignment(Qt.AlignCenter)
        self.battle_timer_label.setStyleSheet(
            "color: #ffd54f; font-size: 22px; font-weight: bold; background: #262626;"
        )
        timer_layout.addWidget(self.battle_timer_label, 0, Qt.AlignmentFlag.AlignHCenter)
        timer_layout.addStretch(1)

        bottom_bar = BottomBarAlignedTimer(
            my_w,
            self.vs_label,
            os_w,
            timer_wrap,
            opp_width_num=TOP_ROW_OPP_PARTY_WIDTH_NUM,
            opp_width_den=TOP_ROW_OPP_PARTY_WIDTH_DEN,
        )

        right_lay.addWidget(self.top_capture_row, 8)
        right_lay.addWidget(bottom_bar, 2)
        right_lay.setStretch(0, 8)
        right_lay.setStretch(1, 2)

        root.addWidget(self.left_sidebar, 0)
        root.addWidget(right, 1)

    def _wire_pokemon_url_clicks(self):
        for slot in self.my_slots:
            slot.clicked_with_name.connect(self._open_pokemon_yakkun_url)
        for slot in self.opp_slots:
            slot.clicked_with_name.connect(self._open_pokemon_yakkun_url)
            slot.set_party_context_manual(True)
            slot.party_manual_append_requested.connect(self._on_party_manual_append)
        for slot in self.opp_sel_slots:
            slot.clicked_with_name.connect(self._open_pokemon_yakkun_url)
            slot.set_selection_context_manual(True)
            slot.selection_manual_pick_requested.connect(self._on_selection_manual_pick)

    def _on_party_manual_append(self, name: str):
        if getattr(self, "ocr_thread", None):
            self.ocr_thread.manual_append_opponent_selection(name)

    def _on_selection_manual_pick(self):
        if not getattr(self, "ocr_thread", None):
            return
        party = self.ocr_thread.opp_party
        cur = list(self.ocr_thread.opp_selection)
        items = [p for p in party if p and p != "Empty" and p not in cur]
        if not items:
            QMessageBox.information(
                self,
                "手動追加",
                "追加できるポケモンがありません（未選出のポケモンがいません）。",
            )
            return
        choice, ok = QInputDialog.getItem(
            self,
            "手動で選出に追加",
            "ポケモンを選んでください（右クリックメニュー）",
            items,
            0,
            False,
        )
        if ok and choice:
            self.ocr_thread.manual_append_opponent_selection(choice)

    def _open_pokemon_yakkun_url(self, name: str):
        url = self._pokemon_url_by_jp.get(name)
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            print(f"[URL] no TSV entry for: {name}")

    def _install_media_seek_shortcuts(self):
        """動画ファイルモードで ±5 秒シーク。左パネル等にフォーカスがあっても効くようにショートカット使用。"""
        for key, delta in ((Qt.Key_Left, -5), (Qt.Key_Right, 5)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda d=delta: self._seek_media_file(d))

    def _seek_media_file(self, delta_sec: int):
        vt = getattr(self, "video_thread", None)
        if vt is None or getattr(vt, "mode", None) != "file":
            return
        if vt.service.seek_seconds(delta_sec):
            print(f"[MEDIA] seek {delta_sec:+d} sec")


    def _start_threads(self, mode, path=None):
        self._stop_threads()
        self.video_thread = VideoThread(mode=mode, video_path=path, shared_frame=self.shared_frame)
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        
        self.ocr_thread = OcrThread(shared_frame=self.shared_frame, service=self.video_thread.service)
        self.ocr_thread.opp_party_signal.connect(self.update_opp_party)
        self.ocr_thread.my_selection_signal.connect(self.update_my_selection)
        self.ocr_thread.opp_selection_signal.connect(self.update_opp_selection)
        self.ocr_thread.opp_active_focus_signal.connect(self._on_opp_active_focus)
        self.ocr_thread.battle_timer_reset_signal.connect(self._on_battle_timer_reset_from_ocr)
        self.ocr_thread.battle_started_signal.connect(self._start_battle_timer)
        self.ocr_thread.battle_stats_signal.connect(self._on_commit_battle_profile_stats)
        self.ocr_thread.battle_ended_signal.connect(self._on_battle_ended)

        self.video_thread.start(); self.ocr_thread.start()

    def _stop_threads(self):
        for t in [getattr(self, 'video_thread', None), getattr(self, 'ocr_thread', None)]:
            if t: t.requestInterruption(); t.quit(); t.wait()

    def update_image(self, img):
        self.image_label.setPixmap(QPixmap.fromImage(img).scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def update_opp_party(self, team):
        for i in range(6):
            name = team[i] if i < len(team) else "Empty"
            self.opp_slots[i].update_pokemon(name)
        self._refresh_cumulative_for_opp_party(team)

    def _init_profile_menu(self):
        self._menu_profile = self.menuBar().addMenu("プロファイル")
        self._menu_profile.addAction("新規作成…").triggered.connect(self._on_profile_new)
        self._sub_profile_switch = self._menu_profile.addMenu("切り替え")
        self._reload_profile_switch_menu()

    def _reload_profile_switch_menu(self):
        if self._sub_profile_switch is None:
            return
        self._sub_profile_switch.clear()
        for pid, name in self._profile_store.list_profiles():
            act = QAction(name, self)
            act.triggered.connect(lambda checked=False, p=pid: self._on_switch_profile(p))
            self._sub_profile_switch.addAction(act)

    def _resolve_active_profile_id(self) -> int:
        pid = int(self._profile_settings.value("stats/active_profile_id", 0) or 0)
        if pid and self._profile_store.profile_exists(pid):
            return pid
        profiles = self._profile_store.list_profiles()
        fid = profiles[0][0] if profiles else 1
        self._profile_settings.setValue("stats/active_profile_id", fid)
        return fid

    def _sync_window_title(self):
        dn = self._profile_store.get_display_name(self._active_profile_id) or "?"
        if self._media_recording:
            self.setWindowTitle(f"● RECORDING… - {dn}")
        else:
            self.setWindowTitle(f"PokeCh Supporter - {dn}")

    def _set_active_profile_id(self, profile_id: int):
        if not self._profile_store.profile_exists(profile_id):
            return
        self._active_profile_id = profile_id
        self._profile_settings.setValue("stats/active_profile_id", profile_id)
        self._sync_window_title()
        ot = getattr(self, "ocr_thread", None)
        if ot is not None:
            scanned = getattr(ot, "opp_party_scanned", None) or []
            if any(n and n != "Empty" for n in scanned):
                self._refresh_cumulative_for_opp_party(scanned)
            elif ot.opp_party:
                self._refresh_cumulative_for_opp_party(ot.opp_party)

    def _set_in_battle(self, in_battle: bool):
        self._in_battle = bool(in_battle)
        if self._menu_profile is not None:
            self._menu_profile.setEnabled(not self._in_battle)

    @staticmethod
    def _fmt_sel_rate(match_c: int, sel_c: int) -> str:
        if match_c <= 0:
            return "-"
        return f"{100.0 * sel_c / match_c:.1f}%"

    @staticmethod
    def _fmt_lead_rate(sel_c: int, lead_c: int) -> str:
        if sel_c <= 0:
            return "-"
        return f"{100.0 * lead_c / sel_c:.1f}%"

    def _clear_opp_party_stat_labels(self):
        for lab in getattr(self, "_opp_party_stat_labels", ()):
            lab.setText("")

    def _refresh_cumulative_for_opp_party(self, team):
        for lab in self._opp_party_stat_labels:
            lab.setText("")
        padded = [team[i] if i < len(team) else "Empty" for i in range(6)]
        names = [n for n in padded if n and n != "Empty"]
        if not names:
            return
        stats = self._profile_store.fetch_stats(self._active_profile_id, names)
        for i, name in enumerate(padded):
            if not name or name == "Empty":
                continue
            m, s, l_ = stats.get(name, (0, 0, 0))
            self._opp_party_stat_labels[i].setText(
                f"出現 {m}\n"
                f"選出 {self._fmt_sel_rate(m, s)}\n"
                f"初手 {self._fmt_lead_rate(s, l_)}"
            )

    def _on_profile_new(self):
        if self._in_battle:
            QMessageBox.warning(
                self, "プロファイル", "バトル中はプロファイルを変更できません。"
            )
            return
        text, ok = QInputDialog.getText(self, "新規プロファイル", "表示名:")
        if not ok:
            return
        label = (text or "").strip() or "無題"
        pid = self._profile_store.create_profile(label)
        self._reload_profile_switch_menu()
        self._set_active_profile_id(pid)

    def _on_switch_profile(self, profile_id: int):
        if self._in_battle:
            QMessageBox.warning(
                self, "プロファイル", "バトル中はプロファイルを変更できません。"
            )
            return
        self._set_active_profile_id(profile_id)

    def _on_battle_timer_reset_from_ocr(self):
        self._reset_battle_timer_display()
        self._set_in_battle(False)

    def _on_commit_battle_profile_stats(self, party: list, selection: list):
        try:
            self._profile_store.commit_battle_end(
                self._active_profile_id, list(party or []), list(selection or [])
            )
            print(
                f"[STATS-DB] battle committed profile={self._active_profile_id} "
                f"party={party} selection={selection}"
            )
        except Exception as ex:
            print(f"[STATS-DB] commit failed: {ex}")

    def update_my_selection(self, team):
        for i, name in enumerate(team): 
            if i < 3: self.my_slots[i].update_pokemon(name)

    def update_opp_selection(self, team):
        for i in range(3):
            name = team[i] if i < len(team) else "Empty"
            self.opp_sel_slots[i].update_pokemon(name)
        self._on_opp_selection_for_stats(team)

    def _on_battle_ended(self):
        self._set_in_battle(False)
        self._stop_battle_timer()
        self._clear_battle_stats_state()

    def _clear_battle_stats_state(self):
        self._stats_battle_generation += 1
        self._battle_stats_cache.clear()
        self._stats_in_flight.clear()
        self._stats_done_failed.clear()
        self._current_stats_focus = None
        self._prev_opp_selection_padded = ["Empty", "Empty", "Empty"]
        self._clear_opp_party_stat_labels()
        self._opp_stats_panel.show_idle("バトル終了。次の対面で表示が更新されます。")

    def _reset_stats_cache_for_new_match(self):
        self._stats_battle_generation += 1
        self._battle_stats_cache.clear()
        self._stats_in_flight.clear()
        self._stats_done_failed.clear()
        self._current_stats_focus = None
        self._clear_opp_party_stat_labels()
        self._opp_stats_panel.show_idle()

    def _on_opp_selection_for_stats(self, team):
        padded = [team[i] if i < len(team) else "Empty" for i in range(3)]
        if all(not x or x == "Empty" for x in padded):
            self._reset_stats_cache_for_new_match()
            self._prev_opp_selection_padded = padded.copy()
            return
        prev = self._prev_opp_selection_padded
        self._prev_opp_selection_padded = padded.copy()
        prev_names = [x for x in prev if x and x != "Empty"]
        new_names = [x for x in padded if x and x != "Empty"]
        if len(new_names) > len(prev_names) and prev_names == new_names[: len(prev_names)]:
            added = new_names[len(prev_names) :]
        else:
            prev_set = set(prev_names)
            added = [x for x in new_names if x not in prev_set]
        for name in added:
            self._request_pokecham_if_needed(name)

    def _request_pokecham_if_needed(self, name: str):
        if (
            name in self._battle_stats_cache
            or name in self._stats_in_flight
            or name in self._stats_done_failed
        ):
            return
        url = self._pokecham_url_by_jp.get(name)
        if not url:
            print(f"[STATS] no pokecham URL in TSV for: {name}")
            return
        self._stats_in_flight.add(name)
        gen = self._stats_battle_generation
        th = PokechamFetchThread(name, url, gen)
        th.finished_ok.connect(self._on_pokecham_ok)
        th.finished_err.connect(self._on_pokecham_err)
        th.finished.connect(th.deleteLater)
        self._stats_threads.append(th)
        th.start()
        print(f"[STATS] fetch start: {name}")

    def _on_pokecham_ok(self, name: str, data: dict, generation: int):
        self._stats_in_flight.discard(name)
        if generation != self._stats_battle_generation:
            return
        self._battle_stats_cache[name] = data
        if self._current_stats_focus == name:
            self._opp_stats_panel.show_stats(data)

    def _on_pokecham_err(self, name: str, err: str, generation: int):
        self._stats_in_flight.discard(name)
        if generation != self._stats_battle_generation:
            return
        self._stats_done_failed[name] = err
        print(f"[STATS] fetch failed: {name} — {err}")
        if self._current_stats_focus == name:
            self._opp_stats_panel.show_error(name, err)

    def _on_opp_active_focus(self, name: str):
        if not name or name == "Empty":
            return
        self._current_stats_focus = name
        self._refresh_stats_panel_for_focus()

    def _refresh_stats_panel_for_focus(self):
        name = self._current_stats_focus
        if not name:
            self._opp_stats_panel.show_idle()
            return
        if name in self._battle_stats_cache:
            self._opp_stats_panel.show_stats(self._battle_stats_cache[name])
        elif name in self._stats_in_flight:
            self._opp_stats_panel.show_loading(name)
        elif name in self._stats_done_failed:
            self._opp_stats_panel.show_error(name, self._stats_done_failed[name])
        elif name in self._pokecham_url_by_jp:
            self._opp_stats_panel.show_loading(name)
        else:
            self._opp_stats_panel.show_error(name, "TSVにポケモンバトルサポートURLがありません")

    def _reset_battle_timer_display(self):
        self.battle_seconds_left = 20 * 60
        self._update_battle_timer_label()
        self._stop_battle_timer()

    def _start_battle_timer(self):
        self._set_in_battle(True)
        if self.battle_seconds_left <= 0:
            self.battle_seconds_left = 20 * 60
        self.battle_timer_running = True
        if not self.battle_timer.isActive():
            self.battle_timer.start(1000)

    def _stop_battle_timer(self):
        self.battle_timer_running = False
        if self.battle_timer.isActive():
            self.battle_timer.stop()

    def _tick_battle_timer(self):
        if not self.battle_timer_running:
            return
        if self.battle_seconds_left > 0:
            self.battle_seconds_left -= 1
            self._update_battle_timer_label()
        if self.battle_seconds_left <= 0:
            self._stop_battle_timer()

    def _update_battle_timer_label(self):
        m = self.battle_seconds_left // 60
        s = self.battle_seconds_left % 60
        self.battle_timer_label.setText(f"{m:02d}:{s:02d}")

    def keyPressEvent(self, e):
        service = self.video_thread.service
        m = service.media
        if e.key() == Qt.Key_S:
            path = m.save_screenshot(self.shared_frame.get_frame())
        elif e.key() == Qt.Key_R:
            if not m.is_recording:
                m.start_recording()
                self._media_recording = True
            else:
                m.stop_recording()
                self._media_recording = False
            self._sync_window_title()
        elif e.key() == Qt.Key_T:
            self.ocr_thread.perform_full_scan()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.exists(path): self._start_threads("file", path)
    def closeEvent(self, event):
        self._stop_threads(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(); window.show()
    sys.exit(app.exec())