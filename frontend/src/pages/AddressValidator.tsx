import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { StepIndicator } from "@/components/StepIndicator"
import { FileDropZone } from "@/components/FileDropZone"
import { SegmentedProgressBar, buildValidatorSegments } from "@/components/SegmentedProgressBar"
import { DownloadCard } from "@/components/DownloadCard"
import { ResultsTable } from "@/components/ResultsTable"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import type { ValidatorJobResult, JobCreatedResponse } from "@/lib/types"

const STEPS = [
  { label: "Carica" },
  { label: "Valida" },
  { label: "Risultato" },
]

export default function AddressValidator() {
  const [isDevMode] = useDevMode()
  const [currentStep, setCurrentStep] = useState(0)
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [confidence, setConfidence] = useState(90)
  const [streetConfidence, setStreetConfidence] = useState(85)
  const [bypassPin, setBypassPin] = useState("")

  // Job polling
  const {
    status: jobStatus,
    progress,
    result,
    error: jobError,
    isExpired,
  } = useJobPolling<ValidatorJobResult>(jobId)

  // Move to results when job completes
  if (jobStatus === "complete" && currentStep === 1) {
    setCurrentStep(2)
  }

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData()
      formData.append("excel_file", excelFile!)
      formData.append("confidence_threshold", String(confidence))
      formData.append("street_confidence_threshold", String(streetConfidence))
      if (bypassPin) formData.append("bypass_pin", bypassPin)
      return api.postForm<JobCreatedResponse>("/api/v1/jobs/validator", formData)
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
      setCurrentStep(1)
    },
  })

  // Reset to start
  const handleReset = () => {
    setCurrentStep(0)
    setExcelFile(null)
    setJobId(null)
    setShowAdvanced(false)
    setBypassPin("")
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
              onClick={() => submitMutation.mutate()}
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
          </>
        )}

        {/* === STEP 1: Processing === */}
        {currentStep === 1 && (
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
                  Validazione in corso...
                </p>
                {progress && (
                  <div className="mt-4 max-w-xs mx-auto">
                    <div className="w-full bg-muted rounded-full h-2">
                      <div
                        className="bg-primary h-2 rounded-full transition-all duration-300"
                        style={{
                          width: `${(progress.current / progress.total) * 100}%`,
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

        {/* === STEP 2: Results === */}
        {currentStep === 2 && result && (
          <>
            {/* Progress bar */}
            <div className="elc-card">
              <SegmentedProgressBar
                segments={buildValidatorSegments(result)}
                total={result.total_rows}
              />

              {/* Breakdown chips */}
              <div className="flex flex-wrap gap-3 mt-4">
                <Badge variant="outline" className="text-xs px-3 py-1">
                  CAP: {result.valid_count} \u2713 \u00B7 {result.corrected_count} corretti \u00B7 {result.review_count} \u26A0
                </Badge>
                <Badge variant="outline" className="text-xs px-3 py-1">
                  Vie: {result.street_verified_count} \u2713 \u00B7 {result.street_corrected_count} corrette
                </Badge>
                {result.skipped_count > 0 && (
                  <Badge variant="outline" className="text-xs px-3 py-1">
                    {result.skipped_count} non-IT saltati
                  </Badge>
                )}
                {result.po_invalid_count > 0 && (
                  <Badge variant="destructive" className="text-xs px-3 py-1">
                    {result.po_invalid_count} PO non validi
                  </Badge>
                )}
              </div>
            </div>

            {/* PO warning */}
            {result.po_invalid_count > 0 && (
              <div className="rounded-lg bg-[#fef2f2] border border-destructive/20 px-5 py-4">
                <p className="text-sm font-semibold text-red-800">
                  Attenzione: {result.po_invalid_count} PO non validi trovati
                </p>
                <p className="text-sm text-red-700 mt-1">
                  Correggi i PO nel file originale oppure inserisci il PIN per scaricare comunque.
                </p>
              </div>
            )}

            {/* Download cards */}
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
                variant={result.review_count > 0 ? "secondary" : "disabled"}
                icon={"\uD83D\uDCCB"}
              />
            </div>

            {/* Results table */}
            <ResultsTable rows={result.results} devMode={isDevMode} />

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
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
