"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Compass, Map, TreePine, Clock, BookOpen, GraduationCap,
  Navigation, Radio, Languages, MessageSquare, Search,
  ChevronRight, ChevronLeft, X, Sparkles,
} from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";

interface GuidedTourProps {
  onComplete: () => void;
}

interface TourStep {
  icon: React.ReactNode;
  title: { en: string; he: string };
  subtitle: { en: string; he: string };
  body: { en: string; he: string };
  tips?: { en: string[]; he: string[] };
  color: string;
}

const STEPS: TourStep[] = [
  {
    icon: <Compass size={32} />,
    title: { en: "Welcome to Korczak", he: "ברוכים הבאים לקורצ'אק" },
    subtitle: { en: "AI Knowledge Navigator", he: "נווט ידע מבוסס בינה מלאכותית" },
    body: {
      en: "Korczak is a learning platform that helps you explore academic knowledge in a deep, connected way. Unlike a search engine, Korczak understands how concepts, theories, and research papers relate to each other — and guides you through that web of knowledge.",
      he: "קורצ'אק הוא פלטפורמת למידה שעוזרת לך לחקור ידע אקדמי בצורה עמוקה ומחוברת. בניגוד למנוע חיפוש, קורצ'אק מבין איך מושגים, תאוריות ומאמרי מחקר מתחברים זה לזה — ומנחה אותך דרך רשת הידע הזו.",
    },
    tips: {
      en: [
        "The knowledge graph currently covers Anthropology and Sleep & Cognition research",
        "Over 300 papers, 1,600 concepts, and 900 claims are mapped",
      ],
      he: [
        "גרף הידע מכסה כרגע מחקר באנתרופולוגיה ושינה וקוגניציה",
        "למעלה מ-300 מאמרים, 1,600 מושגים ו-900 טענות ממופים",
      ],
    },
    color: "#E8B931",
  },
  {
    icon: <MessageSquare size={32} />,
    title: { en: "The Chat — Your Guide", he: "הצ'אט — המדריך שלך" },
    subtitle: { en: "Ask anything, explore everything", he: "שאל הכל, חקור הכל" },
    body: {
      en: "The center of the screen is your conversation with Korczak. Ask about any topic — \"What are the main debates in anthropology?\" or \"How does participant observation work?\" — and Korczak will answer using real academic knowledge from the graph, citing papers and highlighting key concepts.",
      he: "מרכז המסך הוא השיחה שלך עם קורצ'אק. שאל על כל נושא — \"מה הוויכוחים המרכזיים באנתרופולוגיה?\" או \"איך עובדת תצפית משתתפת?\" — וקורצ'אק יענה תוך שימוש בידע אקדמי אמיתי מהגרף, עם ציטוט מאמרים והדגשת מושגים מרכזיים.",
    },
    tips: {
      en: [
        "Gold badges in responses are clickable concepts — click them to explore deeper",
        "Insights are highlighted in special callout boxes",
      ],
      he: [
        "תגים זהובים בתשובות הם מושגים לחיצים — לחץ עליהם כדי לחקור עמוק יותר",
        "תובנות מודגשות בתיבות מיוחדות",
      ],
    },
    color: "#58A6FF",
  },
  {
    icon: <div className="flex gap-1"><Radio size={18} /><Navigation size={18} /><GraduationCap size={18} /></div>,
    title: { en: "Three Modes of Learning", he: "שלושה מצבי למידה" },
    subtitle: { en: "Auto · Navigator · Tutor", he: "אוטומטי · ניווט · מדריך" },
    body: {
      en: "Korczak adapts to how you want to learn. In Auto mode, it detects your intent. Navigator mode gives you broad, connected overviews of a topic. Tutor mode uses the Socratic method — asking you questions to deepen your understanding, adjusting difficulty to your level.",
      he: "קורצ'אק מתאים את עצמו לדרך שבה אתה רוצה ללמוד. במצב אוטומטי, הוא מזהה את הכוונה שלך. מצב ניווט נותן לך סקירות רחבות ומחוברות של נושא. מצב מדריך משתמש בשיטה הסוקרטית — שואל אותך שאלות כדי להעמיק את ההבנה, ומתאים את הרמה אליך.",
    },
    tips: {
      en: [
        "The mode selector is in the top-right of the header (Auto/Navigator/Tutor)",
        "Tutor mode has 4 levels — from direct answers to full Socratic dialogue",
      ],
      he: [
        "בורר המצב נמצא בפינה הימנית-עליונה של הכותרת",
        "למצב מדריך יש 4 רמות — מתשובות ישירות ועד דיאלוג סוקרטי מלא",
      ],
    },
    color: "#3FB950",
  },
  {
    icon: <Map size={32} />,
    title: { en: "Knowledge Map", he: "מפת הידע" },
    subtitle: { en: "See the big picture", he: "ראה את התמונה הגדולה" },
    body: {
      en: "The Knowledge Map is an interactive visualization of the entire knowledge graph. Each dot is a concept — theories, methods, frameworks, phenomena. Colors indicate type, size indicates confidence. Click any dot to read its full definition, key research papers, academic claims, and connections to other concepts. Use the search bar to find specific concepts, and zoom in to explore clusters.",
      he: "מפת הידע היא הדמיה אינטראקטיבית של כל גרף הידע. כל נקודה היא מושג — תאוריות, שיטות, מסגרות, תופעות. צבעים מציינים סוג, גודל מציין ביטחון. לחץ על כל נקודה כדי לקרוא את ההגדרה המלאה, מאמרי מחקר מרכזיים, טענות אקדמיות וחיבורים למושגים אחרים. השתמש בחיפוש כדי למצוא מושגים, והתקרב כדי לחקור אשכולות.",
    },
    tips: {
      en: [
        "Click the 'Knowledge Map' button in the header to open",
        "Navigate between concepts by clicking connections — breadcrumbs track your path",
        "Use A-/A+ buttons to adjust text size for comfortable reading",
      ],
      he: [
        "לחץ על כפתור 'מפת ידע' בכותרת כדי לפתוח",
        "נווט בין מושגים על ידי לחיצה על חיבורים — פירורי לחם עוקבים אחרי המסלול",
        "השתמש בכפתורי A-/A+ כדי להתאים את גודל הטקסט לקריאה נוחה",
      ],
    },
    color: "#E8B931",
  },
  {
    icon: <Clock size={32} />,
    title: { en: "Timeline", he: "ציר הזמן" },
    subtitle: { en: "How knowledge evolves", he: "איך ידע מתפתח" },
    body: {
      en: "The Timeline shows how research has progressed over the decades. See when papers were published, which fields grew fastest, and what milestones changed the landscape. Switch between fields (theory, method, framework, etc.) to compare how different types of knowledge evolved differently. Hover over data points to see the top papers from that year.",
      he: "ציר הזמן מראה כיצד המחקר התקדם לאורך העשורים. ראה מתי מאמרים פורסמו, אילו תחומים צמחו מהר, ואילו אבני דרך שינו את הנוף. עבור בין תחומים (תאוריה, שיטה, מסגרת וכו') כדי להשוות כיצד סוגי ידע שונים התפתחו אחרת. רחף מעל נקודות נתונים כדי לראות את המאמרים המובילים מאותה שנה.",
    },
    tips: {
      en: [
        "Use the field tabs to filter by concept type",
        "Zoom in/out on the chart to focus on specific periods",
        "Play button animates through the years",
      ],
      he: [
        "השתמש בלשוניות התחומים כדי לסנן לפי סוג מושג",
        "התקרב/התרחק בגרף כדי להתמקד בתקופות ספציפיות",
        "כפתור הפעלה מנפיש את השנים",
      ],
    },
    color: "#D29922",
  },
  {
    icon: <BookOpen size={32} />,
    title: { en: "Paper Library", he: "ספריית מאמרים" },
    subtitle: { en: "Build your collection", he: "בנה את האוסף שלך" },
    body: {
      en: "Save papers you discover to your personal library. Organize them into reading lists, add notes, and track your progress (unread → reading → completed). Korczak also recommends papers based on your interests — analyzing which concepts you explore most and suggesting related research you haven't seen yet.",
      he: "שמור מאמרים שאתה מגלה לספרייה האישית שלך. ארגן אותם ברשימות קריאה, הוסף הערות, ועקוב אחרי ההתקדמות שלך. קורצ'אק גם ממליץ על מאמרים על סמך תחומי העניין שלך — מנתח אילו מושגים אתה חוקר ומציע מחקרים קשורים שעדיין לא ראית.",
    },
    color: "#58A6FF",
  },
  {
    icon: <TreePine size={32} />,
    title: { en: "Knowledge Tree", he: "עץ הידע" },
    subtitle: { en: "Your personal learning path", he: "מסלול הלמידה האישי שלך" },
    body: {
      en: "The Knowledge Tree visualizes your personal learning journey as a growing tree. As you explore concepts, branches grow. At fork points, you choose which direction to go deeper — specialization or breadth. Completed branches glow green, in-progress glows gold, and unexplored areas remain in fog. It's your map of what you know and what's left to discover.",
      he: "עץ הידע מדמיין את מסע הלמידה האישי שלך כעץ צומח. ככל שאתה חוקר מושגים, ענפים צומחים. בנקודות הסתעפות, אתה בוחר לאיזה כיוון להתעמק — התמחות או רוחב. ענפים שהושלמו זוהרים בירוק, בתהליך בזהב, ואזורים לא חקורים נשארים בערפל. זו המפה שלך של מה שאתה יודע ומה נותר לגלות.",
    },
    color: "#3FB950",
  },
  {
    icon: <Languages size={32} />,
    title: { en: "Bilingual — EN/HE", he: "דו-לשוני — EN/HE" },
    subtitle: { en: "Switch anytime", he: "עבור בכל רגע" },
    body: {
      en: "The entire interface works in both English and Hebrew. Click the language toggle (HE/EN) in the top-right to switch. The chat also responds in your chosen language, while keeping technical academic terms in their original form for accuracy.",
      he: "כל הממשק עובד גם בעברית וגם באנגלית. לחץ על כפתור השפה (HE/EN) בפינה הימנית-עליונה כדי להחליף. הצ'אט גם מגיב בשפה שבחרת, תוך שמירה על מונחים אקדמיים טכניים בצורתם המקורית לדיוק.",
    },
    color: "#A371F7",
  },
  {
    icon: <Sparkles size={32} />,
    title: { en: "Start Exploring", he: "התחל לחקור" },
    subtitle: { en: "See what you don't see", he: "ראה מה שאתה לא רואה" },
    body: {
      en: "You're ready to go. Try asking a question in the chat, open the Knowledge Map to see the big picture, or browse topics in the left sidebar. Every concept you click, every question you ask, builds your understanding of how knowledge connects. That's what Korczak is about — seeing what you don't see.",
      he: "אתה מוכן. נסה לשאול שאלה בצ'אט, פתח את מפת הידע כדי לראות את התמונה הגדולה, או עיין בנושאים בסרגל הצד השמאלי. כל מושג שאתה לוחץ, כל שאלה שאתה שואל, בונה את ההבנה שלך איך ידע מתחבר. זה מה שקורצ'אק עושה — מראה לך מה שאתה לא רואה.",
    },
    color: "#E8B931",
  },
];

export default function GuidedTour({ onComplete }: GuidedTourProps) {
  const [step, setStep] = useState(0);
  const { locale } = useLocaleStore();
  const lang = locale === "he" ? "he" : "en";
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const isFirst = step === 0;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
          className="w-full max-w-2xl mx-4 bg-surface border border-border rounded-2xl shadow-2xl overflow-hidden"
          dir={locale === "he" ? "rtl" : "ltr"}
        >
          {/* Progress bar */}
          <div className="h-1 bg-surface-sunken">
            <div
              className="h-full transition-all duration-500 rounded-full"
              style={{
                width: `${((step + 1) / STEPS.length) * 100}%`,
                backgroundColor: current.color,
              }}
            />
          </div>

          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-5 pb-2">
            <span className="text-xs text-text-tertiary font-mono">
              {step + 1} / {STEPS.length}
            </span>
            <button
              onClick={onComplete}
              className="p-1 rounded hover:bg-surface-hover text-text-tertiary hover:text-text-secondary transition-colors"
              title={locale === "he" ? "דלג" : "Skip tour"}
            >
              <X size={16} />
            </button>
          </div>

          {/* Content */}
          <div className="px-8 pb-2">
            {/* Icon */}
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
              style={{ backgroundColor: `${current.color}20`, color: current.color }}
            >
              {current.icon}
            </div>

            <h2 className="text-2xl font-bold text-foreground mb-1">
              {current.title[lang]}
            </h2>
            <p className="text-sm font-medium mb-4" style={{ color: current.color }}>
              {current.subtitle[lang]}
            </p>

            <p className="text-[15px] text-text-secondary leading-relaxed mb-4">
              {current.body[lang]}
            </p>

            {current.tips && (
              <div className="bg-background/50 rounded-lg px-4 py-3 mb-2 space-y-1.5">
                {current.tips[lang].map((tip, i) => (
                  <p key={i} className="text-sm text-text-tertiary leading-relaxed">
                    💡 {tip}
                  </p>
                ))}
              </div>
            )}
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between px-8 py-5 border-t border-border/50">
            <button
              onClick={() => setStep(Math.max(0, step - 1))}
              disabled={isFirst}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isFirst
                  ? "text-text-tertiary cursor-default"
                  : "text-text-secondary hover:bg-surface-hover hover:text-foreground"
              }`}
            >
              <ChevronLeft size={16} />
              {locale === "he" ? "הקודם" : "Back"}
            </button>

            <button
              onClick={() => isLast ? onComplete() : setStep(step + 1)}
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
              style={{
                backgroundColor: `${current.color}20`,
                color: current.color,
              }}
            >
              {isLast
                ? (locale === "he" ? "בוא נתחיל!" : "Let's go!")
                : (locale === "he" ? "הבא" : "Next")}
              {!isLast && <ChevronRight size={16} />}
            </button>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
