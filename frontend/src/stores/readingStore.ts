import { create } from "zustand";

export interface Section {
  section: string;
  text: string;
  offset: number;
  concepts: { id: string; name: string }[];
}

export interface ReadingSession {
  id: string;
  paper_id: string;
  started_at: string;
  total_seconds: number;
}

interface ReadingState {
  activeSession: ReadingSession | null;
  currentPaperId: string | null;
  currentPaperTitle: string | null;
  sectionMap: Section[];
  readingTime: number;
  isReadingMode: boolean;
  isLoading: boolean;

  // Actions
  setActiveSession: (session: ReadingSession | null) => void;
  setCurrentPaper: (id: string | null, title?: string | null) => void;
  setSectionMap: (sections: Section[]) => void;
  setReadingTime: (time: number) => void;
  incrementReadingTime: () => void;
  setReadingMode: (mode: boolean) => void;
  setLoading: (loading: boolean) => void;
}

export const useReadingStore = create<ReadingState>((set) => ({
  activeSession: null,
  currentPaperId: null,
  currentPaperTitle: null,
  sectionMap: [],
  readingTime: 0,
  isReadingMode: false,
  isLoading: false,

  setActiveSession: (session) => set({ activeSession: session }),
  setCurrentPaper: (id, title) => set({ currentPaperId: id, currentPaperTitle: title || null }),
  setSectionMap: (sections) => set({ sectionMap: sections }),
  setReadingTime: (time) => set({ readingTime: time }),
  incrementReadingTime: () => set((state) => ({ readingTime: state.readingTime + 1 })),
  setReadingMode: (mode) => set({ isReadingMode: mode }),
  setLoading: (loading) => set({ isLoading: loading }),
}));
