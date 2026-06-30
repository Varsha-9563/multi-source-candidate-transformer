# merge.py — first 4 lines only
import hashlib
from collections import defaultdict
from datetime import date

from .llm_normalizer import canonical_skill, normalize_location # overrides


FIELD_METHODS = {
    "full_name": "direct_extract",
    "emails": "regex_or_direct_extract",
    "phones": "e164_normalization",
    "location": "location_normalization",
    "links": "regex_extract",
    "headline": "keyword_inference",
    "skills": "canonical_skill_match",
    "experience": "pattern_extract",
    "education": "pattern_extract",
}


def _candidate_id(emails: list[str], full_name: str | None) -> str:
    stable_key = emails[0] if emails else full_name or "unknown"
    digest = hashlib.sha1(stable_key.lower().encode("utf-8")).hexdigest()[:10]
    return f"cand_{digest}"


def _add_provenance(provenance: list[dict], field: str, source: str, method: str | None = None) -> None:
    provenance.append({"field": field, "source": source, "method": method or FIELD_METHODS.get(field, "derived")})


def _choose_scalar(records: list[dict], field: str) -> tuple[object | None, str | None]:
    candidates = []
    for record in records:
        value = record["fields"].get(field)
        if value:
            candidates.append((record["reliability"], value, record["source"]))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def _merge_unique_lists(records: list[dict], field: str) -> tuple[list, list[str]]:
    values = []
    sources = []
    seen = set()
    for record in sorted(records, key=lambda item: item["reliability"], reverse=True):
        for value in record["fields"].get(field, []) or []:
            marker = str(value).lower()
            if marker not in seen:
                seen.add(marker)
                values.append(value)
                sources.append(record["source"])
    return values, sources


def _merge_links(records: list[dict], provenance: list[dict]) -> dict:
    links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    for record in records:
        candidate = record["fields"].get("links")
        if not candidate:
            continue
        for key in ["linkedin", "github", "portfolio"]:
            if not links[key] and candidate.get(key):
                links[key] = candidate[key]
                _add_provenance(provenance, f"links.{key}", record["source"], "regex_extract")
        for link in candidate.get("other", []):
            if link not in links["other"]:
                links["other"].append(link)
                _add_provenance(provenance, "links.other", record["source"], "regex_extract")
    return links


def _merge_skills(records: list[dict], provenance: list[dict]) -> list[dict]:
    skill_sources = defaultdict(list)
    skill_scores = defaultdict(float)
    for record in records:
        for skill in record["fields"].get("skills", []) or []:
            if record["source"] == "resume_pdf" and record.get("reliability", 0) >= 0.8:
                canonical = skill
            else:
                canonical = canonical_skill(skill)
            if record["source"] not in skill_sources[canonical]:
                skill_sources[canonical].append(record["source"])
            skill_scores[canonical] = max(skill_scores[canonical], record["reliability"])

    skills = []
    for name in sorted(skill_sources):
        agreement_bonus = min(0.1 * (len(skill_sources[name]) - 1), 0.2)
        confidence = min(round(skill_scores[name] + agreement_bonus, 2), 0.99)
        skills.append({"name": name, "confidence": confidence, "sources": skill_sources[name]})
        for source in skill_sources[name]:
            _add_provenance(provenance, "skills", source, "canonical_skill_match")
    return skills


def _merge_objects(records: list[dict], field: str, provenance: list[dict]) -> list[dict]:
    values = []
    seen = set()
    for record in records:
        for item in record["fields"].get(field, []) or []:
            marker = tuple(sorted((key, str(value)) for key, value in item.items()))
            if marker not in seen:
                seen.add(marker)
                values.append(item)
                _add_provenance(provenance, field, record["source"])
    return values


def _confidence(profile: dict, source_count: int) -> float:
    weighted_fields = {
        "full_name": 0.15,
        "emails": 0.15,
        "phones": 0.12,
        "skills": 0.15,
        "experience": 0.12,
        "education": 0.08,
        "location": 0.08,
        "headline": 0.05,
        "links": 0.05,
        "source_bonus": 0.05,
    }
    score = 0.0
    for field, weight in weighted_fields.items():
        if field == "source_bonus":
            if source_count >= 2:
                score += weight * 0.6
        elif field == "location":
            if any(profile["location"].values()):
                score += weight
        elif field == "links":
            if profile["links"]["linkedin"] or profile["links"]["github"] or profile["links"]["other"]:
                score += weight
        elif profile.get(field):
            score += weight
    if len(profile.get("phones", [])) > 1:
        score -= 0.05
    return round(min(score, 0.99), 2)

def _compute_years_experience(experience: list[dict]) -> float | None:
    """Sum up months across all experience entries, return total years."""
    if not experience:
        return None
    total_months = 0
    today = date.today()
    for entry in experience:
        start_str = entry.get("start")
        end_str = entry.get("end")
        if not start_str:
            continue
        try:
            sy, sm = int(start_str[:4]), int(start_str[5:7])
            if end_str:
                ey, em = int(end_str[:4]), int(end_str[5:7])
            else:
                ey, em = today.year, today.month  # still ongoing
            total_months += max(0, (ey - sy) * 12 + (em - sm))
        except (ValueError, IndexError):
            continue
    if total_months == 0:
        return None
    return round(total_months / 12, 1)

def merge_sources(records: list[dict]) -> dict:
    provenance = []
    full_name, name_source = _choose_scalar(records, "full_name")
    if name_source:
        _add_provenance(provenance, "full_name", name_source)

    emails, email_sources = _merge_unique_lists(records, "emails")
    for source in email_sources:
        _add_provenance(provenance, "emails", source)

    phones, phone_sources = _merge_unique_lists(records, "phones")
    for source in phone_sources:
        _add_provenance(provenance, "phones", source)

    location_text, location_source = _choose_scalar(records, "location_text")
    location = normalize_location(location_text)
    if location_source and any(location.values()):
        _add_provenance(provenance, "location", location_source)

    headline, headline_source = _choose_scalar(records, "headline")
    if not headline:
        title, title_source = _choose_scalar(records, "title")
        company, company_source = _choose_scalar(records, "current_company")
        if title and company:
            headline = f"{title} at {company}"
            _add_provenance(provenance, "headline", title_source or company_source, "derived_from_csv_title_company")
    elif headline_source:
        _add_provenance(provenance, "headline", headline_source)

    links = _merge_links(records, provenance)
    skills = _merge_skills(records, provenance)
    experience = _merge_objects(records, "experience", provenance)
    education = _merge_objects(records, "education", provenance)

    profile = {
        "candidate_id": _candidate_id(emails, full_name),
        "full_name": full_name,
        "emails": emails,
        "phones": phones,
        "location": location,
        "links": links,
        "headline": headline,
        "years_experience": _compute_years_experience(experience),
        "skills": skills,
        "experience": experience,
        "education": education,
        "provenance": provenance,
        "overall_confidence": 0.0,
        "warnings": [],
    }
    profile["overall_confidence"] = _confidence(profile, len(records))
    return profile
