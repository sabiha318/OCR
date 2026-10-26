import re

from pydantic import EmailStr, TypeAdapter, ValidationError

from schemas import Resume, normalize_bd_phone




EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,18}\d")
BULLETS = " \t•·▪●*-– "
NOT_NAMES = {"resume", "curriculum vitae", "cv", "profile", "summary", "contact"}
HEADINGS = {
    "education": "education",
    "academic background": "education",
    "qualifications": "education",

    "skills": "skills",
    "technical skills": "skills",
    "core competencies": "skills",

    "experience": "experience",
    "work experience": "experience",

    "projects": "other",
    "certifications": "other",
    "summary": "other",
    "objective": "other",
    "languages": "other",
    "references": "other",
    "interests": "other",
}

email_check = TypeAdapter(EmailStr)


def clean_lines(text: str) -> list[str]:
    lines = (line.strip(BULLETS) for line in text.splitlines() if not line.startswith("--- Page"))
    return [line for line in lines if line]


def find_email(text: str) -> str | None:
    for match in EMAIL.finditer(text):
        try:
            return str(email_check.validate_python(match.group()))
        except ValidationError:
            continue


def find_phone(text: str) -> str | None:
    for match in PHONE.finditer(text):
        phone = normalize_bd_phone(match.group())
        if phone:
            return phone


def find_name(lines: list[str]) -> str | None:
    for line in lines[:8]:  # the name is almost always near the top
        words = line.split()
        if line.lower() in NOT_NAMES or not 2 <= len(words) <= 4:
            continue
        if all(re.fullmatch(r"[A-Za-z.'-]+", w) for w in words):
            return line.title() if line.isupper() else line


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections, current = {}, None
    for line in lines:
        heading = HEADINGS.get(line.lower().rstrip(":"))
        if heading:
            current = heading
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return sections


def find_skills(lines: list[str]) -> list[str]:
    skills = []
    for line in lines:
        line = line.split(":", 1)[-1]  # drop prefixes like "Languages:"
        skills += [s.strip(BULLETS) for s in re.split(r"[,;|•·]", line)]
    return list(dict.fromkeys(s for s in skills if 1 < len(s) <= 40))  # dedupe, keep order

def find_experiences(lines: list[str]) -> list[dict]:
    experiences = []
    current = {}
    for line in lines:
        # Detect a position line (role, company, years)
        if re.search(r"\d{4}", line):  # crude check for years
            if current:
                experiences.append(current)
                current = {}
            current["position"] = line
        else:
            # Treat as description line
            if "description" in current:
                current["description"] += " " + line
            else:
                current["description"] = line
    if current:
        experiences.append(current)
    return experiences


def parse_resume(text: str) -> Resume:
    lines = clean_lines(text)
    sections = split_sections(lines)
    return Resume(
        name=find_name(lines),
        email=find_email(text),
        phone=find_phone(text),
        education=sections.get("education", []),
        skills=find_skills(sections.get("skills", [])),
        experiences=find_experiences(sections.get("experience", [])),
    )



def missing_fields(data: Resume) -> list[str]:
    return [field for field, value in data.model_dump().items() if not value]