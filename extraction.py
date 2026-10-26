import io
import logging
from functools import lru_cache, wraps
from pathlib import Path

import numpy as np
import pymupdf
import pytesseract
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image, UnidentifiedImageError
from paddleocr import PaddleOCR 
import threading

from statistics import median

MIN_CONFIDENCE = 60  # median Tesseract confidence below this => unsure
MIN_WORDS = 5        # need at least this many words to judge

BASE = Path(__file__).resolve().parent
IN_DIR, OUT_DIR = BASE / "documents", BASE / "output"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
HANDWRITING_CONF = 60  # mean Tesseract confidence below this => handwritten
MIN_IMG_SIZE = 100     # skip tiny embedded images (icons, bullets)
BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("extract")

USED: set[str] = set()  # technologies used for the file currently being processed


def traced(label):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            USED.add(label)
            return fn(*args, **kwargs)
        return wrapper
    return deco


tesseract_text = traced("tesseract")(pytesseract.image_to_string)


@lru_cache(maxsize=1)
def paddle():
     
    return PaddleOCR(lang="en")


def tesseract_unsure(img: Image.Image) -> bool:
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, t in zip(data["conf"], data["text"]) if t.strip() and float(c) >= 0]
    return len(confs) >= MIN_WORDS and median(confs) < MIN_CONFIDENCE


@traced("paddleocr")
def paddle_text(img: Image.Image) -> str:
    lines = []
    for page in paddle().ocr(np.array(img)) or []:
        if isinstance(page, dict):                      # PaddleOCR 3.x
            lines += page.get("rec_texts", [])
        else:                                           # PaddleOCR 2.x
            lines += [item[1][0] for item in page or []]
    return "\n".join(lines)


def ocr(img: Image.Image) -> str:
    img = img.convert("RGB")
    return paddle_text(img) if tesseract_unsure(img) else tesseract_text(img)


def ocr_blob(blob: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(blob))
        return ocr(img).strip() if min(img.size) >= MIN_IMG_SIZE else ""
    except (UnidentifiedImageError, OSError) as e:
        log.warning(f"  skipped embedded image: {e}")
        return ""


def from_image(path: Path) -> str:
    with Image.open(path) as img:
        return ocr(img)


@traced("pymupdf")
def from_pdf(path: Path) -> str:
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("password-protected PDF")
        pages = []
        for num, page in enumerate(doc, 1):
            parts = []
            for block in page.get_text("dict", sort=True)["blocks"]:  # reading order
                if block["type"] == 0:    # text block
                    parts.append("\n".join("".join(s["text"] for s in l["spans"]) for l in block["lines"]))
                elif block["type"] == 1:  # image block -> OCR in place
                    parts.append(ocr_blob(block["image"]))
            body = "\n".join(p for p in parts if p.strip())
            pages.append(f"--- Page {num} ---\n{body}")
    return "\n\n".join(pages)


def docx_paragraph(par: Paragraph) -> str:
    parts = [par.text]
    for blip in par._p.iter(BLIP):  # images inside this paragraph
        rid = blip.get(qn("r:embed"))
        if rid:
            parts.append(ocr_blob(par.part.related_parts[rid].blob))
    return "\n".join(p for p in parts if p.strip())


def docx_blocks(parent, container):
    for child in container.iterchildren():  # body order: paragraphs and tables
        if child.tag == qn("w:p"):
            yield docx_paragraph(Paragraph(child, parent))
        elif child.tag == qn("w:tbl"):
            for row in Table(child, parent).rows:
                yield " | ".join("\n".join(docx_blocks(c, c._tc)) for c in row.cells)


@traced("python-docx")
def from_docx(path: Path) -> str:
    doc = Document(path)
    return "\n".join(b for b in docx_blocks(doc, doc.element.body) if b.strip())


HANDLERS = {".pdf": from_pdf, ".docx": from_docx, **{e: from_image for e in IMAGE_EXT}}

LOCK = threading.Lock()  # USED is a shared global, so process one file at a time


def extract_text(path: Path) -> tuple[str, list[str]]:
    with LOCK:
        USED.clear()
        text = HANDLERS[path.suffix.lower()](path)
        return text, sorted(USED)


def main():
    if not IN_DIR.is_dir():
        log.error(f"input folder not found: {IN_DIR}")
        return
    OUT_DIR.mkdir(exist_ok=True)
    for path in sorted(p for p in IN_DIR.iterdir() if p.is_file()):
        handler = HANDLERS.get(path.suffix.lower())
        if not handler:
            log.warning(f"unsupported, skipped: {path.name}")
            continue
        USED.clear()
        try:
            text = handler(path)
            print(text)
            (OUT_DIR / f"{path.stem}.txt").write_text(text, encoding="utf-8")
            tools = " + ".join(sorted(USED))
            log.info(f"ok: {path.name} ({len(text)} chars) via {tools}")
        except Exception as e:  # corrupted, encrypted, unreadable, etc.
            log.error(f"failed: {path.name} -> {e}")


if __name__ == "__main__":
    main()