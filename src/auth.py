from fastapi import Header, HTTPException, status
from src.config import settings


async def verify_api_key(x_api_key: str = Header(..., alias="x-api-key")) -> None:
    """
    Validate the x-api-key header.

    - Must be present
    - Must match API key from environment
    """

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
        )

    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )