"""Local EN->ZH Translation - saves ~30-40% output tokens.

MiMo outputs English -> local Ollama qwen3.5:0.8b translates -> send Chinese.
"""

import json
import logging
import re
import urllib.request

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"
_MODEL = "qwen3.5:0.8b"
_TIMEOUT = 60


def _is_mostly_english(text):
    if not text or len(text) < 20:
        return False
    if text.startswith("MEDIA:") or text.startswith("```"):
        return False
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / len(text) > 0.6


def _contains_chinese(text):
    cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cn_chars / max(len(text), 1) > 0.15


def _split_text(text, max_chars=1500):
    if len(text) <= max_chars:
        return [text]
    chunks = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]


def translate_en_to_zh(text):
    if not text or len(text) < 20:
        return text
    if _contains_chinese(text):
        return text
    code_markers = text.count("```")
    if code_markers >= 2:
        return text
    try:
        chunks = _split_text(text, max_chars=1500)
        translated_chunks = []
        for chunk in chunks:
            if not _is_mostly_english(chunk):
                translated_chunks.append(chunk)
                continue
            prompt = "Translate to Chinese. Output ONLY the translation, preserve all formatting/markdown/code/URLs:\n" + chunk
            data = json.dumps({
                "model": _MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.1, "num_predict": len(chunk) * 2}
            }).encode()
            req = urllib.request.Request(_OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
            result = json.loads(resp.read())
            translated = result.get("response", "").strip()
            if translated:
                translated_chunks.append(translated)
            else:
                translated_chunks.append(chunk)
        return "\n\n".join(translated_chunks)
    except Exception as e:
        logger.warning("Translation failed: %s, returning original", e)
        return text


def translate_response(text, force=False):
    if not text:
        return text
    if not force and not _is_mostly_english(text):
        return text
    if len(text) < 50:
        return text
    return translate_en_to_zh(text)

def update_session_message(session_id: str, translated_response: str) -> None:
    """Update the last assistant message in the session DB with translated content.
    
    This ensures on_session_finalize stores Chinese (translated) content
    instead of English (raw LLM output).
    """
    if not session_id or not translated_response:
        return
    try:
        import sqlite3
        db_path = os.path.expanduser("~/.hermes/state.db")
        conn = sqlite3.connect(db_path)
        # Find the last assistant message for this session
        cursor = conn.execute(
            "SELECT id FROM messages WHERE session_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
            (session_id,)
        )
        row = cursor.fetchone()
        if row:
            msg_id = row[0]
            conn.execute(
                "UPDATE messages SET content = ? WHERE id = ?",
                (translated_response, msg_id)
            )
            conn.commit()
            logger.info("Updated session %s msg %d with translated content (%d chars)", 
                       session_id, msg_id, len(translated_response))
        conn.close()
    except Exception as e:
        logger.warning("Failed to update session message: %s", e)
