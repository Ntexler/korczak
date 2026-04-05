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

    // Library
    library: "Library",
    myPapers: "My Papers",
    savePaper: "Save to Library",
    removeFromLibrary: "Remove from Library",
    readingLists: "Reading Lists",
    searchLibrary: "Search your library...",
    emptyLibrary: "Your library is empty. Save papers to start building your collection.",
    emptyList: "No papers in this list yet",
    noLists: "No reading lists yet",
    listName: "List name...",
    create: "Create",
    addToList: "Add to list",
    addNotes: "Add notes...",
    notes: "Notes",
    suggestedForYou: "Korczak Suggests",
    recommendations: "Recommendations",
    all: "All",
    unread: "Unread",
    reading: "Reading",
    completed: "Completed",
    archived: "Archived",

    // Highlights & Reading
    highlights: "Highlights",
    recentHighlights: "Recent Highlights",
    annotate: "Add annotation...",
    highlightMode: "Highlight Mode",
    learningPaths: "Learning Paths",
    pathName: "Path name...",
    noPaths: "No learning paths yet",
    emptyPath: "No items in this path",
    readingMode: "Reading Mode",
    sections: "Sections",
    jumpToSection: "Jump to section",
    timeSpent: "Time spent",
    noSections: "No sections available for this paper",

    // Syllabus
    syllabi: "Syllabi",
    searchSyllabi: "Search syllabi...",
    forkSyllabus: "Fork Syllabus",
    customSyllabus: "Custom Syllabus",
    whereAmI: "Where Am I",
    pillars: "Pillars",
    niche: "Niche",
    week: "Week",
    back: "Back",
    active: "Active",
    noSyllabi: "No syllabi yet",
    addTopic: "Add Topic",
    importSyllabus: "Import Syllabus",

    // Community
    comments: "Comments",
    addComment: "Add a comment...",
    reply: "Reply",
    upvote: "Upvote",
    downvote: "Downvote",
    flag: "Flag",
    noComments: "No comments yet. Be the first!",
    sharedHighlights: "Community Highlights",

    // Knowledge Tree
    knowledgeTree: "Knowledge Tree",
    yourTree: "Your Tree",
    choosePath: "Choose Your Path",
    branchPoint: "Branch Point",
    foundations: "Foundations",
    specialization: "Specialization",
    treeProgress: "Tree Progress",
    branchesExplored: "Branches Explored",
    depthReached: "Depth",
    unlockNext: "Unlock Next",
    fogOfWar: "Unexplored Territory",
    growthAnim: "Your tree grew!",
    exploreBoth: "Explore both paths",
    buildingTree: "Growing your knowledge tree...",
    chosen: "Chosen",
    concepts: "concepts",
    locked: "Locked",
    available: "Available",
    in_progress: "In Progress",

    // Rich Knowledge Map
    keyPapers: "Key Papers",
    keyClaims: "Key Claims",
    exploreInDepth: "Explore in depth",
    source: "Source",
    whyConnected: "Why connected",

    // Social / Academic Network
    communitySummaries: "Community Summaries",
    writeSummary: "Write summary",
    discussions: "Discussions",
    startDiscussion: "Start discussion",
    publish: "Publish",
    post: "Post",
    noSummariesYet: "No summaries yet. Be the first!",
    noDiscussionsYet: "No discussions yet.",
    summaryTitle: "Summary title...",
    writeInterpretation: "Write your interpretation...",
    discussionTitle: "Discussion title (optional)...",
    whatsYourTake: "What's your take?",
    follow: "Follow",
    unfollow: "Unfollow",
    followers: "Followers",
    reputation: "Reputation",

    // Translation
    translate: "Translate",
    translated: "Translated",
    showOriginal: "Show original",
    hideOriginal: "Hide original",
    flagTranslation: "Flag poor translation",
    flagged: "Flagged",

    // Connection Feedback
    agreeConnection: "Agree",
    disagreeConnection: "Disagree",
    thanksFeedback: "Thanks for your feedback",
    whyWrong: "Why is this wrong?",
    proposeConnection: "Propose Connection",
    proposalSubmitted: "Proposal submitted",

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

    // Library
    library: "ספרייה",
    myPapers: "המאמרים שלי",
    savePaper: "שמור בספרייה",
    removeFromLibrary: "הסר מהספרי��ה",
    readingLists: "רשימות קריאה",
    searchLibrary: "חפש בספרייה...",
    emptyLibrary: "הספרייה ריקה. שמור מאמרים כדי להתחיל לבנות את האוסף ש��ך.",
    emptyList: "אין עדיין מאמרים ברשימה",
    noLists: "אין עדיין רשימות קריאה",
    listName: "שם הרשימה...",
    create: "צור",
    addToList: "הוסף לרשימה",
    addNotes: "הוסף הערות...",
    notes: "הערות",
    suggestedForYou: "קורצ'אק מציע",
    recommendations: "המלצות",
    all: "הכל",
    unread: "לא נקרא",
    reading: "בקריאה",
    completed: "הושלם",
    archived: "בארכיון",

    // Highlights & Reading
    highlights: "הדגשות",
    recentHighlights: "הדגשות אחרונות",
    annotate: "הוסף הערה...",
    highlightMode: "מצב הדגשה",
    learningPaths: "מסלולי למידה",
    pathName: "שם המסלול...",
    noPaths: "אין עדיין מסלולי למידה",
    emptyPath: "אין פריטים במסלול",
    readingMode: "מצב קריאה",
    sections: "סעיפים",
    jumpToSection: "קפוץ לסעיף",
    timeSpent: "זמן שהושקע",
    noSections: "אין סעיפים זמינים למאמר זה",

    // Syllabus
    syllabi: "סילבוסים",
    searchSyllabi: "חפש סילבוסים...",
    forkSyllabus: "שכפל סילבוס",
    customSyllabus: "סילבוס מותאם",
    whereAmI: "איפה אני",
    pillars: "עמודי תווך",
    niche: "נישה",
    week: "שבוע",
    back: "חזרה",
    active: "פעיל",
    noSyllabi: "אין עדיין סילבוסים",
    addTopic: "הוסף נושא",
    importSyllabus: "ייבא סילבוס",

    // Community
    comments: "תגובות",
    addComment: "הוסף תגובה...",
    reply: "השב",
    upvote: "אהבתי",
    downvote: "לא אהבתי",
    flag: "דגל",
    noComments: "אין תגובות עדיין. היה הראשון!",
    sharedHighlights: "הדגשות קהילתיות",

    // Knowledge Tree
    knowledgeTree: "עץ הידע",
    yourTree: "העץ שלך",
    choosePath: "בחר מסלול",
    branchPoint: "נקודת הסתעפות",
    foundations: "יסודות",
    specialization: "התמחות",
    treeProgress: "התקדמות בעץ",
    branchesExplored: "ענפים שנחקרו",
    depthReached: "עומק",
    unlockNext: "שחרר הבא",
    fogOfWar: "טריטוריה לא ידועה",
    growthAnim: "העץ שלך גדל!",
    exploreBoth: "חקור את שני המסלולים",
    buildingTree: "מגדל את עץ הידע שלך...",
    chosen: "נבחר",
    concepts: "מושגים",
    locked: "נעול",
    available: "זמין",
    in_progress: "בתהליך",

    // Rich Knowledge Map
    keyPapers: "מאמרים מרכזיים",
    keyClaims: "טענות מרכזיות",
    exploreInDepth: "חקור לעומק",
    source: "מקור",
    whyConnected: "למה מחוברים",

    // Social / Academic Network
    communitySummaries: "סיכומים קהילתיים",
    writeSummary: "כתוב סיכום",
    discussions: "דיונים",
    startDiscussion: "התחל דיון",
    publish: "פרסם",
    post: "פרסם",
    noSummariesYet: "אין עדיין סיכומים. היה הראשון!",
    noDiscussionsYet: "אין דיונים עדיין.",
    summaryTitle: "כותרת הסיכום...",
    writeInterpretation: "כתוב את הפרשנות שלך...",
    discussionTitle: "כותרת הדיון (אופציונלי)...",
    whatsYourTake: "מה דעתך?",
    follow: "עקוב",
    unfollow: "הפסק לעקוב",
    followers: "עוקבים",
    reputation: "מוניטין",

    // Translation
    translate: "תרגם",
    translated: "תורגם",
    showOriginal: "הצג מקור",
    hideOriginal: "הסתר מקור",
    flagTranslation: "דווח על תרגום לקוי",
    flagged: "דווח",

    // Connection Feedback
    agreeConnection: "מסכים",
    disagreeConnection: "לא מסכים",
    thanksFeedback: "תודה על המשוב",
    whyWrong: "למה לא נכון?",
    proposeConnection: "הצע חיבור",
    proposalSubmitted: "ההצעה נשלחה",

    // Error
    errorMessage: "מצטער — משהו השתבש בחיבור לגרף הידע. נסה שוב.",
  },
} as const;

export type Translations = typeof translations.en;
