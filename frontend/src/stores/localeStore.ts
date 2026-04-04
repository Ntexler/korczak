import { create } from "zustand";
import type { Locale } from "@/lib/i18n";
import { translations, fonts } from "@/lib/i18n";

type TranslationsType = (typeof translations)["en"] | (typeof translations)["he"];
type FontsType = (typeof fonts)["en"] | (typeof fonts)["he"];

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: TranslationsType;
  fonts: FontsType;
  isRtl: boolean;
}

export const useLocaleStore = create<LocaleState>((set, get) => ({
  locale: "en",
  setLocale: (locale) =>
    set({ locale, t: translations[locale], fonts: fonts[locale], isRtl: locale === "he" }),
  toggleLocale: () => {
    const next = get().locale === "en" ? "he" : "en";
    set({ locale: next, t: translations[next], fonts: fonts[next], isRtl: next === "he" });
  },
  t: translations.en,
  fonts: fonts.en,
  isRtl: false,
}));
