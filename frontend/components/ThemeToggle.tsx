"use client";

import { useSyncExternalStore } from "react";
import { SunIcon, MoonIcon } from "@/components/icons";

type Theme = "light" | "dark";

function subscribe(callback: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener("storage", callback);
  media.addEventListener("change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    media.removeEventListener("change", callback);
  };
}

function getSnapshot(): Theme {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// Arbitrary but deterministic — corrected to the real value on the client
// immediately after hydration, which is what useSyncExternalStore's
// server/client snapshot split is designed for.
function getServerSnapshot(): Theme {
  return "light";
}

export default function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    // `storage` only fires in *other* tabs by spec — dispatch locally so
    // this hook re-syncs in the tab that made the change.
    window.dispatchEvent(new Event("storage"));
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      className="flex h-9 w-9 items-center justify-center rounded-full text-primary opacity-80 transition-colors hover:bg-surface-1 hover:opacity-100"
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
