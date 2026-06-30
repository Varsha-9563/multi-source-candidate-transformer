import argparse
import json
from pathlib import Path

from .extractors.csv_extractor import extract_csv
from .extractors.notes_extractor import extract_notes
from .merge import merge_sources
from .project import project_output
from .validate import validate_profile, validate_projection
from .warnings import WarningCollector
from .extractors.pdf_extractor import extract_pdf
from .extractors.github_extractor import extract_github
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a canonical candidate profile from messy inputs.")
    parser.add_argument("--csv", dest="csv_path", help="Path to recruiter CSV input")
    parser.add_argument("--notes", dest="notes_path", help="Path to recruiter notes or resume text input")
    parser.add_argument("--github-url", dest="github_url", help="Optional GitHub profile URL to record if valid")
    parser.add_argument("--config", dest="config_path", help="Optional output projection config JSON")
    parser.add_argument("--out", dest="out_path", required=True, help="Path to write output JSON")
    parser.add_argument("--resume", dest="resume_path", help="Path to resume PDF file")
    return parser


def load_config(path: str | None) -> dict | None:
    if not path:
        return None
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return json.loads(config_path.read_text(encoding="utf-8"))




def run(
    csv_path: str | None,
    notes_path: str | None,
    config_path: str | None,
    github_url: str | None = None,
    resume_path: str | None = None,
) -> dict:
    warnings = WarningCollector()

    notes_records = extract_notes(notes_path, warnings)
    pdf_records = extract_pdf(resume_path, warnings)
    all_csv_records = extract_csv(csv_path, warnings)

    all_unstructured = notes_records + pdf_records
    matched_csv = []
    if all_csv_records:
        if len(all_csv_records) == 1:
            # only one candidate in CSV — no ambiguity, always use it
            matched_csv = all_csv_records
        elif all_unstructured:
            notes_emails = set()
            for r in all_unstructured:
                notes_emails.update(r["fields"].get("emails", []))
            for csv_record in all_csv_records:
                csv_emails = set(csv_record["fields"].get("emails", []))
                if notes_emails & csv_emails:
                    matched_csv = [csv_record]
                    break
            if not matched_csv:
                warnings.add("No matching CSV row found for this candidate's email; building profile from notes/resume only")
        else:
            # CSV only, no notes/resume to disambiguate — default to first row
            matched_csv = [all_csv_records[0]]

    # ── NEW: auto-detect GitHub URL if not explicitly provided ──
    effective_github_url = github_url
    if not effective_github_url:
        for record in all_unstructured:
            found = record["fields"].get("links", {}).get("github")
            if found:
                effective_github_url = found
                warnings.add(f"GitHub URL auto-detected from {record['source']}: {found}")
                break

    source_records = []
    source_records.extend(matched_csv)
    source_records.extend(notes_records)
    source_records.extend(pdf_records)
    source_records.extend(extract_github(effective_github_url, warnings))

    profile = merge_sources(source_records)
    profile["warnings"] = warnings.as_records()
    validate_profile(profile)

    config = load_config(config_path)
    if config:
        output = project_output(profile, config)
        validate_projection(output, config)
        return output
    return profile


# ← THIS IS WHAT WAS MISSING — you deleted it by accident
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    output = run(
        args.csv_path,
        args.notes_path,
        args.config_path,
        args.github_url,
        args.resume_path,    # ← add this
    )
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out_path}")