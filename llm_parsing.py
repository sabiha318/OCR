import logging
from functools import lru_cache

from google import genai
from google.genai import errors, types

from parsing import missing_fields, parse_resume
from schemas import Profile, Resume

log = logging.getLogger("llm")
MODEL = "gemini-3.8-flash"  # newer Flash models exist; check which are free in AI Studio
LLM_FIELDS = {"name", "education", "skills", "experiences"}  # email and phone are regex-only

SYSTEM = (
    "Extract the candidate's details from the resume text. Use only what the text states; "
    "use null or an empty list when a field is absent. Never use a referee's or "
    "supervisor's details as the candidate's. Education: one entry per degree or school, "
    "copying the wording from the text. Skills: individual skill names only, no category labels. "
    "Experiences: one entry per job; position is the job title line as written, "
    "description is the responsibilities text."
)




@lru_cache(maxsize=1)
def client() -> genai.Client:
    return genai.Client()  # reads GEMINI_API_KEY; raises ValueError if it is missing


def extract_profile(text: str) -> Profile:
    response = client().models.generate_content(
        model=MODEL,
        contents=f"<resume>\n{text}\n</resume>",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=Profile,  # restore this: it forces the right keys
            temperature=0,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),  # remove if the API rejects it
        ),
    )
    if not response.text:
        raise ValueError("empty response from Gemini")
    return Profile.model_validate_json(response.text)


def parse_resume_hybrid(text: str) -> tuple[Resume, str]:
    data = parse_resume(text)  # regex first
    if not LLM_FIELDS & set(missing_fields(data)):
        return data, "regex"

    try:
        profile = extract_profile(text)
    except (errors.APIError, ValueError) as e:
        log.warning("LLM step failed, keeping regex result: %s", e)
        return data, "regex"

    low, filled = text.lower(), {}
    if not data.name and profile.name and profile.name.lower() in low:
        filled["name"] = profile.name
    if not data.education:
        filled["education"] = profile.education
    if not data.skills:
        filled["skills"] = [s for s in profile.skills if s.lower() in low]
    if not data.experiences and profile.experiences:
        filled["experiences"] = profile.experiences

    if not any(filled.values()):
        return data, "regex"
    return data.model_copy(update=filled), "regex+llm"


