export function readTheme(): "light" | "dark" {
  try {
    return localStorage.getItem("dayflow-theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}
