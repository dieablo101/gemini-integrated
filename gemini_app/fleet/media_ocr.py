"""Mobile screenshot OCR extraction and media/music telemetry parser."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union


# Lazy-loaded singleton OCR engine
_OCR_ENGINE = None
_OCR_AVAILABLE: Optional[bool] = None


def get_ocr_engine():
    """Initializes and returns the RapidOCR engine singleton if available."""
    global _OCR_ENGINE, _OCR_AVAILABLE
    if _OCR_AVAILABLE is False:
        return None
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE

    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
        _OCR_AVAILABLE = True
        return _OCR_ENGINE
    except Exception:
        _OCR_AVAILABLE = False
        return None


def extract_screen_text(
    target: Union[str, Path, bytes],
) -> Dict[str, Any]:
    """Runs RapidOCR on an image file path or raw image bytes.
    
    Returns:
        Dict with status, lines, confidence scores, and raw reconstructed text.
    """
    engine = get_ocr_engine()
    if engine is None:
        return {
            "status": "unavailable",
            "error": "RapidOCR engine not available in this environment.",
            "lines": [],
            "raw_text": "",
        }

    try:
        img_input = target
        if isinstance(target, (str, Path)):
            img_path = Path(target)
            if not img_path.exists():
                return {"status": "error", "error": f"Image file not found: {target}", "lines": [], "raw_text": ""}
            img_input = str(img_path)
        elif isinstance(target, bytes):
            import io
            import numpy as np
            from PIL import Image
            pil_img = Image.open(io.BytesIO(target)).convert("RGB")
            img_input = np.array(pil_img)

        result, elapse = engine(img_input)
        if not result:
            return {
                "status": "ok",
                "lines": [],
                "items": [],
                "raw_text": "",
                "confidence_avg": 0.0,
                "elapse": elapse,
            }

        lines: List[str] = []
        items: List[Dict[str, Any]] = []
        scores: List[float] = []

        for box, text, score in result:
            clean_text = str(text).strip()
            if not clean_text:
                continue
            lines.append(clean_text)
            try:
                sc = float(score)
                scores.append(sc)
            except (ValueError, TypeError):
                sc = 0.0
            items.append({
                "text": clean_text,
                "score": sc,
                "box": box,
            })

        avg_score = sum(scores) / len(scores) if scores else 0.0
        return {
            "status": "ok",
            "lines": lines,
            "items": items,
            "raw_text": "\n".join(lines),
            "confidence_avg": round(avg_score, 3),
            "elapse": elapse,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"OCR extraction failed: {exc}",
            "lines": [],
            "raw_text": "",
        }


def parse_mobile_media(
    ocr_result: Dict[str, Any],
    filename: str = "",
) -> Dict[str, Any]:
    """Parses extracted OCR lines and image metadata to identify music/media details."""
    lines: List[str] = ocr_result.get("lines", [])
    raw_text: str = ocr_result.get("raw_text", "")
    fname_lower = filename.lower()

    # Detect player app
    detected_app = "Unknown Media Player"
    if "spotify" in fname_lower or "spotify" in raw_text.lower():
        detected_app = "Spotify"
    elif "youtube" in fname_lower or "ytmusic" in fname_lower or "youtube music" in raw_text.lower():
        detected_app = "YouTube Music"
    elif "apple" in fname_lower or "apple music" in raw_text.lower():
        detected_app = "Apple Music"
    elif "soundcloud" in fname_lower or "soundcloud" in raw_text.lower():
        detected_app = "SoundCloud"
    elif "tidal" in fname_lower or "tidal" in raw_text.lower():
        detected_app = "Tidal"
    elif "bandcamp" in fname_lower or "bandcamp" in raw_text.lower():
        detected_app = "Bandcamp"
    elif "chrome" in fname_lower:
        detected_app = "Chrome Browser"

    # Detect timestamps (e.g., 0:12, 3:04, 01:23)
    timestamp_pattern = re.compile(r"\b\d{1,2}:\d{2}\b")
    timestamps = timestamp_pattern.findall(raw_text)
    time_str = " / ".join(timestamps[:2]) if timestamps else ""

    # Detect audio output devices
    audio_device = ""
    device_keywords = ["earbuds", "headphones", "airpods", "buds", "quietcomfort", "bose", "sony", "wh-", "wf-", "bluetooth", "speaker"]
    for line in lines:
        if any(kw in line.lower() for kw in device_keywords):
            audio_device = line
            break

    # Detect playlist or album
    playlist = ""
    for i, line in enumerate(lines):
        line_l = line.lower()
        if "playlist" in line_l or "playing from" in line_l or "album" in line_l:
            # Check current line or next line
            if ":" in line:
                playlist = line.split(":", 1)[1].strip()
            elif i + 1 < len(lines):
                playlist = lines[i + 1]
            break

    # Detect Explicit flag
    is_explicit = bool(re.search(r"\b(?:explicit|explicitcontent|parental advisory)\b", raw_text, re.IGNORECASE))

    # Detect artist and track title heuristics
    artist = ""
    title = ""
    album = ""

    # If artwork keywords or single token exists
    for line in lines:
        if line.startswith("SST") or line.startswith("EP") or "album" in line.lower():
            album = line
            break

    # Look for artist: In Spotify screenshots, artist usually sits above the progress bar (timestamps)
    # Filter out known UI words
    ui_blacklist = {
        "playing from playlist", "explicitcontent", "misuf", "about the song", "about the sona",
        "beta", "lyrics", "home", "search", "your library", "queue", "devices", "shuffle",
        "repeat", "play", "pause", "next", "previous"
    }

    filtered_candidates = [
        l for l in lines
        if l.lower() not in ui_blacklist
        and not timestamp_pattern.fullmatch(l)
        and l != audio_device
        and l != playlist
        and l != album
    ]

    # In Spotify mobile layout, artist and title appear before the timestamps
    # Often artist is directly before timestamp
    if filtered_candidates:
        if len(filtered_candidates) == 1:
            artist = filtered_candidates[0]
        else:
            # Common pattern: Track is first, Artist is second (or vice versa)
            artist = filtered_candidates[-1]
            title = filtered_candidates[0] if len(filtered_candidates) > 1 else ""

    # Construct one-line summary
    summary_parts = []
    if artist and title:
        summary_parts.append(f"{artist} - {title}")
    elif artist:
        summary_parts.append(artist)
    elif title:
        summary_parts.append(title)
    else:
        summary_parts.append(f"Media playing in {detected_app}")

    if playlist:
        summary_parts.append(f"[{playlist}]")
    if time_str:
        summary_parts.append(f"({time_str})")
    if audio_device:
        summary_parts.append(f"-> {audio_device}")
    if detected_app and detected_app != "Unknown Media Player":
        summary_parts.append(f"via {detected_app}")

    summary = " ".join(summary_parts)

    return {
        "app": detected_app,
        "artist": artist,
        "title": title,
        "playlist": playlist,
        "album": album,
        "timestamps": time_str,
        "audio_device": audio_device,
        "explicit": is_explicit,
        "summary": summary,
        "ocr_confidence": ocr_result.get("confidence_avg", 0.0),
        "raw_lines": lines,
    }
