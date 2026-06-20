#!/usr/bin/env python3
"""
OCR Tool — Extract text from images using RapidOCR (PaddleOCR models via ONNX Runtime).

Supports: Chinese, English, Japanese, Korean, and 80+ languages.
Much better than EasyOCR for Chinese text recognition.
"""
import logging
from tools.registry import registry

logger = logging.getLogger(__name__)

# Lazy-loaded OCR engine
_ocr_engine = None

def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine

OCR_SCHEMA = {
    "name": "ocr_extract",
    "description": "Extract text from an image using OCR. Best for screenshots, documents, handwritten text. Supports Chinese/English/Japanese/Korean.",
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to image file or URL"
            },
            "language": {
                "type": "string",
                "description": "Hint language (ch/en/ja/ko). Default: auto-detect",
                "default": "auto"
            }
        },
        "required": ["image_path"]
    }
}

def _handle_ocr(args):
    image_path = args.get("image_path", "")
    if not image_path:
        return {"error": "image_path is required"}
    
    try:
        ocr = _get_ocr()
        result, elapse = ocr(image_path)
        
        if result is None:
            return {"text": "", "confidence": 0, "elapse": elapse}
        
        # Format results
        lines = []
        total_conf = 0
        for item in result:
            box, text, conf = item
            lines.append({"text": text, "confidence": round(conf, 4), "box": box})
            total_conf += conf
        
        avg_conf = total_conf / len(lines) if lines else 0
        
        return {
            "text": "\n".join(l["text"] for l in lines),
            "lines": lines,
            "line_count": len(lines),
            "avg_confidence": round(avg_conf, 4),
            "elapse": {"total": round(elapse[0], 3), "detect": round(elapse[1], 3), "recognize": round(elapse[2], 3)}
        }
    except Exception as e:
        return {"error": str(e)}

registry.register(
    name="ocr_extract",
    toolset="vision",
    schema=OCR_SCHEMA,
    handler=_handle_ocr,
    is_async=False,
    emoji="📝",
)
