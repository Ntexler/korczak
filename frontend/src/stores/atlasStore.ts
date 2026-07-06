"use client";

import { create } from "zustand";

// A stop on the user's journey through the knowledge universe.
// The trail is the "Ariadne thread" — you can always see where you came
// from and jump back to any station.
export interface JourneyStop {
  id: string;
  name: string;
  kind: "concept" | "thinker" | "paper" | "field";
  field?: string;
}

interface AtlasState {
  trail: JourneyStop[];
  currentId: string | null;
  addStop: (stop: JourneyStop) => void;
  jumpTo: (id: string) => void;
  clearTrail: () => void;
}

export const useAtlasStore = create<AtlasState>((set) => ({
  trail: [],
  currentId: null,

  addStop: (stop) =>
    set((state) => {
      // Re-visiting an existing stop truncates the trail back to it
      const existing = state.trail.findIndex((s) => s.id === stop.id);
      if (existing >= 0) {
        return { trail: state.trail.slice(0, existing + 1), currentId: stop.id };
      }
      return { trail: [...state.trail.slice(-30), stop], currentId: stop.id };
    }),

  jumpTo: (id) =>
    set((state) => {
      const idx = state.trail.findIndex((s) => s.id === id);
      if (idx < 0) return state;
      return { trail: state.trail.slice(0, idx + 1), currentId: id };
    }),

  clearTrail: () => set({ trail: [], currentId: null }),
}));
