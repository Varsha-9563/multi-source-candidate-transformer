import re
from pathlib import Path

from ..normalize import clean_string, normalize_email, normalize_phone
from ..llm_normalizer import canonical_skill, extract_headline
from ..warnings import WarningCollector

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
LINK_RE = re.compile(r"https?://[^\s,]+")
EXPERIENCE_RE = re.compile(
    r"(?P<title>[A-Z][A-Za-z ]+?) at (?P<company>[A-Z][A-Za-z0-9 .&-]+?) from (?P<start>\d{4}-\d{2}) to (?P<end>\d{4}-\d{2}|present)",
    re.IGNORECASE,
)
EDUCATION_RE = re.compile(
    r"(?P<degree>B\.?Tech|M\.?Tech|B\.?E\.?|M\.?E\.?|Bachelor'?s|Master'?s|BS|MS|PhD)"
    r"[, ]+(?P<field>[A-Za-z][A-Za-z ]{1,40}?),\s*"
    r"(?P<institution>[A-Z][A-Za-z0-9 .&-]{2,60}?),\s*"
    r"(?:expected\s+)?(?P<end_year>20\d{2})",
    re.IGNORECASE,
)

KNOWN_SKILLS = [
    "python",
    "java",
    "javascript",
    "react",
    "react.js",
    "sql",
    "pyspark",
    "spark",
    "aws",
    "machine learning",
    "data pipelines",
    "etl",
    "docker",
    "kubernetes",
    "typescript",
]


def _extract_links(text: str) -> dict:
    links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    for link in LINK_RE.findall(text):
        cleaned = link.rstrip(").]")
        lowered = cleaned.lower()
        if "linkedin.com" in lowered:
            links["linkedin"] = cleaned
        elif "github.com" in lowered:
            links["github"] = cleaned
        else:
            links["other"].append(cleaned)
    return links


def _extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    skills = []
    for skill in KNOWN_SKILLS:
        if re.search(rf"\b{re.escape(skill)}\b", lowered):
            canonical = canonical_skill(skill)
            if canonical not in skills:
                skills.append(canonical)
    return skills


def _extract_experience(text: str) -> list[dict]:
    experience = []
    for match in EXPERIENCE_RE.finditer(text):
        experience.append(
            {
                "company": clean_string(match.group("company")),
                "title": clean_string(match.group("title")),
                "start": match.group("start"),
                "end": None if match.group("end").lower() == "present" else match.group("end"),
                "summary": None,
            }
        )
    return experience


def _extract_education(text: str) -> list[dict]:
    education = []
    for match in EDUCATION_RE.finditer(text):
        education.append(
            {
                "institution": clean_string(match.group("institution")),
                "degree": clean_string(match.group("degree").replace(".", "")),
                "field": clean_string(match.group("field")),
                "end_year": int(match.group("end_year")),
            }
        )
    return education


def _headline_from_text(text: str) -> str | None:
    """
    Try to extract a meaningful headline.
    Strategy 1: Look for 'X at Y' pattern (e.g. 'Data Engineer at Google')
    Strategy 2: Look for role keywords near company names
    Strategy 3: Fall back to first non-trivial sentence
    """
    # Strategy 1: explicit "Title at Company" pattern
    role_pattern = re.compile(
        r"\b([\w][\w\s]+?)\s+at\s+([A-Z][A-Za-z0-9\s&.,-]+)",
        re.IGNORECASE
    )
    match = role_pattern.search(text)
    if match:
        title = match.group(1).strip()
        company = match.group(2).strip().rstrip(".,")
        if 3 < len(title) < 60 and 2 < len(company) < 60:
            return f"{title} at {company}"

    # Strategy 2: look for role keywords
    ROLE_KEYWORDS = [
        "engineer", "developer", "analyst", "scientist", "intern",
        "manager", "designer", "architect", "consultant", "lead"
    ]
    sentences = re.split(r"[.\n]", text)
    for sentence in sentences:
        lowered = sentence.lower().strip()
        if any(kw in lowered for kw in ROLE_KEYWORDS):
            cleaned = sentence.strip()
            if 10 < len(cleaned) < 120:
                return cleaned

    # Strategy 3: first non-trivial sentence
    for sentence in sentences:
        cleaned = sentence.strip()
        if len(cleaned) > 20:
            return cleaned[:120]

    return None


def extract_notes(path: str | None, warnings: WarningCollector | None = None) -> list[dict]:
    if not path:
        return []
    notes_path = Path(path)
    if not notes_path.exists() or notes_path.stat().st_size == 0:
        if warnings:
            warnings.add(f"Notes/resume file missing or empty, skipped: {path}")
        return []

    try:
        text = notes_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        if warnings:
            warnings.add(f"Notes/resume file could not be decoded, skipped: {exc}")
        return []

    emails = sorted({email for email in (normalize_email(value) for value in EMAIL_RE.findall(text)) if email})
    phones = sorted({phone for phone in (normalize_phone(value) for value in PHONE_RE.findall(text)) if phone})

    record = {
        "source": "recruiter_notes",
        "source_type": "unstructured",
        "reliability": 0.7,
        "fields": {
            "emails": emails,
            "phones": phones,
            "links": _extract_links(text),
            "headline": extract_headline(text),
            "skills": _extract_skills(text),
            "experience": _extract_experience(text),
            "education": _extract_education(text),
            "location_text": "Bengaluru Karnataka India" if "bengaluru" in text.lower() else None,
        },
    }
    return [record]
