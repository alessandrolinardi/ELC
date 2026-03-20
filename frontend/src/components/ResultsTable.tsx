import { useState } from "react"
import { cn } from "@/lib/utils"
import { statusColors, statusBgColors } from "@/lib/colors"
import type { ValidatorResultRow } from "@/lib/types"

interface ResultsTableProps {
  rows: ValidatorResultRow[]
  devMode?: boolean
}

type FilterMode = "all" | "problems"

export function ResultsTable({ rows, devMode = false }: ResultsTableProps) {
  const [filter, setFilter] = useState<FilterMode>("all")
  const [showAll, setShowAll] = useState(false)

  const filteredRows =
    filter === "problems"
      ? rows.filter((r) => r.status !== "verified")
      : rows

  const displayRows = showAll ? filteredRows : filteredRows.slice(0, 10)
  const hasMore = filteredRows.length > 10

  const statusLabels: Record<string, string> = {
    verified: "Verificato",
    corrected: "Corretto",
    review: "Da verificare",
  }

  return (
    <div className="elc-card overflow-hidden">
      {/* Filter tabs */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-border">
        <button
          onClick={() => { setFilter("all"); setShowAll(false) }}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
            filter === "all"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted"
          )}
        >
          Tutti ({rows.length})
        </button>
        <button
          onClick={() => { setFilter("problems"); setShowAll(false) }}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
            filter === "problems"
              ? "bg-warning text-white"
              : "text-muted-foreground hover:bg-muted"
          )}
        >
          Solo problemi ({rows.filter((r) => r.status !== "verified").length})
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground border-b border-border">
              <th className="px-5 py-3 font-medium">Stato</th>
              <th className="px-5 py-3 font-medium w-10">Tipo</th>
              <th className="px-5 py-3 font-medium">Citta</th>
              <th className="px-5 py-3 font-medium">Indirizzo</th>
              <th className="px-5 py-3 font-medium">CAP</th>
              {devMode && <th className="px-5 py-3 font-medium">Correzioni</th>}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-border last:border-b-0"
                style={{ backgroundColor: statusBgColors[row.status] }}
              >
                {/* Status dot + label */}
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: statusColors[row.status] }}
                    />
                    <span className="text-xs font-medium">
                      {statusLabels[row.status]}
                    </span>
                  </div>
                </td>

                {/* Parse method indicator */}
                <td className="px-5 py-3 text-center" title={row.parse_method === "regex" ? "Regex" : "AI"}>
                  {row.parse_method === "regex" ? "\u2699\uFE0F" : "\uD83E\uDD16"}
                </td>

                {/* City */}
                <td className="px-5 py-3 text-foreground">{row.city}</td>

                {/* Street -- show correction inline */}
                <td className="px-5 py-3">
                  {row.suggested_street ? (
                    <span>
                      <span className="text-muted-foreground line-through">{row.street}</span>
                      {" \u2192 "}
                      <span className="font-semibold text-foreground">{row.suggested_street}</span>
                    </span>
                  ) : (
                    <span className="text-foreground">{row.street}</span>
                  )}
                </td>

                {/* ZIP -- show correction inline */}
                <td className="px-5 py-3">
                  {row.suggested_zip ? (
                    <span>
                      <span className="text-muted-foreground line-through">{row.original_zip}</span>
                      {" \u2192 "}
                      <span className="font-semibold text-foreground">{row.suggested_zip}</span>
                    </span>
                  ) : (
                    <span className="text-foreground">{row.original_zip}</span>
                  )}
                </td>

                {/* Corrections (dev mode only) */}
                {devMode && (
                  <td className="px-5 py-3 text-xs text-muted-foreground">
                    {row.corrections.join(", ") || "-"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Show more */}
      {hasMore && !showAll && (
        <div className="px-5 py-3 text-center border-t border-border">
          <button
            onClick={() => setShowAll(true)}
            className="text-xs text-primary font-medium hover:underline"
          >
            Mostra tutte le {filteredRows.length} righe {"\u25BE"}
          </button>
        </div>
      )}

      {/* Row count */}
      <div className="px-5 py-2 text-xs text-muted-foreground border-t border-border">
        {displayRows.length} di {filteredRows.length} righe
      </div>
    </div>
  )
}
