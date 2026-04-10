import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { submitFreightRequest } from "@/api/client"
import { FileDropZone } from "@/components/FileDropZone"
import { AddressCombobox } from "@/components/AddressCombobox"
import { Button } from "@/components/ui/button"
import type { Address, AddressCreate, FreightRequestResponse } from "@/lib/types"
import type { ManualAddressData } from "@/components/AddressCombobox"

interface FreightRequestTabProps {
  addresses: Address[]
  selectedAddress: Address | null
  onAddressSelect: (addr: Address) => void
  onManualEntry: (data: ManualAddressData) => void
  onOpenDrawer: () => void
  onSaveAndUse: (data: AddressCreate) => Promise<void>
  addressesLoading: boolean
}

export function FreightRequestTab({
  addresses,
  selectedAddress,
  onAddressSelect,
  onManualEntry,
  onOpenDrawer,
  onSaveAndUse,
  addressesLoading,
}: FreightRequestTabProps) {
  const [file, setFile] = useState<File | null>(null)
  const [notes, setNotes] = useState("")
  const [successResult, setSuccessResult] = useState<FreightRequestResponse | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("File richiesto")
      if (!selectedAddress) throw new Error("Seleziona un indirizzo mittente")

      const formData = new FormData()
      formData.append("file", file)
      formData.append("from_name", selectedAddress.contact_name || selectedAddress.company || selectedAddress.name)
      formData.append("from_company", selectedAddress.company || "")
      formData.append("from_street1", selectedAddress.street)
      formData.append("from_city", selectedAddress.city)
      if (selectedAddress.province) formData.append("from_state", selectedAddress.province)
      formData.append("from_zip", selectedAddress.zip)
      formData.append("from_country", "IT")
      formData.append("from_phone", selectedAddress.phone || "")
      if (notes.trim()) formData.append("notes", notes.trim())

      return submitFreightRequest(formData)
    },
    onSuccess: (data) => {
      setSuccessResult(data)
      setFile(null)
      setNotes("")
    },
  })

  return (
    <div className="space-y-6">
      {/* Success banner */}
      {successResult && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-4">
          <p className="text-sm font-semibold text-emerald-800">Richiesta inviata al team</p>
          <p className="text-sm text-emerald-700 mt-1">Riferimento: {successResult.reference_id}</p>
        </div>
      )}

      {/* File upload */}
      <FileDropZone
        label="File spedizioni freight"
        subtitle="Excel o CSV con dettagli spedizioni"
        accept=".xlsx,.xls,.csv"
        icon="📦"
        onFilesSelected={(files) => { setFile(files[0] || null); setSuccessResult(null) }}
        selectedFiles={file ? [file] : []}
      />

      {/* Address */}
      <div className="elc-card">
        <div className="flex items-center justify-between mb-4">
          <label className="text-sm font-semibold text-foreground">Indirizzo mittente</label>
        </div>
        <AddressCombobox
          addresses={addresses}
          selectedAddress={selectedAddress}
          onSelect={onAddressSelect}
          onManualEntry={onManualEntry}
          onOpenDrawer={onOpenDrawer}
          onSaveAndUse={onSaveAndUse}
          isLoading={addressesLoading}
        />
      </div>

      {/* Notes */}
      <div className="elc-card">
        <label className="block text-sm font-semibold text-foreground mb-2">Note (opzionale)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 500))}
          placeholder="Es. urgente, consegna con sponda..."
          className="w-full border border-border rounded-lg px-3 py-2 text-sm resize-y min-h-[60px] bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
          disabled={mutation.isPending}
        />
        <p className="text-xs text-muted-foreground mt-1 text-right">{notes.length}/500</p>
      </div>

      {/* Submit */}
      <Button
        onClick={() => mutation.mutate()}
        disabled={!file || !selectedAddress || mutation.isPending}
        className="bg-primary hover:bg-primary/90 text-white w-full"
      >
        {mutation.isPending ? "Invio in corso..." : "Invia richiesta freight"}
      </Button>

      {/* Error */}
      {mutation.error && (
        <p className="text-sm text-destructive text-center">
          {mutation.error instanceof Error ? mutation.error.message : "Errore durante l'invio"}
        </p>
      )}
    </div>
  )
}
