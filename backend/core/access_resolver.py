"""Resolve a paper's user-facing access URL and access status.

Feature 6.5 requires every paper to surface a clear "where do I read this?"
answer:
  - `access_url` — the best URL we can point a reader at
  - `access_status` — open / paywalled / hybrid / preprint / author_copy / unknown

Inputs:
  - Unpaywall API response (preferred source of truth)
  - OpenAlex open-access metadata (fallback + augmentation)
  - DOI (fallback URL)

The resolver never does network I/O itself. It's a pure function over
data already fetched by the pipeline. This keeps it easy to test and
lets the calling code pick when to hit the network.
"""

from typing import Any


def resolve_access(
    *,
    unpaywall: dict | None = None,
    openalex_oa: dict | None = None,
    doi: str | None = None,
) -> tuple[str | None, str]:
    """Return (access_url, access_status) from available metadata.

    Status reasoning:
      - If Unpaywall reports `is_oa=True` with a `best_oa_location`, status is
        'open' (gold/green/hybrid/bronze OA) — except when only an author copy
        is available, then 'author_copy'.
      - If Unpaywall reports `is_oa=False` but has a preprint location in
        `oa_locations` (e.g., arXiv version), status is 'preprint'.
      - If OpenAlex reports `is_oa=True` but Unpaywall is missing, status is
        'hybrid' (we believe it's free somewhere, but we can't pinpoint).
      - Otherwise 'paywalled' when we have a DOI, 'unknown' when we have nothing.

    URL reasoning:
      - Prefer Unpaywall's best_oa_location `url_for_landing_page` (stable,
        human-readable), fall back to `url` (may be a direct PDF).
      - Fall back to any oa_location.
      - Fall back to DOI URL (`https://doi.org/<doi>`) — takes the reader to
        the publisher; paywall or not.
    """

    # --- Try Unpaywall first ---
    if unpaywall:
        is_oa = bool(unpaywall.get("is_oa"))
        best = unpaywall.get("best_oa_location") or {}
        best_url = (
            best.get("url_for_landing_page")
            or best.get("url")
            or best.get("url_for_pdf")
        )
        best_host_type = (best.get("host_type") or "").lower()  # 'publisher' | 'repository'
        best_version = (best.get("version") or "").lower()  # 'publishedVersion' | 'acceptedVersion' | 'submittedVersion'

        if is_oa and best_url:
            # Author-uploaded accepted manuscript via a non-publisher repository
            # → distinguish from true gold/hybrid OA for honest labelling
            if best_host_type == "repository" and best_version in ("submittedversion", "acceptedversion"):
                return best_url, "author_copy"
            return best_url, "open"

        # Not OA per Unpaywall — check for preprint locations
        for loc in unpaywall.get("oa_locations") or []:
            host_type = (loc.get("host_type") or "").lower()
            version = (loc.get("version") or "").lower()
            url = loc.get("url_for_landing_page") or loc.get("url")
            if url and (host_type == "repository" or "arxiv" in (url or "").lower() or version == "submittedversion"):
                return url, "preprint"

    # --- OpenAlex fallback ---
    if openalex_oa:
        oa_url = openalex_oa.get("oa_url")
        is_oa = bool(openalex_oa.get("is_oa"))
        if is_oa and oa_url:
            return oa_url, "hybrid"

    # --- DOI fallback ---
    if doi:
        clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        return f"https://doi.org/{clean_doi}", "paywalled"

    return None, "unknown"


def summarize_for_ui(access_status: str) -> dict[str, Any]:
    """Return a small UI-friendly descriptor of an access status.

    Consumed by the frontend to render access badges without hardcoding
    status strings on the client.
    """
    mapping = {
        "open": {
            "label": "Open access",
            "tone": "positive",
            "cta": "Read the paper",
        },
        "hybrid": {
            "label": "Open access available",
            "tone": "positive",
            "cta": "Read the paper",
        },
        "preprint": {
            "label": "Preprint available",
            "tone": "neutral",
            "cta": "Read the preprint",
        },
        "author_copy": {
            "label": "Author manuscript",
            "tone": "neutral",
            "cta": "Read author copy",
        },
        "paywalled": {
            "label": "Paywalled",
            "tone": "warning",
            "cta": "Go to publisher page",
        },
        "unknown": {
            "label": "Access unknown",
            "tone": "muted",
            "cta": None,
        },
    }
    return mapping.get(access_status, mapping["unknown"])
