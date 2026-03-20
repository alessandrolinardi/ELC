import { cn } from "@/lib/utils"

interface DownloadCardProps {
  /** File display name */
  label: string
  /** Subtitle (e.g., file format info) */
  subtitle?: string
  /** Download URL */
  href: string
  /** Visual variant */
  variant: "primary" | "secondary" | "disabled"
  /** File icon/emoji */
  icon?: string
}

export function DownloadCard({
  label,
  subtitle,
  href,
  variant,
  icon,
}: DownloadCardProps) {
  const isDisabled = variant === "disabled"

  return (
    <a
      href={isDisabled ? undefined : href}
      download
      className={cn(
        "block rounded-lg p-5 transition-all",
        variant === "primary" &&
          "bg-primary text-primary-foreground hover:bg-primary/90 shadow-[var(--shadow-card)]",
        variant === "secondary" &&
          "bg-card border border-border text-foreground hover:border-primary hover:shadow-[var(--shadow-card)]",
        variant === "disabled" &&
          "bg-muted text-muted-foreground cursor-not-allowed opacity-60"
      )}
      onClick={(e) => isDisabled && e.preventDefault()}
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">
          {isDisabled ? "\uD83D\uDD12" : icon || "\uD83D\uDCE5"}
        </span>
        <div>
          <p className={cn(
            "font-semibold text-sm",
            variant === "primary" && "text-primary-foreground",
          )}>
            {label}
          </p>
          {subtitle && (
            <p className={cn(
              "text-xs mt-0.5",
              variant === "primary" ? "text-primary-foreground/80" : "text-muted-foreground",
            )}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </a>
  )
}
