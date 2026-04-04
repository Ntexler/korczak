import { create } from "zustand";
import type { Locale } from "@/lib/i18n";
import { translations } from "@/lib/i18n";

type TranslationsType = (typeof translations)["en"] | (typeof translations)["he"];

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: TranslationsType;
}

export const useLocaleStore = create<LocaleState>((set, get) => ({
  locale: "en",
  setLocale: (locale) => set({ locale, t: translations[locale] }),
  toggleLocale: () => {
    const next = get().locale === "en" ? "he" : "en";
    set({ locale: next, t: translations[next] });
  },
  t: translations.en,
}));
