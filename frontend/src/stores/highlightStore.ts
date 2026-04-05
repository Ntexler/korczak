import { create } from "zustand";

export interface Highlight {
  id: string;
  user_id: string;
  source_type: string;
  source_id: string;
  highlighted_text: string;
  start_offset: number | null;
  end_offset: number | null;
  annotation: string | null;
  color: string;
  concept_ids: string[];
  is_public: boolean;
  created_at: string;
}

export interface LearningPath {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  is_public: boolean;
  domain: string | null;
  items?: LearningPathItem[];
}

export interface LearningPathItem {
  id: string;
  item_type: "highlight" | "concept" | "paper";
  item_id: string;
  position: number;
  annotation: string | null;
}

interface HighlightState {
  highlights: Highlight[];
  learningPaths: LearningPath[];
  isHighlightMode: boolean;
  selectedColor: string;
  isLoading: boolean;

  // Actions
  setHighlights: (highlights: Highlight[]) => void;
  addHighlight: (highlight: Highlight) => void;
  removeHighlight: (id: string) => void;
  setLearningPaths: (paths: LearningPath[]) => void;
  setHighlightMode: (mode: boolean) => void;
  setSelectedColor: (color: string) => void;
  setLoading: (loading: boolean) => void;
}

export const useHighlightStore = create<HighlightState>((set) => ({
  highlights: [],
  learningPaths: [],
  isHighlightMode: false,
  selectedColor: "#E8B931",
  isLoading: false,

  setHighlights: (highlights) => set({ highlights }),
  addHighlight: (highlight) =>
    set((state) => ({ highlights: [highlight, ...state.highlights] })),
  removeHighlight: (id) =>
    set((state) => ({ highlights: state.highlights.filter((h) => h.id !== id) })),
  setLearningPaths: (paths) => set({ learningPaths: paths }),
  setHighlightMode: (mode) => set({ isHighlightMode: mode }),
  setSelectedColor: (color) => set({ selectedColor: color }),
  setLoading: (loading) => set({ isLoading: loading }),
}));
