import { create } from "zustand";

type FieldMode = "learn" | "research" | "discover";

interface FieldState {
  currentField: string | null;
  currentMode: FieldMode;
  setField: (field: string) => void;
  setMode: (mode: FieldMode) => void;
  clearField: () => void;
}

export const useFieldStore = create<FieldState>((set) => ({
  currentField: null,
  currentMode: "learn",
  setField: (field) => set({ currentField: field }),
  setMode: (mode) => set({ currentMode: mode }),
  clearField: () => set({ currentField: null }),
}));
