import { create } from "zustand";

export interface SavedPaper {
  id: string;
  paper_id: string;
  user_id: string;
  status: "unread" | "reading" | "completed" | "archived";
  notes: string | null;
  rating: number | null;
  tags: string[];
  save_context: string;
  title: string;
  authors: any[];
  publication_year: number;
  cited_by_count: number;
  abstract: string | null;
  doi: string | null;
  created_at: string;
}

export interface ReadingList {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  is_public: boolean;
  color: string;
  source_type: string;
  papers?: SavedPaper[];
  reading_list_papers?: { count: number }[];
}

export interface Recommendation {
  id: string;
  title: string;
  authors: any[];
  publication_year: number;
  cited_by_count: number;
  abstract: string | null;
  reason: string;
  score: number;
}

interface LibraryState {
  papers: SavedPaper[];
  readingLists: ReadingList[];
  recommendations: Recommendation[];
  libraryOpen: boolean;
  statusFilter: string | null;
  searchQuery: string;
  isLoadingPapers: boolean;
  isLoadingLists: boolean;
  isLoadingRecs: boolean;

  // Actions
  setPapers: (papers: SavedPaper[]) => void;
  setReadingLists: (lists: ReadingList[]) => void;
  setRecommendations: (recs: Recommendation[]) => void;
  setLibraryOpen: (open: boolean) => void;
  setStatusFilter: (status: string | null) => void;
  setSearchQuery: (query: string) => void;
  setLoadingPapers: (loading: boolean) => void;
  setLoadingLists: (loading: boolean) => void;
  setLoadingRecs: (loading: boolean) => void;
  updatePaperStatus: (paperId: string, status: SavedPaper["status"]) => void;
  removePaper: (paperId: string) => void;
}

export const useLibraryStore = create<LibraryState>((set) => ({
  papers: [],
  readingLists: [],
  recommendations: [],
  libraryOpen: false,
  statusFilter: null,
  searchQuery: "",
  isLoadingPapers: false,
  isLoadingLists: false,
  isLoadingRecs: false,

  setPapers: (papers) => set({ papers }),
  setReadingLists: (lists) => set({ readingLists: lists }),
  setRecommendations: (recs) => set({ recommendations: recs }),
  setLibraryOpen: (open) => set({ libraryOpen: open }),
  setStatusFilter: (status) => set({ statusFilter: status }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setLoadingPapers: (loading) => set({ isLoadingPapers: loading }),
  setLoadingLists: (loading) => set({ isLoadingLists: loading }),
  setLoadingRecs: (loading) => set({ isLoadingRecs: loading }),
  updatePaperStatus: (paperId, status) =>
    set((state) => ({
      papers: state.papers.map((p) =>
        p.paper_id === paperId ? { ...p, status } : p
      ),
    })),
  removePaper: (paperId) =>
    set((state) => ({
      papers: state.papers.filter((p) => p.paper_id !== paperId),
    })),
}));
