# Korczak — מערכת Multi-Source Validation וביקורת פנימית
## תוספת לאפיון | אפריל 2026
## "אל תסמוך על מקור אחד — אף פעם"

---

# 1. רציונאל — למה מקור אחד לא מספיק

## 1.1 הבעיה

OpenAlex הוא מקור מצוין — 250M+ works, API חינמי ונדיב, metadata עשירה. אבל כל מקור בודד מביא איתו הטיות:

**הטיית שפה:** OpenAlex מכסה פרסומים באנגלית הרבה יותר טוב מאשר סינית, ערבית, עברית, ספרדית. 34% מהפרסומים ב-CRISPR הם מסין — אם המקור לא מכסה אותם, הגרף "עיוור" לשליש מהתחום.

**הטיית סוג:** מאמרים ב-journals מיוצגים היטב. Working papers, דוחות ממשלתיים, grey literature, תזות דוקטורט — פחות.

**הטיית classification:** כל מקור מסווג מושגים אחרת. OpenAlex משתמש ב-concepts tree מבוסס Wikidata. Semantic Scholar משתמש ב-SPECTER embeddings. שני הסיווגים לגיטימיים — אבל שונים.

**הטיית ציטוטים:** ספירת ציטוטים שונה בין מקורות. OpenAlex סופר preprints, S2 לא תמיד. Google Scholar סופר הכל כולל slides ובלוגים. ההבדל יכול להיות 20-40%.

## 1.2 העיקרון המנחה

**כמו עיתונות טובה: שני מקורות עצמאיים לפחות לכל טענה.**

כל אלמנט בגרף (מושג, קשר, טענה) חייב אישור ממקור נוסף לפחות. כשמקורות חולקים — זה לא באג, זה **מידע.** חילוקי דעות בין מקורות מוצפים למשתמש כחלק מהערך של המערכת.

## 1.3 מה זה נותן בפועל

**בלי multi-source:**
"CRISPR-Cas9 has 15,000 papers and is widely studied."

**עם multi-source:**
"CRISPR-Cas9 has approximately 15,000 papers (OpenAlex: 15,200, Semantic Scholar: 14,800 — the difference is preprint inclusion policy). ⚠️ 3 cited papers in this area were retracted in the last two years (Retraction Watch), including [name] with 450 citations. 💰 63% of sub-field [X] research is funded by two companies. Independent studies mostly agree, but there's a gap on [Y]. 🌍 This analysis is primarily based on English-language publications."

---

# 2. מפת מקורות הידע

## 2.1 Tier 1: מקורות ליבה (חינמיים, API פתוח, MVP)

### OpenAlex
- **מה נותן:** metadata (כותרת, מחברים, מוסד, שנה), ציטוטים, concepts classification, funding/grants, co-authorship networks, open access status, 250M+ works
- **מה חסר:** אין full text, classification לפעמים שטחית, כיסוי חלש ל-non-English
- **API:** חינם, polite pool עם email, 10 req/sec, 100K/day
- **Base URL:** `https://api.openalex.org`
- **שימוש בקורצאק:** מקור ראשי ל-paper metadata, citation networks, funding analysis, institutional data
- **משקל ב-confidence:** 0.3

### Semantic Scholar (S2)
- **מה נותן:** metadata, abstracts, **TLDR summaries** (AI-generated), **influential citation count** (לא רק כמות — כמה מהציטוטים הם "influential"), **citation intent** (background/method/result), embedding-based paper similarity
- **מה חסר:** כיסוי קטן יותר מ-OpenAlex (~210M vs 250M), חלש ב-humanities
- **API:** חינם, 100 req/sec (with API key), 1 req/sec (without)
- **Base URL:** `https://api.semanticscholar.org/graph/v1`
- **שימוש בקורצאק:** cross-validation של ציטוטים, **citation intent analysis** (מי מצטט כדי לתמוך ומי כדי לחלוק — signal קריטי ל-CONTRADICTS edges), influential citations, paper similarity
- **משקל ב-confidence:** 0.3
- **נקודת חוזק ייחודית:** citation intent analysis — S2 מסווג ציטוטים ל-"background", "method", "result extension", "comparison/contrast". זה signal ישיר לסוגי קשרים בגרף

### arXiv
- **מה נותן:** **full text** של preprints (PDF + LaTeX source), categories, submission history
- **מה חסר:** רק preprints, בעיקר CS/Math/Physics/Biology/Economics
- **API:** חינם, OAI-PMH + bulk access
- **שימוש בקורצאק:** full text analysis (כשזמין — נותן ניתוח הרבה יותר עמוק מ-abstract בלבד), version tracking (האם מאמר השתנה מהותית בין versions)
- **משקל ב-confidence:** 0.15 (מוגבל לתחומים ספציפיים)
- **נקודת חוזק ייחודית:** full text מאפשר ניתוח LLM מעמיק הרבה יותר מ-abstract

### CrossRef
- **מה נותן:** DOI registry, publisher metadata, references, license info, Funder Registry
- **מה חסר:** אין abstracts לרוב, אין citation counts
- **API:** חינם, polite pool עם email
- **Base URL:** `https://api.crossref.org`
- **שימוש בקורצאק:** DOI validation (האם מאמר קיים?), publisher info, reference lists (מה מאמר מצטט — אם OpenAlex חסר), funder standardization
- **משקל ב-confidence:** 0.1 (בעיקר metadata validation)

### ORCID
- **מה נותן:** researcher identity, publications list, affiliations history, grants
- **מה חסר:** רק חוקרים שנרשמו (~18M), לא שלם
- **API:** חינם, public API
- **שימוש בקורצאק:** researcher identity resolution (חוקר עם שם נפוץ — ORCID מזהה ייחודית), career tracking, affiliation history, User Graph enrichment (כשמשתמש מחבר ORCID)
- **משקל ב-confidence:** 0.1

### Unpaywall
- **מה נותן:** open access status — האם מאמר זמין בחינם, ואיפה (publisher, repository, preprint)
- **מה חסר:** רק OA status, לא תוכן
- **API:** חינם עם email
- **שימוש בקורצאק:** לדעת אם אפשר להשיג full text (→ ניתוח מעמיק יותר), להפנות משתמשים לגרסה חינמית, open access tracking per domain
- **משקל ב-confidence:** 0.05 (enrichment, not validation)

## 2.2 Tier 2: מקורות העשרה (חינמיים/זולים, ערך גבוה)

### Retraction Watch Database
- **מה נותן:** מאמרים שנסוגו, expressions of concern, corrections
- **למה קריטי:** מאמר שנסוג אבל עדיין מצוטט הוא **מפגע ידע.** קורצאק חייב לדעת ולהתריע. ~45,000 retractions in database, updated regularly
- **גישה:** חינם, bulk download + API (limited)
- **שימוש בקורצאק:** כל מאמר שנכנס לגרף נבדק מול Retraction Watch. אם נסוג → confidence drops to near-zero, flag "RETRACTED" מוצמד, כל מאמר שמצטט אותו מקבל warning
- **משקל ב-confidence:** 0.3 (כשרלוונטי — retraction = veto power)

### OpenSyllabus
- **מה נותן:** סילבוסים מ-7,000+ מוסדות, 20M+ syllabus mentions, "how often is this taught" data
- **למה חשוב:** signal ייחודי שאף מקור אחר לא נותן — מה ה-teaching consensus, מה נלמד ומה לא, סדר פדגוגי
- **גישה:** API בתשלום (Galaxy subscription), data explorer חינם
- **שימוש בקורצאק:** PREREQUISITE_FOR relationships (סדר הנושאים בסילבוסים), "teaching consensus" signal, Syllabus Intelligence feature, gap analysis (מה מצוטט הרבה אבל לא נלמד — ולהפך)
- **משקל ב-confidence:** 0.2 (כשזמין)
- **תזמון:** Phase 2 — אחרי MVP עובד

### Altmetric
- **מה נותן:** attention data — ציטוטים בתקשורת, social media, policy documents, Wikipedia, patents
- **למה מעניין:** "buzz" vs "impact" — מאמר עם 50 ציטוטים אקדמיים ו-500 mentions בתקשורת = סיפור שונה ממאמר עם 500 ציטוטים ו-0 media
- **גישה:** API חינם (basic), paid for detailed
- **שימוש בקורצאק:** public impact tracking, controversy detection (מאמר עם הרבה media attention שלילית = controversy signal), policy relevance
- **משקל ב-confidence:** 0.05 (enrichment, not validation)

### Dimensions
- **מה נותן:** grants, patents, clinical trials, policy documents — **מחוברים למאמרים.** "Paper X received $2M from NIH Grant Y and led to Patent Z and Clinical Trial W"
- **למה חשוב:** Funding X-Ray feature מקבל עומק משמעותי. קשר מחקר→פטנט הוא signal ל-commercial viability
- **גישה:** חינם (basic), paid (full)
- **שימוש בקורצאק:** funding analysis מעמיקה, patent connections, clinical trial tracking (for biomedical domain)
- **משקל ב-confidence:** 0.1
- **תזמון:** Phase 2-3

## 2.3 Tier 3: מקורות עתידיים (בתשלום / דורשים שותפות)

| מקור | מה נותן | מתי רלוונטי |
|------|---------|-------------|
| Scopus / Web of Science | classification מדויקת, journal impact factors | כשיש תקציב ל-enterprise API |
| Google Scholar | ה-citation count הכי מקיף | אין API רשמי, scraping בעייתי משפטית |
| PubMed/PMC | full text למאמרים רפואיים, MeSH controlled vocabulary | כש-domain adapter לרפואה |
| Institutional repositories | grey literature, theses | שותפויות עם אוניברסיטאות |
| Patent databases (USPTO, EPO) | קישור מחקר→פטנטים | domain adapter ל-R&D/innovation |
| Replication Markets / PsychFileDrawer | replication status | כשיש מספיק data |

---

# 3. Cross-Source Validation Architecture

## 3.1 עקרון מרכזי: "Dual-Source Minimum"

כל אלמנט בגרף חייב אישור ממקור נוסף לפחות:

```
VALIDATION RULES:

Concept existence:
  ✅ CONFIRMED: appears in 2+ sources
  ⚠️ PROBABLE: appears in 1 source + LLM identifies
  ❌ UNVALIDATED: LLM only — flag for review

Relationship type:
  ✅ CONFIRMED: 2 LLM analyses agree on type
  ⚠️ PROBABLE: 1 LLM analysis + citation intent supports
  ❌ DISPUTED: LLM analyses disagree — flag, show both to user

Paper reliability:
  ✅ HIGH: not retracted + replicated + multiple funders
  ⚠️ MEDIUM: not retracted + not replicated + mixed funding
  ❌ LOW: retracted, or concern expressed, or single-funder
  ☠️ RETRACTED: retracted — near-zero confidence, active warning
```

## 3.2 Multi-Source Ingestion Pipeline

```python
# pipeline/multi_source_ingest.py

class MultiSourcePipeline:
    """
    Fetches data from multiple sources, cross-validates,
    and produces high-confidence graph updates.
    """
    
    def __init__(self):
        self.sources = {
            "openalex": OpenAlexSource(),
            "semantic_scholar": SemanticScholarSource(),
            "crossref": CrossRefSource(),
            "retraction_watch": RetractionWatchSource(),
            "unpaywall": UnpaywallSource(),
        }
        
        self.analyzers = {
            "primary": ClaudeAnalyzer(
                model="claude-sonnet-4-20250514",
                temperature=0.2
            ),
            "secondary": ClaudeAnalyzer(
                model="claude-sonnet-4-20250514",
                temperature=0.5
            ),
            # Different temperature = different "perspective"
            # Agreement between temperatures → higher confidence
        }
    
    async def ingest_paper(self, paper_id: str) -> GraphUpdate:
        """
        Full pipeline for a single paper:
        1. Fetch from all available sources
        2. Cross-validate metadata
        3. Analyze content with dual LLM
        4. Reconcile analyses
        5. Enrich with source-specific signals
        6. Check for red flags
        7. Calculate confidence scores
        8. Produce graph update
        """
        
        # Step 1: Fetch from multiple sources
        source_data = {}
        for name, source in self.sources.items():
            try:
                source_data[name] = await source.fetch(paper_id)
                await self._log_source_health(name, success=True)
            except Exception as e:
                source_data[name] = None
                await self._log_source_health(name, success=False, 
                                               error=str(e))
        
        # Step 2: Cross-validate metadata
        metadata = self._cross_validate_metadata(source_data)
        
        # Step 3: Dual LLM analysis
        abstract = metadata.abstract or ""
        full_text = self._get_full_text(source_data)  # from arXiv/PMC if available
        
        primary = await self.analyzers["primary"].analyze(
            title=metadata.title,
            abstract=abstract,
            full_text=full_text,
            metadata=metadata.to_context()
        )
        
        secondary = await self.analyzers["secondary"].analyze(
            title=metadata.title,
            abstract=abstract,
            full_text=full_text,
            metadata=metadata.to_context()
        )
        
        # Step 4: Reconcile
        reconciled = self._reconcile_analyses(primary, secondary)
        
        # Step 5: Enrich with source-specific signals
        enriched = self._enrich(reconciled, source_data)
        
        # Step 6: Calculate final confidence scores
        enriched = self._calculate_confidences(enriched)
        
        return enriched
    
    def _cross_validate_metadata(self, source_data: dict) -> PaperMetadata:
        """
        Cross-check basic facts across sources.
        Title, authors, year should agree.
        """
        fields_by_source = {}
        for source_name, data in source_data.items():
            if data is None:
                continue
            fields_by_source[source_name] = {
                "title": data.get("title"),
                "year": data.get("year"),
                "author_count": len(data.get("authors", [])),
                "doi": data.get("doi"),
            }
        
        # Check agreement
        disagreements = []
        
        # Year disagreement
        years = [f["year"] for f in fields_by_source.values() if f["year"]]
        if years and max(years) - min(years) > 1:
            disagreements.append({
                "field": "publication_year",
                "values": {s: f["year"] for s, f in fields_by_source.items()},
                "resolution": "use_majority"
            })
        
        # Title disagreement (fuzzy match)
        titles = {s: f["title"] for s, f in fields_by_source.items() if f["title"]}
        if len(set(titles.values())) > 1:
            # Could be formatting differences — check similarity
            # Only flag if substantially different
            pass
        
        # Log disagreements
        for d in disagreements:
            self._log_disagreement(d)
        
        # Use OpenAlex as primary, S2 as fallback
        primary_source = source_data.get("openalex") or source_data.get("semantic_scholar")
        return PaperMetadata.from_source(primary_source, disagreements)
    
    def _reconcile_analyses(self, primary: Analysis, 
                             secondary: Analysis) -> Analysis:
        """
        Compare two independent LLM analyses.
        Agreement = confidence boost.
        Disagreement = flag + use primary with reduced confidence.
        """
        reconciled = primary.copy()
        
        # Compare concepts
        for concept in reconciled.concepts:
            match = secondary.find_similar_concept(concept.name)
            if match and match.similarity > 0.8:
                concept.confidence += 0.1  # agreement boost
                concept.validation_notes.append("dual_llm_confirmed")
            else:
                concept.confidence -= 0.1
                concept.validation_notes.append("single_llm_only")
                concept.flags.append("SINGLE_LLM_ONLY")
        
        # Check for concepts secondary found that primary missed
        for sec_concept in secondary.concepts:
            if not primary.find_similar_concept(sec_concept.name):
                # Secondary found something primary missed
                sec_concept.confidence = 0.4  # low confidence
                sec_concept.validation_notes.append(
                    "found_by_secondary_only"
                )
                reconciled.concepts.append(sec_concept)
        
        # Compare relationships
        for rel in reconciled.relationships:
            sec_rel = secondary.find_relationship(rel.source, rel.target)
            if sec_rel:
                if sec_rel.type == rel.type:
                    rel.confidence += 0.1  # type agreement
                    rel.validation_notes.append("dual_llm_type_confirmed")
                else:
                    rel.confidence -= 0.15
                    rel.flags.append("TYPE_DISPUTED")
                    rel.validation_notes.append(
                        f"primary={rel.type}, secondary={sec_rel.type}"
                    )
                    # Log disagreement for review
                    self._log_type_disagreement(rel, sec_rel)
            else:
                rel.confidence -= 0.1
                rel.flags.append("SINGLE_LLM_ONLY")
        
        return reconciled
    
    def _enrich(self, analysis: Analysis, 
                 source_data: dict) -> GraphUpdate:
        """
        Add signals that only specific sources provide.
        """
        update = GraphUpdate.from_analysis(analysis)
        
        # === Retraction Watch ===
        rw_data = source_data.get("retraction_watch")
        if rw_data:
            if rw_data.is_retracted:
                update.add_flag("RETRACTED", severity="critical",
                    detail=f"Retracted on {rw_data.retraction_date}. "
                           f"Reason: {rw_data.reason}")
                update.confidence_multiplier = 0.1
            elif rw_data.has_expression_of_concern:
                update.add_flag("CONCERN_EXPRESSED", severity="high",
                    detail=f"Expression of concern issued "
                           f"{rw_data.concern_date}")
                update.confidence_multiplier = 0.5
            elif rw_data.has_correction:
                update.add_flag("CORRECTED", severity="low",
                    detail=f"Correction issued {rw_data.correction_date}")
        
        # === Semantic Scholar citation intents ===
        s2_data = source_data.get("semantic_scholar")
        if s2_data and s2_data.citations:
            for citation in s2_data.citations:
                if citation.intent == "disputes":
                    update.add_relationship(
                        source=citation.citing_paper_id,
                        target=analysis.paper_id,
                        type="CONTRADICTS",
                        confidence=0.65,
                        evidence_source="s2_citation_intent"
                    )
                elif citation.intent == "extends":
                    update.add_relationship(
                        source=citation.citing_paper_id,
                        target=analysis.paper_id,
                        type="EXTENDS",
                        confidence=0.6,
                        evidence_source="s2_citation_intent"
                    )
            
            update.metadata["influential_citation_count"] = (
                s2_data.influential_citation_count
            )
            update.metadata["citation_velocity"] = s2_data.citation_velocity
        
        # === OpenAlex funding ===
        oa_data = source_data.get("openalex")
        if oa_data and oa_data.grants:
            funding = {
                "sources": [
                    {"name": g.funder_name, "type": g.funder_type, 
                     "amount": g.amount}
                    for g in oa_data.grants
                ],
                "is_industry_funded": any(
                    g.funder_type == "company" for g in oa_data.grants
                ),
                "total_funders": len(set(g.funder_name for g in oa_data.grants)),
            }
            update.metadata["funding"] = funding
            
            # Concentration check
            if len(oa_data.grants) > 0:
                top_funder_share = max(
                    sum(1 for g in oa_data.grants if g.funder_name == f) 
                    / len(oa_data.grants)
                    for f in set(g.funder_name for g in oa_data.grants)
                )
                if top_funder_share > 0.8:
                    update.add_flag("HIGH_FUNDING_CONCENTRATION",
                        severity="medium",
                        detail=f"80%+ funding from single source")
        
        # === Unpaywall ===
        up_data = source_data.get("unpaywall")
        if up_data:
            update.metadata["open_access"] = up_data.is_oa
            update.metadata["oa_url"] = up_data.best_oa_url
            update.metadata["oa_status"] = up_data.oa_status
            # gold, green, hybrid, bronze, closed
        
        # === CrossRef ===
        cr_data = source_data.get("crossref")
        if cr_data:
            update.metadata["publisher"] = cr_data.publisher
            update.metadata["license"] = cr_data.license
            update.metadata["reference_count"] = cr_data.reference_count
        
        return update
    
    def _get_full_text(self, source_data: dict) -> str | None:
        """
        Try to get full text from available sources.
        Priority: arXiv > PMC > Unpaywall OA link
        """
        # arXiv full text
        if source_data.get("arxiv") and source_data["arxiv"].full_text:
            return source_data["arxiv"].full_text
        
        # PMC full text
        if source_data.get("pubmed") and source_data["pubmed"].pmc_text:
            return source_data["pubmed"].pmc_text
        
        # Unpaywall OA PDF (would need PDF extraction)
        # Future: fetch and extract
        
        return None
```

## 3.3 Dual-LLM Analysis — למה ואיך

### למה שני ניתוחים

LLM יחיד יכול "להחליט" על סיווג קשר ולהיות בטוח בעצמו — גם כשהוא טועה. שני ניתוחים עצמאיים (עם temperature שונה) נותנים signal נוסף:

- **שניהם מסכימים:** confidence עולה. כנראה זה באמת נכון.
- **שניהם חולקים על סוג הקשר:** signal שהקשר באמת מורכב — אולי הוא גם EXTENDS וגם CONTRADICTS. זה מידע חשוב, לא שגיאה.
- **רק אחד מצא משהו:** confidence נמוך — אולי artifact, אולי תובנה שדורשת עוד data.

### למה temperature שונה

Temperature 0.2 (primary) = דטרמיניסטי, conservative, נשאר קרוב ל-"expected".
Temperature 0.5 (secondary) = קצת יותר creative, עלול לתפוס חיבורים שה-primary מפספס.

**לא GPT vs Claude.** שני ניתוחים מ-Claude עם parameters שונים מספיקים ועולים פחות. החלפה ל-GPT כ-secondary = שלב עתידי.

### עלות

ניתוח כפול = כפול API calls. אבל: batch processing (זול יותר), ורק על מאמרים חדשים (~50-200/יום). העלות הנוספת: ~$100-150/חודש. שווה את ה-quality jump.

---

# 4. Confidence Score — המודל המלא

## 4.1 Source Weights

```python
# graph/confidence.py

SOURCE_WEIGHTS = {
    # Primary sources — metadata validation
    "openalex_metadata": 0.15,
    "semantic_scholar_metadata": 0.15,
    
    # LLM analysis
    "llm_primary": 0.20,
    "llm_secondary": 0.10,
    
    # Structural signals
    "citation_network": 0.15,       # citation count + patterns
    "citation_intent": 0.10,        # S2 citation intent (disputes/extends)
    
    # Safety checks
    "retraction_check": 0.10,       # Retraction Watch — veto power
    
    # Teaching consensus (when available)
    "syllabus_presence": 0.10,      # OpenSyllabus
    
    # Human validation (when available)  
    "expert_review": 0.25,          # highest weight
    "user_feedback_aggregate": 0.05, # weak signal, needs volume
}

# Note: weights sum to >1.0 because not all sources 
# are available for every element. Score is normalized 
# by available weights.
```

## 4.2 Confidence Calculation

```python
class ConfidenceCalculator:
    
    def calculate(self, element_id: str, 
                   element_type: str) -> ConfidenceScore:
        """
        Calculate confidence score for any graph element.
        """
        # Gather all evidence from source_evidence table
        evidence = self.db.query(
            "SELECT source_name, signal_type, signal_value, signal_detail "
            "FROM source_evidence "
            "WHERE element_id = %s AND element_type = %s",
            (element_id, element_type)
        )
        
        # Calculate weighted score
        score = 0.0
        total_weight = 0.0
        source_count = 0
        
        for ev in evidence:
            weight = SOURCE_WEIGHTS.get(ev.source_name, 0.05)
            if ev.signal_value is not None:
                score += weight * ev.signal_value
                total_weight += weight
                if ev.signal_value > 0.5:
                    source_count += 1
        
        if total_weight == 0:
            return ConfidenceScore(value=0.0, basis="no_evidence")
        
        raw_score = score / total_weight
        
        # Bonus: multiple independent sources agree
        if source_count >= 3:
            raw_score = min(raw_score + 0.05, 1.0)
        if source_count >= 5:
            raw_score = min(raw_score + 0.05, 1.0)
        
        # Check for critical flags
        flags = self.get_active_flags(element_id, element_type)
        
        for flag in flags:
            if flag.flag_type == "RETRACTED":
                raw_score *= 0.1  # near-zero
            elif flag.flag_type == "CONCERN_EXPRESSED":
                raw_score *= 0.5
            elif flag.flag_type == "TYPE_DISPUTED":
                raw_score *= 0.8
            elif flag.flag_type == "SINGLE_LLM_ONLY":
                raw_score *= 0.9
            elif flag.flag_type == "HIGH_FUNDING_CONCENTRATION":
                raw_score *= 0.95  # small penalty, big signal
        
        # Decay for old elements without new evidence
        last_evidence = max(ev.fetched_at for ev in evidence)
        days_since = (datetime.utcnow() - last_evidence).days
        if days_since > 730:  # 2 years
            decay = max(0.3, 1.0 - (days_since - 730) / 3650)
            raw_score *= decay
        
        return ConfidenceScore(
            value=round(raw_score, 3),
            source_count=source_count,
            flags=[f.flag_type for f in flags],
            last_updated=last_evidence,
            basis="multi_source" if source_count >= 2 else "single_source"
        )
```

## 4.3 ה-Navigator מציג confidence

ה-Navigator **תמיד** מציג confidence כשהוא רלוונטי:

- **Confidence > 0.85:** מוצג כעובדה. "X builds on Y."
- **Confidence 0.6-0.85:** מוצג עם הסתייגות. "X likely builds on Y (based on 3 sources, moderate confidence)."
- **Confidence 0.4-0.6:** מוצג עם אזהרה. "The relationship between X and Y is unclear — some evidence suggests [A], but this hasn't been widely validated."
- **Confidence < 0.4:** לא מוצג כעובדה. "There's limited evidence about the connection between X and Y."
- **Flags:** תמיד מוצגים. "⚠️ Note: this paper has been retracted." "💰 Note: this research area has concentrated funding."

---

# 5. Quality Flags System

## 5.1 סוגי Flags

```
FLAG TYPES:

CRITICAL (block/warn immediately):
  RETRACTED              — paper was retracted
  CONCERN_EXPRESSED      — expression of concern issued

HIGH (warn user, reduce confidence):
  HIGH_FUNDING_CONCENTRATION  — 80%+ from single funder
  TYPE_DISPUTED              — LLMs disagree on relationship type
  CITATION_ANOMALY           — unusual citation patterns
                               (e.g., citation ring suspected)

MEDIUM (note in Navigator responses):
  SINGLE_LLM_ONLY       — only one LLM analysis supports this
  STALE                  — no new evidence in 2+ years
  CORRECTED              — paper had a correction issued
  GEOGRAPHIC_BIAS        — evidence primarily from one region

LOW (internal tracking):
  MERGE_CANDIDATE        — possible duplicate concept
  GRANULARITY_ISSUE      — node may need splitting or merging
  MISSING_ABSTRACT       — no abstract available for analysis
```

## 5.2 Flag Lifecycle

```
Created → Active → Resolved / Dismissed

Created: by pipeline, consistency checker, or user report
Active: shown to Navigator, affects confidence
Resolved: issue fixed (e.g., duplicate merged, type corrected)
Dismissed: reviewed and determined to be non-issue

Every flag has:
  - who/what created it (pipeline, user, monitor)
  - when
  - severity
  - suggested action
  - resolution (if resolved)
```

---

# 6. Source Disagreements — Feature, Not Bug

## 6.1 רציונאל

כשמקורות חולקים, זה לא שגיאה — זה **מידע שימושי.** ה-Navigator צריך לדעת ולהציג את חילוקי הדעות.

## 6.2 סוגי חילוקי דעות

```
DISAGREEMENT TYPES:

CITATION_COUNT:
  OpenAlex says 500 citations, S2 says 200
  → Explain difference: preprint inclusion, counting methodology
  → Show both, note the reason for gap

RELATIONSHIP_TYPE:
  LLM1 says "CONTRADICTS", LLM2 says "EXTENDS"
  → This is genuinely ambiguous
  → Show both interpretations to user
  → "The relationship between A and B can be seen as either
     an extension or a challenge, depending on whether you
     focus on [aspect X] or [aspect Y]"

RETRACTION_VS_CITATION:
  Paper is retracted but still cited by 23 recent papers
  → CRITICAL: Navigator must warn
  → "This paper was retracted but is still cited by 23 recent
     papers. These citing papers may need re-evaluation."

FUNDING_VS_CONCLUSION:
  Industry-funded paper reaches favorable conclusion,
  independent papers disagree
  → Flag: "potential funding bias — independent studies
     show different results on [specific aspect]"

GEOGRAPHIC_PERSPECTIVE:
  Western sources emphasize X, non-Western sources emphasize Y
  → Signal: "note: this analysis is primarily based on
     English-language publications. [Additional context
     from other traditions]"

SYLLABUS_VS_RESEARCH:
  Topic taught in 50 syllabi but only 10 papers in 5 years
  → Signal: "established concept, but active research
     has shifted to [newer direction]"
```

## 6.3 Disagreement Surfacing

```python
# core/disagreement_surfacer.py

class DisagreementSurfacer:
    """
    When Navigator discusses a concept or paper,
    check for relevant disagreements and include them.
    """
    
    def get_context_for_navigator(self, 
                                   element_id: str) -> str:
        """
        Returns text that should be included in
        Navigator's response when discussing this element.
        """
        disagreements = self.db.query(
            "SELECT * FROM source_disagreements "
            "WHERE element_id = %s AND resolution IS NULL "
            "ORDER BY created_at DESC",
            (element_id,)
        )
        
        flags = self.db.query(
            "SELECT * FROM quality_flags "
            "WHERE element_id = %s AND status = 'active' "
            "ORDER BY severity DESC",
            (element_id,)
        )
        
        parts = []
        
        for flag in flags:
            if flag.severity == "critical":
                parts.append(
                    f"⚠️ CRITICAL: {flag.detail}"
                )
            elif flag.severity == "high":
                parts.append(
                    f"⚠️ Note: {flag.detail}"
                )
            elif flag.severity == "medium":
                parts.append(
                    f"ℹ️ {flag.detail}"
                )
        
        for d in disagreements:
            if d.disagreement_type == "RETRACTION_VS_CITATION":
                parts.append(
                    f"⚠️ This paper was retracted but is still "
                    f"cited by {d.details['citing_count']} "
                    f"recent papers."
                )
            elif d.disagreement_type == "FUNDING_VS_CONCLUSION":
                parts.append(
                    f"💰 This finding is primarily supported by "
                    f"industry-funded research. Independent "
                    f"studies show "
                    f"{'similar' if d.details['agrees'] else 'different'} "
                    f"results."
                )
            elif d.disagreement_type == "RELATIONSHIP_TYPE":
                parts.append(
                    f"🔍 The relationship between "
                    f"{d.details['concept_a']} and "
                    f"{d.details['concept_b']} is ambiguous — "
                    f"it can be interpreted as "
                    f"'{d.details['type_a']}' or "
                    f"'{d.details['type_b']}' depending on "
                    f"perspective."
                )
        
        return "\n".join(parts) if parts else ""
```

---

# 7. Database Schema — New Tables

```sql
-- =============================================
-- MULTI-SOURCE VALIDATION TABLES
-- Add to existing schema (korczak-2.0-prd.md)
-- =============================================

-- Source evidence: which sources confirmed what
CREATE TABLE source_evidence (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- What this evidence is about
  element_type TEXT NOT NULL 
    CHECK (element_type IN ('concept', 'relationship', 'paper', 'entity')),
  element_id TEXT NOT NULL,
  
  -- Which source
  source_name TEXT NOT NULL,
  -- 'openalex_metadata', 'semantic_scholar_metadata',
  -- 'llm_primary', 'llm_secondary', 'citation_network',
  -- 'citation_intent', 'retraction_check', 'syllabus_presence',
  -- 'expert_review', 'user_feedback_aggregate'
  source_id TEXT,  -- ID in that source's system
  
  -- What it says
  signal_type TEXT NOT NULL 
    CHECK (signal_type IN ('confirms', 'contradicts', 'enriches')),
  signal_value FLOAT CHECK (signal_value BETWEEN 0 AND 1),
  signal_detail JSONB DEFAULT '{}',
  
  fetched_at TIMESTAMPTZ DEFAULT now(),
  
  UNIQUE(element_type, element_id, source_name, signal_type)
);

-- Quality flags: issues detected
CREATE TABLE quality_flags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  element_type TEXT NOT NULL,
  element_id TEXT NOT NULL,
  
  flag_type TEXT NOT NULL,
  -- 'RETRACTED', 'CONCERN_EXPRESSED', 'HIGH_FUNDING_CONCENTRATION',
  -- 'SINGLE_LLM_ONLY', 'TYPE_DISPUTED', 'STALE',
  -- 'CITATION_ANOMALY', 'GEOGRAPHIC_BIAS', 'CORRECTED',
  -- 'MERGE_CANDIDATE', 'GRANULARITY_ISSUE', 'MISSING_ABSTRACT'
  
  severity TEXT NOT NULL 
    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  detail TEXT,
  suggested_action TEXT,
  
  -- Lifecycle
  status TEXT DEFAULT 'active' 
    CHECK (status IN ('active', 'resolved', 'dismissed')),
  created_by TEXT DEFAULT 'pipeline',  -- 'pipeline', 'monitor', 'user', 'expert'
  resolved_by UUID REFERENCES auth.users(id),
  resolved_at TIMESTAMPTZ,
  resolution_notes TEXT,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Source disagreements: when sources conflict
CREATE TABLE source_disagreements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  element_type TEXT NOT NULL,
  element_id TEXT NOT NULL,
  
  -- The two conflicting sources
  source_a TEXT NOT NULL,
  source_a_value JSONB NOT NULL,
  source_b TEXT NOT NULL,
  source_b_value JSONB NOT NULL,
  
  -- Type of disagreement
  disagreement_type TEXT NOT NULL,
  -- 'citation_count', 'relationship_type', 'retraction_status',
  -- 'funding_bias', 'geographic_perspective', 'syllabus_vs_research',
  -- 'metadata_mismatch'
  
  -- Metadata
  details JSONB DEFAULT '{}',
  
  -- Resolution
  resolution TEXT,
  resolution_source TEXT,  -- who/what resolved it
  
  -- Was this surfaced to users?
  surfaced_to_users BOOLEAN DEFAULT false,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Source health: are our data sources working?
CREATE TABLE source_health (
  source_name TEXT PRIMARY KEY,
  
  last_successful_fetch TIMESTAMPTZ,
  last_error TEXT,
  last_error_at TIMESTAMPTZ,
  
  -- Rolling stats
  success_rate_24h FLOAT DEFAULT 1.0,
  avg_latency_ms INT DEFAULT 0,
  error_count_24h INT DEFAULT 0,
  fetch_count_24h INT DEFAULT 0,
  
  status TEXT DEFAULT 'healthy' 
    CHECK (status IN ('healthy', 'degraded', 'down')),
  
  -- Rate limit tracking
  rate_limit_remaining INT,
  rate_limit_resets_at TIMESTAMPTZ,
  
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================
-- INDEXES
-- =============================================

CREATE INDEX idx_source_evidence_element 
  ON source_evidence(element_type, element_id);
CREATE INDEX idx_source_evidence_source 
  ON source_evidence(source_name);
CREATE INDEX idx_quality_flags_active 
  ON quality_flags(element_type, element_id) 
  WHERE status = 'active';
CREATE INDEX idx_quality_flags_severity 
  ON quality_flags(severity) 
  WHERE status = 'active';
CREATE INDEX idx_disagreements_unresolved 
  ON source_disagreements(element_type, element_id) 
  WHERE resolution IS NULL;
CREATE INDEX idx_source_health_status 
  ON source_health(status);
```

---

# 8. Source Integration Code

## 8.1 Source Interface

```python
# integrations/base_source.py

from abc import ABC, abstractmethod

class DataSource(ABC):
    """
    Abstract base for all data sources.
    Every source implements the same interface.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Source name for logging and DB."""
        pass
    
    @abstractmethod
    async def fetch(self, paper_id: str) -> dict | None:
        """
        Fetch data about a paper from this source.
        Returns None if not found.
        """
        pass
    
    @abstractmethod
    async def search(self, query: str, 
                      limit: int = 20) -> list[dict]:
        """
        Search for papers matching a query.
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Quick check: is this source responding?
        """
        pass
```

## 8.2 Semantic Scholar Client

```python
# integrations/semantic_scholar.py

import httpx

class SemanticScholarSource(DataSource):
    name = "semantic_scholar"
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["x-api-key"] = api_key
    
    async def fetch(self, paper_id: str) -> dict | None:
        """
        Fetch paper details including citation intents.
        """
        fields = (
            "paperId,title,abstract,year,authors,"
            "citationCount,influentialCitationCount,"
            "citations.intent,citations.isInfluential,"
            "citations.paperId,citations.title,"
            "references.paperId,references.title,"
            "tldr,fieldsOfStudy,s2FieldsOfStudy,"
            "publicationVenue,openAccessPdf"
        )
        
        async with httpx.AsyncClient() as client:
            # Try DOI first, then S2 ID
            for id_type in ["DOI:", ""]:
                try:
                    resp = await client.get(
                        f"{self.BASE_URL}/paper/{id_type}{paper_id}",
                        params={"fields": fields},
                        headers=self.headers,
                        timeout=15
                    )
                    if resp.status_code == 200:
                        return resp.json()
                except Exception:
                    continue
        
        return None
    
    async def get_citation_intents(self, paper_id: str) -> list[dict]:
        """
        Get citation intents for a paper.
        S2 classifies citations as: 
        background, methodology, result comparison
        """
        data = await self.fetch(paper_id)
        if not data or "citations" not in data:
            return []
        
        intents = []
        for citation in data["citations"]:
            if citation.get("intent"):
                intents.append({
                    "citing_paper_id": citation["paperId"],
                    "citing_paper_title": citation.get("title"),
                    "intent": citation["intent"],
                    "is_influential": citation.get("isInfluential", False)
                })
        
        return intents
    
    async def health_check(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/paper/DOI:10.1038/nature12373",
                    params={"fields": "title"},
                    headers=self.headers,
                    timeout=5
                )
                return resp.status_code == 200
            except Exception:
                return False
```

## 8.3 Retraction Watch Client

```python
# integrations/retraction_watch.py

class RetractionWatchSource(DataSource):
    name = "retraction_watch"
    
    def __init__(self, db_path: str = None):
        """
        Retraction Watch database can be downloaded in bulk.
        We store it locally and check against it.
        """
        self.db_path = db_path
        self._cache = {}
    
    async def fetch(self, paper_id: str) -> dict | None:
        """
        Check if a paper has been retracted.
        """
        # Check local DB (bulk downloaded periodically)
        result = self._check_local_db(paper_id)
        
        if result:
            return {
                "is_retracted": result.get("retraction", False),
                "has_expression_of_concern": result.get("concern", False),
                "has_correction": result.get("correction", False),
                "retraction_date": result.get("date"),
                "reason": result.get("reason"),
                "original_paper_doi": result.get("doi"),
            }
        
        return {
            "is_retracted": False,
            "has_expression_of_concern": False,
            "has_correction": False,
        }
    
    async def bulk_update(self):
        """
        Download latest Retraction Watch database.
        Run weekly.
        """
        # Download from Retraction Watch bulk data
        # Parse and update local DB
        pass
```

---

# 9. Monitoring Additions

## 9.1 Source Health Monitor

```python
# monitoring/source_health.py

class SourceHealthMonitor:
    """
    Monitor health of all data sources.
    Runs every hour.
    """
    
    async def check_all_sources(self):
        sources = [
            OpenAlexSource(),
            SemanticScholarSource(),
            CrossRefSource(),
            RetractionWatchSource(),
            UnpaywallSource(),
        ]
        
        for source in sources:
            try:
                start = time.time()
                healthy = await source.health_check()
                latency = int((time.time() - start) * 1000)
                
                await self.update_health(
                    source_name=source.name,
                    status="healthy" if healthy else "degraded",
                    latency_ms=latency
                )
            except Exception as e:
                await self.update_health(
                    source_name=source.name,
                    status="down",
                    error=str(e)
                )
        
        # Check for cascading issues
        down_sources = await self.get_down_sources()
        if len(down_sources) >= 2:
            await self.alert(
                severity="high",
                message=f"Multiple sources down: "
                        f"{', '.join(down_sources)}. "
                        f"Graph quality may be degraded."
            )
    
    async def get_degradation_impact(self) -> dict:
        """
        When a source is down, what's the impact on graph quality?
        """
        down = await self.get_down_sources()
        
        impact = {
            "affected_features": [],
            "confidence_impact": "none",
            "user_message": None
        }
        
        if "retraction_watch" in down:
            impact["affected_features"].append("retraction_checking")
            impact["confidence_impact"] = "safety_degraded"
            impact["user_message"] = (
                "⚠️ Retraction checking temporarily unavailable. "
                "Paper quality flags may not be current."
            )
        
        if "semantic_scholar" in down:
            impact["affected_features"].append("citation_intent")
            impact["confidence_impact"] = "moderate"
        
        if "openalex" in down:
            impact["affected_features"].append("paper_ingestion")
            impact["confidence_impact"] = "severe"
            impact["user_message"] = (
                "ℹ️ Primary data source temporarily unavailable. "
                "Some information may be up to 24 hours old."
            )
        
        return impact
```

## 9.2 Updated Scheduled Tasks

| Task | Frequency | What it does |
|------|-----------|-------------|
| **Source Health Check** | Every hour | Verify all APIs responding, track latency |
| **Retraction Watch Sync** | Weekly | Download latest retraction database |
| **Citation Intent Enrichment** | Daily | Fetch S2 citation intents for new papers |
| **Confidence Recalculation** | Every 6 hours | Recalculate scores with latest evidence |
| **Flag Review** | Daily | Surface unresolved flags for review |
| **Disagreement Detection** | With each ingestion | Compare sources, log disagreements |
| **Source Coverage Report** | Weekly | How many elements have 2+ source validation |

---

# 10. Navigator Behavior Updates

## 10.1 System Prompt Addition

```
MULTI-SOURCE AWARENESS:

You have access to a knowledge graph that cross-validates 
information from multiple independent academic sources.

When discussing any claim, concept, or relationship:

1. If confidence > 0.85: state as fact.
2. If confidence 0.6-0.85: note it's "well-supported but 
   not fully validated."
3. If confidence < 0.6: note uncertainty explicitly.

ALWAYS surface these signals when present:
- ⚠️ Retraction: "[Paper] has been retracted. [Reason]."
- 💰 Funding concentration: "Research in [area] is 
  predominantly funded by [source]. Note potential bias."
- 🔍 Disputed relationship: "The connection between [A] 
  and [B] is ambiguous — [interpretation 1] vs [interpretation 2]."
- 🌍 Geographic bias: "This analysis is primarily based on 
  [language] publications."
- 📊 Source disagreement: "Sources disagree on [specific thing]. 
  [Source A] says [X], [Source B] says [Y]."

NEVER hide quality concerns to appear more confident.
Showing uncertainty IS the value — it's what makes Korczak 
different from ChatGPT.
```

## 10.2 דוגמה מלאה

**שאלה:** "מה המצב של מחקר ב-gut microbiome ואוטיזם?"

**תשובה (עם multi-source):**

"הקשר בין gut microbiome לאוטיזם הוא תחום פעיל עם כ-1,200 מאמרים (OpenAlex: 1,240, Semantic Scholar: 1,180). הנה מה שחשוב לדעת:

📈 **מגמה:** עלייה של 40% בפרסומים ב-3 שנים האחרונות. התחום חם.

⚠️ **אזהרה חשובה:** 2 מאמרים מצוטטים בתחום נסוגו (Retraction Watch), כולל [שם] עם 180 ציטוטים. 15 מאמרים עדיין מצטטים אותו ללא הערה.

🔍 **מחלוקת פעילה:** הקשר בין GI symptoms לאוטיזם שנוי במחלוקת. LLM analysis suggests BUILDS_ON relationship, אבל citation intent analysis מ-Semantic Scholar מראה ש-40% מהציטוטים הם 'disputes' — מה שמעיד על מחלוקת אמיתית, לא קונצנזוס.

💰 **מימון:** 55% NIH, 22% private foundations, 18% industry (3 חברות probiotics). המאמרים הממומנים ע"י industry מראים effect sizes גדולים יותר מהמאמרים העצמאיים — pattern שצריך להיות מודע לו.

🌍 **הערה:** הניתוח מבוסס בעיקר על פרסומים באנגלית. יש קבוצות פעילות בסין ודרום קוריאה שהפרסומים שלהן לא תמיד מכוסים.

Confidence כולל: 0.72 (moderate — active area with disputes and retractions)."

---

# 11. עלויות נוספות

| רכיב | עלות חודשית |
|------|-------------|
| Dual LLM analysis (batch) | +$100-150 |
| Semantic Scholar API | חינם (with key) |
| Retraction Watch DB | חינם (bulk download) |
| CrossRef API | חינם |
| Unpaywall API | חינם |
| ORCID API | חינם |
| OpenSyllabus (Phase 2) | ~$50-100/mo subscription |
| **סה"כ נוסף** | **~$100-250/mo** |

**סה"כ infrastructure מוערך (עם multi-source):** $500-1,050/חודש

---

# 12. שלבי הטמעה

```
MVP (שבועות 1-5):
  Sources: OpenAlex + Semantic Scholar + Retraction Watch
  Validation: Dual-LLM analysis
  Confidence: Basic weighted scoring
  Flags: RETRACTED, SINGLE_LLM_ONLY, TYPE_DISPUTED
  Disagreements: Logged, not yet surfaced

V1 (שבועות 6-10):
  + CrossRef, Unpaywall, ORCID
  + Funding analysis (OpenAlex grants)
  + Source health monitoring
  + Disagreement surfacing in Navigator
  + Flag lifecycle (resolve/dismiss)

V2 (שבועות 11-16):
  + OpenSyllabus (paid)
  + Altmetric
  + Geographic bias detection
  + Full disagreement dashboard
  + Expert review workflow

V3 (future):
  + Dimensions (grants → patents → trials)
  + PubMed/PMC (biomedical full text)
  + Scopus/WoS (better classification)
  + GPT as secondary LLM (true cross-model validation)
```

---

# 13. מה זה משנה ב-Moat

**ה-moat של קורצאק מתחזק משמעותית:**

**לפני multi-source:** גרף מבוסס OpenAlex + Claude analysis. כל אחד יכול לשחזר.

**אחרי multi-source:** גרף מבוסס 7+ מקורות, cross-validated, עם confidence scoring, retraction awareness, funding analysis, citation intent, ומערכת flags. **הcombination הזה לא קיים באף מוצר.** Elicit לא עושה cross-validation. Semantic Scholar לא עושה funding analysis. Connected Papers לא בודק retractions. קורצאק עושה את כולם ומשלב אותם ל-confidence score אחד.

**וזה מצטבר:** ככל שעובר זמן, ה-source_evidence table גדלה, disagreements מתועדים, flags נפתרים — והגרף הופך **אמין יותר מכל מקור בודד שהוא מבוסס עליו.** זו תכונה שאי אפשר להעתיק ביום אחד.
