import { cn } from "@/lib/utils"
import fedexLogo from "@/assets/carriers/fedex.svg"
import dhlLogo from "@/assets/carriers/dhl.svg"
import upsLogo from "@/assets/carriers/ups.svg"

interface CarrierTileProps {
  carrier: string
  icon?: string
  selected: boolean
  onClick: () => void
}

const carrierLogos: Record<string, string> = {
  FedEx: fedexLogo,
  DHL: dhlLogo,
  UPS: upsLogo,
}

export function CarrierTile({ carrier, selected, onClick }: CarrierTileProps) {
  const logo = carrierLogos[carrier]

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
      {logo ? (
        <img
          src={logo}
          alt={`${carrier} logo`}
          className="h-8 mb-2 object-contain"
        />
      ) : (
        <span className="text-3xl mb-2">&#128230;</span>
      )}
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
