"""Vault Parser — parse Obsidian Markdown files into structured note data.

Handles:
- YAML frontmatter extraction
- [[wikilink]] detection
- #tag extraction
- Note content cleaning
"""

import logging
import re
import io
import zipfile
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Patterns
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z][a-zA-Z0-9_/-]+)", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
YAML_KV_RE = re.compile(r"^(\w[\w_-]*):\s*(.+)$", re.MULTILINE)
YAML_LIST_ITEM_RE = re.compile(r"^\s+-\s+(.+)$", re.MULTILINE)


@dataclass
class ParsedNote:
    """A single parsed Obsidian note."""
    title: str
    content: str                          # raw content (without frontmatter)
    excerpt: str = ""                     # first ~300 chars of meaningful text
    frontmatter: dict = field(default_factory=dict)
    wikilinks: list[str] = field(default_factory=list)    # [[linked note names]]
    tags: list[str] = field(default_factory=list)          # #tags found
    headings: list[str] = field(default_factory=list)      # heading texts
    word_count: int = 0
    folder: str = ""                      # folder path within vault


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from Markdown text.

    Returns (frontmatter_dict, remaining_content).
    Uses simple regex parsing to avoid PyYAML dependency.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    yaml_block = match.group(1)
    remaining = text[match.end():]

    # Simple YAML parsing (key: value pairs + lists)
    fm: dict = {}
    current_key = None

    for line in yaml_block.split("\n"):
        kv = YAML_KV_RE.match(line)
        if kv:
            key, value = kv.group(1), kv.group(2).strip()
            # Clean up quoted values
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            fm[key] = value
            current_key = key
        elif line.strip().startswith("- ") and current_key:
            item = line.strip()[2:].strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            # Convert to list if needed
            if isinstance(fm.get(current_key), list):
                fm[current_key].append(item)
            elif current_key in fm and fm[current_key] == "":
                fm[current_key] = [item]
            else:
                fm[current_key] = [item]
        elif line.strip().endswith(":") and not line.strip().startswith("-"):
            current_key = line.strip()[:-1]
            fm[current_key] = ""

    return fm, remaining


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from text."""
    links = WIKILINK_RE.findall(text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for link in links:
        clean = link.strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


def extract_tags(text: str) -> list[str]:
    """Extract all #tags from text (excluding YAML frontmatter tags)."""
    tags = TAG_RE.findall(text)
    seen = set()
    unique = []
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique.append(tag_lower)
    return unique


def extract_headings(text: str) -> list[str]:
    """Extract heading texts from Markdown."""
    return [m.group(2).strip() for m in HEADING_RE.finditer(text)]


def make_excerpt(text: str, max_length: int = 300) -> str:
    """Create an excerpt from the note content, skipping headings and blank lines."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ")
        lines.append(stripped)
        if sum(len(l) for l in lines) >= max_length:
            break
    excerpt = " ".join(lines)
    if len(excerpt) > max_length:
        excerpt = excerpt[:max_length].rsplit(" ", 1)[0] + "..."
    return excerpt


def parse_note(filename: str, content: str, folder: str = "") -> ParsedNote:
    """Parse a single Obsidian Markdown file into structured data."""
    # Title from filename (remove .md extension)
    title = filename
    if title.endswith(".md"):
        title = title[:-3]

    # Parse frontmatter
    frontmatter, body = parse_frontmatter(content)

    # Also include tags from frontmatter
    fm_tags = frontmatter.get("tags", [])
    if isinstance(fm_tags, str):
        fm_tags = [t.strip() for t in fm_tags.split(",")]

    # Extract from body
    wikilinks = extract_wikilinks(body)
    body_tags = extract_tags(body)
    headings = extract_headings(body)
    excerpt = make_excerpt(body)

    # Combine tags
    all_tags = list(set(
        [t.lower() for t in fm_tags if isinstance(t, str)] + body_tags
    ))

    # Word count (rough)
    word_count = len(body.split())

    return ParsedNote(
        title=title,
        content=body,
        excerpt=excerpt,
        frontmatter=frontmatter,
        wikilinks=wikilinks,
        tags=all_tags,
        headings=headings,
        word_count=word_count,
        folder=folder,
    )


def parse_vault_zip(zip_bytes: bytes) -> list[ParsedNote]:
    """Parse a ZIP file containing an Obsidian vault.

    Reads all .md files, skips hidden files, templates, and metadata.
    """
    notes = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for info in zf.infolist():
            # Skip directories
            if info.is_dir():
                continue

            # Only process Markdown files
            if not info.filename.endswith(".md"):
                continue

            # Skip hidden files and common Obsidian internals
            parts = info.filename.split("/")
            if any(p.startswith(".") for p in parts):
                continue
            if any(p in (".obsidian", ".trash", "templates", "Templates") for p in parts):
                continue

            try:
                content = zf.read(info.filename).decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"Failed to read {info.filename}: {e}")
                continue

            # Skip near-empty files
            if len(content.strip()) < 10:
                continue

            # Determine folder and filename
            filename = parts[-1]
            folder = "/".join(parts[:-1]) if len(parts) > 1 else ""

            note = parse_note(filename, content, folder=folder)
            notes.append(note)

    logger.info(f"Parsed {len(notes)} notes from vault ZIP")
    return notes


@dataclass
class VaultStats:
    """Summary statistics about a parsed vault."""
    note_count: int = 0
    total_links: int = 0
    total_tags: int = 0
    unique_tags: int = 0
    total_words: int = 0
    avg_note_length: int = 0
    folders: list[str] = field(default_factory=list)
    top_tags: list[tuple[str, int]] = field(default_factory=list)
    most_linked: list[tuple[str, int]] = field(default_factory=list)  # most referenced notes


def compute_vault_stats(notes: list[ParsedNote]) -> VaultStats:
    """Compute summary statistics from parsed notes."""
    if not notes:
        return VaultStats()

    all_tags: dict[str, int] = {}
    link_targets: dict[str, int] = {}
    total_links = 0
    total_words = 0
    folders = set()

    for note in notes:
        total_links += len(note.wikilinks)
        total_words += note.word_count
        if note.folder:
            folders.add(note.folder)
        for tag in note.tags:
            all_tags[tag] = all_tags.get(tag, 0) + 1
        for link in note.wikilinks:
            link_targets[link] = link_targets.get(link, 0) + 1

    top_tags = sorted(all_tags.items(), key=lambda x: -x[1])[:20]
    most_linked = sorted(link_targets.items(), key=lambda x: -x[1])[:20]

    return VaultStats(
        note_count=len(notes),
        total_links=total_links,
        total_tags=sum(all_tags.values()),
        unique_tags=len(all_tags),
        total_words=total_words,
        avg_note_length=total_words // len(notes) if notes else 0,
        folders=sorted(folders),
        top_tags=top_tags,
        most_linked=most_linked,
    )
