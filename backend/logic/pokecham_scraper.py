"""ポケモンバトルサポート（pokechamdb.com）のHTMLを1回取得して統計を抽出する。"""
from __future__ import annotations

import urllib.request
from typing import Any

from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_html(url: str, *, timeout_sec: float = 30.0, user_agent: str = DEFAULT_USER_AGENT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")


def _extract_items(soup: BeautifulSoup, title: str) -> list[dict[str, str]]:
    data: list[dict[str, str]] = []
    for span in soup.select("span.text-xs.font-black"):
        text = span.get_text(strip=True)
        if title not in text:
            continue
        flex_div = span.find_parent("div")
        if flex_div is None:
            continue
        card = flex_div.find_parent("div")
        if card is None:
            continue
        ul = card.find("ul")
        if ul is None:
            continue
        for row in ul.find_all("li", recursive=False):
            name_el = row.select_one(".font-bold")
            rate_el = row.select_one(".tabular-nums")
            if name_el and rate_el:
                data.append(
                    {
                        "名前": name_el.get_text(strip=True),
                        "採用率": rate_el.get_text(strip=True),
                    }
                )
        break
    return data


def _extract_evs(soup: BeautifulSoup) -> list[dict[str, str]]:
    data: list[dict[str, str]] = []
    table = None
    for t in soup.find_all("table"):
        cls = t.get("class") or []
        if "w-full" in cls and any("min-w-" in c for c in cls):
            table = t
            break
    if table is None:
        return data
    tbody = table.find("tbody")
    if tbody is None:
        return data
    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 8:
            continue
        data.append(
            {
                "H": tds[1].get_text(strip=True),
                "A": tds[2].get_text(strip=True),
                "B": tds[3].get_text(strip=True),
                "C": tds[4].get_text(strip=True),
                "D": tds[5].get_text(strip=True),
                "S": tds[6].get_text(strip=True),
                "採用率": tds[7].get_text(strip=True),
            }
        )
    return data


def parse_pokecham_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    return {
        "ポケモン名": name,
        "わざ": _extract_items(soup, "わざ"),
        "もちもの": _extract_items(soup, "もちもの"),
        "とくせい": _extract_items(soup, "とくせい"),
        "せいかく": _extract_items(soup, "せいかく"),
        "能力ポイント配分": _extract_evs(soup),
    }


def scrape_pokemon_page(url: str) -> dict[str, Any]:
    html = fetch_html(url)
    return parse_pokecham_html(html)
