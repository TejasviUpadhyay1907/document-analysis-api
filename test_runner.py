"""
test_runner.py
--------------
Scans test_files/ subdirectories, encodes each file as Base64,
and generates ready-to-use JSON request bodies for the document analysis API.

Usage:
    # Process all files in all test_files/ subdirectories
    python test_runner.py

    # Process a single file
    python test_runner.py --single "test_files/pdfs/invoice.pdf"
"""

import argparse
import base64
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_DIRS = {
    "pdf":   Path("test_files/pdfs"),
    "docx":  Path("test_files/docx"),
    "image": Path("test_files/images"),
}

OUTPUT_DIR = Path("test_files/output")

EXTENSION_MAP = {
    ".pdf":  "pdf",
    ".docx": "docx",
    ".png":  "image",
    ".jpg":  "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".bmp":  "image",
    ".webp": "image",
}


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def encode_file(path: Path) -> str:
    """Read a file and return its Base64-encoded string."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def detect_file_type(path: Path) -> str | None:
    """Return the API fileType string for a given file, or None if unsupported."""
    return EXTENSION_MAP.get(path.suffix.lower())


def build_request_body(path: Path) -> dict:
    """Build the full JSON request body dict for a given file."""
    file_type = detect_file_type(path)
    if file_type is None:
        raise ValueError(f"Unsupported file extension: {path.suffix}")
    return {
        "fileName": path.name,
        "fileType": file_type,
        "fileBase64": encode_file(path),
    }


def save_json(body: dict, source_path: Path) -> Path:
    """Save the request body as a pretty-printed JSON file in the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{source_path.name}.json"
    out_path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def print_result(body: dict, saved_path: Path) -> None:
    """Print a formatted block for one file result."""
    preview = body["fileBase64"][:60] + "..." if len(body["fileBase64"]) > 60 else body["fileBase64"]
    display = {**body, "fileBase64": preview}
    print("-" * 60)
    print(f"FILE : {body['fileName']}")
    print(f"TYPE : {body['fileType']}")
    print(f"SIZE : {len(body['fileBase64'])} Base64 chars")
    print(f"SAVED: {saved_path}")
    print("REQUEST BODY (fileBase64 truncated for display):")
    print(json.dumps(display, indent=2))
    print("-" * 60)
    print()


# ---------------------------------------------------------------------------
# Processing logic
# ---------------------------------------------------------------------------

def process_file(path: Path) -> bool:
    """Process a single file. Returns True on success, False on skip/error."""
    file_type = detect_file_type(path)
    if file_type is None:
        print(f"[SKIP] Unsupported file type: {path.name}")
        return False

    try:
        body = build_request_body(path)
        saved = save_json(body, path)
        print_result(body, saved)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to process {path.name}: {e}")
        return False


def process_all() -> None:
    """Scan all test_files/ subdirectories and process every supported file."""
    total = 0
    success = 0

    for file_type, directory in TEST_DIRS.items():
        if not directory.exists():
            print(f"[INFO] Directory not found, skipping: {directory}")
            continue

        files = [f for f in sorted(directory.iterdir()) if f.is_file()]
        if not files:
            print(f"[INFO] No files found in: {directory}")
            continue

        print(f"\n{'='*60}")
        print(f"SCANNING: {directory}  ({len(files)} file(s))")
        print(f"{'='*60}\n")

        for f in files:
            total += 1
            if process_file(f):
                success += 1

    print(f"\n{'='*60}")
    print(f"DONE — {success}/{total} file(s) processed successfully.")
    print(f"JSON bodies saved to: {OUTPUT_DIR.resolve()}")
    print(f"{'='*60}\n")


def process_single(file_path: str) -> None:
    """Process one specific file by path."""
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    print(f"\nProcessing single file: {path.resolve()}\n")
    if not process_file(path):
        sys.exit(1)

    print(f"JSON body saved to: {OUTPUT_DIR.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Base64 JSON request bodies for the document analysis API."
    )
    parser.add_argument(
        "--single",
        metavar="FILE_PATH",
        help="Process a single file instead of scanning all test_files/ directories.",
    )
    args = parser.parse_args()

    if args.single:
        process_single(args.single)
    else:
        process_all()


if __name__ == "__main__":
    main()
