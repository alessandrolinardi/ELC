import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format ISO date "2026-03-20" to "20/03/2026" */
export function formatDateIT(iso: string): string {
  const [y, m, d] = iso.split("-")
  return `${d}/${m}/${y}`
}

/** Format ISO time "09:00:00" to "09:00" */
export function formatTime(iso: string): string {
  return iso.slice(0, 5)
}
