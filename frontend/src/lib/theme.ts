import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "noru-theme";

const systemTheme = (): Theme =>
  window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

const stored = (): Theme | null => {
  const value = localStorage.getItem(KEY);
  return value === "light" || value === "dark" ? value : null;
};

/** Follows the OS until someone hits the toggle, then their pick sticks. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => stored() ?? systemTheme());
  const [pinned, setPinned] = useState(() => stored() !== null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (pinned) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setTheme(media.matches ? "dark" : "light");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [pinned]);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem(KEY, next);
    setPinned(true);
    setTheme(next);
  };

  return { theme, toggle };
}
