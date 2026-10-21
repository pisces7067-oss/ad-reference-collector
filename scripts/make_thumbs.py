"""웹사이트(Streamlit Cloud)용 썸네일 만들기.

원본(data/media, 5GB)은 GitHub에 못 올리고, 페이스북 이미지 주소는 몇 주 뒤 만료돼서
웹사이트에서 이미지가 빈칸이 된다. 광고마다 작은 썸네일을 data/thumbs/{ad_id}.webp로
만들어 GitHub에 같이 올린다. 이미 만든 건 건너뛴다.

    python scripts/make_thumbs.py
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data"
THUMB_DIR = DATA_ROOT / "thumbs"
WIDTH = 400
QUALITY = 70


def media_abspath(rel_path: str) -> Path:
    if rel_path.startswith("data/"):
        return DATA_ROOT / rel_path[len("data/"):]
    return DATA_ROOT / rel_path


def local_source(media_paths: list[str]) -> Path | None:
    """대시보드와 같은 순서: preview_ 우선 → image_."""
    for key in ("preview_", "image_"):
        for rel in media_paths:
            path = media_abspath(rel)
            if key in path.name and path.exists():
                return path
    return None


def cdn_source(raw_json: str) -> str | None:
    try:
        snap = json.loads(raw_json or "{}").get("snapshot", {})
    except Exception:
        return None
    for img in snap.get("images", []):
        url = img.get("original_image_url") or img.get("resized_image_url") or img.get("url")
        if url:
            return url
    for vid in snap.get("videos", []):
        if vid.get("video_preview_image_url"):
            return vid["video_preview_image_url"]
    return None


def save_thumb(src: Image.Image, dst: Path) -> None:
    img = src.convert("RGB")
    if img.width > WIDTH:
        img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
    img.save(dst, "WEBP", quality=QUALITY, method=6)


def main() -> int:
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA_ROOT / "ads.db")
    rows = conn.execute("SELECT ad_id, media_paths, raw_json FROM ads").fetchall()

    made = skipped = missing = 0
    for ad_id, media_paths, raw_json in rows:
        dst = THUMB_DIR / f"{ad_id}.webp"
        if dst.exists():
            skipped += 1
            continue
        try:
            paths = json.loads(media_paths or "[]")
        except Exception:
            paths = []
        try:
            src = local_source(paths)
            if src:
                save_thumb(Image.open(src), dst)
            else:
                url = cdn_source(raw_json)
                if not url:
                    missing += 1
                    continue
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                save_thumb(Image.open(io.BytesIO(resp.content)), dst)
            made += 1
        except Exception as exc:
            missing += 1
            print(f"  ⚠️  {ad_id}: {exc}")

    size_mb = sum(p.stat().st_size for p in THUMB_DIR.glob("*.webp")) / 1024 / 1024
    print(f"✅ 썸네일 신규 {made}개 / 기존 {skipped}개 / 원본 없음 {missing}개 (전체 {size_mb:.1f}MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
