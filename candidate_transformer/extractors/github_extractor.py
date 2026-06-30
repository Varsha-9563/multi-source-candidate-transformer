"""
GitHub profile extractor.
Calls the public GitHub REST API (no auth needed, rate-limited to 60/hr).
Extracts bio, location, name, and infers skills from repo languages.
"""

import re
import requests

from ..warnings import WarningCollector

GITHUB_URL_RE = re.compile(r"github\.com/([A-Za-z0-9_-]+)/?$")


def _extract_username(url: str) -> str | None:
    match = GITHUB_URL_RE.search(url.strip().rstrip("/"))
    return match.group(1) if match else None


def extract_github(url: str | None, warnings: WarningCollector | None = None) -> list[dict]:
    if not url:
        return []

    username = _extract_username(url)
    if not username:
        if warnings:
            warnings.add(f"GitHub URL is missing or invalid, skipped: {url}")
        return []

    headers = {"Accept": "application/vnd.github+json"}

    # ── Profile call ──────────────────────────────────────────────
    try:
        resp = requests.get(
            f"https://api.github.com/users/{username}",
            headers=headers, timeout=6
        )
    except requests.RequestException as exc:
        if warnings:
            warnings.add(f"GitHub API unreachable, skipped: {exc}")
        return []

    if resp.status_code == 404:
        if warnings:
            warnings.add(f"GitHub user not found, skipped: {username}")
        return []
    if resp.status_code == 403:
        if warnings:
            warnings.add("GitHub API rate limit hit, skipped GitHub enrichment")
        return []
    if resp.status_code != 200:
        if warnings:
            warnings.add(f"GitHub API returned {resp.status_code}, skipped: {username}")
        return []

    profile = resp.json()

    # ── Repos call (for skill inference via language) ───────────────
    languages = []
    try:
        repos_resp = requests.get(
            f"https://api.github.com/users/{username}/repos",
            headers=headers, params={"per_page": 30, "sort": "updated"},
            timeout=6
        )
        if repos_resp.status_code == 200:
            for repo in repos_resp.json():
                lang = repo.get("language")
                if lang and lang not in languages:
                    languages.append(lang)
    except requests.RequestException:
        pass  # repos are a bonus, don't fail the whole extraction

    return [{
        "source": "github_api",
        "source_type": "unstructured",
        "reliability": 0.75,   # self-reported profile, decent but not as strong as resume
        "fields": {
            "full_name":     profile.get("name"),
            "headline":      profile.get("bio"),
            "location_text": profile.get("location"),
            "skills":        languages,
            "links": {
                "linkedin": None,
                "github": profile.get("html_url"),
                "portfolio": profile.get("blog") or None,
                "other": [],
            },
        },
    }]