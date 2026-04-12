"""Pydantic models for the syllabus scoring and course generation engine."""

from enum import Enum
from pydantic import BaseModel, Field


class ReadingTier(str, Enum):
    CANONICAL = "canonical"           # >60% frequency, 3+ institutions
    IMPORTANT = "important"           # 30-60% frequency
    SPECIALIZED = "specialized"       # 10-30% frequency
    NICHE = "niche"                   # <10% frequency
    AI_RECOMMENDED = "ai_recommended" # Low frequency but graph-important


class CourseLevel(str, Enum):
    INTRO = "intro"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    GRADUATE = "graduate"


class ReadingScore(BaseModel):
    """Scored reading from cross-syllabus analysis."""
    paper_id: str | None = None
    reading_title: str
    department: str
    frequency_score: float = 0.0        # % of syllabi that include it
    institution_diversity: float = 0.0  # unique institutions normalized
    position_score: float = 0.0         # avg week position (lower = foundational)
    citation_weight: float = 0.0        # log(citations) normalized
    teaching_score: float = 0.0         # Open Syllabus score if available
    user_adjustment: float = 0.0        # capped at ±0.15
    combined_score: float = 0.0
    tier: ReadingTier = ReadingTier.NICHE
    source_count: int = 0
    source_institutions: list[str] = Field(default_factory=list)
    authors: str = ""
    publication_year: int | None = None


class CuratedReading(BaseModel):
    """AI-recommended reading that's underrepresented in syllabi but important."""
    paper_id: str
    title: str
    importance_score: float  # 0-1
    rationale: str
    suggested_week: int = 1
    concept_connections: int = 0
    is_bridge_paper: bool = False
    controversy_score: float = 0.0


class DepartmentAnalysis(BaseModel):
    """Summary analysis of a department's syllabus landscape."""
    department: str
    total_syllabi: int = 0
    source_breakdown: dict[str, int] = Field(default_factory=dict)  # source → count
    canonical_count: int = 0
    important_count: int = 0
    specialized_count: int = 0
    niche_count: int = 0
    ai_recommended_count: int = 0
    concept_coverage: float = 0.0  # % of graph concepts covered by syllabi
    gap_concepts: list[str] = Field(default_factory=list)  # concepts with no syllabus coverage
    top_readings: list[ReadingScore] = Field(default_factory=list)


class GeneratedWeek(BaseModel):
    """One week in a generated course."""
    week_number: int
    title: str
    learning_objectives: list[str] = Field(default_factory=list)
    required_readings: list[dict] = Field(default_factory=list)
    recommended_readings: list[dict] = Field(default_factory=list)
    hidden_gem: dict | None = None  # AI-recommended reading with rationale


class GeneratedCourse(BaseModel):
    """A complete AI-generated course based on cross-syllabus analysis."""
    title: str
    department: str
    level: CourseLevel
    description: str = ""
    methodology: str = ""  # how the course was generated
    weeks: list[GeneratedWeek] = Field(default_factory=list)
    source_syllabi_count: int = 0
    reading_count: int = 0
    ai_recommendations_count: int = 0
    institutions_analyzed: list[str] = Field(default_factory=list)


class FeedbackVote(BaseModel):
    """User vote on a course reading."""
    user_id: str
    course_reading_id: str
    vote_type: str  # upvote | downvote


# --- Abuse protection constants ---
MAX_VOTES_PER_USER_PER_DAY = 10
MAX_VOTES_PER_USER_PER_COURSE = 3
USER_ADJUSTMENT_CAP = 0.15
CANONICAL_SCORE_FLOOR = 0.5
ANOMALY_DOWNVOTE_THRESHOLD = 10  # per hour
ANOMALY_DOWNVOTE_RATIO = 0.8     # >80% downvotes in a course = suspicious
