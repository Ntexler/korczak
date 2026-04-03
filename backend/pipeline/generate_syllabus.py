"""
Generate syllabus files from seeded papers in Supabase.
Creates markdown files organized by topic (grouped from subfields).

Usage:
  python -m backend.pipeline.generate_syllabus
"""

import os
import re
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Prefer": "",
}

SYLLABUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "syllabus")

# Map granular subfields → broader syllabus topics
TOPIC_MAP = {
    # Anthropology core
    "anthropological theory": "Anthropological Theory & Philosophy",
    "theoretical anthropology": "Anthropological Theory & Philosophy",
    "philosophical anthropology": "Anthropological Theory & Philosophy",
    "anthropological ontology": "Anthropological Theory & Philosophy",
    "anthropological theory and disciplinary critique": "Anthropological Theory & Philosophy",
    "anthropological temporality": "Anthropological Theory & Philosophy",
    "anthropology of time": "Anthropological Theory & Philosophy",
    "anthropology of time and capitalism": "Anthropological Theory & Philosophy",
    "phenomenological anthropology": "Anthropological Theory & Philosophy",
    "moral philosophy": "Anthropological Theory & Philosophy",
    "social theory": "Anthropological Theory & Philosophy",
    "sociological theory": "Anthropological Theory & Philosophy",
    "critical social theory": "Anthropological Theory & Philosophy",
    "critical theory": "Anthropological Theory & Philosophy",
    "philosophical psychology": "Anthropological Theory & Philosophy",

    # Methodology
    "anthropological methodology": "Methods & Methodology",
    "ethnographic methodology": "Methods & Methodology",
    "comparative methodology": "Methods & Methodology",
    "historical methodology": "Methods & Methodology",
    "global history methodology": "Methods & Methodology",
    "autoethnography": "Methods & Methodology",
    "anthropological ethics and methodology": "Methods & Methodology",

    # Indigenous studies
    "indigenous studies": "Indigenous & Decolonial Studies",
    "Indigenous studies": "Indigenous & Decolonial Studies",
    "Indigenous studies methodology": "Indigenous & Decolonial Studies",
    "Indigenous research methodology": "Indigenous & Decolonial Studies",
    "indigenous research methodology": "Indigenous & Decolonial Studies",
    "Indigenous social work": "Indigenous & Decolonial Studies",
    "Indigenous gender studies": "Indigenous & Decolonial Studies",
    "indigenous studies and settler colonial theory": "Indigenous & Decolonial Studies",
    "indigenous water governance": "Indigenous & Decolonial Studies",
    "settler colonial studies": "Indigenous & Decolonial Studies",
    "decolonial studies": "Indigenous & Decolonial Studies",
    "decolonial theory": "Indigenous & Decolonial Studies",
    "decolonial sociology": "Indigenous & Decolonial Studies",
    "decolonial geography": "Indigenous & Decolonial Studies",
    "decolonial research methodology": "Indigenous & Decolonial Studies",
    "decolonial feminist studies": "Indigenous & Decolonial Studies",
    "decolonial international relations theory": "Indigenous & Decolonial Studies",
    "decolonial management and organizational studies": "Indigenous & Decolonial Studies",

    # Political anthropology
    "political anthropology": "Political Anthropology & Power",
    "political theory": "Political Anthropology & Power",
    "political sociology": "Political Anthropology & Power",
    "international relations theory": "Political Anthropology & Power",
    "visual international relations theory": "Political Anthropology & Power",
    "critical international relations theory": "Political Anthropology & Power",
    "political communication and media studies": "Political Anthropology & Power",
    "nationalism studies": "Political Anthropology & Power",
    "subaltern studies": "Political Anthropology & Power",

    # Postcolonial & critical
    "critical anthropology": "Critical & Postcolonial Anthropology",
    "postcolonial anthropology": "Critical & Postcolonial Anthropology",
    "critical colonial studies": "Critical & Postcolonial Anthropology",
    "colonial historiography": "Critical & Postcolonial Anthropology",
    "postcolonial war studies": "Critical & Postcolonial Anthropology",
    "postcolonial literary studies": "Critical & Postcolonial Anthropology",
    "postcolonial queer studies": "Critical & Postcolonial Anthropology",
    "critical race theory and visual studies": "Critical & Postcolonial Anthropology",
    "critical race studies": "Critical & Postcolonial Anthropology",
    "racial stratification sociology": "Critical & Postcolonial Anthropology",
    "slavery studies": "Critical & Postcolonial Anthropology",
    "feminist anthropology": "Critical & Postcolonial Anthropology",
    "feminist geography": "Critical & Postcolonial Anthropology",

    # Urban & space
    "urban anthropology": "Urban & Spatial Anthropology",
    "urban geography": "Urban & Spatial Anthropology",
    "urban political geography": "Urban & Spatial Anthropology",
    "urban political ecology": "Urban & Spatial Anthropology",
    "urban political economy": "Urban & Spatial Anthropology",
    "urban political theory": "Urban & Spatial Anthropology",
    "urban religious studies": "Urban & Spatial Anthropology",
    "urban ethnomusicology": "Urban & Spatial Anthropology",
    "carceral geography": "Urban & Spatial Anthropology",

    # Environment & ecology
    "environmental anthropology": "Environmental & Ecological Anthropology",
    "political ecology": "Environmental & Ecological Anthropology",
    "agrarian political ecology": "Environmental & Ecological Anthropology",
    "ecological Marxism": "Environmental & Ecological Anthropology",
    "multispecies anthropology": "Environmental & Ecological Anthropology",
    "more-than-human geography": "Environmental & Ecological Anthropology",
    "critical animal studies": "Environmental & Ecological Anthropology",
    "anthropology of human-animal relations": "Environmental & Ecological Anthropology",
    "conservation social science": "Environmental & Ecological Anthropology",
    "environmental policy and forest governance": "Environmental & Ecological Anthropology",

    # Geography (general)
    "human geography": "Geography & Place",
    "cultural geography": "Geography & Place",
    "critical geography": "Geography & Place",
    "economic geography": "Geography & Place",
    "critical human geography": "Geography & Place",
    "social and cultural geography": "Geography & Place",
    "emotional geography": "Geography & Place",
    "political geography": "Geography & Place",
    "border anthropology": "Geography & Place",
    "critical border studies": "Geography & Place",
    "Caribbean anthropology": "Geography & Place",
    "anthropological studies of West Papua": "Geography & Place",

    # Religion & ritual
    "anthropology of religion": "Religion, Ritual & Ethics",
    "religious anthropology": "Religion, Ritual & Ethics",
    "religious studies methodology": "Religion, Ritual & Ethics",
    "religious studies and urban geography": "Religion, Ritual & Ethics",
    "human geography and theology": "Religion, Ritual & Ethics",
    "anthropology of ethics": "Religion, Ritual & Ethics",
    "anthropology of ethics and morality": "Religion, Ritual & Ethics",

    # Culture, symbols, senses
    "cultural anthropology": "Cultural & Symbolic Anthropology",
    "sociocultural anthropology": "Cultural & Symbolic Anthropology",
    "symbolic anthropology": "Cultural & Symbolic Anthropology",
    "semiotic anthropology": "Cultural & Symbolic Anthropology",
    "sensory anthropology": "Cultural & Symbolic Anthropology",
    "cultural studies": "Cultural & Symbolic Anthropology",
    "psychological anthropology": "Cultural & Symbolic Anthropology",
    "sociology of emotions": "Cultural & Symbolic Anthropology",

    # Medical & health
    "medical anthropology": "Medical & Health Anthropology",
    "clinical psychology/trauma studies": "Medical & Health Anthropology",

    # Migration & conflict
    "migration studies": "Migration, Conflict & Humanitarianism",
    "refugee history": "Migration, Conflict & Humanitarianism",
    "humanitarian studies": "Migration, Conflict & Humanitarianism",
    "anthropology of humanitarianism": "Migration, Conflict & Humanitarianism",
    "African conflict studies": "Migration, Conflict & Humanitarianism",
    "transformative justice studies": "Migration, Conflict & Humanitarianism",

    # Historical & archaeological
    "historical anthropology": "Historical & Archaeological Anthropology",
    "archaeological theory": "Historical & Archaeological Anthropology",
    "archaeological anthropology": "Historical & Archaeological Anthropology",
    "maritime archaeology": "Historical & Archaeological Anthropology",
    "island archaeology": "Historical & Archaeological Anthropology",
    "ethnoarchaeology": "Historical & Archaeological Anthropology",
    "memory studies": "Historical & Archaeological Anthropology",
    "anthropology of history": "Historical & Archaeological Anthropology",
    "heritage studies": "Historical & Archaeological Anthropology",
    "museum studies": "Historical & Archaeological Anthropology",
    "classical studies": "Historical & Archaeological Anthropology",

    # Digital & technology
    "digital anthropology": "Digital & Technology Studies",
    "digital sociology": "Digital & Technology Studies",
    "digital media anthropology": "Digital & Technology Studies",
    "critical data studies": "Digital & Technology Studies",
    "critical AI studies": "Digital & Technology Studies",
    "anthropology of technology and sexuality": "Digital & Technology Studies",

    # Economic & development
    "economic anthropology": "Economic & Development Anthropology",
    "development anthropology": "Economic & Development Anthropology",
    "development studies": "Economic & Development Anthropology",
    "critical development studies": "Economic & Development Anthropology",
    "critical political economy": "Economic & Development Anthropology",
    "organizational studies": "Economic & Development Anthropology",
    "consumer behavior and marketing": "Economic & Development Anthropology",
    "tourism anthropology": "Economic & Development Anthropology",

    # Death, grief, hope
    "anthropology of death": "Life, Death & Meaning",
    "anthropology of grief": "Life, Death & Meaning",
    "anthropology of hope": "Life, Death & Meaning",
    "death studies": "Life, Death & Meaning",

    # Language
    "sociolinguistics": "Language & Communication",
    "critical sociolinguistics": "Language & Communication",
    "educational anthropology": "Language & Communication",

    # African studies
    "African studies": "African Studies",
    "African studies anthropology": "African Studies",

    # Sleep & cognition
    "sleep neuroscience": "Sleep & Cognition Research",
    "sleep medicine": "Sleep & Cognition Research",
    "sleep medicine and neurodegeneration": "Sleep & Cognition Research",
    "sleep and circadian rhythm research": "Sleep & Cognition Research",
    "systems neuroscience": "Sleep & Cognition Research",
    "neuropharmacology": "Sleep & Cognition Research",
    "clinical psychiatry": "Sleep & Cognition Research",
    "biomedical signal processing": "Sleep & Cognition Research",
}


def classify_topic(subfield: str) -> str:
    """Map a subfield to a broader topic."""
    if not subfield:
        return "Other"
    # Exact match
    if subfield in TOPIC_MAP:
        return TOPIC_MAP[subfield]
    # Case-insensitive match
    for key, topic in TOPIC_MAP.items():
        if key.lower() == subfield.lower():
            return topic
    # Keyword fallback
    sf = subfield.lower()
    if "sleep" in sf or "neuroscience" in sf or "cognit" in sf or "circadian" in sf:
        return "Sleep & Cognition Research"
    if "anthrop" in sf:
        return "Anthropological Theory & Philosophy"
    if "geograph" in sf:
        return "Geography & Place"
    if "decoloni" in sf or "indigenous" in sf or "settler" in sf:
        return "Indigenous & Decolonial Studies"
    if "polit" in sf:
        return "Political Anthropology & Power"
    if "archaeo" in sf:
        return "Historical & Archaeological Anthropology"
    if "urban" in sf:
        return "Urban & Spatial Anthropology"
    if "ecolog" in sf or "environ" in sf or "species" in sf:
        return "Environmental & Ecological Anthropology"
    if "relig" in sf or "ritual" in sf:
        return "Religion, Ritual & Ethics"
    if "medic" in sf or "health" in sf:
        return "Medical & Health Anthropology"
    if "digital" in sf or "tech" in sf:
        return "Digital & Technology Studies"
    if "colonial" in sf or "postcolonial" in sf:
        return "Critical & Postcolonial Anthropology"
    return "Other"


def fetch_all_papers():
    """Fetch all papers from Supabase."""
    papers = []
    offset = 0
    while True:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/papers",
            params={
                "select": "id,title,doi,publication_year,cited_by_count,source_journal,subfield,paper_type,authors",
                "order": "cited_by_count.desc",
                "limit": "500",
                "offset": str(offset),
            },
            headers=HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"Error fetching papers: {r.status_code} {r.text[:200]}")
            break
        batch = r.json()
        if not batch:
            break
        papers.extend(batch)
        offset += len(batch)
        print(f"  Fetched {len(papers)} papers...")
    return papers


def group_by_topic(papers):
    """Group papers by broader topic derived from subfield."""
    topics = {}
    for p in papers:
        topic = classify_topic(p.get("subfield") or "")
        if topic not in topics:
            topics[topic] = []
        topics[topic].append(p)
    return topics


def extract_first_author(authors_str):
    """Extract first author name from JSON string."""
    if not authors_str:
        return ""
    try:
        import json
        authors = json.loads(authors_str) if isinstance(authors_str, str) else authors_str
        if authors and isinstance(authors, list):
            return authors[0].get("name", "")
    except Exception:
        pass
    return ""


def write_topic_syllabus(topic: str, papers: list):
    """Write a syllabus markdown file for a topic."""
    os.makedirs(SYLLABUS_DIR, exist_ok=True)

    # Clean topic name for filename
    filename = re.sub(r'[^\w\s-]', '', topic.lower()).strip().replace(" ", "_")
    filepath = os.path.join(SYLLABUS_DIR, f"{filename}.md")

    # Sort by citations desc
    papers.sort(key=lambda p: p.get("cited_by_count", 0), reverse=True)

    # Collect subfields in this topic
    subfields = {}
    for p in papers:
        sf = p.get("subfield") or "unknown"
        subfields[sf] = subfields.get(sf, 0) + 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n")
        f.write(f"**Papers:** {len(papers)} | ")

        years = [p["publication_year"] for p in papers if p.get("publication_year")]
        if years:
            f.write(f"**Years:** {min(years)}–{max(years)} | ")

        total_cites = sum(p.get("cited_by_count", 0) for p in papers)
        f.write(f"**Total citations:** {total_cites:,}\n\n")

        # Subfields in this topic
        f.write("**Subfields:** ")
        top_sf = sorted(subfields.items(), key=lambda x: -x[1])[:10]
        f.write(", ".join(f"{sf} ({c})" for sf, c in top_sf))
        f.write("\n\n")

        # Top journals
        journals = {}
        for p in papers:
            j = p.get("source_journal") or "Unknown"
            journals[j] = journals.get(j, 0) + 1
        top_j = sorted(journals.items(), key=lambda x: -x[1])[:5]
        if top_j:
            f.write("**Top journals:** ")
            f.write(", ".join(f"{j} ({c})" for j, c in top_j))
            f.write("\n\n")

        f.write("---\n\n")

        # Paper list
        for i, p in enumerate(papers, 1):
            title = p.get("title", "Untitled")
            doi = p.get("doi", "")
            year = p.get("publication_year", "?")
            cites = p.get("cited_by_count", 0)
            journal = p.get("source_journal", "")
            ptype = p.get("paper_type", "")
            author = extract_first_author(p.get("authors"))

            f.write(f"**{i}. {title}**\n")
            parts = []
            if author:
                parts.append(author)
            parts.append(str(year))
            if journal:
                parts.append(journal)
            if ptype:
                parts.append(f"[{ptype}]")
            parts.append(f"{cites:,} citations")
            f.write(f"  {' · '.join(parts)}\n")

            if doi:
                doi_url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
                f.write(f"  DOI: {doi_url}\n")
            f.write("\n")

    print(f"  {topic}: {len(papers)} papers -> {filepath}")
    return filepath


def write_index(topics: dict):
    """Write an index file linking all syllabus files."""
    os.makedirs(SYLLABUS_DIR, exist_ok=True)
    filepath = os.path.join(SYLLABUS_DIR, "README.md")

    total = sum(len(ps) for ps in topics.values())

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Korczak AI — Knowledge Syllabus\n\n")
        f.write("All papers in Korczak's knowledge graph, organized by topic.\n\n")
        f.write(f"**Total papers:** {total}\n\n")
        f.write("## Topics\n\n")
        f.write("| Topic | Papers | Citations |\n")
        f.write("|-------|-------:|----------:|\n")

        for topic in sorted(topics.keys()):
            papers = topics[topic]
            filename = re.sub(r'[^\w\s-]', '', topic.lower()).strip().replace(" ", "_")
            cites = sum(p.get("cited_by_count", 0) for p in papers)
            f.write(f"| [{topic}]({filename}.md) | {len(papers)} | {cites:,} |\n")

        f.write("\n---\n*Generated from Korczak AI's seeded knowledge graph*\n")

    print(f"  Index: {filepath}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("Fetching papers from Supabase...")
    papers = fetch_all_papers()
    print(f"Total: {len(papers)} papers\n")

    print("Grouping by topic...")
    topics = group_by_topic(papers)
    for t in sorted(topics.keys()):
        print(f"  {t}: {len(topics[t])}")

    print(f"\nWriting {len(topics)} syllabus files...")
    for topic, topic_papers in sorted(topics.items()):
        write_topic_syllabus(topic, topic_papers)

    write_index(topics)
    print(f"\nDone! Files in: {os.path.abspath(SYLLABUS_DIR)}")


if __name__ == "__main__":
    main()
