"""
<summary>日本語ファイル名による読み込み失敗を回避しつつ、背景を透過処理するスクリプト</summary>
"""
import cv2
import numpy as np
import os
import glob

def convert_bg_to_transparent_smart(input_dir, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    # フォルダ内の全てのpngファイルを取得
    image_paths = glob.glob(os.path.join(input_dir, "*.png"))
    
    if not image_paths:
        print(f"No images found in {input_dir}")
        return

    for path in image_paths:
        # --- 日本語パス対応の読み込み ---
        try:
            # np.fromfile でバイナリとして読み込み、cv2.imdecode で画像に変換
            img_array = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"Load Error ({os.path.basename(path)}): {e}")
            continue

        if img is None:
            print(f"Failed to decode: {os.path.basename(path)}")
            continue

        # 1. 処理用にアルファチャンネルを追加 (BGR -> BGRA)
        img_bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        h, w = img.shape[:2]

        # 2. 背景を特定するためのマスク作成 (FloodFill)
        mask = np.zeros((h + 2, w + 2), np.uint8)
        
        # 左上(0,0)の色を基準に、外側から繋がっている部分を塗りつぶす
        # diff=(5,5,5) で、圧縮等によるわずかな色ズレを許容
        flood_flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
        cv2.floodFill(img, mask, (0, 0), (0,0,0), (5, 5, 5), (5, 5, 5), flood_flags)

        # 抽出されたマスク部分（背景部分）
        bg_mask = mask[1:-1, 1:-1]

        # 3. 背景部分のアルファチャンネルを 0 (透明) に設定
        img_bgra[bg_mask == 255] = [0, 0, 0, 0]

        # --- 日本語パス対応の保存 ---
        file_name = os.path.basename(path)
        save_path = os.path.join(output_dir, file_name)
        
        try:
            # cv2.imencode でメモリ上の画像をエンコードし、tofile で書き出す
            ext = os.path.splitext(file_name)[1]
            result, n_img = cv2.imencode(ext, img_bgra)
            if result:
                n_img.tofile(save_path)
                print(f"Smart Processed: {file_name}")
        except Exception as e:
            print(f"Save Error ({file_name}): {e}")

if __name__ == "__main__":
    # 実行場所によらずプロジェクトルートを基準にする
    current_file_path = os.path.abspath(__file__)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)))
    
    in_dir = os.path.join(base_dir, "resources", "icons")
    out_dir = os.path.join(base_dir, "resources", "icons", "edited")
    
    print(f"Input Directory: {in_dir}")
    convert_bg_to_transparent_smart(in_dir, out_dir)