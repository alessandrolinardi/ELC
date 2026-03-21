import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import { statusColors, statusBgColors } from "@/lib/colors"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ValidatorResultRow } from "@/lib/types"

interface ResultsTableProps {
  rows: ValidatorResultRow[]
  devMode?: boolean
  /** User edits keyed by row index: { "0": { street: "..." } } */
  edits: Record<string, Record<string, string>>
  onEditRow: (index: number, field: string, value: string) => void
  onGenerate: () => void
  isGenerating: boolean
  filesReady: boolean
}

type FilterMode = "all" | "corrected" | "review"

export function ResultsTable({
  rows,
  devMode = false,
  edits,
  onEditRow,
  onGenerate,
  isGenerating,
  filesReady,
}: ResultsTableProps) {
  const reviewCount = rows.filter((r) => r.status === "review").length
  const correctedCount = rows.filter((r) => r.status !== "review").length

  // Default to "review" if there are items to review
  const [filter, setFilter] = useState<FilterMode>(reviewCount > 0 ? "review" : "all")
  const [showAll, setShowAll] = useState(false)
  const [editingRow, setEditingRow] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState<Record<string, string>>({})

  const filteredRows = rows
    .map((r, i) => ({ ...r, _index: i }))
    .filter((r) => {
      if (filter === "corrected") return r.status !== "review"
      if (filter === "review") return r.status === "review"
      return true
    })

  const displayRows = showAll ? filteredRows : filteredRows.slice(0, 15)
  const hasMore = filteredRows.length > 15

  const statusLabels: Record<string, string> = {
    verified: "Verificato",
    corrected: "Corretto",
    review: "Da verificare",
  }

  // Get display value, preferring user edits
  function getVal(rowIndex: number, row: ValidatorResultRow, field: "street" | "city" | "zip"): string {
    const e = edits[String(rowIndex)]
    if (e && field in e) return e[field]
    if (field === "street") return row.suggested_street || row.street
    if (field === "city") return row.city
    if (field === "zip") return row.suggested_zip || row.original_zip
    return ""
  }

  function startEditing(rowIndex: number, row: ValidatorResultRow) {
    setEditingRow(rowIndex)
    setEditDraft({
      street: getVal(rowIndex, row, "street"),
      city: getVal(rowIndex, row, "city"),
      zip: getVal(rowIndex, row, "zip"),
    })
  }

  function saveEdit(rowIndex: number) {
    for (const [field, value] of Object.entries(editDraft)) {
      onEditRow(rowIndex, field, value)
    }
    setEditingRow(null)
    setEditDraft({})
  }

  function cancelEdit() {
    setEditingRow(null)
    setEditDraft({})
  }

  const editCount = Object.keys(edits).length

  return (
    <div className="space-y-4">
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
            onClick={() => { setFilter("corrected"); setShowAll(false) }}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
              filter === "corrected"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            Corretti ({correctedCount})
          </button>
          {reviewCount > 0 && (
            <button
              onClick={() => { setFilter("review"); setShowAll(false) }}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                filter === "review"
                  ? "bg-warning text-white"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              Da verificare ({reviewCount})
            </button>
          )}
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
                <th className="px-5 py-3 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row) => {
                const idx = row._index
                const isEditing = editingRow === idx
                const hasUserEdit = !!edits[String(idx)]

                return (
                  <tr
                    key={idx}
                    className="border-b border-border last:border-b-0"
                    style={{ backgroundColor: hasUserEdit ? "#eff6ff" : statusBgColors[row.status] }}
                  >
                    {/* Status */}
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: hasUserEdit ? "#3b82f6" : statusColors[row.status] }}
                        />
                        <span className="text-xs font-medium whitespace-nowrap">
                          {hasUserEdit ? "Modificato" : statusLabels[row.status]}
                        </span>
                      </div>
                    </td>

                    {/* Parse method */}
                    <td className="px-5 py-3 text-center" title={row.parse_method === "regex" ? "Regex" : "AI"}>
                      {row.parse_method === "regex" ? "\u2699\uFE0F" : "\uD83E\uDD16"}
                    </td>

                    {isEditing ? (
                      <>
                        {/* Inline edit mode */}
                        <td className="px-3 py-2">
                          <Input
                            value={editDraft.city || ""}
                            onChange={(e) => setEditDraft((d) => ({ ...d, city: e.target.value }))}
                            className="h-8 text-sm"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            value={editDraft.street || ""}
                            onChange={(e) => setEditDraft((d) => ({ ...d, street: e.target.value }))}
                            className="h-8 text-sm"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            value={editDraft.zip || ""}
                            onChange={(e) => setEditDraft((d) => ({ ...d, zip: e.target.value }))}
                            className="h-8 text-sm w-24"
                          />
                        </td>
                        {devMode && <td />}
                        <td className="px-3 py-2">
                          <div className="flex gap-1">
                            <button
                              onClick={() => saveEdit(idx)}
                              className="p-1 rounded text-green-600 hover:bg-green-50"
                              title="Salva"
                            >
                              <CheckIcon />
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="p-1 rounded text-muted-foreground hover:bg-muted"
                              title="Annulla"
                            >
                              <XIcon />
                            </button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        {/* City */}
                        <td className="px-5 py-3 text-foreground">
                          {getVal(idx, row, "city")}
                        </td>

                        {/* Street */}
                        <td className="px-5 py-3">
                          {hasUserEdit ? (
                            <span className="font-semibold text-blue-600">
                              {getVal(idx, row, "street")}
                            </span>
                          ) : row.suggested_street ? (
                            <span>
                              <span className="text-muted-foreground line-through">{row.street}</span>
                              {" \u2192 "}
                              <span className="font-semibold text-foreground">{row.suggested_street}</span>
                            </span>
                          ) : (
                            <span className="text-foreground">{row.street}</span>
                          )}
                        </td>

                        {/* ZIP */}
                        <td className="px-5 py-3">
                          {hasUserEdit ? (
                            <span className="font-semibold text-blue-600">
                              {getVal(idx, row, "zip")}
                            </span>
                          ) : row.suggested_zip && row.suggested_zip !== row.original_zip ? (
                            <span>
                              <span className="text-muted-foreground line-through">{row.original_zip}</span>
                              {" \u2192 "}
                              <span className="font-semibold text-foreground">{row.suggested_zip}</span>
                            </span>
                          ) : (
                            <span className="text-foreground">{row.original_zip}</span>
                          )}
                        </td>

                        {/* Dev corrections */}
                        {devMode && (
                          <td className="px-5 py-3 text-xs text-muted-foreground">
                            {row.corrections.join(", ") || "-"}
                          </td>
                        )}

                        {/* Edit button */}
                        <td className="px-3 py-3">
                          {(row.status === "review" || hasUserEdit) && (
                            <button
                              onClick={() => startEditing(idx, row)}
                              className="p-1 rounded hover:bg-muted transition-colors"
                              title="Modifica"
                            >
                              <PencilIcon />
                            </button>
                          )}
                        </td>
                      </>
                    )}
                  </tr>
                )
              })}
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
          {editCount > 0 && (
            <span className="ml-2 text-blue-600 font-medium">
              ({editCount} {editCount === 1 ? "modifica" : "modifiche"})
            </span>
          )}
        </div>
      </div>

      {/* Generate button */}
      {!filesReady && (
        <div className="flex justify-center pt-2">
          <Button
            onClick={onGenerate}
            disabled={isGenerating}
            className="bg-primary hover:bg-primary/90 text-white px-8"
          >
            {isGenerating ? (
              <>
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
                Generazione file...
              </>
            ) : (
              <>Conferma e genera file</>
            )}
          </Button>
        </div>
      )}
    </div>
  )
}

function PencilIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className="text-muted-foreground">
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function XIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  )
}
