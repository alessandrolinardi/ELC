import { useState } from "react"
import { usePickupHistory } from "@/hooks/usePickupHistory"
import { Badge } from "@/components/ui/badge"
import { cn, formatDateIT, formatTime } from "@/lib/utils"
import { ChevronDown, ChevronRight } from "lucide-react"
import type { PickupRecord } from "@/lib/types"

const CARRIER_COLORS: Record<string, string> = {
  FedEx: "bg-purple-100 text-purple-700 border-purple-300",
  DHL: "bg-yellow-100 text-yellow-700 border-yellow-300",
  UPS: "bg-amber-100 text-amber-800 border-amber-300",
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  booked: { label: "Confermato", color: "bg-emerald-100 text-emerald-700 border-emerald-300" },
  pending_review: { label: "In revisione", color: "bg-amber-100 text-amber-700 border-amber-300" },
  scheduled: { label: "Programmato", color: "bg-blue-100 text-blue-700 border-blue-300" },
  failed: { label: "Errore", color: "bg-red-100 text-red-700 border-red-300" },
  rejected: { label: "Rifiutato", color: "bg-red-100 text-red-700 border-red-300" },
}

export function PickupHistory() {
  const [filter, setFilter] = useState<"upcoming" | "archive">("upcoming")
  const [showAll, setShowAll] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const isUpcoming = filter === "upcoming"
  const limit = showAll ? 500 : 20
  const { pickups, total, isLoading } = usePickupHistory(isUpcoming, limit, 0)

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleFilterChange = (f: "upcoming" | "archive") => {
    setFilter(f)
    setShowAll(false)
    setExpanded(new Set())
  }

  return (
    <div className="space-y-4">
      <div className="elc-card">
        {/* Sub-tab pills */}
        <div className="flex gap-2 mb-4">
          {([
            { key: "upcoming" as const, label: "Prossimi" },
            { key: "archive" as const, label: "Archivio" },
          ]).map((tab) => (
            <button
              key={tab.key}
              onClick={() => handleFilterChange(tab.key)}
              className={cn(
                "px-3 py-1 text-sm font-medium rounded-md transition-colors",
                filter === tab.key
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="text-center py-8">
            <div className="inline-block w-6 h-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
          </div>
        )}

        {/* Empty state */}
        {!isLoading && pickups.length === 0 && (
          <div className="text-center py-8 text-sm text-muted-foreground">
            {isUpcoming ? "Nessun ritiro in programma" : "Nessun ritiro passato"}
          </div>
        )}

        {/* Table */}
        {!isLoading && pickups.length > 0 && (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="pb-2 font-medium">Data</th>
                  <th className="pb-2 font-medium">Corriere</th>
                  <th className="pb-2 font-medium">Indirizzo</th>
                  <th className="pb-2 font-medium text-right">Colli</th>
                  <th className="pb-2 font-medium text-right">Peso tot.</th>
                  <th className="pb-2 w-8"></th>
                </tr>
              </thead>
              <tbody>
                {pickups.map((p) => (
                  <PickupRow
                    key={p.id}
                    pickup={p}
                    isExpanded={expanded.has(p.id)}
                    onToggle={() => toggleExpand(p.id)}
                  />
                ))}
              </tbody>
            </table>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-border mt-3">
              <span className="text-xs text-muted-foreground">
                {pickups.length} di {total} ritiri
              </span>
              {!showAll && total > pickups.length && (
                <button
                  onClick={() => setShowAll(true)}
                  className="text-xs text-primary font-medium hover:underline"
                >
                  Mostra tutti ({total})
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function PickupRow({
  pickup: p,
  isExpanded,
  onToggle,
}: {
  pickup: PickupRecord
  isExpanded: boolean
  onToggle: () => void
}) {
  const totalWeight = p.num_packages * p.weight_per_package
  const carrierColor = CARRIER_COLORS[p.carrier] || "bg-gray-100 text-gray-700 border-gray-300"
  const statusInfo = p.pickup_status ? STATUS_LABELS[p.pickup_status] : null

  return (
    <>
      <tr
        onClick={onToggle}
        className="border-b border-border/50 cursor-pointer hover:bg-muted/30 transition-colors"
      >
        <td className="py-2.5">{formatDateIT(p.pickup_date)}</td>
        <td className="py-2.5">
          <Badge variant="outline" className={cn("text-xs", carrierColor)}>
            {p.carrier}
          </Badge>
        </td>
        <td className="py-2.5 text-muted-foreground truncate max-w-[200px]">
          {p.city}{p.province ? ` (${p.province})` : ""}
        </td>
        <td className="py-2.5 text-right">{p.num_packages}</td>
        <td className="py-2.5 text-right">{totalWeight.toFixed(1)} kg</td>
        <td className="py-2.5 text-right">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </td>
      </tr>

      {isExpanded && (
        <tr>
          <td colSpan={6} className="py-0">
            <div className="bg-muted/30 border-l-2 border-primary px-4 py-3 mb-1">
              <div className="grid grid-cols-2 gap-6 text-sm">
                {/* Left: Address */}
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Indirizzo</p>
                  {p.company && <p className="font-medium">{p.company}</p>}
                  {p.contact_name && <p>{p.contact_name}</p>}
                  <p>{p.address}</p>
                  <p>{p.zip_code} {p.city}{p.province ? ` (${p.province})` : ""}</p>
                  {p.phone && <p className="text-muted-foreground">Tel: {p.phone}</p>}
                  {p.reference && <p className="text-muted-foreground">Rif: {p.reference}</p>}
                </div>

                {/* Right: Details */}
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Dettagli</p>
                  <p>Fascia oraria: {formatTime(p.time_start)} \u2013 {formatTime(p.time_end)}</p>
                  <p>{p.num_packages} colli \u00d7 {p.weight_per_package} kg \u2014 {p.length}\u00d7{p.width}\u00d7{p.height} cm</p>
                  {p.use_pallet && (
                    <p>{p.num_pallets} pallet \u2014 {p.pallet_length}\u00d7{p.pallet_width}\u00d7{p.pallet_height} cm</p>
                  )}
                  {p.notes && (
                    <p className="text-muted-foreground mt-1">Note: {p.notes}</p>
                  )}
                  <div className="mt-2">
                    {statusInfo ? (
                      <>
                        <Badge variant="outline" className={cn("text-xs", statusInfo.color)}>
                          {statusInfo.label}
                        </Badge>
                        {p.confirmation_id && (
                          <span className="text-xs text-muted-foreground ml-2">#{p.confirmation_id}</span>
                        )}
                      </>
                    ) : (
                      <Badge variant="outline" className="text-xs bg-gray-100 text-gray-600 border-gray-300">
                        Inviato
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
