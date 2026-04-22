"""SQLite: プロファイル別の対面ポケモン累計統計。"""
from __future__ import annotations

import sqlite3
from typing import Iterable

from backend.config.constants import Config


class ProfileStatsStore:
    def __init__(self, db_path: str | None = None):
        self._path = db_path or getattr(Config, "PROFILE_STATS_DB_PATH", "")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pokemon_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    pokemon_name TEXT NOT NULL,
                    match_count INTEGER NOT NULL DEFAULT 0,
                    selected_count INTEGER NOT NULL DEFAULT 0,
                    lead_count INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id),
                    UNIQUE(profile_id, pokemon_name)
                );
                """
            )
            n = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
            if n == 0:
                conn.execute(
                    "INSERT INTO profiles (display_name) VALUES (?)", ("デフォルト",)
                )

    def list_profiles(self) -> list[tuple[int, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, display_name FROM profiles ORDER BY id ASC"
            ).fetchall()
        return [(int(r[0]), str(r[1])) for r in rows]

    def create_profile(self, display_name: str) -> int:
        name = (display_name or "").strip() or "無題"
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO profiles (display_name) VALUES (?)", (name,)
            )
            return int(cur.lastrowid)

    def get_display_name(self, profile_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return str(row[0]) if row else ""

    def profile_exists(self, profile_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return row is not None

    def fetch_stats(
        self, profile_id: int, pokemon_names: Iterable[str]
    ) -> dict[str, tuple[int, int, int]]:
        """ポケモン名 -> (match_count, selected_count, lead_count)"""
        names = [n for n in pokemon_names if n and n != "Empty"]
        if not names:
            return {}
        placeholders = ",".join("?" * len(names))
        args: list = [profile_id, *names]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT pokemon_name, match_count, selected_count, lead_count
                FROM pokemon_stats
                WHERE profile_id = ? AND pokemon_name IN ({placeholders})
                """,
                args,
            ).fetchall()
        out: dict[str, tuple[int, int, int]] = {}
        for r in rows:
            out[str(r[0])] = (int(r[1]), int(r[2]), int(r[3]))
        return out

    def commit_battle_end(
        self, profile_id: int, party: list[str], selection: list[str]
    ) -> None:
        """バトル終了時: 6体 match+1、選出3体 selected+1、選出先頭 lead+1。"""
        clean_party = [p for p in party if p and p != "Empty"]
        clean_sel = [p for p in selection if p and p != "Empty"]
        if not clean_party:
            return

        sql_match = """
            INSERT INTO pokemon_stats (profile_id, pokemon_name, match_count, selected_count, lead_count)
            VALUES (?, ?, 1, 0, 0)
            ON CONFLICT(profile_id, pokemon_name) DO UPDATE SET
                match_count = match_count + 1
        """
        sql_sel = """
            INSERT INTO pokemon_stats (profile_id, pokemon_name, match_count, selected_count, lead_count)
            VALUES (?, ?, 0, 1, 0)
            ON CONFLICT(profile_id, pokemon_name) DO UPDATE SET
                selected_count = selected_count + 1
        """
        sql_lead = """
            INSERT INTO pokemon_stats (profile_id, pokemon_name, match_count, selected_count, lead_count)
            VALUES (?, ?, 0, 0, 1)
            ON CONFLICT(profile_id, pokemon_name) DO UPDATE SET
                lead_count = lead_count + 1
        """

        with self._connect() as conn:
            for p in clean_party:
                conn.execute(sql_match, (profile_id, p))
            for p in clean_sel:
                conn.execute(sql_sel, (profile_id, p))
            if clean_sel:
                conn.execute(sql_lead, (profile_id, clean_sel[0]))
            conn.commit()
