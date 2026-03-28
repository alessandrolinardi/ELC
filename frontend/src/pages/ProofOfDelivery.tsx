import { useState, useCallback } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

const BASE_URL = import.meta.env.VITE_API_URL || ""

interface PodSingleResult {
  status: string
  pod_base64: string
  tracking_number: string
  carrier: string
  file_type: string
  error_message?: string
}

interface PodBatchItem {
  input_value: string
  status: "found" | "no_pod" | "unmatched" | "ambiguous" | "error"
  tracking_number?: string
  carrier?: string
  file_key?: string
  message?: string
}

interface PodBatchResult {
  job_id: string
  status: string
  summary: {
    total_input: number
    duplicates_removed: number
    found: number
    no_pod: number
    unmatched: number
    ambiguous: number
    error: number
  }
  results: PodBatchItem[]
}

const STATUS_LABELS: Record<string, string> = {
  found: "Trovato",
  no_pod: "Non disponibile",
  unmatched: "Non trovato",
  ambiguous: "Ambiguo",
  error: "Errore",
}

const STATUS_COLORS: Record<string, string> = {
  found: "bg-emerald-100 text-emerald-700 border-emerald-300",
  no_pod: "bg-amber-100 text-amber-700 border-amber-300",
  unmatched: "bg-gray-100 text-gray-600 border-gray-300",
  ambiguous: "bg-orange-100 text-orange-700 border-orange-300",
  error: "bg-red-100 text-red-700 border-red-300",
}

function parseIdentifiers(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

export default function ProofOfDelivery() {
  const [isDevMode] = useDevMode()
  const [textInput, setTextInput] = useState("")
  const [jobId, setJobId] = useState<string | null>(null)
  const [remoteJobId, setRemoteJobId] = useState<string | null>(null)
  const [singleResult, setSingleResult] = useState<PodSingleResult | null>(null)
  const [isDownloadingZip, setIsDownloadingZip] = useState(false)

  const { status: jobStatus, result: rawResult, error: jobError } =
    useJobPolling<PodBatchResult>(jobId)

  const batchResult = jobStatus === "complete" ? (rawResult as PodBatchResult) : null

  // Extract identifiers from text or Excel
  const getIdentifiers = useCallback((): string[] => {
    const fromText = parseIdentifiers(textInput)
    // Excel parsing happens server-side — we'd need a separate endpoint
    // For now, text input is the primary method
    return fromText
  }, [textInput])

  // Single POD mutation (1 identifier → instant PDF download)
  const singleMutation = useMutation({
    mutationFn: async (identifier: string) => {
      const resp = await api.post<{ ok: boolean; data: PodSingleResult; error?: { message: string } }>(
        "/api/v1/jobs/pod",
        { identifier }
      )
      if (!resp.ok) throw new Error(resp.error?.message || "Errore")
      return resp.data
    },
    onSuccess: (data) => {
      setSingleResult(data)
      if (data.status === "found" && data.pod_base64) {
        // Auto-download the PDF
        const bytes = Uint8Array.from(atob(data.pod_base64), (c) => c.charCodeAt(0))
        const blob = new Blob([bytes], { type: "application/pdf" })
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `pod_${data.tracking_number || "download"}.pdf`
        a.click()
        URL.revokeObjectURL(url)
      }
    },
  })

  // Bulk POD mutation
  const batchMutation = useMutation({
    mutationFn: async (identifiers: string[]) => {
      return api.post<{ ok: boolean; data: { job_id: string; total: number } }>(
        "/api/v1/jobs/pod-batch",
        { identifiers }
      )
    },
    onSuccess: (resp) => {
      setJobId(resp.data.job_id)
    },
  })

  const handleSubmit = () => {
    const identifiers = getIdentifiers()
    if (identifiers.length === 0) return

    if (identifiers.length === 1) {
      singleMutation.mutate(identifiers[0])
    } else {
      batchMutation.mutate(identifiers)
    }
  }

  // Extract remote job_id from batch result for ZIP download
  const effectiveRemoteJobId = batchResult?.job_id || remoteJobId

  const handleDownloadZip = async () => {
    if (!effectiveRemoteJobId) return
    setIsDownloadingZip(true)
    try {
      const formData = new FormData()
      formData.append("remote_job_id", effectiveRemoteJobId)
      const resp = await fetch(`${BASE_URL}/api/v1/jobs/pod-download-zip`, {
        method: "POST",
        body: formData,
      })
      if (!resp.ok) throw new Error("Download fallito")
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `pod_${effectiveRemoteJobId.slice(0, 8)}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // Silently fail — user can retry
    } finally {
      setIsDownloadingZip(false)
    }
  }

  const handleReset = () => {
    setTextInput("")
    setJobId(null)
    setRemoteJobId(null)
    setSingleResult(null)
    singleMutation.reset()
    batchMutation.reset()
  }

  const identifiers = getIdentifiers()
  const isProcessing = !!jobId && jobStatus !== "complete" && jobStatus !== "failed"
  const hasInput = identifiers.length > 0

  return (
    <PageShell title="Proof of Delivery" subtitle="Cerca e scarica le prove di consegna (POD) per le spedizioni.">
      <div className="space-y-6">
        {/* Input section — hidden once we have results */}
        {!batchResult && !singleResult && (
          <>
            {/* Text input */}
            <div className="elc-card">
              <label className="text-sm font-semibold text-foreground block mb-2">
                Tracking number o ID ordine
              </label>
              <textarea
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                rows={5}
                placeholder={"Inserisci uno o più tracking number, uno per riga.\nEs: 870045464495\n1Z999AA10123456784\nTESTPLAT-ORDER-123"}
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                disabled={isProcessing}
              />
              {hasInput && (
                <p className="text-xs text-muted-foreground mt-1">
                  {identifiers.length} identificativ{identifiers.length === 1 ? "o" : "i"} trovat{identifiers.length === 1 ? "o" : "i"}
                </p>
              )}
            </div>

            {/* Submit */}
            <Button
              onClick={handleSubmit}
              disabled={!hasInput || singleMutation.isPending || batchMutation.isPending || isProcessing}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              {singleMutation.isPending
                ? "Ricerca POD..."
                : batchMutation.isPending || isProcessing
                  ? "Elaborazione..."
                  : identifiers.length === 1
                    ? "Cerca POD"
                    : `Cerca ${identifiers.length} POD`}
            </Button>

            {/* Errors */}
            {singleMutation.error && (
              <p className="text-sm text-destructive text-center">
                {singleMutation.error instanceof Error ? singleMutation.error.message : "Errore"}
              </p>
            )}
            {batchMutation.error && (
              <p className="text-sm text-destructive text-center">
                {batchMutation.error instanceof Error ? batchMutation.error.message : "Errore"}
              </p>
            )}

            {/* Processing spinner */}
            {isProcessing && (
              <div className="elc-card text-center py-8">
                <div className="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
                <p className="text-sm font-semibold text-foreground">
                  Ricerca POD in corso...
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Potrebbe richiedere alcuni minuti per file grandi
                </p>
              </div>
            )}

            {/* Job error */}
            {jobStatus === "failed" && (
              <div className="elc-card text-center py-6 space-y-3">
                <p className="text-sm font-semibold text-destructive">Errore</p>
                <p className="text-sm text-muted-foreground">{jobError || "Errore sconosciuto"}</p>
                <Button variant="outline" onClick={handleReset}>Riprova</Button>
              </div>
            )}
          </>
        )}

        {/* Single result */}
        {singleResult && (
          <div className="space-y-4">
            <div className="elc-card">
              {singleResult.status === "found" ? (
                <div className="text-center py-4 space-y-2">
                  <div className="text-4xl mb-2">&#9989;</div>
                  <p className="text-sm font-semibold text-foreground">POD scaricato</p>
                  <p className="text-xs text-muted-foreground">
                    {singleResult.tracking_number} {singleResult.carrier ? `(${singleResult.carrier})` : ""}
                  </p>
                </div>
              ) : (
                <div className="text-center py-4 space-y-2">
                  <div className="text-4xl mb-2">&#10060;</div>
                  <p className="text-sm font-semibold text-foreground">
                    {STATUS_LABELS[singleResult.status] || singleResult.status}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {singleResult.error_message || "POD non disponibile"}
                  </p>
                </div>
              )}
            </div>
            <div className="text-center">
              <Button variant="outline" onClick={handleReset}>Nuova ricerca</Button>
            </div>
          </div>
        )}

        {/* Batch results */}
        {batchResult && (
          <div className="space-y-4">
            {/* Summary */}
            <div className="elc-card">
              <div className="flex flex-wrap gap-3">
                <Badge variant="outline" className="text-xs px-3 py-1 bg-emerald-50 border-emerald-300 text-emerald-700">
                  {batchResult.summary.found} trovati
                </Badge>
                {batchResult.summary.no_pod > 0 && (
                  <Badge variant="outline" className="text-xs px-3 py-1 bg-amber-50 border-amber-300 text-amber-700">
                    {batchResult.summary.no_pod} non disponibili
                  </Badge>
                )}
                {batchResult.summary.unmatched > 0 && (
                  <Badge variant="outline" className="text-xs px-3 py-1">
                    {batchResult.summary.unmatched} non trovati
                  </Badge>
                )}
                {batchResult.summary.error > 0 && (
                  <Badge variant="outline" className="text-xs px-3 py-1 bg-red-50 border-red-300 text-red-700">
                    {batchResult.summary.error} errori
                  </Badge>
                )}
              </div>
            </div>

            {/* ZIP download */}
            {batchResult.summary.found > 0 && (
              <Button
                onClick={handleDownloadZip}
                disabled={isDownloadingZip}
                className="bg-primary hover:bg-primary/90 text-white w-full"
              >
                {isDownloadingZip
                  ? "Download in corso..."
                  : `Scarica ${batchResult.summary.found} POD (ZIP)`}
              </Button>
            )}

            {/* Results table */}
            <div className="elc-card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Identificativo</th>
                    <th className="pb-2 pr-4">Tracking</th>
                    <th className="pb-2 pr-4">Corriere</th>
                    <th className="pb-2">Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {batchResult.results.map((item, i) => (
                    <tr key={i} className="border-b border-border/50 last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{item.input_value}</td>
                      <td className="py-2 pr-4 font-mono text-xs">{item.tracking_number || "—"}</td>
                      <td className="py-2 pr-4 text-xs">{item.carrier || "—"}</td>
                      <td className="py-2">
                        <Badge variant="outline" className={`text-xs ${STATUS_COLORS[item.status] || ""}`}>
                          {STATUS_LABELS[item.status] || item.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Reset */}
            <div className="text-center">
              <Button variant="outline" onClick={handleReset}>Nuova ricerca</Button>
            </div>

            {/* Dev mode */}
            {isDevMode && (
              <details className="elc-card">
                <summary className="text-sm font-medium text-muted-foreground cursor-pointer">
                  Debug: Raw Result
                </summary>
                <pre className="mt-3 text-xs overflow-auto p-3 bg-[var(--color-surface)] rounded-md">
                  {JSON.stringify(batchResult, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </div>
    </PageShell>
  )
}
