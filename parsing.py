import logging
import time
from pathlib import Path

from extraction import HANDLERS, extract_text
from parsing import missing_fields
from schemas import ExtractionResult

log = logging.getLogger("pipeline")
OUT_DIR = Path(__file__).resolve().parent / "output"


class ExtractionError(Exception):
    """The file could not be turned into text."""


class UnsupportedFile(ExtractionError):
    """The file type is not supported."""


def process_file(path: Path) -> ExtractionResult:
    suffix = path.suffix.lower()
    if suffix not in HANDLERS:
        raise UnsupportedFile(f"unsupported file type: {suffix or 'unknown'}")
    try:
        text, tools = extract_text(path)
    except Exception as e:  # corrupted, encrypted, unreadable
        raise ExtractionError(f"could not read file: {e}") from e
    if not text.strip():
        raise ExtractionError("no text could be extracted from the file")

    data, method = parse_resume_hybrid(text)
    return ExtractionResult(
        data=data, missing_fields=missing_fields(data), tools_used=tools, parsing=method
    )


def save_json(name: str, result: ExtractionResult) -> None:
    folder = OUT_DIR / "json"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{Path(name).name}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")


def process_named(path: Path, name: str) -> dict:
    """Process one file, save its JSON, return a summary entry. Never raises."""
    start, entry = time.perf_counter(), {"file": name}
    try:
        result = process_file(path)
        save_json(name, result)
        entry |= {
            "status": "success",
            "parsing": result.parsing,
            "tools": result.tools_used,
            "missing_fields": result.missing_fields,
            "data": result.data.model_dump(),
        }
    except ExtractionError as e:
        entry |= {"status": "failed", "error": str(e)}
    except Exception as e:  # an unexpected bug in one file must not stop the batch
        log.exception("unexpected error: %s", name)
        entry |= {"status": "failed", "error": f"unexpected error: {e}"}
    entry["seconds"] = round(time.perf_counter() - start, 1)
    return entry


def build_summary(entries: list[dict], seconds: float) -> dict:
    ok = [e for e in entries if e["status"] == "success"]
    return {
        "total": len(entries),
        "succeeded": len(ok),
        "failed": len(entries) - len(ok),
        "incomplete": sum(1 for e in ok if e["missing_fields"]),
        "seconds": round(seconds, 1),
        "files": entries,
    }