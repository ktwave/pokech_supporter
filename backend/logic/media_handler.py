"""
<summary>FFmpegによる録画およびOpenCVによる静止画保存を担当するモジュール</summary>
"""
import os
import cv2
import datetime
import subprocess
from backend.config.constants import Config

class MediaHandler:
    def __init__(self):
        self.record_process = None
        self.is_recording = False

    def save_screenshot(self, frame):
        """<summary>スクリーンショットを保存する</summary>"""
        if frame is None: return None
        custom = getattr(Config, "SCREENSHOT_SAVE_DIR", "") or ""
        save_dir = custom.strip() if custom.strip() else os.path.join(Config.RESOURCES_DIR, "screenshots")
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, f"capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        cv2.imwrite(path, frame)
        return path

    def start_recording(self):
        """<summary>録画を開始する</summary>"""
        if self.is_recording: return
        custom = getattr(Config, "RECORD_SAVE_DIR", "") or ""
        save_dir = custom.strip() if custom.strip() else os.path.join(Config.RESOURCES_DIR, "videos")
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"record_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        
        command = [
            Config.FFMPEG_PATH, '-f', 'dshow', '-i', f'video={Config.VIDEO_DEVICE}',
            '-vcodec', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p', filename
        ]
        self.record_process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        self.is_recording = True
        return filename

    def stop_recording(self):
        """<summary>録画を停止する</summary>"""
        if self.is_recording and self.record_process:
            self.record_process.communicate(input=b'q')
            self.record_process = None
            self.is_recording = False