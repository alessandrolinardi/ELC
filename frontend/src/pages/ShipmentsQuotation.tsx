import { useState, useEffect, useCallback, useRef } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { FileDropZone } from "@/components/FileDropZone"
import { AddressCombobox } from "@/components/AddressCombobox"
import { AddressDrawer } from "@/components/AddressDrawer"
import { useAddresses } from "@/hooks/useAddresses"
import { useJobPolling } from "@/hooks/useJobPolling"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { Address, ShipmentsQuotationResult, CarrierQuote, JobCreatedResponse } from "@/lib/types"
import type { ManualAddressData } from "@/components/AddressCombobox"

const CARRIER_DISPLAY: Record<string, string> = {
  MyDHL: "DHL",
  UPSv2: "UPS",
  FedExv2: "FedEx",
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}m ${s.toString().padStart(2, "0")}s` : `${s}s`
}

export default function ShipmentsQuotation() {
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [copied, setCopied] = useState(false)

  const progressRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const {
    addresses,
    isLoading: addressesLoading,
    createAddress,
    updateAddress,
    deleteAddress,
    setDefault,
  } = useAddresses()

  const { status: jobStatus, progress, result: rawResult, error: jobError } =
    useJobPolling<ShipmentsQuotationResult>(jobId)

  const quotationResult = jobStatus === "complete" ? (rawResult as ShipmentsQuotationResult) : null

  const isProcessing = !!jobId && jobStatus !== "complete" && jobStatus !== "failed"

  // Live elapsed timer during processing
  useEffect(() => {
    if (isProcessing) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((prev) => prev + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isProcessing])

  // Auto-scroll to progress
  useEffect(() => {
    if (isProcessing && progressRef.current) {
      progressRef.current.scrollIntoView({ behavior: "smooth", block: "center" })
    }
  }, [isProcessing])

  // Auto-select default address
  const selectAddress = useCallback((addr: Address) => {
    setSelectedAddress(addr)
  }, [])

  useEffect(() => {
    if (addresses.length > 0 && !selectedAddress) {
      const defaultAddr = addresses.find((a) => a.is_default) || addresses[0]
      selectAddress(defaultAddr)
    }
  }, [addresses, selectedAddress, selectAddress])

  const handleManualEntry = (data: ManualAddressData) => {
    setSelectedAddress({
      id: "__manual__",
      name: "Manuale",
      company: data.company,
      contact_name: data.contact_name,
      street: data.address,
      zip: data.zip_code,
      city: data.city,
      province: data.province,
      phone: data.phone,
      reference: data.reference,
      is_default: false,
    })
  }

  const handleSaveAndUse = async (data: Parameters<typeof createAddress>[0]) => {
    const result = await createAddress(data)
    if (result && "id" in result) {
      setSelectedAddress({
        id: result.id,
        name: data.name,
        company: data.company,
        contact_name: data.contact_name ?? "",
        street: data.street,
        zip: data.zip_code,
        city: data.city,
        province: data.province ?? "",
        phone: data.phone ?? "",
        reference: data.reference ?? "",
        is_default: data.is_default ?? false,
      })
    }
  }

  // Submit
  const submitMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!selectedAddress) throw new Error("Seleziona un indirizzo mittente")
      const formData = new FormData()
      formData.append("file", file)
      formData.append("from_name", selectedAddress.contact_name || selectedAddress.company || selectedAddress.name)
      if (selectedAddress.company) formData.append("from_company", selectedAddress.company)
      formData.append("from_street1", selectedAddress.street)
      formData.append("from_city", selectedAddress.city)
      if (selectedAddress.province) formData.append("from_state", selectedAddress.province)
      formData.append("from_zip", selectedAddress.zip)
      formData.append("from_country", "IT")
      formData.append("from_phone", selectedAddress.phone || "0000000000")
      return api.postForm<JobCreatedResponse>("/api/v1/jobs/shipments-quotation", formData)
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
    },
  })

  const handleSubmit = () => {
    if (excelFile) submitMutation.mutate(excelFile)
  }

  // Reset only the job, preserve file + address (#5 — retry keeps form state)
  const handleRetry = () => {
    setJobId(null)
  }

  // Full reset for new quotation
  const handleReset = () => {
    setExcelFile(null)
    setJobId(null)
  }

  // Estimated shipment count from progress message
  const shipmentCountMatch = progress?.message?.match(/(\d+) spedizioni/)
  const estimatedCount = shipmentCountMatch ? parseInt(shipmentCountMatch[1]) : null
  const estimatedMinutes = estimatedCount ? Math.max(1, Math.round(estimatedCount / 1.8 / 60)) : null
  const estimatedTotalSeconds = estimatedMinutes ? estimatedMinutes * 60 : null
  const estimatedRemaining = estimatedTotalSeconds ? Math.max(0, estimatedTotalSeconds - elapsed) : null

  // Copy results to clipboard (#4)
  const handleCopyResults = () => {
    if (!quotationResult) return
    const lines = [`Quotazione: ${quotationResult.shipment_count} spedizioni\n`]
    for (const [key, data] of Object.entries(quotationResult.carriers)) {
      const name = CARRIER_DISPLAY[key] || key
      const total = data.total_with_markup.toLocaleString("it-IT", { minimumFractionDigits: 2 })
      lines.push(`${name}: €${total} (${data.rated_count}/${quotationResult.shipment_count} quotate${data.error_count ? `, ${data.error_count} errori` : ""})`)
    }
    navigator.clipboard.writeText(lines.join("\n"))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Find cheapest carrier
  const cheapestCarrier = quotationResult
    ? Object.entries(quotationResult.carriers).reduce<string | null>((best, [name, data]) => {
        if (!best) return name
        return data.total_with_markup < quotationResult.carriers[best].total_with_markup ? name : best
      }, null)
    : null

  return (
    <PageShell title="Quotazione Spedizioni" subtitle="Carica un file Excel per ottenere tariffe da DHL, UPS e FedEx.">
      <div className="space-y-6">
        {/* Upload + Address */}
        {!quotationResult && (
          <>
            <FileDropZone
              label="File spedizioni"
              subtitle="Excel con indirizzi e dimensioni colli"
              accept=".xlsx,.xls"
              icon="📦"
              onFilesSelected={(files) => setExcelFile(files[0] || null)}
              selectedFiles={excelFile ? [excelFile] : []}
            />

            <div className="elc-card">
              <div className="flex items-center justify-between mb-4">
                <label className="text-sm font-semibold text-foreground">Indirizzo mittente</label>
              </div>
              <AddressCombobox
                addresses={addresses}
                selectedAddress={selectedAddress}
                onSelect={selectAddress}
                onManualEntry={handleManualEntry}
                onOpenDrawer={() => setDrawerOpen(true)}
                onSaveAndUse={handleSaveAndUse}
                isLoading={addressesLoading}
              />
            </div>

            <Button
              onClick={handleSubmit}
              disabled={!excelFile || !selectedAddress || submitMutation.isPending || isProcessing}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              {submitMutation.isPending || isProcessing ? "Avvio..." : "Avvia Quotazione"}
            </Button>

            {submitMutation.error && (
              <p className="text-sm text-destructive text-center">
                {submitMutation.error instanceof Error ? submitMutation.error.message : "Errore durante l'invio"}
              </p>
            )}

            {/* Progress with live timer (#1) */}
            {isProcessing && (
              <div ref={progressRef} className="elc-card text-center py-8">
                <div className="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3" />
                <p className="text-sm font-semibold text-foreground">
                  {progress?.message || "Elaborazione in corso..."}
                </p>

                {/* Pulsing progress bar — indeterminate during webhook call */}
                <div className="mt-3 max-w-xs mx-auto">
                  <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                    <div className="bg-primary h-2 rounded-full animate-pulse" style={{ width: "100%" }} />
                  </div>
                </div>

                {/* Live timer + estimated remaining */}
                <div className="mt-3 space-y-1">
                  <p className="text-sm font-medium text-foreground tabular-nums">
                    {formatElapsed(elapsed)} trascorsi
                  </p>
                  {estimatedRemaining !== null && estimatedRemaining > 0 && (
                    <p className="text-xs text-muted-foreground">
                      ~{formatElapsed(estimatedRemaining)} rimanenti{estimatedCount ? ` per ${estimatedCount} spedizioni` : ""}
                    </p>
                  )}
                  {!estimatedRemaining && (
                    <p className="text-xs text-muted-foreground">
                      Potrebbe richiedere alcuni minuti per file grandi
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Job error — retry preserves form state (#5) */}
            {jobStatus === "failed" && (
              <div className="elc-card text-center py-6 space-y-3">
                <p className="text-sm font-semibold text-destructive">Errore</p>
                <p className="text-sm text-muted-foreground">{jobError || "Errore sconosciuto"}</p>
                <Button variant="outline" onClick={handleRetry}>Riprova</Button>
              </div>
            )}
          </>
        )}

        {/* Results */}
        {quotationResult && (
          <div className="space-y-6">
            {/* Summary */}
            <div className="text-center text-sm text-muted-foreground">
              {quotationResult.shipment_count} spedizioni analizzate in{" "}
              {quotationResult.processing_time_seconds < 60
                ? `${Math.round(quotationResult.processing_time_seconds)}s`
                : `${Math.round(quotationResult.processing_time_seconds / 60)} min`}
            </div>

            {/* Carrier cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Object.entries(quotationResult.carriers).map(([carrierKey, data]) => (
                <CarrierCard
                  key={carrierKey}
                  carrierKey={carrierKey}
                  data={data}
                  totalShipments={quotationResult.shipment_count}
                  isCheapest={carrierKey === cheapestCarrier}
                />
              ))}
            </div>

            {/* Actions (#4 — copy results) */}
            <div className="flex justify-center gap-3">
              <Button variant="outline" onClick={handleCopyResults}>
                {copied ? "Copiato!" : "Copia risultati"}
              </Button>
              <Button variant="outline" onClick={handleReset}>Nuova quotazione</Button>
            </div>
          </div>
        )}
      </div>

      <AddressDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        addresses={addresses}
        onAdd={async (data) => { await createAddress(data) }}
        onUpdate={async (id, data) => { await updateAddress({ id, data }) }}
        onDelete={async (id) => {
          await deleteAddress(id)
          if (selectedAddress?.id === id) setSelectedAddress(null)
        }}
        onSetDefault={async (id) => { await setDefault(id) }}
      />
    </PageShell>
  )
}

// --- Carrier Card Component ---

function CarrierCard({
  carrierKey,
  data,
  totalShipments,
  isCheapest,
}: {
  carrierKey: string
  data: CarrierQuote
  totalShipments: number
  isCheapest: boolean
}) {
  const [showErrors, setShowErrors] = useState(false)
  const displayName = CARRIER_DISPLAY[carrierKey] || carrierKey

  return (
    <div
      className={`elc-card space-y-3 ${isCheapest ? "ring-2 ring-emerald-400" : ""}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">{displayName}</span>
        {isCheapest && (
          <Badge className="bg-emerald-100 text-emerald-700 border-emerald-300 text-xs">
            Più conveniente
          </Badge>
        )}
      </div>

      <p className="text-2xl font-bold text-foreground">
        €{data.total_with_markup.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </p>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{data.rated_count}/{totalShipments} quotate</span>
        {data.error_count > 0 && (
          <Badge variant="outline" className="text-xs px-2 py-0.5 border-amber-400 text-amber-700">
            {data.error_count} errori
          </Badge>
        )}
      </div>

      {data.error_count > 0 && (
        <button
          type="button"
          onClick={() => setShowErrors(!showErrors)}
          className="text-xs text-primary hover:underline"
        >
          {showErrors ? "Nascondi errori" : "Mostra errori"}
        </button>
      )}

      {showErrors && data.errors.length > 0 && (
        <div className="max-h-40 overflow-y-auto rounded border border-border text-xs">
          <table className="w-full">
            <thead className="bg-muted sticky top-0">
              <tr>
                <th className="text-left px-2 py-1 font-medium">Riga</th>
                <th className="text-left px-2 py-1 font-medium">Errore</th>
              </tr>
            </thead>
            <tbody>
              {data.errors.map((err, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="px-2 py-1 text-muted-foreground">{err.row}</td>
                  <td className="px-2 py-1">{err.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
