import { create } from "zustand";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  conceptsReferenced?: { id: string; name: string }[];
  insight?: { type: string; content: string } | null;
  createdAt: Date;
}

interface GraphStats {
  total_papers: number;
  total_concepts: number;
  total_relationships: number;
  total_claims: number;
  total_entities: number;
}

interface ChatState {
  messages: Message[];
  conversationId: string | null;
  mode: "auto" | "navigator" | "tutor" | "briefing";
  isLoading: boolean;

  // Panel state
  selectedConceptId: string | null;
  sidebarOpen: boolean;
  conceptPanelOpen: boolean;

  // Graph stats cache
  graphStats: GraphStats | null;

  // Actions
  addMessage: (msg: Omit<Message, "id" | "createdAt">) => void;
  setLoading: (loading: boolean) => void;
  setMode: (mode: ChatState["mode"]) => void;
  setConversationId: (id: string) => void;
  clearMessages: () => void;
  setSelectedConceptId: (id: string | null) => void;
  setSidebarOpen: (open: boolean) => void;
  setConceptPanelOpen: (open: boolean) => void;
  setGraphStats: (stats: GraphStats) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  conversationId: null,
  mode: "auto",
  isLoading: false,
  selectedConceptId: null,
  sidebarOpen: true,
  conceptPanelOpen: false,
  graphStats: null,

  addMessage: (msg) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { ...msg, id: crypto.randomUUID(), createdAt: new Date() },
      ],
    })),
  setLoading: (loading) => set({ isLoading: loading }),
  setMode: (mode) => set({ mode }),
  setConversationId: (id) => set({ conversationId: id }),
  clearMessages: () => set({ messages: [], conversationId: null }),
  setSelectedConceptId: (id) =>
    set({ selectedConceptId: id, conceptPanelOpen: id !== null }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setConceptPanelOpen: (open) =>
    set({ conceptPanelOpen: open, selectedConceptId: open ? undefined : null }),
  setGraphStats: (stats) => set({ graphStats: stats }),
}));
