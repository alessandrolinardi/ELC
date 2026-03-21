import { useState, useEffect, useCallback } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/api/client"
import { confirmValidation } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { StepIndicator } from "@/components/StepIndicator"
import { FileDropZone } from "@/components/FileDropZone"
import { SegmentedProgressBar, buildValidatorSegments } from "@/components/SegmentedProgressBar"
import { DownloadCard } from "@/components/DownloadCard"
import { ResultsTable } from "@/components/ResultsTable"
import { ParseReviewTable } from "@/components/ParseReviewTable"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import type {
  ValidatorJobResult,
  JobCreatedResponse,
  ParsedJobResult,
  ConfirmRequest,
} from "@/lib/types"

const STEPS = [
  { label: "Carica" },
  { label: "Revisione AI" },
  { label: "Valida" },
  { label: "Risultato" },
]

export default function AddressValidator() {
  const queryClient = useQueryClient()
  const [isDevMode] = useDevMode()
  const [currentStep, setCurrentStep] = useState(0)
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [confidence, setConfidence] = useState(90)
  const [streetConfidence, setStreetConfidence] = useState(85)
  const [bypassPin, setBypassPin] = useState("")

  // Edit state for the review step (Phase 1)
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({})

  // Edit state for results step (Phase 2 results review)
  const [resultEdits, setResultEdits] = useState<Record<string, Record<string, string>>>({})
  const [filesReady, setFilesReady] = useState(false)

  // Job polling — result type varies by phase
  // During Phase 1 (parsing): result is ParsedJobResult
  // During Phase 2 (validation): result is ValidatorJobResult
  const {
    status: jobStatus,
    progress,
    result: rawResult,
    error: jobError,
    isExpired,
  } = useJobPolling<ParsedJobResult | ValidatorJobResult>(jobId)

  // Step transitions based on job status
  useEffect(() => {
    if (jobStatus === "parsed" && currentStep === 0) {
      setCurrentStep(1)
    }
  }, [jobStatus, currentStep])

  useEffect(() => {
    if (jobStatus === "complete" && currentStep === 2) {
      setCurrentStep(3)
    }
  }, [jobStatus, currentStep])

  // Typed result accessors
  const parsedResult = jobStatus === "parsed" ? (rawResult as ParsedJobResult | null) : null
  const validatorResult = jobStatus === "complete" ? (rawResult as ValidatorJobResult | null) : null

  // Submit mutation (Phase 1: upload + parse)
  const submitMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append("excel_file", file)
      formData.append("confidence_threshold", String(confidence))
      formData.append("street_confidence_threshold", String(streetConfidence))
      if (bypassPin) formData.append("bypass_pin", bypassPin)
      return api.postForm<JobCreatedResponse>("/api/v1/jobs/validator", formData)
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
      // Stay on step 0 — the useEffect will advance to step 1 when status="parsed"
    },
  })

  // Confirm mutation (Phase 2: send edits, start Google validation)
  const confirmMutation = useMutation({
    mutationFn: async (body: ConfirmRequest) => {
      return confirmValidation(jobId!, body)
    },
    onSuccess: () => {
      // Move to step 2 (validation spinner)
      setCurrentStep(2)
      // Invalidate the polling query so it refetches and sees "processing_validate"
      queryClient.invalidateQueries({ queryKey: ["job-status", jobId] })
    },
  })

  // Edit handler for ParseReviewTable
  const handleEditRow = useCallback((index: number, field: string, value: string) => {
    setEdits((prev) => ({
      ...prev,
      [String(index)]: {
        ...(prev[String(index)] || {}),
        [field]: value,
      },
    }))
  }, [])

  // Confirm handler
  const handleConfirm = useCallback(() => {
    confirmMutation.mutate({ edits, retry_regex_rows: false })
  }, [confirmMutation, edits])

  // Retry regex handler
  const handleRetryRegex = useCallback(() => {
    confirmMutation.mutate({ edits, retry_regex_rows: true })
  }, [confirmMutation, edits])

  // Edit handler for results table (Phase 2)
  const handleResultEdit = useCallback((index: number, field: string, value: string) => {
    setResultEdits((prev) => ({
      ...prev,
      [String(index)]: {
        ...(prev[String(index)] || {}),
        [field]: value,
      },
    }))
  }, [])

  // Generate files mutation
  const generateMutation = useMutation({
    mutationFn: async () => {
      if (Object.keys(resultEdits).length > 0) {
        // Apply user corrections then generate
        return api.post(`/api/v1/jobs/${jobId}/apply-corrections`, {
          corrections: resultEdits,
        })
      }
      // No edits — files already exist from Phase 2
      return Promise.resolve()
    },
    onSuccess: () => {
      setFilesReady(true)
    },
  })

  const handleGenerate = useCallback(() => {
    generateMutation.mutate()
  }, [generateMutation])

  // Reset to start
  const handleReset = () => {
    setCurrentStep(0)
    setExcelFile(null)
    setJobId(null)
    setShowAdvanced(false)
    setBypassPin("")
    setEdits({})
    setResultEdits({})
    setFilesReady(false)
  }

  return (
    <PageShell
      title="Address Validator"
      subtitle="Valida e correggi indirizzi italiani da file Excel."
      stepIndicator={<StepIndicator steps={STEPS} currentStep={currentStep} />}
    >
      <div className="space-y-6">

        {/* === STEP 0: Upload === */}
        {currentStep === 0 && (
          <>
            <FileDropZone
              label="Carica file Excel"
              subtitle="Formato .xlsx o .xls con colonne indirizzo"
              accept=".xlsx,.xls"
              icon={"\uD83D\uDCCA"}
              maxSizeMB={50}
              onFilesSelected={(files) => setExcelFile(files[0] || null)}
              selectedFiles={excelFile ? [excelFile] : []}
            />

            {/* Usage stats placeholder */}
            <div className="text-sm text-muted-foreground">
              Validazioni disponibili: <span className="font-semibold">1000</span> righe / 12 ore
            </div>

            {/* Advanced options */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-sm text-primary font-medium hover:underline"
            >
              {showAdvanced ? "Nascondi opzioni avanzate \u25B4" : "Opzioni avanzate \u25BE"}
            </button>

            {showAdvanced && (
              <div className="elc-card space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Soglia confidenza CAP (%)
                    </Label>
                    <Input
                      type="number"
                      min={50}
                      max={100}
                      value={confidence}
                      onChange={(e) => setConfidence(Number(e.target.value))}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Soglia confidenza via (%)
                    </Label>
                    <Input
                      type="number"
                      min={50}
                      max={100}
                      value={streetConfidence}
                      onChange={(e) => setStreetConfidence(Number(e.target.value))}
                      className="mt-1"
                    />
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">PIN bypass (opzionale)</Label>
                  <Input
                    type="password"
                    value={bypassPin}
                    onChange={(e) => setBypassPin(e.target.value)}
                    className="mt-1 max-w-[200px]"
                    placeholder="PIN per bypassare il limite"
                  />
                </div>
              </div>
            )}

            <Button
              onClick={() => excelFile && submitMutation.mutate(excelFile)}
              disabled={!excelFile || submitMutation.isPending}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              {submitMutation.isPending ? "Avvio..." : "Avvia Validazione"}
            </Button>

            {submitMutation.error && (
              <p className="text-sm text-destructive">
                {submitMutation.error instanceof Error
                  ? submitMutation.error.message
                  : "Errore durante l'invio"}
              </p>
            )}

            {/* Parsing in progress (between upload and "parsed" status) */}
            {jobId && jobStatus !== "parsed" && jobStatus !== "failed" && !isExpired && (
              <div className="elc-card text-center py-8">
                <div className="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
                <p className="text-sm font-semibold text-foreground">
                  Parsing AI in corso...
                </p>
                {progress && (
                  <div className="mt-3 max-w-xs mx-auto">
                    <div className="w-full bg-muted rounded-full h-2">
                      <div
                        className="bg-primary h-2 rounded-full transition-all duration-300"
                        style={{
                          width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">
                      {progress.message || `${progress.current} / ${progress.total}`}
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* === STEP 1: AI Review === */}
        {currentStep === 1 && (
          <>
            {isExpired ? (
              <div className="elc-card text-center py-12">
                <p className="text-lg font-semibold text-foreground mb-2">
                  Job scaduto
                </p>
                <p className="text-sm text-muted-foreground mb-6">
                  Il server e stato riavviato. Riprova.
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </div>
            ) : jobStatus === "failed" ? (
              <div className="elc-card text-center py-12">
                <p className="text-lg font-semibold text-destructive mb-2">
                  Errore
                </p>
                <p className="text-sm text-muted-foreground mb-6">
                  {jobError}
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </div>
            ) : parsedResult ? (
              <>
                <ParseReviewTable
                  rows={parsedResult.rows}
                  summary={parsedResult.parsing_summary}
                  edits={edits}
                  onEditRow={handleEditRow}
                  onRetryRegex={handleRetryRegex}
                  onConfirm={handleConfirm}
                  isConfirming={confirmMutation.isPending}
                />

                {confirmMutation.error && (
                  <p className="text-sm text-destructive text-center">
                    {confirmMutation.error instanceof Error
                      ? confirmMutation.error.message
                      : "Errore durante la conferma"}
                  </p>
                )}

                {/* Dev mode debug */}
                {isDevMode && (
                  <details className="elc-card">
                    <summary className="text-sm font-medium text-muted-foreground cursor-pointer">
                      Debug: Parsed Result
                    </summary>
                    <pre className="mt-3 text-xs overflow-auto p-3 bg-[var(--color-surface)] rounded-md">
                      {JSON.stringify(parsedResult, null, 2)}
                    </pre>
                  </details>
                )}
              </>
            ) : (
              /* Still loading parsed data */
              <div className="elc-card text-center py-12">
                <div className="inline-block w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4" />
                <p className="text-lg font-semibold text-foreground">
                  Parsing AI in corso...
                </p>
              </div>
            )}
          </>
        )}

        {/* === STEP 2: Google Validation (processing) === */}
        {currentStep === 2 && (
          <div className="elc-card text-center py-12">
            {isExpired ? (
              <>
                <p className="text-lg font-semibold text-foreground mb-2">
                  Job scaduto
                </p>
                <p className="text-sm text-muted-foreground mb-6">
                  Il server e stato riavviato. Riprova.
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </>
            ) : jobStatus === "failed" ? (
              <>
                <p className="text-lg font-semibold text-destructive mb-2">
                  Errore
                </p>
                <p className="text-sm text-muted-foreground mb-6">
                  {jobError}
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </>
            ) : (
              <>
                {/* Spinner */}
                <div className="inline-block w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4" />
                <p className="text-lg font-semibold text-foreground">
                  Validazione Google in corso...
                </p>
                {progress && (
                  <div className="mt-4 max-w-xs mx-auto">
                    <div className="w-full bg-muted rounded-full h-2">
                      <div
                        className="bg-primary h-2 rounded-full transition-all duration-300"
                        style={{
                          width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">
                      {progress.message || `${progress.current} / ${progress.total}`}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* === STEP 3: Results === */}
        {currentStep === 3 && validatorResult && (
          <>
            {/* Progress bar */}
            <div className="elc-card">
              <SegmentedProgressBar
                segments={buildValidatorSegments(validatorResult)}
                total={validatorResult.total_rows}
              />

              {/* Breakdown chips */}
              <div className="flex flex-wrap gap-3 mt-4">
                <Badge variant="outline" className="text-xs px-3 py-1">
                  CAP: {validatorResult.valid_count} {"\u2713"} {"\u00B7"} {validatorResult.corrected_count} corretti {"\u00B7"} {validatorResult.review_count} {"\u26A0"}
                </Badge>
                <Badge variant="outline" className="text-xs px-3 py-1">
                  Vie: {validatorResult.street_verified_count} {"\u2713"} {"\u00B7"} {validatorResult.street_corrected_count} corrette
                </Badge>
                {validatorResult.skipped_count > 0 && (
                  <Badge variant="outline" className="text-xs px-3 py-1">
                    {validatorResult.skipped_count} non-IT saltati
                  </Badge>
                )}
                {validatorResult.po_invalid_count > 0 && (
                  <Badge variant="destructive" className="text-xs px-3 py-1">
                    {validatorResult.po_invalid_count} PO non validi
                  </Badge>
                )}
              </div>
            </div>

            {/* PO warning */}
            {validatorResult.po_invalid_count > 0 && (
              <div className="rounded-lg bg-[#fef2f2] border border-destructive/20 px-5 py-4">
                <p className="text-sm font-semibold text-red-800">
                  Attenzione: {validatorResult.po_invalid_count} PO non validi trovati
                </p>
                <p className="text-sm text-red-700 mt-1">
                  Correggi i PO nel file originale oppure inserisci il PIN per scaricare comunque.
                </p>
              </div>
            )}

            {/* Results table with inline edit + generate */}
            <ResultsTable
              rows={validatorResult.results}
              devMode={isDevMode}
              edits={resultEdits}
              onEditRow={handleResultEdit}
              onGenerate={handleGenerate}
              isGenerating={generateMutation.isPending}
              filesReady={filesReady}
            />

            {generateMutation.error && (
              <p className="text-sm text-destructive text-center">
                {generateMutation.error instanceof Error
                  ? generateMutation.error.message
                  : "Errore durante la generazione"}
              </p>
            )}

            {/* Download cards — only after user confirms */}
            {filesReady && (
              <div className="grid grid-cols-2 gap-4">
                <DownloadCard
                  label="File corretto"
                  subtitle="Excel con correzioni applicate"
                  href={api.fileUrl(jobId!, "corrected.xlsx")}
                  variant="primary"
                  icon={"\uD83D\uDCCA"}
                />
                <DownloadCard
                  label="Report revisione"
                  subtitle="Dettaglio righe da verificare"
                  href={api.fileUrl(jobId!, "review.xlsx")}
                  variant={validatorResult.review_count > 0 ? "secondary" : "disabled"}
                  icon={"\uD83D\uDCCB"}
                />
              </div>
            )}

            {/* Reset button */}
            <div className="text-center">
              <Button variant="outline" onClick={handleReset}>
                Nuova validazione
              </Button>
            </div>

            {/* Dev mode debug */}
            {isDevMode && (
              <details className="elc-card">
                <summary className="text-sm font-medium text-muted-foreground cursor-pointer">
                  Debug: Raw Result
                </summary>
                <pre className="mt-3 text-xs overflow-auto p-3 bg-[var(--color-surface)] rounded-md">
                  {JSON.stringify(validatorResult, null, 2)}
                </pre>
              </details>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
