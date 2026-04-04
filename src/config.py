from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

# Resolve .env path (project root)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # Core API key (for your app)
    api_key: Optional[str] = None

    # OCR (optional)
    tesseract_cmd: Optional[str] = None

    # OpenRouter LLM (optional)
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = "arcee-ai/trinity-mini:free"

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    def model_post_init(self, __context) -> None:
        # Clean values
        if self.api_key:
            object.__setattr__(self, "api_key", self.api_key.strip())

        if self.openrouter_api_key:
            cleaned_key = self.openrouter_api_key.strip()
            if cleaned_key == "":
                cleaned_key = None
            object.__setattr__(self, "openrouter_api_key", cleaned_key)

        if self.openrouter_model:
            cleaned_model = self.openrouter_model.strip()
            if cleaned_model == "":
                cleaned_model = "arcee-ai/trinity-mini:free"
            object.__setattr__(self, "openrouter_model", cleaned_model)


settings = Settings()