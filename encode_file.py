"""
encode_file.py - Convert a local file to Base64 for API testing.

Usage:
    python encode_file.py <file_path>
    python encode_file.py <file_path> --save

Examples:
    python encode_file.py sample.pdf
    python encode_file.py report.docx --save
    python encode_file.py scan.png --save
"""

import base64
import sys
from pathlib import Path


def encode_file(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_file_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".bmp": "image",
        ".gif": "image",
        ".webp": "image",
    }
    file_type = mapping.get(ext)
    if not file_type:
        print(f"WARNING: Unrecognised extension '{ext}'. Defaulting fileType to 'image'.")
        return "image"
    return file_type


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    file_path = sys.argv[1]
    save_to_file = "--save" in sys.argv

    file_name = Path(file_path).name
    file_type = detect_file_type(file_path)
    b64_string = encode_file(file_path)

    # Print the ready-to-use JSON request body
    print("\n" + "=" * 60)
    print("FILE INFO")
    print("=" * 60)
    print(f"  Name : {file_name}")
    print(f"  Type : {file_type}")
    print(f"  Size : {len(b64_string)} Base64 characters")

    print("\n" + "=" * 60)
    print("REQUEST BODY (paste into Swagger or curl)")
    print("=" * 60)
    print("{")
    print(f'  "fileName": "{file_name}",')
    print(f'  "fileType": "{file_type}",')
    print(f'  "fileBase64": "{b64_string[:60]}...  <truncated - use full string below>"')
    print("}")

    if save_to_file:
        output_path = Path("encoded_output.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"fileName: {file_name}\n")
            f.write(f"fileType: {file_type}\n")
            f.write(f"fileBase64:\n{b64_string}\n")
        print(f"\nFull Base64 saved to: {output_path.resolve()}")
    else:
        print("\n" + "=" * 60)
        print("FULL BASE64 STRING")
        print("=" * 60)
        print(b64_string)

    print("\n" + "=" * 60)
    print("CURL COMMAND")
    print("=" * 60)
    print("curl -X POST http://127.0.0.1:8000/api/document-analyze \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -H "x-api-key: sk_track2_123456" \\')
    print('  -d @- << EOF')
    print("{")
    print(f'  "fileName": "{file_name}",')
    print(f'  "fileType": "{file_type}",')
    print(f'  "fileBase64": "{b64_string[:40]}..."')
    print("}")
    print("EOF")
    print("\nTip: Use --save to write the full Base64 to encoded_output.txt")


if __name__ == "__main__":
    main()
