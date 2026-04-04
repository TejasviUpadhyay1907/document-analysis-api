from fastapi import HTTPException, status
import base64
import binascii


def decode_base64_file(file_base64: str) -> bytes:
    """
    Safely decode a Base64-encoded string into raw bytes.

    - Adds missing padding if required
    - Validates Base64 format
    - Raises HTTP 400 on invalid input
    """

    if not file_base64 or not isinstance(file_base64, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Base64 input must be a non-empty string.",
        )

    try:
        # Fix missing padding
        padded = file_base64 + "=" * (-len(file_base64) % 4)

        return base64.b64decode(padded, validate=True)

    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Base64 encoding. Please provide a valid Base64-encoded file.",
        )