export const colors = {
  primary: "#6366f1",
  primaryLight: "#eef2ff",
  primaryBorder: "#c7d2fe",

  success: "#22c55e",
  successLight: "#f0fdf4",

  warning: "#f59e0b",
  warningLight: "#fffbeb",

  error: "#dc2626",
  errorLight: "#fef2f2",

  surface: "#f8f9fc",
  card: "#ffffff",
  border: "#e5e7eb",

  textPrimary: "#0f172a",
  textSecondary: "#64748b",
  textMuted: "#9ca3af",
} as const

/**
 * Status color mapping for result tables and progress bars.
 * Maps validation status -> color token.
 */
export const statusColors = {
  verified: colors.success,
  corrected: colors.primary,
  review: colors.warning,
} as const

/**
 * Status background tints for table rows.
 */
export const statusBgColors = {
  verified: "transparent",
  corrected: "#fafaff",    // subtle indigo tint
  review: colors.warningLight,
} as const
