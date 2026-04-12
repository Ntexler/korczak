"""
Full-text ingestion pipeline for academic papers.

Fetches full text from open-access sources for papers that have a DOI
but no full_text yet. Tries Unpaywall first, then Semantic Scholar as fallback.

Usage:
  python -m backend.pipeline.fetch_full_text --limit 10
  python -m backend.pipeline.fetch_full_text --limit 50 --dry-run
"""

import argparse
import os
import re
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Config ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# --- HTML stripping ---

def strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities. No BeautifulSoup needed."""
    # Remove script and style blocks entirely
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    entity_map = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&apos;": "'", "&nbsp;": " ", "&#39;": "'",
    }
    for entity, char in entity_map.items():
        text = text.replace(entity, char)
    # Decode numeric entities
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_article_text(html: str) -> str:
    """Try to extract the main article body from an HTML page."""
    # Try to find content in <article> tags first
    article_match = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL | re.IGNORECASE)
    if article_match:
        return strip_html(article_match.group(1))

    # Try common content div patterns
    for pattern in [
        r'<div[^>]*class="[^"]*(?:article-body|paper-body|full-text|fulltext|main-content|body-content)[^"]*"[^>]*>(.*?)</div>',
        r'<section[^>]*class="[^"]*(?:article|body|content)[^"]*"[^>]*>(.*?)</section>',
    ]:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return strip_html(match.group(1))

    # Fallback: strip everything in <body>
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if body_match:
        text = strip_html(body_match.group(1))
        # If body text is too short, it's probably not useful
        if len(text) > 500:
            return text

    # Last resort: strip the whole thing
    text = strip_html(html)
    return text if len(text) > 200 else ""


# --- Supabase helpers (same pattern as seed_graph.py) ---

def supabase_get(table: str, params: dict) -> list:
    """Query Supabase via REST API."""
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    print(f"  Supabase GET error: {resp.status_code} {resp.text[:200]}")
    return []


def supabase_patch(table: str, match_params: dict, data: dict) -> bool:
    """Update rows in Supabase via REST API (PATCH)."""
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=match_params,
        json=data,
        headers=HEADERS_SUPABASE,
        timeout=15,
    )
    if resp.status_code in (200, 204):
        return True
    print(f"  Supabase PATCH error: {resp.status_code} {resp.text[:200]}")
    return False


# --- Unpaywall ---

def fetch_via_unpaywall(doi: str) -> tuple[str, str] | None:
    """
    Try to get full text via Unpaywall API.
    Returns (full_text, "unpaywall") or None.
    """
    if not OPENALEX_EMAIL:
        return None

    # Clean DOI — remove https://doi.org/ prefix if present
    clean_doi = re.sub(r"^https?://doi\.org/", "", doi)

    try:
        resp = httpx.get(
            f"{UNPAYWALL_BASE}/{clean_doi}",
            params={"email": OPENALEX_EMAIL},
            timeout=20,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()

        # Find the best open-access URL
        oa_url = None
        best_location = data.get("best_oa_location")
        if best_location:
            # Prefer PDF URL for direct text, but HTML URL is also fine
            oa_url = best_location.get("url_for_landing_page") or best_location.get("url")

        if not oa_url:
            # Check all OA locations
            for loc in data.get("oa_locations", []):
                url = loc.get("url_for_landing_page") or loc.get("url")
                if url:
                    oa_url = url
                    break

        if not oa_url:
            return None

        # Rate limit before fetching the actual page
        time.sleep(1)

        # Fetch the HTML page
        page_resp = httpx.get(
            oa_url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "KorczakAI/1.0 (academic research; mailto:{})".format(OPENALEX_EMAIL)},
        )
        if page_resp.status_code != 200:
            return None

        content_type = page_resp.headers.get("content-type", "")

        # Skip PDFs — we can't parse binary PDF with regex
        if "application/pdf" in content_type:
            return None

        # Only process HTML/text responses
        if "text/" not in content_type and "html" not in content_type:
            return None

        text = extract_article_text(page_resp.text)

        # Minimum viable full text: at least 1000 chars
        if len(text) < 1000:
            return None

        # Cap at ~100k chars to avoid storing huge documents
        if len(text) > 100_000:
            text = text[:100_000] + "\n\n[Truncated at 100,000 characters]"

        return (text, "unpaywall")

    except Exception as e:
        print(f"    Unpaywall error: {e}")
        return None


# --- Semantic Scholar ---

def fetch_via_semantic_scholar(doi: str) -> tuple[str, str] | None:
    """
    Fallback: get TLDR + abstract from Semantic Scholar.
    Returns (combined_text, "semantic_scholar") or None.
    """
    clean_doi = re.sub(r"^https?://doi\.org/", "", doi)

    try:
        resp = httpx.get(
            f"{SEMANTIC_SCHOLAR_BASE}/paper/DOI:{clean_doi}",
            params={"fields": "tldr,abstract"},
            timeout=20,
        )
        if resp.status_code == 429:
            # Rate limited — wait and retry once
            retry_after = int(resp.headers.get("retry-after", 5))
            print(f"    S2 rate limited — waiting {retry_after}s...")
            time.sleep(retry_after)
            resp = httpx.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/DOI:{clean_doi}",
                params={"fields": "tldr,abstract"},
                timeout=20,
            )

        if resp.status_code != 200:
            return None

        data = resp.json()
        parts = []

        # TLDR
        tldr = data.get("tldr")
        if tldr and isinstance(tldr, dict):
            tldr_text = tldr.get("text", "")
            if tldr_text:
                parts.append(f"TLDR: {tldr_text}")

        # Abstract (may be longer/different than what OpenAlex has)
        abstract = data.get("abstract")
        if abstract:
            parts.append(f"Abstract: {abstract}")

        if not parts:
            return None

        combined = "\n\n".join(parts)

        # Only useful if we got more than just a short abstract
        if len(combined) < 100:
            return None

        return (combined, "semantic_scholar")

    except Exception as e:
        print(f"    Semantic Scholar error: {e}")
        return None


# --- Main Pipeline ---

def fetch_papers_needing_full_text(limit: int) -> list:
    """Get papers that have a DOI but no full_text."""
    papers = supabase_get("papers", {
        "select": "id,doi,title",
        "doi": "not.is.null",
        "full_text": "is.null",
        "order": "cited_by_count.desc",
        "limit": str(limit),
    })
    return papers


def run_pipeline(limit: int, dry_run: bool = False):
    """Main pipeline: fetch full text for papers missing it."""
    print(f"\n{'='*60}")
    print(f"FULL TEXT INGESTION PIPELINE")
    print(f"Limit: {limit} papers | Dry run: {dry_run}")
    if not OPENALEX_EMAIL:
        print("WARNING: OPENALEX_EMAIL not set — Unpaywall requests will be skipped")
    print(f"{'='*60}\n")

    papers = fetch_papers_needing_full_text(limit)
    print(f"Found {len(papers)} papers needing full text\n")

    if not papers:
        print("Nothing to do.")
        return

    stats = {"unpaywall": 0, "semantic_scholar": 0, "failed": 0, "skipped": 0}

    for i, paper in enumerate(papers):
        doi = paper.get("doi")
        title = (paper.get("title") or "?")[:60]
        print(f"[{i+1}/{len(papers)}] {title}...")

        if not doi:
            print("    No DOI — skipping")
            stats["skipped"] += 1
            continue

        # Try Unpaywall first
        result = fetch_via_unpaywall(doi)
        if result:
            full_text, source = result
            print(f"    -> Unpaywall: {len(full_text)} chars")
            if not dry_run:
                supabase_patch(
                    "papers",
                    {"id": f"eq.{paper['id']}"},
                    {"full_text": full_text, "full_text_source": source},
                )
            stats["unpaywall"] += 1
            # Rate limit for Unpaywall: 1 req/sec (already waited 1s inside)
            continue

        # Rate limit between Unpaywall attempt and S2
        time.sleep(1)

        # Fallback: Semantic Scholar
        result = fetch_via_semantic_scholar(doi)
        if result:
            full_text, source = result
            print(f"    -> Semantic Scholar: {len(full_text)} chars")
            if not dry_run:
                supabase_patch(
                    "papers",
                    {"id": f"eq.{paper['id']}"},
                    {"full_text": full_text, "full_text_source": source},
                )
            stats["semantic_scholar"] += 1
        else:
            print(f"    -> No full text found")
            stats["failed"] += 1

        # Rate limit between papers (S2 allows ~100 req/5min = ~1 req/3sec)
        time.sleep(3)

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Unpaywall:         {stats['unpaywall']}")
    print(f"  Semantic Scholar:  {stats['semantic_scholar']}")
    print(f"  Failed:            {stats['failed']}")
    print(f"  Skipped:           {stats['skipped']}")
    print(f"  Total processed:   {sum(stats.values())}")
    print(f"{'='*60}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch full text for papers in Korczak DB")
    parser.add_argument("--limit", type=int, default=10, help="Max papers to process (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write to DB")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    run_pipeline(args.limit, args.dry_run)


if __name__ == "__main__":
    main()
