import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import type { ParsedRow, ParsingSummary } from "@/lib/types"

interface ParseReviewTableProps {
  rows: ParsedRow[]
  summary: ParsingSummary
  edits: Record<string, Record<string, string>>
  onEditRow: (index: number, field: string, value: string) => void
  onRetryRegex: () => void
  onConfirm: () => void
  isConfirming: boolean
}

export function ParseReviewTable({
  rows,
  summary,
  edits,
  onEditRow,
  onRetryRegex,
  onConfirm,
  isConfirming,
}: ParseReviewTableProps) {
  const [editingRow, setEditingRow] = useState<number | null>(null)
  const [showAllRows, setShowAllRows] = useState(false)

  // Inline edit draft state (local to this component, flushed on Save)
  const [editDraft, setEditDraft] = useState<Record<string, string>>({})

  const modifiedRows = rows.filter((r) => r.changed && r.method === "ai")
  const aiCoverage = summary.total > 0 ? Math.round((summary.ai_parsed / summary.total) * 100) : 0

  // Get the current display value for a row field (edits override parsed)
  function getDisplayValue(row: ParsedRow, field: keyof ParsedRow["parsed"]): string {
    const rowEdits = edits[String(row.index)]
    if (rowEdits && field in rowEdits) return rowEdits[field]
    return row.parsed[field]
  }

  function startEditing(row: ParsedRow) {
    setEditingRow(row.index)
    setEditDraft({
      street: getDisplayValue(row, "street"),
      city: getDisplayValue(row, "city"),
      zip: getDisplayValue(row, "zip"),
    })
  }

  function saveEdit(index: number) {
    for (const [field, value] of Object.entries(editDraft)) {
      onEditRow(index, field, value)
    }
    setEditingRow(null)
    setEditDraft({})
  }

  function cancelEdit() {
    setEditingRow(null)
    setEditDraft({})
  }

  return (
    <div className="space-y-4">
      {/* === Summary Banner === */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Risultato parsing AI</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Coverage bar */}
          <div>
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
              <span>Copertura AI</span>
              <span className="font-semibold text-foreground">{aiCoverage}%</span>
            </div>
            <div className="w-full h-2.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                style={{ width: `${aiCoverage}%` }}
              />
            </div>
          </div>

          {/* Stats row */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-xs px-2.5 py-1">
              {summary.ai_parsed} AI
            </Badge>
            {summary.regex_fallback > 0 && (
              <Badge variant="outline" className="text-xs px-2.5 py-1 border-amber-400 text-amber-700">
                {summary.regex_fallback} regex fallback
              </Badge>
            )}
            <Badge variant="outline" className="text-xs px-2.5 py-1">
              {summary.ai_modified} modificati
            </Badge>
            <Badge variant="outline" className="text-xs px-2.5 py-1">
              {summary.unchanged} invariati
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* === Modified Rows (AI) === */}
      {modifiedRows.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Righe modificate dall&apos;AI ({modifiedRows.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-0 px-0">
            {modifiedRows.map((row) => {
              const isEditing = editingRow === row.index
              const hasUserEdits = !!edits[String(row.index)]

              return (
                <div key={row.index}>
                  <div className="px-4 py-3">
                    {/* Row header */}
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs text-muted-foreground">
                        Riga {row.index + 1} &middot; {row.original.city}
                      </span>
                      <div className="flex items-center gap-2">
                        {hasUserEdits && (
                          <Badge variant="outline" className="text-xs px-2 py-0.5 border-blue-400 text-blue-600">
                            modificato
                          </Badge>
                        )}
                        {!isEditing && (
                          <button
                            onClick={() => startEditing(row)}
                            className="p-1 rounded hover:bg-muted transition-colors"
                            title="Modifica"
                          >
                            <PencilIcon />
                          </button>
                        )}
                      </div>
                    </div>

                    {isEditing ? (
                      /* Inline edit form */
                      <div className="space-y-2 mt-2">
                        <div>
                          <label className="text-xs text-muted-foreground">Indirizzo</label>
                          <Input
                            value={editDraft.street || ""}
                            onChange={(e) => setEditDraft((d) => ({ ...d, street: e.target.value }))}
                            className="mt-0.5"
                          />
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-xs text-muted-foreground">Citta</label>
                            <Input
                              value={editDraft.city || ""}
                              onChange={(e) => setEditDraft((d) => ({ ...d, city: e.target.value }))}
                              className="mt-0.5"
                            />
                          </div>
                          <div>
                            <label className="text-xs text-muted-foreground">CAP</label>
                            <Input
                              value={editDraft.zip || ""}
                              onChange={(e) => setEditDraft((d) => ({ ...d, zip: e.target.value }))}
                              className="mt-0.5"
                            />
                          </div>
                        </div>
                        <div className="flex gap-2 mt-1">
                          <Button size="sm" onClick={() => saveEdit(row.index)}>
                            Salva
                          </Button>
                          <Button size="sm" variant="outline" onClick={cancelEdit}>
                            Annulla
                          </Button>
                        </div>
                      </div>
                    ) : (
                      /* Diff display */
                      <div className="text-sm">
                        <span className="text-muted-foreground line-through">
                          {row.original.street}
                        </span>
                        {" \u2192 "}
                        <span className="font-bold text-indigo-600">
                          {getDisplayValue(row, "street")}
                        </span>
                      </div>
                    )}
                  </div>
                  <Separator />
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* === Regex Fallback Warning === */}
      {summary.regex_fallback > 0 && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-5 py-4">
          <p className="text-sm font-semibold text-amber-800">
            {summary.regex_fallback} {summary.regex_fallback === 1 ? "riga elaborata" : "righe elaborate"} con regex (senza AI)
          </p>
          <p className="text-sm text-amber-700 mt-1">
            Il parsing regex e meno accurato. Puoi riprovare con AI o procedere comunque.
          </p>
          <div className="flex gap-2 mt-3">
            <Button
              size="sm"
              variant="outline"
              onClick={onRetryRegex}
              disabled={isConfirming}
              className="border-amber-400 text-amber-800 hover:bg-amber-100"
            >
              Riprova con AI
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onConfirm}
              disabled={isConfirming}
              className="text-muted-foreground"
            >
              Procedi comunque
            </Button>
          </div>
        </div>
      )}

      {/* === All Rows (Collapsed) === */}
      <div className="elc-card overflow-hidden">
        <button
          onClick={() => setShowAllRows(!showAllRows)}
          className="w-full px-5 py-3 text-left text-sm font-medium text-primary hover:bg-muted/50 transition-colors flex items-center justify-between"
        >
          <span>Mostra tutti ({rows.length} righe)</span>
          <span className="text-xs">{showAllRows ? "\u25B4" : "\u25BE"}</span>
        </button>

        {showAllRows && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-t border-b border-border">
                  <th className="px-5 py-2.5 font-medium w-10">#</th>
                  <th className="px-5 py-2.5 font-medium w-10">Tipo</th>
                  <th className="px-5 py-2.5 font-medium">Indirizzo</th>
                  <th className="px-5 py-2.5 font-medium">Citta</th>
                  <th className="px-5 py-2.5 font-medium">CAP</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.index}
                    className={cn(
                      "border-b border-border last:border-b-0",
                      row.changed && "bg-indigo-50/50"
                    )}
                  >
                    <td className="px-5 py-2.5 text-xs text-muted-foreground">
                      {row.index + 1}
                    </td>
                    <td className="px-5 py-2.5 text-center" title={row.method === "ai" ? "AI" : "Regex"}>
                      {row.method === "ai" ? "\uD83E\uDD16" : "\u2699\uFE0F"}
                    </td>
                    <td className="px-5 py-2.5">
                      {row.changed ? (
                        <span>
                          <span className="text-muted-foreground line-through text-xs">
                            {row.original.street}
                          </span>
                          {" \u2192 "}
                          <span className="font-semibold text-indigo-600">
                            {getDisplayValue(row, "street")}
                          </span>
                        </span>
                      ) : (
                        <span className="text-foreground">{getDisplayValue(row, "street")}</span>
                      )}
                    </td>
                    <td className="px-5 py-2.5 text-foreground">
                      {getDisplayValue(row, "city")}
                    </td>
                    <td className="px-5 py-2.5 text-foreground">
                      {getDisplayValue(row, "zip")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* === Action Bar === */}
      <div className="flex justify-center pt-2">
        <Button
          onClick={onConfirm}
          disabled={isConfirming}
          className="bg-primary hover:bg-primary/90 text-white px-6"
        >
          {isConfirming ? (
            <>
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
              Avvio validazione...
            </>
          ) : (
            "Conferma e avvia validazione Google"
          )}
        </Button>
      </div>
    </div>
  )
}

/** Simple pencil SVG icon */
function PencilIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-muted-foreground"
    >
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </svg>
  )
}
