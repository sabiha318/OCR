import json
import logging
import sys
import time
from pathlib import Path

from pipeline import OUT_DIR, build_summary, process_named

IN_DIR = Path(__file__).resolve().parent / "documents"


def render_report(summary: dict) -> str:
    lines = [
        f"Processed {summary['total']} files in {summary['seconds']}s: "
        f"{summary['succeeded']} succeeded ({summary['incomplete']} with missing fields), "
        f"{summary['failed']} failed",
        "",
    ]
    for e in summary["files"]:
        if e["status"] == "success":
            missing = ", ".join(e["missing_fields"]) or "none"
            lines.append(f"OK    {e['file']:<40} {e['parsing']:<10} missing: {missing}")
        else:
            lines.append(f"FAIL  {e['file']:<40} {e['error']}")
    return "\n".join(lines)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    in_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else IN_DIR
    if not in_dir.is_dir():
        sys.exit(f"input folder not found: {in_dir}")

    start = time.perf_counter()
    files = sorted(p for p in in_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    summary = build_summary([process_named(p, p.name) for p in files], time.perf_counter() - start)

    OUT_DIR.mkdir(exist_ok=True)
    slim = {**summary, "files": [{k: v for k, v in e.items() if k != "data"} for e in summary["files"]]}
    (OUT_DIR / "summary.json").write_text(json.dumps(slim, indent=2), encoding="utf-8")
    report = render_report(summary)
    (OUT_DIR / "summary.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()