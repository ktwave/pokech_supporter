"""
<summary>映像取得および各専門ロジック（OCR・形状認識・録画）を統括する監督サービス</summary>
"""
import subprocess
import numpy as np
import cv2
import threading
from backend.config.constants import Config
from backend.logic.ocr_processor import OcrProcessor
from backend.logic.team_analyzer import TeamAnalyzer
from backend.logic.media_handler import MediaHandler

class CaptureService:
    def __init__(self, mode="device", video_path=None):
        self.mode = mode
        self.video_path = video_path
        self.process = None
        self.cap = None
        self.cap_lock = threading.Lock()
        
        # 各専門ロジックのインスタンス化
        self.ocr = OcrProcessor()
        self.analyzer = TeamAnalyzer()
        self.media = MediaHandler()

        self.ocr = OcrProcessor()
        self.analyzer = TeamAnalyzer()
        self.media = MediaHandler()

    def start_capture(self):
        """<summary>映像入力を開始する</summary>"""
        if self.mode == "device":
            command = [
                Config.FFMPEG_PATH, '-f', 'dshow', '-rtbufsize', '500M',
                '-i', f'video={Config.VIDEO_DEVICE}',
                '-vf', f'scale={Config.WIDTH}:{Config.HEIGHT}',
                '-pix_fmt', 'bgr24', '-vcodec', 'rawvideo', '-an', '-f', 'image2pipe', '-'
            ]
            self.process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=Config.WIDTH * Config.HEIGHT * 3, 
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            if self.video_path: self.cap = cv2.VideoCapture(self.video_path)

    def run_debug_ocr(self, frame):
        """<summary>Logic層のデバッグ機能を実行する</summary>"""
        return self.ocr.debug_check(frame)

    def get_frame(self):
        """<summary>最新の1フレームを取得する</summary>"""
        if self.mode == "device":
            if not self.process: return None
            try:
                raw = self.process.stdout.read(Config.WIDTH * Config.HEIGHT * 3)
                if len(raw) != Config.WIDTH * Config.HEIGHT * 3: return None
                return np.frombuffer(raw, dtype=np.uint8).reshape((Config.HEIGHT, Config.WIDTH, 3))
            except: return None
        else:
            if not self.cap: return None
            with self.cap_lock:
                ret, frame = self.cap.read()
                if not ret:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
            return cv2.resize(frame, (Config.WIDTH, Config.HEIGHT))

    def seek_seconds(self, delta_seconds):
        """<summary>動画モード時に再生位置を秒単位でシークする</summary>"""
        if self.mode != "file" or not self.cap:
            return False
        with self.cap_lock:
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if not fps or fps <= 0:
                fps = 30.0
            current_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
            total_frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            delta_frames = int(delta_seconds * fps)
            target = int(current_frame + delta_frames)
            max_frame = int(total_frames - 1) if total_frames and total_frames > 0 else target
            target = max(0, min(target, max_frame))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        return True

    def stop_capture(self):
        """<summary>リソースを解放する</summary>"""
        self.media.stop_recording()
        if self.cap: self.cap.release()
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=0.5)
            except: self.process.kill()

    # --- Logic層への橋渡しメソッド群 ---
    
    def recognize_party(self, frame, is_opponent=True):
        rois = Config.OPPONENT_ROIS if is_opponent else Config.MY_POKEMON_ROIS
        return self.analyzer.identify_pokemon(frame, rois)

    def check_time(self, frame):
        return self.ocr.is_target_time(frame)

    def check_waiting(self, frame):
        return self.ocr.is_waiting(frame)

    def identify_my_selection(self, frame):
        """<summary>選出画面から選出された3匹を特定する</summary>"""
        selected = []
        for i in range(min(len(Config.MY_SELECT_NUM_ROIS), 6)):
            num_text = self.ocr.read_text(frame, Config.MY_SELECT_NUM_ROIS[i])
            if num_text in ["1", "2", "3"]:
                p_name = self.analyzer.identify_pokemon(frame, [Config.MY_POKEMON_ROIS[i]])[0]
                selected.append((num_text, p_name))
        selected.sort()
        return [p[1] for p in selected]