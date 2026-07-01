import json
import re
from html import unescape
from pathlib import Path
from typing import Any


def load_content_list(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_report(report_id: str, source_json_path: Path, pages: list) -> list[dict]:
    rows = []
    for page_index, page in enumerate(pages, start=1):
        for block_index, block in enumerate(page):
            content = block.get("content")
            content_keys = sorted(content.keys()) if isinstance(content, dict) else []
            html = _table_html(content)
            caption = _caption_text(content)
            footnote = _footnote_text(content)
            image_path = _image_path(content)
            text_parts = [_block_text(block), _html_to_text(html), caption, footnote]
            text = _clean_text("\n".join(part for part in text_parts if part))
            rows.append(
                {
                    "report_id": report_id,
                    "source_json_path": str(source_json_path),
                    "page_no": page_index,
                    "block_index": block_index,
                    "block_id": f"{report_id}:p{page_index}:b{block_index}",
                    "block_type": block.get("type", ""),
                    "sub_type": block.get("sub_type", ""),
                    "bbox": json.dumps(block.get("bbox", []), ensure_ascii=False),
                    "text": text,
                    "html": html,
                    "caption_text": caption,
                    "footnote_text": footnote,
                    "image_path": image_path,
                    "table_type": _content_value(content, "table_type"),
                    "table_nest_level": _content_value(content, "table_nest_level"),
                    "raw_content_keys": "|".join(content_keys),
                }
            )
    return rows


def _block_text(block: dict) -> str:
    content = block.get("content", "")
    if isinstance(content, dict):
        block_type = block.get("type")
        if block_type == "list":
            return _list_text(content)
        if block_type == "table":
            return ""
        if "content" in content:
            return _text_of(content.get("content"))
    return _text_of(content)


def _list_text(content: dict) -> str:
    items = []
    for item in content.get("list_items", []) or []:
        if isinstance(item, dict):
            items.append(_text_of(item.get("item_content", "")))
        else:
            items.append(_text_of(item))
    return "\n".join(item for item in items if item)


def _text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(_text_of(item) for item in value)
    if isinstance(value, dict):
        if "content" in value and isinstance(value.get("content"), (str, int, float)):
            return str(value.get("content"))
        return "\n".join(_text_of(v) for v in value.values())
    return str(value)


def _table_html(content: Any) -> str:
    return _content_value(content, "html")


def _caption_text(content: Any) -> str:
    if not isinstance(content, dict):
        return ""
    values = []
    for key in ("table_caption", "chart_caption", "image_caption"):
        values.append(_text_of(content.get(key, "")))
    return _clean_text("\n".join(value for value in values if value))


def _footnote_text(content: Any) -> str:
    if not isinstance(content, dict):
        return ""
    values = []
    for key in ("table_footnote", "chart_footnote", "image_footnote"):
        values.append(_text_of(content.get(key, "")))
    return _clean_text("\n".join(value for value in values if value))


def _image_path(content: Any) -> str:
    if not isinstance(content, dict):
        return ""
    source = content.get("image_source")
    if isinstance(source, dict):
        return str(source.get("path", "") or "")
    return ""


def _content_value(content: Any, key: str) -> str:
    if isinstance(content, dict):
        value = content.get(key, "")
        if value is None:
            return ""
        return str(value)
    return ""


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " | ", html, flags=re.I)
    text = re.sub(r"</tr>\s*<tr[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_text(unescape(text))


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text or "")
    text = re.sub(r"\n\s*", "\n", text)
    return text.strip()

