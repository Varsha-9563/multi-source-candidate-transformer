from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "Eightfold_Design.pdf"


SECTIONS = [
    (
        "Problem Framing",
        "The transformer ingests candidate data from multiple sources and emits one trustworthy canonical profile. "
        "I implemented a structured recruiter CSV source and an unstructured recruiter-notes/resume-text source. "
        "The design is deterministic: no invented values, every populated field has provenance, and malformed or "
        "missing optional sources are logged as warnings instead of crashing the run.",
    ),
    (
        "Pipeline",
        "load inputs -> extract -> normalize -> merge/conflict resolution -> confidence -> projection -> validation. "
        "CSV fields are read directly with alias support. Notes/resume text is parsed with deterministic regex and "
        "keyword rules for emails, phones, links, skills, education, and experience.",
    ),
    (
        "Canonical Schema",
        "The internal profile contains candidate_id, full_name, emails, phones, location, links, headline, "
        "years_experience, skills, experience, education, provenance, overall_confidence, and warnings. "
        "This canonical record is built before custom output shaping so merge logic stays separate from presentation.",
    ),
    (
        "Normalization",
        "Emails are lowercased, phones are converted to E.164, countries use ISO-3166 alpha-2, dates stay in YYYY-MM, "
        "and skills use a canonical alias map such as JS -> JavaScript, React.js -> React, and PySpark -> PySpark.",
    ),
    (
        "Merge And Confidence",
        "Email is the primary identity key. If sources disagree on scalar fields, higher-reliability sources win, "
        "with CSV weighted above free text. Emails and phones are deduplicated but not overwritten; conflicting valid "
        "phones are retained and confidence is reduced. Skill confidence increases when multiple sources agree.",
    ),
    (
        "Runtime Output Config",
        "A projection layer accepts a JSON config with output paths, optional from mappings, required flags, types, "
        "field-level normalization, confidence/provenance toggles, and missing-value behavior: null, omit, or error. "
        "The projected result is validated before being returned.",
    ),
    (
        "Edge Cases And Scope",
        "Handled: name conflicts for the same email, invalid GitHub URL warning, phone conflicts, skill aliases, empty "
        "CSV rows, missing notes, and malformed sources. Descoped: live GitHub/LinkedIn API fetching and PDF/DOCX parsing "
        "to avoid auth, rate-limit, and parsing risk under the deadline.",
    ),
]


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=colors.HexColor("#244f8f"),
        spaceAfter=6,
    )
    section_title = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.3,
        leading=11,
        textColor=colors.HexColor("#244f8f"),
        spaceBefore=4,
        spaceAfter=2,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.4,
        leading=10.2,
        spaceAfter=1,
    )

    story = [Paragraph("Multi-Source Candidate Data Transformer - Technical Design", title)]
    for heading, text in SECTIONS:
        story.append(Paragraph(heading, section_title))
        story.append(Paragraph(text, body))
        story.append(Spacer(1, 1))
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
