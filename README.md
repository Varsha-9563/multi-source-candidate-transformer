# Multi-Source Candidate Data Transformer

Turns messy, multi-source candidate inputs into one canonical, schema-valid JSON profile — with provenance and confidence tracking on every field.

Every command below was run end-to-end against this exact repo before being written down, so following them in order from a clean clone will reproduce a working result in one shot.

## Sources Supported

| Source | Type | Extraction method |
|---|---|---|
| Recruiter CSV | Structured | Direct field parsing, one row per candidate |
| Recruiter notes (.txt) | Unstructured | Regex-based (fast, deterministic, sufficient for short casual notes) |
| Resume (.pdf) | Unstructured | **LLM-first** (Claude primary, Gemini fallback), regex fallback if no API key |
| GitHub profile URL | Unstructured | Real GitHub REST API call (no auth needed) — name, bio, location, repo languages |

This satisfies both required groups: CSV (structured) + notes/resume/GitHub (3 unstructured sources, only 1 was required).

## 1. Setup

Requires **Python 3.10+** (the codebase uses `str | None` type hints).

```bash
git clone <this-repo-url>
cd "eightfold ai"

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

That installs everything needed: `streamlit`, `requests`, `pdfplumber`, `python-dotenv`.

## 2. Quick Start (no setup beyond step 1 — works with zero API keys)

All sample inputs already exist under `samples/`. Run exactly as-is from the repo root:

Default canonical output:
```bash
python -m candidate_transformer --csv samples/recruiter.csv --notes samples/varsha_notes.txt --out outputs/default_output.json
```

With resume PDF + GitHub:
```bash
python -m candidate_transformer --csv samples/recruiter.csv --notes samples/varsha_notes.txt --resume samples/varsha_resume.pdf --github-url https://github.com/torvalds --out outputs/with_resume_github.json
```

Custom projected output (runtime config, see below):
```bash
python -m candidate_transformer --csv samples/recruiter.csv --notes samples/varsha_notes.txt --config configs/custom_output.json --out outputs/custom_output.json
```

Each command prints `Wrote outputs/<file>.json` on success and writes schema-valid JSON to that path — open it to see the canonical profile.

Other ready-to-use sample combinations in `samples/`:
- Notes only: `varsha_notes.txt`, `niki_notes.txt`
- Resume PDFs: `varsha_resume.pdf`, `uday_274.pdf`, `niki_158.pdf`, `praj_174.pdf`, `girish_senior.pdf`, `MPG_139.pdf`
- Structured source: `recruiter.csv` (multiple candidate rows, including one blank row — matched to the right candidate by email overlap with `--notes`/`--resume`)

Run tests:
```bash
python -m unittest discover tests -v
```
Expect `Ran 5 tests in ...s` / `OK`.

## 3. Optional — Streamlit UI

A thin UI sits on top of the same engine (it calls `candidate_transformer.cli.run(...)` directly, no logic duplicated):

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Upload the CSV/notes/resume from `samples/`, optionally paste a GitHub URL or point at `configs/custom_output.json`, and it renders the profile as a card plus raw JSON.

## 4. Optional — Enable LLM-Augmented Extraction

Resume parsing and skill/location normalization use an LLM as the primary method for resumes (real resumes use irregular table/column layouts that regex cannot reliably parse) and as a fallback for unknown skills/locations in notes.

```bash
cp .env.example .env
```
Then edit `.env` and fill in your own key(s):
```
ANTHROPIC_API_KEY=sk-ant-...   # primary
GEMINI_API_KEY=AIzaSy...       # fallback if Anthropic unavailable
```

`.env` is git-ignored — never commit real keys. Without either key set, the system falls back to regex-based extraction with lower confidence (0.6 vs 0.85) — it never crashes, but resume fields parsed from complex layouts may be incomplete. You'll see a one-line `Gemini key loaded: ...` debug print on each run while a key is present; this is informational only and does not affect output correctness.

## Behavior By Input Combination

The same resume can produce very different output depending on what's provided
and whether an LLM key is active. This is intentional — see "Assumptions" above
for why we don't guess a name from layout heuristics.

| Inputs | LLM key working? | `full_name` | Skills | Confidence |
|---|---|---|---|---|
| Resume only, no CSV | No / unavailable | best-effort guess from first lines (flagged unverified in warnings) | ~5, hardcoded alias map only | ~0.55-0.60 |
| Resume only, no CSV | Yes | extracted directly from resume text | full list (15-25+, whatever the resume contains) | ~0.85+ |

**Why `full_name` is `null` without a working LLM key and no CSV:** a name sitting
in a resume header (often near a logo, in a two-column layout, or styled
differently from body text) isn't reliably regex-extractable. Per our
"wrong-but-confident is worse than honestly-empty" principle, we return `null`
with a warning instead of guessing — we do **not** fall back to a first-line
heuristic. CSV remains the most reliable name source for this reason.

**To get full resume-only extraction**, make sure `google-genai` is installed
(`pip install -r requirements.txt` covers this) and `GEMINI_API_KEY` (or
`ANTHROPIC_API_KEY`) is set in `.env`. Watch the terminal: if you see
`DEBUG GEMINI SDK EXCEPTION`, the LLM call is failing and the pipeline has
silently degraded to the regex fallback row above — output is still valid
JSON, just lower-confidence.

## Pipeline

```text
load inputs -> extract source records -> match candidate across CSV via email
-> normalize values -> merge into canonical profile -> assign confidence/provenance
-> project requested output -> validate -> write JSON
```

The internal canonical record is always built first. Runtime config only reshapes the final output — extraction/merging stays separate from presentation.

Candidate matching: when both CSV (many rows) and notes/resume (one candidate) are provided, the pipeline matches the correct CSV row by email overlap. If no match is found, the profile is built from notes/resume alone rather than silently merging an unrelated CSV row.

## Output Config

```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```

`on_missing`: `null` (include with null) | `omit` (skip field) | `error` (fail validation)

The exact file used in the Quick Start custom-config command above lives at `configs/custom_output.json`.

## Assumptions

- Phone normalization assumes Indian numbers by default for 10-digit local numbers.
- LinkedIn has no public API and scraping violates their ToS; the URL is validated and stored as a link, content is not fetched.
- GitHub IS fetched live via the public REST API (profile + repo languages), since it's freely available without auth.
- Skill/location/headline extraction uses a hybrid approach: hardcoded canonical maps handle common cases instantly and deterministically; LLM is only invoked for values outside the map, with results cached per run.

## Edge Cases Handled

- Multiple candidates in one CSV: matched to the correct row via email overlap with notes/resume, not just the first row.
- Same candidate, conflicting name spelling across sources: email is the stable match key; name conflicts resolved by source reliability.
- Missing/invalid/404 GitHub URL: warning logged, pipeline continues with other sources.
- GitHub API rate limit (60/hr unauthenticated): caught and warned, doesn't crash. If you hit this while testing, the JSON output still writes successfully — check the `warnings` array in the output.
- Conflicting phone numbers: all valid numbers retained, confidence reduced slightly.
- Skill aliases (`JS`, `React.js`, `PySpark`, etc.): canonical map normalizes; unknown skills go through LLM fallback if a key is set, else title-cased.
- Empty/malformed CSV row: skipped with warning, not crashed.
- Missing/empty notes or resume file: skipped with warning, profile still builds from remaining sources.
- Resume with no formal "Title at Company from X to Y" sentence (common in real resumes using tables/bullets): regex fallback returns empty experience/education honestly rather than guessing; LLM path handles these correctly when a key is available.

## What Was Descoped

- LinkedIn content scraping (ToS violation, fragile, not pursued)
- DOCX resume parsing (PDF only, given time constraints)
- Multi-candidate batch processing in a single run (one profile per run, by design)

## Demo Talking Points

1. Default pipeline command + generated canonical JSON
2. Custom config command + projected output
3. Resume PDF with LLM extraction vs. regex fallback — show the difference in completeness
4. Design decision: hybrid fast-path/LLM-slow-path normalization (deterministic + handles the unknown case)
5. Edge case: candidate matching across multi-row CSV via email, not just row 1
6. Edge case: missing notes/resume/GitHub doesn't crash, confidence drops honestly

## Project Layout

```text
candidate_transformer/   pipeline engine (extractors, normalize, merge, project, validate, CLI)
app.py                   Streamlit UI on top of the same engine
configs/                 runtime output-projection configs
samples/                 sample CSV / notes / resume / inputs used above
outputs/                 JSON written by pipeline runs
tests/                   unittest suite
DESIGN.md                one-page technical design doc
```
