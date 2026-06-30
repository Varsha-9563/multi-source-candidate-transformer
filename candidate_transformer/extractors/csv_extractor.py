import csv
from pathlib import Path

from ..normalize import clean_string, normalize_email, normalize_phone
from ..warnings import WarningCollector


FIELD_ALIASES = {
    "full_name": ["name", "full_name", "candidate_name"],
    "emails": ["email", "emails", "primary_email"],
    "phones": ["phone", "phones", "mobile"],
    "current_company": ["current_company", "company", "employer"],
    "title": ["title", "current_title", "role"],
    "location_text": ["location", "city", "candidate_location"],
}


def _first(row: dict, aliases: list[str]) -> str | None:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        value = lowered.get(alias)
        if value is not None and clean_string(value):
            return clean_string(value)
    return None


def extract_csv(path: str | None, warnings: WarningCollector | None = None) -> list[dict]:
    if not path:
        return []
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        if warnings:
            warnings.add(f"Recruiter CSV missing or empty, skipped: {path}")
        return []

    records = []
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=1):
                if not row or not any(clean_string(value) for value in row.values()):
                    if warnings:
                        warnings.add(f"Empty CSV row skipped: row {index}")
                    continue
                email = normalize_email(_first(row, FIELD_ALIASES["emails"]))
                raw_phone = _first(row, FIELD_ALIASES["phones"])
                phone = normalize_phone(raw_phone)
                if raw_phone and not phone and warnings:
                    warnings.add(f"Invalid phone skipped in CSV row {index}: {raw_phone}")
                records.append(
                    {
                        "source": f"recruiter_csv:row_{index}",
                        "source_type": "structured",
                        "reliability": 0.9,
                        "fields": {
                            "full_name": _first(row, FIELD_ALIASES["full_name"]),
                            "emails": [email] if email else [],
                            "phones": [phone] if phone else [],
                            "current_company": _first(row, FIELD_ALIASES["current_company"]),
                            "title": _first(row, FIELD_ALIASES["title"]),
                            "location_text": _first(row, FIELD_ALIASES["location_text"]),
                        },
                    }
                )
    except (csv.Error, UnicodeDecodeError) as exc:
        if warnings:
            warnings.add(f"Recruiter CSV could not be parsed, skipped: {exc}")
        return []
    return records
