export type Locale = "en" | "he";

export const fonts = {
  en: {
    sans: "var(--font-geist-sans), system-ui, sans-serif",
    display: "var(--font-geist-sans), system-ui, sans-serif",
  },
  he: {
    sans: "var(--font-assistant), 'Assistant', 'Segoe UI', sans-serif",
    display: "var(--font-assistant), 'Assistant', 'Segoe UI', sans-serif",
  },
} as const;

export const translations = {
  en: {
    // Header
    appName: "Korczak",
    subtitle: "Knowledge Navigator",

    // Welcome
    welcomeTitle: "Welcome to",
    tagline: "See what you don't see",
    statsLabel: { papers: "papers", concepts: "concepts", connections: "connections" },

    // Suggested prompts
    prompts: [
      "What are the main debates in anthropology?",
      "How does participant observation work?",
      "What connects sleep research to cognitive anthropology?",
      "Show me the most influential papers on decolonization",
    ],

    // Sidebar
    explore: "Explore",
    knowledgeGraph: "Knowledge Graph",
    recentConcepts: "Recent Concepts",
    exploreTopics: "Explore Topics",
    searchConcepts: "Search concepts...",
    searching: "Searching...",

    // Chat
    inputPlaceholder: "Explore a concept, ask a question...",
    navigating: "Navigating...",
    tellMeMore: "Tell me more",
    whatsControversial: "What's controversial?",
    showRelated: "Show related concepts",

    // Concept panel
    conceptDetail: "Concept Detail",
    noConceptSelected: "No concept selected",
    clickBadgeHint: "Click any gold concept badge in the chat to explore it here",
    loadingConcept: "Loading concept...",
    connectedConcepts: "Connected Concepts",
    conceptNotFound: "Concept not found",
    wellEstablished: "Well-established",
    likelyAccurate: "Likely accurate",
    needsMoreEvidence: "Needs more evidence",
    emerging: "Emerging concept",
    referencedIn: "Referenced in",
    papers: "papers",

    // Insight types
    blindSpot: "Blind Spot",
    connection: "Connection",
    insight: "Insight",

    // Modes
    navigator: "navigator",
    tutor: "tutor",
    briefing: "briefing",
    auto: "auto",
    modeAuto: "Auto-detect mode",

    // Health
    systemHealth: "System Health",
    healthy: "Healthy",
    degraded: "Degraded",
    graphHealth: "Graph",
    apisHealth: "APIs",
    costEstimate: "Est. Cost",

    // Features
    discoveries: "Discoveries",
    risingStars: "Rising Stars",
    researchGaps: "Research Gaps",
    controversies: "Controversies",
    trendingConcepts: "Trending Concepts",
    risingPapers: "Rising Papers",
    orphanConcepts: "Orphan Concepts",
    missingConnections: "Missing Connections",
    knowledgeMap: "Knowledge Map",
    viewGraph: "View Graph",
    noData: "No data available",
    recentPapers: "recent papers",
    citations: "citations",
    gapsFound: "gaps found",

    // Error
    errorMessage: "I apologize — something went wrong connecting to the knowledge graph. Please try again.",
  },
  he: {
    // Header
    appName: "קורצ'אק",
    subtitle: "נווט ידע",

    // Welcome
    welcomeTitle: "ברוכים הבאים ל",
    tagline: "תראה מה שאתה לא רואה",
    statsLabel: { papers: "מאמרים", concepts: "מושגים", connections: "קשרים" },

    // Suggested prompts
    prompts: [
      "מה הוויכוחים המרכזיים באנתרופולוגיה?",
      "איך עובדת תצפית משתתפת?",
      "מה מחבר בין מחקר שינה לאנתרופולוגיה קוגניטיבית?",
      "הראה לי את המאמרים המשפיעים ביותר על דה-קולוניזציה",
    ],

    // Sidebar
    explore: "חקירה",
    knowledgeGraph: "גרף ידע",
    recentConcepts: "מושגים אחרונים",
    exploreTopics: "חקור נושאים",
    searchConcepts: "חפש מושגים...",
    searching: "מחפש...",

    // Chat
    inputPlaceholder: "חקור מושג, שאל שאלה...",
    navigating: "מנווט...",
    tellMeMore: "ספר לי עוד",
    whatsControversial: "מה שנוי במחלוקת?",
    showRelated: "הצג מושגים קשורים",

    // Concept panel
    conceptDetail: "פרטי מושג",
    noConceptSelected: "לא נבחר מושג",
    clickBadgeHint: "לחץ על תג מושג זהוב בצ'אט כדי לחקור אותו כאן",
    loadingConcept: "טוען מושג...",
    connectedConcepts: "מושגים מחוברים",
    conceptNotFound: "המושג לא נמצא",
    wellEstablished: "מבוסס היטב",
    likelyAccurate: "כנראה מדויק",
    needsMoreEvidence: "דרוש יותר ביסוס",
    emerging: "מושג מתפתח",
    referencedIn: "מוזכר ב",
    papers: "מאמרים",

    // Insight types
    blindSpot: "נקודה עיוורת",
    connection: "חיבור",
    insight: "תובנה",

    // Modes
    navigator: "ניווט",
    tutor: "מדריך",
    briefing: "תדרוך",
    auto: "אוטומטי",
    modeAuto: "זיהוי מצב אוטומטי",

    // Health
    systemHealth: "תקינות המערכת",
    healthy: "תקין",
    degraded: "לקוי",
    graphHealth: "גרף",
    apisHealth: "ממשקים",
    costEstimate: "עלות משוערת",

    // Features
    discoveries: "תגליות",
    risingStars: "כוכבים עולים",
    researchGaps: "פערי מחקר",
    controversies: "מחלוקות",
    trendingConcepts: "מושגים מגמתיים",
    risingPapers: "מאמרים עולים",
    orphanConcepts: "מושגים יתומים",
    missingConnections: "קשרים חסרים",
    knowledgeMap: "מפת ידע",
    viewGraph: "צפה בגרף",
    noData: "אין נתונים",
    recentPapers: "מאמרים אחרונים",
    citations: "ציטוטים",
    gapsFound: "פערים נמצאו",

    // Error
    errorMessage: "מצטער — משהו השתבש בחיבור לגרף הידע. נסה שוב.",
  },
} as const;

export type Translations = typeof translations.en;
