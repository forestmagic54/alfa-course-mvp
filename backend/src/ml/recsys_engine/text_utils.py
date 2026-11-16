"""Offline-safe text normalization matching RecSys v5.4."""

import html
import re


def display_text(value: object) -> str:
    if value is None:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value: object) -> str:
    return display_text(value).lower().replace("ё", "е")
