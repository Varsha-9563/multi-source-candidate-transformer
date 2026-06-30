# Multi-Source Candidate Data Transformer - Technical Design

## Problem Framing

The transformer ingests candidate data from multiple sources and emits one trustworthy canonical profile. I implemented a structured recruiter CSV source and an unstructured recruiter-notes/resume-text source. The design is deterministic: no invented values, every populated field has provenance, and malformed or missing optional sources are logged as warnings instead of crashing the run.

## Pipeline

`load inputs -> extract -> normalize -> merge/conflict resolution -> confidence -> projection -> validation`

Extraction uses source-specific adapters. CSV fields are read directly with alias support for common field names. Notes/resume text is parsed with regular expressions and keyword rules for emails, phones, links, skills, education, and experience. Normalization lowercases emails, converts phones to E.164, maps countries to ISO-3166 alpha-2, canonicalizes skill aliases such as `JS -> JavaScript`, and keeps dates in `YYYY-MM` where present.

## Canonical Schema

The internal canonical profile contains `candidate_id`, `full_name`, `emails`, `phones`, `location`, `links`, `headline`, `years_experience`, `skills`, `experience`, `education`, `provenance`, `overall_confidence`, and `warnings`. This internal schema is built before any custom output shaping so the merge logic stays independent of presentation needs.

## Merge And Confidence Policy

Email is the primary stable identity key for candidate ID generation. If two sources provide different names for the same email, the higher-reliability source wins, with CSV weighted above free text. List fields such as emails and phones are deduplicated but not overwritten; conflicting valid phone numbers are retained and confidence is slightly reduced. Skills are merged by canonical name, and skill confidence increases when multiple sources support the same skill. Provenance records the field, source, and method for each chosen or extracted value.

## Runtime Output Config

The projection layer accepts a runtime JSON config with field paths, optional `from` mappings, required flags, type expectations, field-level normalization, confidence/provenance toggles, and missing-value behavior: `null`, `omit`, or `error`. After projection, the output is validated against the requested schema. This keeps the same engine usable for both the default canonical output and customer-specific shapes.

## Edge Cases And Scope

Handled edge cases include: same candidate in two sources with slightly different names, missing or invalid GitHub URL logged as a warning, conflicting phones retained with lower confidence, skill aliases canonicalized, empty CSV rows skipped, missing notes skipped, and malformed files degraded gracefully. Under time pressure, I intentionally left out live GitHub/LinkedIn API fetching and PDF/DOCX resume parsing because API/auth/rate-limit and document parsing complexity would increase risk without improving the core transformer design.
