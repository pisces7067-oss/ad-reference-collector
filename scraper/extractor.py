"""광고 라이브러리 GraphQL/HTML 응답에서 필드 추출.

광고 라이브러리는 GraphQL로 데이터를 받아오는데, 응답 구조가 자주 바뀜.
"흔히 등장하는 필드 이름"을 여러 가능성으로 시도하는 방어적 코드.

⚠️ 메타가 응답 스키마 바꾸면 여기가 가장 먼저 깨짐. 셀렉터/필드명을 한 곳에 모음.
"""
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Any


def _walk(obj: Any, key_names: tuple[str, ...]) -> list[Any]:
    """obj 안의 모든 깊이를 탐색하며 key_names 중 하나와 매칭되는 값들 수집."""
    found: list[Any] = []

    def visit(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in key_names:
                    found.append(v)
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(obj)
    return found


def extract_ads_from_graphql(payload: dict) -> list[dict]:
    """GraphQL 응답 한 덩어리에서 광고 카드들을 뽑아냄."""
    cards: list[dict] = []
    # 메타가 사용해온 컨테이너 이름들 — 자주 바뀌니 후보 여러 개
    containers = _walk(
        payload,
        ("ad_archive_id", "adArchiveID", "adArchiveId"),
    )
    if not containers:
        return cards

    # 광고 카드 노드를 찾으려면 ad_archive_id를 가진 dict를 찾아야 함
    def find_ad_nodes(node, acc):
        if isinstance(node, dict):
            if any(k in node for k in ("ad_archive_id", "adArchiveID", "adArchiveId")):
                acc.append(node)
            for v in node.values():
                find_ad_nodes(v, acc)
        elif isinstance(node, list):
            for item in node:
                find_ad_nodes(item, acc)

    nodes: list[dict] = []
    find_ad_nodes(payload, nodes)

    for node in nodes:
        try:
            cards.append(_node_to_ad(node))
        except Exception as e:
            # 한 광고가 깨져도 다음 광고는 계속
            cards.append({"_extract_error": str(e), "raw": node})
    return cards


def _first_value(node: dict, *keys: str, default=None):
    for k in keys:
        if k in node and node[k] is not None:
            return node[k]
    return default


def _node_to_ad(node: dict) -> dict:
    ad_id = str(_first_value(node, "ad_archive_id", "adArchiveID", "adArchiveId", default=""))
    snapshot = _first_value(node, "snapshot", default={}) or {}
    page_id = str(_first_value(snapshot, "page_id", "pageId", default=""))
    page_name = _first_value(snapshot, "page_name", "pageName", default="")

    # caption = 광고 본문 글
    body = snapshot.get("body") or {}
    if isinstance(body, dict):
        caption = body.get("text", "") or ""
    else:
        caption = str(body) if body else ""

    cta_text = snapshot.get("cta_text", "") or ""
    landing_url = snapshot.get("link_url", "") or ""
    display_url = snapshot.get("caption", "") or ""

    # media_urls
    media_urls: list[dict] = []
    for img in (snapshot.get("images") or []):
        url = img.get("original_image_url") or img.get("resized_image_url") or img.get("url")
        if url:
            media_urls.append({"type": "image", "url": url})
    for vid in (snapshot.get("videos") or []):
        url = vid.get("video_hd_url") or vid.get("video_sd_url")
        preview = vid.get("video_preview_image_url")
        if url:
            media_urls.append({"type": "video", "url": url})
        if preview:
            media_urls.append({"type": "image", "url": preview})
    for img in (snapshot.get("extra_images") or []):
        url = img.get("original_image_url") or img.get("url")
        if url:
            media_urls.append({"type": "image", "url": url})
    for vid in (snapshot.get("extra_videos") or []):
        url = vid.get("video_hd_url") or vid.get("video_sd_url")
        if url:
            media_urls.append({"type": "video", "url": url})

    # platforms
    raw_platforms = node.get("publisher_platform") or []
    platforms = [p.lower() for p in raw_platforms]

    # has_video
    has_video = bool(
        snapshot.get("display_format") == "VIDEO"
        or any(m["type"] == "video" for m in media_urls)
    )

    # is_active
    is_active = bool(node.get("is_active", True))

    # dates
    start_ts = node.get("start_date")
    end_ts = node.get("end_date")
    start_date = None
    start_datetime = None
    active_days = None

    if start_ts:
        try:
            dt = datetime.fromtimestamp(int(start_ts))
            start_date = dt.strftime("%Y-%m-%d")
            start_datetime = dt.isoformat()
            today = date.today()
            if is_active:
                active_days = (today - dt.date()).days
            elif end_ts:
                end_dt = datetime.fromtimestamp(int(end_ts))
                active_days = (end_dt.date() - dt.date()).days
        except (ValueError, OSError):
            pass

    return {
        "ad_id": ad_id,
        "page_id": page_id,
        "page_name": page_name,
        "caption": caption,
        "cta_text": cta_text,
        "landing_url": landing_url,
        "display_url": display_url,
        "platforms": platforms,
        "start_date": start_date,
        "start_datetime": start_datetime,
        "active_days": active_days,
        "is_active": is_active,
        "has_video": has_video,
        "media_urls": media_urls,
        "raw": node,
    }
