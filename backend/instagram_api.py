# backend/instagram_api.py
import os
import io
import re
import time
import urllib.parse
import requests
from collections.abc import Mapping, Sequence


class InstaApiError(Exception):
    """Ошибка при работе с ScrapeCreators API."""
    pass


# --- helpers --------------------------------------------------------------

# поддерживаем /reel/, /reels/ и /p/
_SHORTCODE_RE = re.compile(r"instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_\-]+)/?")

def _get_api_key() -> str:
    key = os.getenv("SCRAPE_CREATORS_API_KEY")
    if not key:
        raise InstaApiError("SCRAPE_CREATORS_API_KEY не задан в окружении (.env)")
    return key

def _get_post_detail_endpoint() -> str:
    return os.getenv(
        "POST_DETAIL_ENDPOINT",
        "https://api.scrapecreators.com/v1/instagram/post",
    )

def _extract_shortcode(insta_url: str) -> str | None:
    # режем query/фрагмент на всякий случай (иногда ссылка приходит с ?igshid=...)
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(insta_url)
        normalized = f"{parts.scheme}://{parts.netloc}{parts.path}"
    except Exception:
        normalized = insta_url
    m = _SHORTCODE_RE.search(normalized)
    return m.group(1) if m else None


# Рекурсивный проход по любому JSON и сбор «похожих на видео» ссылок
def _deep_find_video_urls(obj) -> list[str]:
    found: list[str] = []

    def walk(x):
        if isinstance(x, Mapping):
            # частые поля
            direct = (
                x.get("video_url")
                or x.get("media_url")
                or x.get("download_url")
                or x.get("url")
                or x.get("src")
            )
            if isinstance(direct, str) and direct.startswith("http"):
                found.append(direct)

            # варианты видео у моб. API IG
            vv = x.get("video_versions")
            if isinstance(vv, Sequence):
                for it in vv:
                    if isinstance(it, Mapping):
                        u = it.get("url")
                        if isinstance(u, str) and u.startswith("http"):
                            found.append(u)

            for v in x.values():
                walk(v)

        elif isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)

    walk(obj)

    # уникализируем, сохранив порядок; отдаём сначала mp4
    seen = set()
    out = []
    for u in found:
        if u not in seen and u.startswith("http"):
            out.append(u)
            seen.add(u)
    out.sort(key=lambda u: (".mp4" not in u, len(u)))
    return out


# --- main API -------------------------------------------------------------

def get_post_details_by_url(insta_url: str) -> dict:
    """
    Запрос к ScrapeCreators (Post Detail).
    Пробуем сначала ?url=..., если неудачно — ?shortcode=...
    """
    api_key = _get_api_key()
    endpoint = _get_post_detail_endpoint()
    headers = {"x-api-key": api_key}

    # 1) пробуем по полной ссылке (с сохранением query — API это переварит)
    q1 = urllib.parse.urlencode({"url": insta_url})
    url1 = f"{endpoint}?{q1}"
    try:
        r1 = requests.get(url1, headers=headers, timeout=(10, 40))  # (connect, read)
        if r1.ok:
            return r1.json()
    except Exception:
        # продолжим со вторым вариантом
        pass

    # 2) пробуем по shortcode (работает и для /reels/)
    sc = _extract_shortcode(insta_url)
    if sc:
        q2 = urllib.parse.urlencode({"shortcode": sc})
        url2 = f"{endpoint}?{q2}"
        r2 = requests.get(url2, headers=headers, timeout=(10, 40))
        r2.raise_for_status()
        return r2.json()

    raise InstaApiError("Не удалось получить данные о посте: нет url и shortcode")


def extract_best_video_url(data: dict) -> str | None:
    """Универсально ищет прямой URL видео в ответе API."""
    candidates = _deep_find_video_urls(data)
    return candidates[0] if candidates else None


def download_video_to_memory(url: str, max_bytes: int = 49 * 1024 * 1024) -> io.BytesIO | None:
    """
    Скачивает видео и возвращает BytesIO (для Telegram).
    Если файл > max_bytes — вернёт None.
    С простым ретраем при таймаутах.
    """
    for attempt in range(3):
        try:
            with requests.get(url, stream=True, timeout=(10, 180)) as r:  # до 3 мин на чтение
                r.raise_for_status()
                buf = io.BytesIO()
                size = 0
                for chunk in r.iter_content(chunk_size=1024 * 128):
                    if not chunk:
                        continue
                    buf.write(chunk)
                    size += len(chunk)
                    if size > max_bytes:
                        return None
                buf.seek(0)
                buf.name = "reel.mp4"
                return buf
        except requests.Timeout:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
