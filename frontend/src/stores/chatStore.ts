import { create } from "zustand";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  conceptsReferenced?: { id: string; name: string }[];
  insight?: { type: string; content: string } | null;
  createdAt: Date;
}

interface ChatState {
  messages: Message[];
  conversationId: string | null;
  mode: "navigator" | "tutor" | "briefing";
  isLoading: boolean;
  addMessage: (msg: Omit<Message, "id" | "createdAt">) => void;
  setLoading: (loading: boolean) => void;
  setMode: (mode: ChatState["mode"]) => void;
  setConversationId: (id: string) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  conversationId: null,
  mode: "navigator",
  isLoading: false,
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
}));
