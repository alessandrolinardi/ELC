import type { ReactNode } from "react"

interface PageShellProps {
  title: string
  subtitle?: string
  stepIndicator?: ReactNode
  children: ReactNode
}

/**
 * Page wrapper -- title, optional subtitle, optional step indicator, then children.
 * Centered at max-width 780px matching the design spec.
 */
export function PageShell({ title, subtitle, stepIndicator, children }: PageShellProps) {
  return (
    <main className="max-w-[var(--max-width-content)] mx-auto px-4 py-8">
      {/* Step indicator (above title) */}
      {stepIndicator && <div className="mb-8">{stepIndicator}</div>}

      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">{title}</h1>
        {subtitle && (
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>

      {/* Page content */}
      {children}
    </main>
  )
}
