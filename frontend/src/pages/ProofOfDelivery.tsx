import { useState, useCallback } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { FileDropZone } from "@/components/FileDropZone"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

const BASE_URL = import.meta.env.VITE_API_URL || ""

/** Safely decode base64 to Blob without stack overflow on large PDFs. */
function base64ToBlob(b64: string, mimeType: string): Blob {
  const raw = atob(b64)
  const bytes = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return new Blob([bytes], { type: mimeType })
}

/** Trigger a browser download from a Blob. */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

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
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [singleResult, setSingleResult] = useState<PodSingleResult | null>(null)
  const [isDownloadingZip, setIsDownloadingZip] = useState(false)
  const [zipError, setZipError] = useState<string | null>(null)

  const { status: jobStatus, result: rawResult, error: jobError } =
    useJobPolling<PodBatchResult>(jobId)

  const batchResult = jobStatus === "complete" ? (rawResult as PodBatchResult) : null

  // Extract identifiers from text input
  const getIdentifiers = useCallback((): string[] => {
    return parseIdentifiers(textInput)
  }, [textInput])

  // Single POD mutation (1 identifier → instant PDF download)
  const singleMutation = useMutation({
    mutationFn: async (identifier: string) => {
      // api.post unwraps {ok, data} → returns data directly
      return api.post<PodSingleResult>("/api/v1/jobs/pod", { identifier })
    },
    onSuccess: (data) => {
      setSingleResult(data)
      if (data.status === "found" && data.pod_base64) {
        downloadBlob(
          base64ToBlob(data.pod_base64, "application/pdf"),
          `pod_${data.tracking_number || "download"}.pdf`,
        )
      }
    },
  })

  // Bulk POD mutation (from text input)
  const batchMutation = useMutation({
    mutationFn: async (identifiers: string[]) => {
      return api.post<{ job_id: string; total: number }>(
        "/api/v1/jobs/pod-batch",
        { identifiers }
      )
    },
    onSuccess: (resp) => {
      setJobId(resp.job_id)
    },
  })

  // Excel upload mutation (server extracts tracking numbers)
  const excelMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      return api.postForm<{
        mode: "single" | "batch"
        job_id?: string
        total?: number
        identifiers_preview?: string[]
        result?: PodSingleResult
      }>("/api/v1/jobs/pod-from-excel", formData)
    },
    onSuccess: (data) => {
      if (data.mode === "single" && data.result) {
        setSingleResult(data.result)
        if (data.result.status === "found" && data.result.pod_base64) {
          downloadBlob(
            base64ToBlob(data.result.pod_base64, "application/pdf"),
            `pod_${data.result.tracking_number || "download"}.pdf`,
          )
        }
      } else if (data.mode === "batch" && data.job_id) {
        setJobId(data.job_id)
      }
    },
  })

  const handleSubmit = () => {
    // Excel file takes priority
    if (excelFile) {
      excelMutation.mutate(excelFile)
      return
    }
    const identifiers = getIdentifiers()
    if (identifiers.length === 0) return

    if (identifiers.length === 1) {
      singleMutation.mutate(identifiers[0])
    } else {
      batchMutation.mutate(identifiers)
    }
  }

  // Remote job_id from batch result for ZIP download
  const remoteJobId = batchResult?.job_id || null

  const handleDownloadZip = async () => {
    if (!remoteJobId) {
      setZipError("Job ID non disponibile. Riprova la ricerca.")
      return
    }
    setIsDownloadingZip(true)
    setZipError(null)
    try {
      const formData = new FormData()
      formData.append("remote_job_id", remoteJobId)
      const resp = await fetch(`${BASE_URL}/api/v1/jobs/pod-download-zip`, {
        method: "POST",
        body: formData,
      })
      if (!resp.ok) {
        const text = await resp.text().catch(() => "")
        throw new Error(text || `HTTP ${resp.status}`)
      }
      const blob = await resp.blob()
      downloadBlob(blob, `pod_${remoteJobId.slice(0, 8)}.zip`)
    } catch (err) {
      setZipError(err instanceof Error ? err.message : "Download fallito. Riprova.")
    } finally {
      setIsDownloadingZip(false)
    }
  }

  const handleReset = () => {
    setTextInput("")
    setExcelFile(null)
    setJobId(null)
    setSingleResult(null)
    setZipError(null)
    singleMutation.reset()
    batchMutation.reset()
    excelMutation.reset()
  }

  const identifiers = getIdentifiers()
  const isProcessing = !!jobId && jobStatus !== "complete" && jobStatus !== "failed"
  const hasInput = identifiers.length > 0 || !!excelFile
  const isSubmitting = singleMutation.isPending || batchMutation.isPending || excelMutation.isPending

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
                onChange={(e) => { setTextInput(e.target.value); setExcelFile(null) }}
                disabled={isProcessing || !!excelFile}
              />
              {identifiers.length > 0 && !excelFile && (
                <p className="text-xs text-muted-foreground mt-1">
                  {identifiers.length} identificativ{identifiers.length === 1 ? "o" : "i"} trovat{identifiers.length === 1 ? "o" : "i"}
                </p>
              )}
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 border-t border-border" />
              <span className="text-xs text-muted-foreground">oppure</span>
              <div className="flex-1 border-t border-border" />
            </div>

            {/* Excel upload */}
            <FileDropZone
              label="Carica file Excel"
              subtitle="Excel con colonna tracking (ShippyPro export, XLSX, XLS)"
              accept=".xlsx,.xls"
              icon="&#128196;"
              onFilesSelected={(files) => { setExcelFile(files[0] || null); setTextInput("") }}
              selectedFiles={excelFile ? [excelFile] : []}
            />

            {/* Submit */}
            <Button
              onClick={handleSubmit}
              disabled={!hasInput || isSubmitting || isProcessing}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              {isSubmitting
                ? "Ricerca POD..."
                : isProcessing
                  ? "Elaborazione..."
                  : excelFile
                    ? "Cerca POD da file"
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
            {excelMutation.error && (
              <p className="text-sm text-destructive text-center">
                {excelMutation.error instanceof Error ? excelMutation.error.message : "Errore lettura file"}
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

            {zipError && (
              <p className="text-sm text-destructive text-center">{zipError}</p>
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
