import { useTheme } from "../lib/theme";

const SUN = "M8 11.2a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4zM8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1M12.9 12.9l-1.1-1.1M4.2 4.2L3.1 3.1";
const MOON = "M13.5 9.6A5.8 5.8 0 016.4 2.5a5.8 5.8 0 107.1 7.1z";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      title={`Switch to ${next} mode`}
      aria-label={`Switch to ${next} mode`}
    >
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3"
           strokeLinecap="round" strokeLinejoin="round">
        <path d={theme === "dark" ? MOON : SUN} />
      </svg>
      <span>{theme === "dark" ? "Dark" : "Light"}</span>
    </button>
  );
}
