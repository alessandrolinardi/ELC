import { useState, useEffect } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { StepIndicator } from "@/components/StepIndicator"
import { FileDropZone } from "@/components/FileDropZone"
import { SuccessBanner } from "@/components/SuccessBanner"
import { DownloadCard } from "@/components/DownloadCard"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import type { LabelJobResult, JobCreatedResponse } from "@/lib/types"

const STEPS = [
  { label: "Carica" },
  { label: "Configura" },
  { label: "Elabora" },
  { label: "Scarica" },
]

type SortMethod = "excel_order" | "order_id_numeric"

export default function LabelSorter() {
  const [isDevMode] = useDevMode()
  const [currentStep, setCurrentStep] = useState(0)
  const [pdfFiles, setPdfFiles] = useState<File[]>([])
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [sortMethod, setSortMethod] = useState<SortMethod>("order_id_numeric")
  const [jobId, setJobId] = useState<string | null>(null)

  // Job polling
  const {
    status: jobStatus,
    progress,
    result,
    error: jobError,
    isExpired,
  } = useJobPolling<LabelJobResult>(jobId)

  // Transition to download step when complete
  useEffect(() => {
    if (jobStatus === "complete" && currentStep === 2) {
      setCurrentStep(3)
    }
  }, [jobStatus, currentStep])

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData()
      pdfFiles.forEach((f) => formData.append("pdf_files", f))
      formData.append("excel_file", excelFile!)
      formData.append("sort_method", sortMethod)
      return api.postForm<JobCreatedResponse>("/api/v1/jobs/labels", formData)
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
      setCurrentStep(2)
    },
  })

  // Reset
  const handleReset = () => {
    setCurrentStep(0)
    setPdfFiles([])
    setExcelFile(null)
    setSortMethod("order_id_numeric")
    setJobId(null)
  }

  // Can advance from upload to configure?
  const canConfigure = pdfFiles.length > 0 && excelFile !== null

  return (
    <PageShell
      title="Label Sorter"
      subtitle="Riordina le etichette PDF in base all'ordine dell'export Excel."
      stepIndicator={<StepIndicator steps={STEPS} currentStep={currentStep} />}
    >
      <div className="space-y-6">

        {/* === STEP 0: Upload === */}
        {currentStep === 0 && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <FileDropZone
                label="PDF Etichette"
                subtitle="Uno o piu file PDF con le etichette"
                accept=".pdf"
                multiple
                icon={"\uD83D\uDCC4"}
                maxSizeMB={50}
                onFilesSelected={(files) => setPdfFiles(files)}
                selectedFiles={pdfFiles}
              />
              <FileDropZone
                label="Export Excel ShippyPro"
                subtitle="File .xlsx con l'elenco ordini"
                accept=".xlsx,.xls"
                icon={"\uD83D\uDCCA"}
                maxSizeMB={50}
                onFilesSelected={(files) => setExcelFile(files[0] || null)}
                selectedFiles={excelFile ? [excelFile] : []}
              />
            </div>

            <Button
              onClick={() => setCurrentStep(1)}
              disabled={!canConfigure}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              Continua
            </Button>
          </>
        )}

        {/* === STEP 1: Configure === */}
        {currentStep === 1 && (
          <>
            <div className="elc-card">
              <Label className="text-sm font-semibold text-foreground mb-4 block">
                Metodo di ordinamento
              </Label>
              <div className="grid grid-cols-2 gap-4">
                {/* Sort method cards */}
                <button
                  type="button"
                  onClick={() => setSortMethod("order_id_numeric")}
                  className={cn(
                    "rounded-lg border-2 p-5 text-left transition-all",
                    sortMethod === "order_id_numeric"
                      ? "border-primary bg-indigo-light"
                      : "border-border hover:border-indigo-border"
                  )}
                >
                  <p className="font-semibold text-sm text-foreground">
                    Ordine numerico ID
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Ordina per numero d'ordine crescente
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setSortMethod("excel_order")}
                  className={cn(
                    "rounded-lg border-2 p-5 text-left transition-all",
                    sortMethod === "excel_order"
                      ? "border-primary bg-indigo-light"
                      : "border-border hover:border-indigo-border"
                  )}
                >
                  <p className="font-semibold text-sm text-foreground">
                    Ordine Excel
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Mantieni l'ordine delle righe nel file Excel
                  </p>
                </button>
              </div>
            </div>

            {/* File summary */}
            <div className="text-sm text-muted-foreground">
              <span className="font-medium">{pdfFiles.length}</span> PDF
              {pdfFiles.length > 1 ? " files" : ""} +{" "}
              <span className="font-medium">{excelFile?.name}</span>
            </div>

            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setCurrentStep(0)}>
                Indietro
              </Button>
              <Button
                onClick={() => submitMutation.mutate()}
                disabled={submitMutation.isPending}
                className="bg-primary hover:bg-primary/90 text-white flex-1"
              >
                {submitMutation.isPending ? "Avvio..." : "Avvia Elaborazione"}
              </Button>
            </div>

            {submitMutation.error && (
              <p className="text-sm text-destructive">
                {submitMutation.error instanceof Error
                  ? submitMutation.error.message
                  : "Errore durante l'invio"}
              </p>
            )}
          </>
        )}

        {/* === STEP 2: Processing === */}
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
                <div className="inline-block w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4" />
                <p className="text-lg font-semibold text-foreground">
                  Elaborazione in corso...
                </p>
                {progress && (
                  <p className="text-sm text-muted-foreground mt-2">
                    {progress.message || `${progress.current} / ${progress.total}`}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {/* === STEP 3: Download === */}
        {currentStep === 3 && result && (
          <>
            {/* Success banner */}
            <SuccessBanner
              message={`${result.matched} di ${result.total_pages} matchate (${result.match_rate.toFixed(1)}%)`}
              details={
                result.unmatched > 0
                  ? `${result.unmatched} non matchate in fondo al PDF`
                  : undefined
              }
            />

            {/* Download cards */}
            <div className="grid grid-cols-2 gap-4">
              <DownloadCard
                label="PDF Riordinato"
                subtitle="Etichette ordinate pronte per la stampa"
                href={api.fileUrl(jobId!, "reordered.pdf")}
                variant="primary"
                icon={"\uD83D\uDCC4"}
              />
              <DownloadCard
                label="Report CSV"
                subtitle="Dettaglio etichette non matchate"
                href={api.fileUrl(jobId!, "unmatched.csv")}
                variant={result.unmatched > 0 ? "secondary" : "disabled"}
                icon={"\uD83D\uDCCB"}
              />
            </div>

            {/* Unmatched table (if any) */}
            {result.unmatched > 0 && (
              <details className="elc-card">
                <summary className="text-sm font-medium text-muted-foreground cursor-pointer">
                  Mostra dettagli ({result.unmatched} non matchate) \u25BE
                </summary>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground border-b border-border">
                        <th className="px-4 py-2 font-medium">Pag.</th>
                        <th className="px-4 py-2 font-medium">Tracking</th>
                        <th className="px-4 py-2 font-medium">Corriere</th>
                        <th className="px-4 py-2 font-medium">Motivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.unmatched_details.map((row, i) => (
                        <tr key={i} className="border-b border-border last:border-b-0">
                          <td className="px-4 py-2">{row.page}</td>
                          <td className="px-4 py-2 font-mono text-xs">{row.tracking}</td>
                          <td className="px-4 py-2">{row.carrier}</td>
                          <td className="px-4 py-2 text-muted-foreground">{row.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}

            {/* Reset */}
            <div className="text-center">
              <Button variant="outline" onClick={handleReset}>
                Nuova elaborazione
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
