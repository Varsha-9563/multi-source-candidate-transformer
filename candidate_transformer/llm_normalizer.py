"""
LLM-augmented normalization.
Hardcoded maps handle the common cases (fast, deterministic).
LLM handles anything unknown (slow path, called only when needed).
Results are cached in-memory so LLM is called at most once per unknown value.
"""
from dotenv import load_dotenv

load_dotenv(override=True)
import json
import os
import re
import requests
from functools import lru_cache
import time
# ── Hardcoded fast-path maps ─────────────────────────────────────────────────

SKILL_ALIASES = {
    "py": "Python", "python": "Python",
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "react": "React", "react.js": "React", "reactjs": "React",
    "node": "Node.js", "node.js": "Node.js", "nodejs": "Node.js",
    "next": "Next.js", "next.js": "Next.js", "nextjs": "Next.js",
    "sql": "SQL", "mysql": "MySQL", "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL", "mongo": "MongoDB", "mongodb": "MongoDB",
    "aws": "AWS", "gcp": "GCP", "azure": "Azure",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "dl": "Deep Learning", "deep learning": "Deep Learning",
    "pyspark": "PySpark", "spark": "Apache Spark",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "docker": "Docker", "git": "Git",
    "java": "Java", "c++": "C++", "cpp": "C++",
    "golang": "Go", "go": "Go", "rust": "Rust",
    "etl": "ETL", "data pipelines": "Data Pipelines",
}

CITY_MAP = {
    # India
    "bengaluru": ("Bengaluru", "KA", "IN"),
    "bangalore": ("Bengaluru", "KA", "IN"),
    "mumbai": ("Mumbai", "MH", "IN"),
    "bombay": ("Mumbai", "MH", "IN"),
    "delhi": ("Delhi", "DL", "IN"),
    "new delhi": ("Delhi", "DL", "IN"),
    "hyderabad": ("Hyderabad", "TS", "IN"),
    "chennai": ("Chennai", "TN", "IN"),
    "pune": ("Pune", "MH", "IN"),
    "kolkata": ("Kolkata", "WB", "IN"),
    "noida": ("Noida", "UP", "IN"),
    "gurugram": ("Gurugram", "HR", "IN"),
    "gurgaon": ("Gurugram", "HR", "IN"),
    # US
    "san francisco": ("San Francisco", "CA", "US"),
    "new york": ("New York", "NY", "US"),
    "seattle": ("Seattle", "WA", "US"),
    "austin": ("Austin", "TX", "US"),
    "boston": ("Boston", "MA", "US"),
    # Europe
    "berlin": ("Berlin", "BE", "DE"),
    "london": ("London", "ENG", "GB"),
    "paris": ("Paris", "IDF", "FR"),
}

COUNTRY_ALIASES = {
    "india": "IN", "in": "IN",
    "usa": "US", "united states": "US", "us": "US",
    "uk": "GB", "united kingdom": "GB",
    "germany": "DE", "france": "FR",
    "canada": "CA", "australia": "AU",
}


# ── LLM fallback ─────────────────────────────────────────────────────────────

# def _call_claude(prompt: str) -> str | None:
#     """
#     Call an LLM API. Tries Anthropic Claude first (if key present),
#     falls back to Google Gemini free tier (if key present).
#     Returns text response or None if both fail / neither configured.
#     """
#     anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
#     gemini_key = os.environ.get("GEMINI_API_KEY", "")

#     # ── Try Anthropic first ──────────────────────────────────────
#     if anthropic_key:
#         try:
#             resp = requests.post(
#                 "https://api.anthropic.com/v1/messages",
#                 headers={
#                     "x-api-key": anthropic_key,
#                     "anthropic-version": "2023-06-01",
#                     "content-type": "application/json",
#                 },
#                 json={
#                     "model": "claude-haiku-4-5-20251001",
#                     "max_tokens": 1000,
#                     "messages": [{"role": "user", "content": prompt}],
#                 },
#                 timeout=10,
#             )
#             if resp.status_code == 200:
#                 return resp.json()["content"][0]["text"].strip()
#         except Exception:
#             pass  # fall through to Gemini

    
# # ── Fall back to Gemini (free tier) ──────────────────────────
#     print(f"DEBUG: anthropic_key={'set' if anthropic_key else 'EMPTY'}, gemini_key={'set' if gemini_key else 'EMPTY'}")

#     # ── Fall back to Gemini (free tier) ──────────────────────────
#     if gemini_key:
#         time.sleep(2) 
#         try:
#             resp = requests.post(
#                 f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-001:generateContent?key={gemini_key}",
#                 headers={"content-type": "application/json"},
#                 json={
#                     "contents": [{"parts": [{"text": prompt}]}],
#                     "generationConfig": {"maxOutputTokens": 1000},
#                 },
#                 timeout=10,
#             )
#             print(f"DEBUG GEMINI: status={resp.status_code}, body={resp.text[:300]}")
#             if resp.status_code == 200:
#                 data = resp.json()
#                 return data["candidates"][0]["content"]["parts"][0]["text"].strip()
#         except Exception as exc:
#             print(f"DEBUG GEMINI EXCEPTION: {exc}")

#     return None
def _call_claude(prompt: str) -> str | None:
    """
    Call an LLM API. Tries Anthropic Claude first (if key present),
    falls back to Google Gemini (if key present), using the new
    google-genai SDK which supports the newer AQ.-prefixed key format.
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    print("Gemini key loaded:", bool(gemini_key))
        
    print("Gemini key prefix:", gemini_key[:10] if gemini_key else "NONE")

    # ── Try Anthropic first ──────────────────────────────────────
    if anthropic_key:
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception:
            pass  # fall through to Gemini

    # ── Fall back to Gemini using the new SDK ────────────────────
    # ── Fall back to Gemini using the new SDK ────────────────────
    # ── Fall back to Gemini using the new SDK ────────────────────
    if gemini_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=15000)  # milliseconds
                ),
            )
            if response and response.text:
                return response.text.strip()
        except Exception as exc:
            print(f"DEBUG GEMINI SDK EXCEPTION: {exc}")

    return None


@lru_cache(maxsize=256)
def canonicalize_skill_llm(raw: str) -> str:
    """
    Ask LLM to canonicalize an unknown skill.
    lru_cache means each unique unknown is only sent once per run.
    """
    prompt = (
        f'Return only the canonical industry-standard name for this programming '
        f'skill or technology: "{raw}". '
        f'Examples: "py" -> "Python", "k8s" -> "Kubernetes", "nextjs" -> "Next.js". '
        f'Return ONLY the name, nothing else.'
    )
    result = _call_claude(prompt)
    # safety check — if LLM returns something wild, fall back to title case
    if result and len(result) < 50 and "\n" not in result:
        return result
    return raw.title()


@lru_cache(maxsize=128)
def normalize_location_llm(raw: str) -> dict:
    """
    Ask LLM to parse an unknown location into city/region/country.
    """
    prompt = (
        f'Parse this location text into JSON with keys city, region, country. '
        f'country must be ISO-3166 alpha-2 code. '
        f'Return ONLY valid JSON, no explanation. '
        f'If a value is unknown return null. '
        f'Location: "{raw}"'
    )
    result = _call_claude(prompt)
    if result:
        try:
            # strip markdown fences if LLM adds them
            clean = re.sub(r"```json|```", "", result).strip()
            parsed = json.loads(clean)
            return {
                "city": parsed.get("city"),
                "region": parsed.get("region"),
                "country": parsed.get("country"),
            }
        except (json.JSONDecodeError, KeyError):
            pass
    return {"city": None, "region": None, "country": None}


@lru_cache(maxsize=64)
def extract_headline_llm(text: str) -> str | None:
    """
    Ask LLM to extract a clean one-line professional headline
    from unstructured recruiter notes.
    """
    # only send first 500 chars to keep token cost low
    snippet = text[:500]
    prompt = (
        f'From the following recruiter notes, extract a single professional '
        f'headline (max 100 chars) like "Senior Data Engineer at Google" or '
        f'"Full Stack Developer with 3 years experience". '
        f'Return ONLY the headline, no quotes, no explanation. '
        f'If you cannot determine one, return null.\n\nNotes: {snippet}'
    )
    result = _call_claude(prompt)
    if result and result.lower() != "null" and len(result) < 120:
        return result
    return None


# ── Public hybrid functions (these replace the old normalize.py ones) ─────────

def canonical_skill(value: str) -> str:
    """Fast path: hardcoded map. Slow path: LLM."""
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    # fast path
    if lowered in SKILL_ALIASES:
        return SKILL_ALIASES[lowered]
    # slow path — only if ANTHROPIC_API_KEY or GEMINI_API_KEY is set
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return canonicalize_skill_llm(cleaned)
    # no key → title case fallback
    return cleaned.title()


def normalize_location(value: str) -> dict:
    """Fast path: city map. Slow path: LLM."""
    text = (value or "").lower().strip()

    # fast path — check city map
    for keyword, (city, region, country) in CITY_MAP.items():
        if keyword in text:
            return {"city": city, "region": region, "country": country}

    # fast path — at least get country
    country = None
    for alias, code in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            country = code
            break

    if country:
        return {"city": None, "region": None, "country": country}

    # slow path — ask LLM
    # slow path — ask LLM
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return normalize_location_llm(text)

    return {"city": None, "region": None, "country": None}


def extract_headline(notes_text: str) -> str | None:
    """Regex fast path first, LLM slow path if needed."""
    # fast path — "Title at Company" pattern
    # in llm_normalizer.py, extract_headline function:
    match = re.search(
        r"\b([A-Z][a-zA-Z \t]{2,40}?)[ \t]+at[ \t]+([A-Z][A-Za-z0-9 \t&.]{2,30}?)(?=[ \t]+from|[ \t]*[,.\n]|$)",
        notes_text  # no IGNORECASE — capital-letter requirement must hold
    )
    if match:
        title = match.group(1).strip()
        company = match.group(2).strip().rstrip(".,")
        if 3 < len(title) < 60:
            return f"{title} at {company}"

    # slow path — LLM
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return extract_headline_llm(notes_text)

    return None