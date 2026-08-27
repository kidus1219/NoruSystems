import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

const KEY = "noru-theme";

const stored = (): Theme | null => {
  const value = localStorage.getItem(KEY);
  return value === "light" || value === "dark" ? value : null;
};

type ThemeValue = { theme: Theme; toggle: () => void };

const ThemeContext = createContext<ThemeValue | null>(null);

/** One piece of theme state for the whole app. It has to live in a provider
 *  rather than a plain hook, otherwise every caller gets its own copy and the
 *  bits that read `theme` (the logo) miss the change. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => stored() ?? "light");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      localStorage.setItem(KEY, next);
      return next;
    });
  }, []);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside <ThemeProvider>");
  return value;
}
