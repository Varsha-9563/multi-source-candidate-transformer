# """
# PDF resume extractor.
# Uses pdfplumber to extract raw text, then reuses the same
# regex/keyword logic as notes_extractor to pull structured fields.
# """

# import re
# from pathlib import Path

# from ..warnings import WarningCollector


# def extract_pdf(path: str | None, warnings: WarningCollector | None = None) -> list[dict]:
#     if not path:
#         return []

#     pdf_path = Path(path)
#     if not pdf_path.exists():
#         if warnings:
#             warnings.add(f"Resume PDF missing, skipped: {path}")
#         return []

#     # try importing pdfplumber — graceful if not installed
#     try:
#         import pdfplumber
#     except ImportError:
#         if warnings:
#             warnings.add("pdfplumber not installed, PDF resume skipped. Run: pip install pdfplumber")
#         return []

#     try:
#         text = ""
#         with pdfplumber.open(str(pdf_path)) as pdf:
#             for page in pdf.pages:
#                 page_text = page.extract_text()
#                 if page_text:
#                     text += page_text + "\n"
#     except Exception as exc:
#         if warnings:
#             warnings.add(f"Resume PDF could not be read, skipped: {exc}")
#         return []

#     if not text.strip():
#         if warnings:
#             warnings.add(f"Resume PDF has no extractable text, skipped: {path}")
#         return []

#     # clean up messy extracted text — collapse repeated spaces/blank lines
#     text = re.sub(r"[ \t]+", " ", text)
#     text = re.sub(r"\n{2,}", "\n", text)

#     # reuse notes extractor logic — PDF text is just unstructured text
#     from .notes_extractor import (
#         EMAIL_RE, PHONE_RE,
#         _extract_links, _extract_skills,
#         _extract_experience, _extract_education,
#     )
#     from ..normalize import normalize_email, normalize_phone
#     from ..llm_normalizer import extract_headline

#     emails = sorted({
#         e for e in (normalize_email(v) for v in EMAIL_RE.findall(text)) if e
#     })
#     phones = sorted({
#         p for p in (normalize_phone(v) for v in PHONE_RE.findall(text)) if p
#     })

#     # use only the FIRST line for headline extraction to avoid
#     # bleeding into "SKILLS" / "EXPERIENCE" section headers below it
#     first_block = text.split("\n\n")[0] if "\n\n" in text else "\n".join(text.split("\n")[:6])

#     return [{
#         "source": "resume_pdf",
#         "source_type": "unstructured",
#         "reliability": 0.85,   # resume is high reliability — candidate wrote it
#         "fields": {
#             "emails":        emails,
#             "phones":        phones,
#             "links":         _extract_links(text),
#             "headline":      extract_headline(first_block) or extract_headline(text),
#             "skills":        _extract_skills(text),
#             "experience":    _extract_experience(text),
#             "education":     _extract_education(text),
#             "location_text": _extract_location_hint(text),
#         },
#     }]


# def _extract_location_hint(text: str) -> str | None:
#     """Look for location patterns in resume text (first few lines only)."""
#     head = "\n".join(text.split("\n")[:6])
#     match = re.search(
#         r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Z][a-zA-Z\s]+?)(?:\n|$|\|)",
#         head
#     )
#     if match:
#         return f"{match.group(1)} {match.group(2)}".strip()
#     return None

"""
PDF resume extractor.
Strategy: real-world resumes use irregular layouts (tables, bullet points,
column headers) that simple regex cannot reliably parse. We use the LLM
as the PRIMARY extraction method for resumes, with regex as a fallback
only when no API key is available — this is the inverse of recruiter
notes, where regex is primary because notes are short and informal.
"""

import json
import re
import os
from pathlib import Path

from ..warnings import WarningCollector
from ..llm_normalizer import _call_claude


def extract_pdf(path: str | None, warnings: WarningCollector | None = None) -> list[dict]:
    if not path:
        return []

    pdf_path = Path(path)
    if not pdf_path.exists():
        if warnings:
            warnings.add(f"Resume PDF missing, skipped: {path}")
        return []

    try:
        import pdfplumber
    except ImportError:
        if warnings:
            warnings.add("pdfplumber not installed, PDF resume skipped. Run: pip install pdfplumber")
        return []

    try:
        text = ""
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as exc:
        if warnings:
            warnings.add(f"Resume PDF could not be read, skipped: {exc}")
        return []

    if not text.strip():
        if warnings:
            warnings.add(f"Resume PDF has no extractable text, skipped: {path}")
        return []

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)

    # ── PRIMARY PATH: LLM extraction (handles any resume layout) ──
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        fields = _extract_resume_via_llm(text)
        if fields:
            return [{
                "source": "resume_pdf",
                "source_type": "unstructured",
                "reliability": 0.85,
                "fields": fields,
            }]
        if warnings:
            warnings.add("LLM resume extraction failed, falling back to regex")

    # ── FALLBACK PATH: regex (only when no API key, or LLM failed) ──
    return _extract_resume_via_regex(text)


def _extract_resume_via_llm(text: str) -> dict | None:
    """
    Send full resume text to Claude and ask for structured JSON back.
    This handles ANY layout — tables, bullets, columns, icons —
    because the LLM reads it the way a human recruiter would.
    """
    snippet = text[:4000]  # keep token cost reasonable, most resumes fit
    prompt = f"""Extract structured information from this resume text. Return ONLY valid JSON, no markdown fences, no explanation.

Schema:
{{
  "full_name": string or null,
  "emails": array of strings,
  "phones": array of strings,
  "headline": string or null (a one-line professional summary, e.g. "Backend Engineer with ML experience"),
  "location_text": string or null,
  "skills": array of strings (technical skills only, canonical names like "React" not "react.js"),
  "experience": array of {{"company": string, "title": string, "start": "YYYY-MM" or null, "end": "YYYY-MM" or null, "summary": string or null}},
  "education": array of {{"institution": string, "degree": string, "field": string or null, "end_year": number or null}},
  "links": {{"linkedin": string or null, "github": string or null, "portfolio": string or null, "other": array of strings}}
}}

Rules:
- If a field cannot be determined, use null (never invent data)
- Dates: convert "June 2025" to "2025-06". If only a year is given, use "YYYY-01"
- For ongoing roles (e.g. "Present", "Status: In Progress"), set "end" to null
- Internships, work experience, AND substantial projects all count as "experience" if they show real technical work
- Only include genuinely technical skills, not soft skills

Resume text:
{snippet}"""

    result = _call_claude(prompt)
    if not result:
        return None

    try:
        clean = re.sub(r"```json|```", "", result).strip()
        parsed = json.loads(clean)
        # safety defaults
        parsed.setdefault("emails", [])
        parsed.setdefault("phones", [])
        parsed.setdefault("skills", [])
        parsed.setdefault("experience", [])
        parsed.setdefault("education", [])
        parsed.setdefault("links", {"linkedin": None, "github": None, "portfolio": None, "other": []})
        return parsed
    except (json.JSONDecodeError, AttributeError):
        return None


def _extract_resume_via_regex(text: str) -> list[dict]:
    """Fallback when no API key is set. Best-effort only."""
    from .notes_extractor import (
        EMAIL_RE, PHONE_RE,
        _extract_links, _extract_skills,
        _extract_experience, _extract_education,
    )
    from ..normalize import normalize_email, normalize_phone
    from ..llm_normalizer import extract_headline

    emails = sorted({e for e in (normalize_email(v) for v in EMAIL_RE.findall(text)) if e})
    phones = sorted({p for p in (normalize_phone(v) for v in PHONE_RE.findall(text)) if p})
    first_block = "\n".join(text.split("\n")[:6])

    return [{
        "source": "resume_pdf",
        "source_type": "unstructured",
        "reliability": 0.6,  # lower reliability — regex on resumes is unreliable
        "fields": {
            "emails": emails,
            "phones": phones,
            "links": _extract_links(text),
            "headline": extract_headline(first_block) or extract_headline(text),
            "skills": _extract_skills(text),
            "experience": _extract_experience(text),
            "education": _extract_education(text),
            "location_text": None,
        },
    }]