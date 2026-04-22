"""ポケ轍URL（TSV）の読み込み"""
import csv
import os


def load_yakkun_urls_by_japanese_name(tsv_path):
    """3列目=日本語名、4列目=ポケ轍URL。同一日本語名は後勝ち。"""
    mapping = {}
    if not os.path.exists(tsv_path):
        print(f"DEBUG: pokemon TSV NOT FOUND: {tsv_path}")
        return mapping
    try:
        with open(tsv_path, encoding="utf-8", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader, None)  # header
            for row in reader:
                if len(row) < 4:
                    continue
                jp = row[2].strip()
                url = row[3].strip()
                if jp and url.startswith("http"):
                    mapping[jp] = url
    except Exception as e:
        print(f"DEBUG: failed to load pokemon TSV: {e}")
    return mapping


def load_pokecham_battle_support_urls_by_japanese_name(tsv_path):
    """3列目=日本語名、5列目=ポケモンバトルサポートURL。同一日本語名は後勝ち。"""
    mapping = {}
    if not os.path.exists(tsv_path):
        print(f"DEBUG: pokemon TSV NOT FOUND: {tsv_path}")
        return mapping
    try:
        with open(tsv_path, encoding="utf-8", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader, None)
            for row in reader:
                if len(row) < 5:
                    continue
                jp = row[2].strip()
                url = row[4].strip()
                if jp and url.startswith("http"):
                    mapping[jp] = url
    except Exception as e:
        print(f"DEBUG: failed to load pokecham URLs from TSV: {e}")
    return mapping
