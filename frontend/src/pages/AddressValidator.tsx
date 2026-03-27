import { useState, useEffect, useCallback, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/api/client"
import { confirmValidation, fetchBrands, createBrand } from "@/api/client"
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
  const navigate = useNavigate()
  const [isDevMode] = useDevMode()
  const [currentStep, setCurrentStep] = useState(0)
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [confidence, setConfidence] = useState(90)
  const [streetConfidence, setStreetConfidence] = useState(85)
  const [bypassPin, setBypassPin] = useState("")

  const [brand, setBrand] = useState("")
  const [campaign, setCampaign] = useState("")
  const [brands, setBrands] = useState<string[]>([])
  const [showNewBrand, setShowNewBrand] = useState(false)
  const [newBrandName, setNewBrandName] = useState("")
  const [brandError, setBrandError] = useState("")
  const [poNumber, setPoNumber] = useState("")

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

  // True while a background job is running (Phase 1 or Phase 2)
  const isProcessing = !!jobId && jobStatus !== "parsed" && jobStatus !== "failed" && jobStatus !== "complete" && !isExpired
  const progressRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to progress indicator when parsing starts
  useEffect(() => {
    if (isProcessing && progressRef.current) {
      progressRef.current.scrollIntoView({ behavior: "smooth", block: "center" })
    }
  }, [isProcessing])

  // Step transitions based on job status
  useEffect(() => {
    if (jobStatus === "parsed" && currentStep === 0) {
      setCurrentStep(1)
    } else if (jobStatus === "complete" && currentStep === 2) {
      setCurrentStep(3)
    }
  }, [jobStatus, currentStep])

  useEffect(() => {
    fetchBrands().then(data => setBrands(data.map(b => b.name))).catch(() => {})
  }, [])

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
      if (brand) formData.append("brand", brand)
      if (campaign) formData.append("campaign", campaign)
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

  // PO is resolved from auto-detection or manual entry — must be present to confirm
  const detectedPo = parsedResult?.order_id_summary?.detected_po
  const resolvedPo = detectedPo || poNumber.trim()
  const poOverride = resolvedPo || undefined
  const allOrderIdsBroken = parsedResult?.order_id_summary != null
    && parsedResult.order_id_summary.valid === 0
    && parsedResult.order_id_summary.format_errors > 0
  const poMissing = parsedResult?.order_id_summary != null && !resolvedPo && !allOrderIdsBroken

  // Confirm handler
  const handleConfirm = useCallback(() => {
    confirmMutation.mutate({ edits, retry_regex_rows: false, po_override: poOverride })
  }, [confirmMutation, edits, poOverride])

  // Confirm with version bump (re-upload)
  const handleConfirmWithVersionBump = useCallback(() => {
    const summary = parsedResult?.order_id_summary
    const nextVersion = (summary?.detected_version || 1) + 1
    const bumpedCampaign = campaign ? `${campaign} V${nextVersion}` : `V${nextVersion}`
    setCampaign(bumpedCampaign)
    confirmMutation.mutate({ edits, retry_regex_rows: false, campaign_override: bumpedCampaign, po_override: poOverride })
  }, [confirmMutation, edits, parsedResult, campaign, poOverride])

  // Retry regex handler
  const handleRetryRegex = useCallback(() => {
    confirmMutation.mutate({ edits, retry_regex_rows: true, po_override: poOverride })
  }, [confirmMutation, edits, poOverride])

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
    queryClient.removeQueries({ queryKey: ["job-status"] })
    setCurrentStep(0)
    setExcelFile(null)
    setJobId(null)
    setShowAdvanced(false)
    setBypassPin("")
    setEdits({})
    setResultEdits({})
    setFilesReady(false)
    setBrand("")
    setCampaign("")
    setPoNumber("")
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

            {/* Brand + Campaign — shown after file is selected */}
            {excelFile && (
              <div className="elc-card space-y-4">
                <p className="text-sm font-semibold text-foreground">Configurazione spedizione</p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Brand <span className="text-destructive">*</span>
                    </Label>
                    {showNewBrand ? (
                      <>
                        <div className="flex gap-2 mt-1">
                          <Input
                            value={newBrandName}
                            onChange={(e) => setNewBrandName(e.target.value)}
                            placeholder="Nome brand"
                            className="flex-1"
                            autoFocus
                          />
                          <Button
                            size="sm"
                            onClick={async () => {
                              if (newBrandName.trim()) {
                                setBrandError("")
                                try {
                                  await createBrand(newBrandName)
                                  const upper = newBrandName.trim().toUpperCase()
                                  setBrands(prev => [...prev, upper].sort())
                                  setBrand(upper)
                                  setShowNewBrand(false)
                                  setNewBrandName("")
                                } catch (err) {
                                  setBrandError(err instanceof Error ? err.message : "Errore durante la creazione del brand")
                                }
                              }
                            }}
                          >
                            Salva
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => { setShowNewBrand(false); setNewBrandName(""); setBrandError("") }}>
                            Annulla
                          </Button>
                        </div>
                        {brandError && (
                          <p className="text-sm text-red-500 mt-1">{brandError}</p>
                        )}
                      </>
                    ) : (
                      <div className="relative mt-1">
                        <select
                          value={brand}
                          onChange={(e) => {
                            if (e.target.value === "__new__") setShowNewBrand(true)
                            else setBrand(e.target.value)
                          }}
                          className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring appearance-none"
                        >
                          <option value="">Seleziona brand...</option>
                          {brands.map(b => <option key={b} value={b}>{b}</option>)}
                          <option value="__new__">+ Aggiungi brand</option>
                        </select>
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">{"\u25BE"}</span>
                      </div>
                    )}
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Campagna <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      value={campaign}
                      onChange={(e) => setCampaign(e.target.value)}
                      placeholder="es. GENNAIO TRADE VISIBILITY"
                      className="mt-1"
                    />
                  </div>
                </div>
              </div>
            )}

            <Button
              onClick={() => excelFile && submitMutation.mutate(excelFile)}
              disabled={!excelFile || !brand || !campaign.trim() || submitMutation.isPending || isProcessing}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              {submitMutation.isPending || isProcessing ? "Avvio..." : "Avvia Validazione"}
            </Button>

            {submitMutation.error && (
              <p className="text-sm text-destructive">
                {submitMutation.error instanceof Error
                  ? submitMutation.error.message
                  : "Errore durante l'invio"}
              </p>
            )}

            {/* Parsing in progress (between upload and "parsed" status) */}
            {isProcessing && (
              <div ref={progressRef} className="elc-card text-center py-8">
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
                {/* Order ID Warnings — shown BEFORE the table so problems are visible first */}
                {parsedResult?.order_id_summary && parsedResult.order_id_summary.warnings.length > 0 && (
                  <div className="rounded-lg bg-amber-50 border border-amber-200 px-5 py-4 space-y-3">
                    <p className="text-sm font-semibold text-amber-800">
                      Problemi con gli Order ID
                    </p>
                    {parsedResult.order_id_summary.warnings.map((w, i) => (
                      <p key={i} className="text-sm text-amber-700">
                        {w.type === "within_file_duplicate" && "\u26A0\uFE0F "}
                        {w.type === "cross_file_duplicate" && "\uD83D\uDD04 "}
                        {w.message}
                      </p>
                    ))}
                    {parsedResult.order_id_summary.cross_file_duplicates > 0 && (
                      <div className="pt-2 border-t border-amber-200">
                        <p className="text-sm text-amber-800 font-medium">
                          È un ri-caricamento per correggere errori?
                        </p>
                        <div className="flex gap-2 mt-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleConfirmWithVersionBump}
                            disabled={confirmMutation.isPending || poMissing}
                            className="border-amber-400 text-amber-800 hover:bg-amber-100"
                          >
                            Sì, incrementa versione
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleConfirm}
                            disabled={confirmMutation.isPending || poMissing}
                            className="text-muted-foreground"
                          >
                            No, procedi comunque
                          </Button>
                        </div>
                        {poMissing && (
                          <p className="text-xs text-amber-700 mt-1">Inserisci prima il PO per poter procedere.</p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Order ID stats + PO detection */}
                {parsedResult?.order_id_summary && (
                  <div className="space-y-2">
                    <div className="flex gap-2 text-xs text-muted-foreground items-center">
                      <span>Order ID: {parsedResult.order_id_summary.valid}/{parsedResult.order_id_summary.total} validi</span>
                      {parsedResult.order_id_summary.format_errors > 0 && (
                        <Badge variant="outline" className="text-xs px-2 py-0.5 border-amber-400 text-amber-700">
                          {parsedResult.order_id_summary.format_errors} errori formato
                        </Badge>
                      )}
                      {parsedResult.order_id_summary.detected_po ? (
                        <Badge variant="outline" className="text-xs px-2 py-0.5 border-emerald-400 text-emerald-700">
                          PO: {parsedResult.order_id_summary.detected_po}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs px-2 py-0.5 border-slate-300 text-slate-500">
                          Nessun PO rilevato
                        </Badge>
                      )}
                    </div>
                    {!parsedResult.order_id_summary.detected_po && !poNumber && (
                      <div className="rounded-md bg-amber-50 border border-amber-200 px-4 py-3">
                        <p className="text-sm text-amber-800 font-medium">
                          PO non rilevato — inseriscilo per continuare
                        </p>
                        <div className="flex gap-2 mt-2 items-center">
                          <Input
                            value={poNumber}
                            onChange={(e) => setPoNumber(e.target.value)}
                            placeholder="Es. 3501494822"
                            className="w-48 h-8 text-sm"
                          />
                        </div>
                        <p className="text-xs text-amber-600 mt-1">Necessario per il tracciamento ordini</p>
                      </div>
                    )}
                    {!parsedResult.order_id_summary.detected_po && poNumber && (
                      <div className="flex gap-2 text-xs items-center">
                        <Badge variant="outline" className="px-2 py-0.5 border-blue-400 text-blue-700">
                          PO: {poNumber}
                        </Badge>
                        <button
                          type="button"
                          onClick={() => setPoNumber("")}
                          className="text-xs text-muted-foreground underline hover:text-foreground"
                        >
                          Modifica
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <ParseReviewTable
                  rows={parsedResult.rows}
                  summary={parsedResult.parsing_summary}
                  edits={edits}
                  onEditRow={handleEditRow}
                  onRetryRegex={handleRetryRegex}
                  onConfirm={handleConfirm}
                  isConfirming={confirmMutation.isPending}
                  blockReason={poMissing ? "Inserisci il PO per procedere" : undefined}
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

            {/* Quotation CTA */}
            {filesReady && (
              <div className="elc-card text-center py-6 space-y-3">
                <p className="text-sm font-semibold text-foreground">
                  Vuoi anche una quotazione?
                </p>
                <p className="text-sm text-muted-foreground">
                  Usa il file corretto per ottenere tariffe da DHL, UPS e FedEx.
                </p>
                <Button
                  onClick={() =>
                    navigate("/quotation", {
                      state: { validatorJobId: jobId },
                    })
                  }
                  className="bg-primary hover:bg-primary/90 text-white"
                >
                  Vai alla Quotazione
                </Button>
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
