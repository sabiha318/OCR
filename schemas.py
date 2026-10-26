import re
from pydantic import BaseModel, EmailStr, field_validator
from typing import Literal


def normalize_bd_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    for prefix in ("00880", "880", "0"):  # international, country code, local trunk zero
        if digits.startswith(prefix):
            digits = digits[len(prefix):]
            break
    return f"+880{digits}" if len(digits) == 10 else None



class Experience(BaseModel):
    position: str | None = None
    description: str | None = None


class Profile(BaseModel):
    name: str | None = None
    education: list[str] = []
    skills: list[str] = []
    experiences: list[Experience] = []


class Resume(Profile):
    """Profile plus the fields found by regex."""
    email: EmailStr | None = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v):
        return normalize_bd_phone(v) if v else None


class ExtractionResult(BaseModel):
    data: Resume
    missing_fields: list[str]
    tools_used: list[str]
    parsing: Literal["regex", "regex+llm"]