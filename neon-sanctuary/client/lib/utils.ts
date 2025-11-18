import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function normalizeAdType(text: string): string {
  if (!text) return text;

  // Known acronyms that should be fully capitalized
  const acronyms = new Set(["sba", "sbv", "toa"]);

  // Split on underscores first
  const words = text.split("_");

  return words
    .map((word) => {
      // Insert spaces between camelCase words
      const splitWords = word
        .replace(/([a-z])([A-Z])/g, "$1 $2") // Insert space before uppercase letters
        .toLowerCase()
        .split(" ");

      return splitWords
        .map((w) => {
          // Check if this word is a known acronym
          if (acronyms.has(w)) {
            return w.toUpperCase();
          }
          // Capitalize first letter
          return w.charAt(0).toUpperCase() + w.slice(1);
        })
        .join(" ");
    })
    .join(" ");
}
