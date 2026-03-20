import { cn } from "@/lib/utils"

interface CarrierTileProps {
  carrier: string
  icon: string
  selected: boolean
  onClick: () => void
}

const carrierIcons: Record<string, string> = {
  FedEx: "\uD83D\uDCE6",
  DHL: "\u2708\uFE0F",
  UPS: "\uD83D\uDE9A",
}

export function CarrierTile({ carrier, icon, selected, onClick }: CarrierTileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border-2 p-5 transition-all cursor-pointer w-full",
        selected
          ? "border-primary bg-indigo-light shadow-[var(--shadow-card)]"
          : "border-border bg-card hover:border-indigo-border hover:shadow-[var(--shadow-card)]"
      )}
    >
      <span className="text-3xl mb-2">{icon || carrierIcons[carrier] || "\uD83D\uDCE6"}</span>
      <span
        className={cn(
          "text-sm font-semibold",
          selected ? "text-primary" : "text-foreground"
        )}
      >
        {carrier}
      </span>
    </button>
  )
}
