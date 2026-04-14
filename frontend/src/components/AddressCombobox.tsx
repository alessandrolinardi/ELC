import { useState, useRef, useEffect, useCallback } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import type { Address, AddressCreate } from "@/lib/types"

export interface ManualAddressData {
  company: string
  contact_name: string
  address: string
  zip_code: string
  city: string
  province: string
  phone: string
  reference: string
}

interface AddressComboboxProps {
  addresses: Address[]
  selectedAddress: Address | null
  onSelect: (address: Address) => void
  onManualEntry: (data: ManualAddressData) => void
  onOpenDrawer: () => void
  onSaveAndUse?: (data: AddressCreate) => Promise<void>
  onClearSelection?: () => void
  isLoading?: boolean
}

const EMPTY_MANUAL: ManualAddressData = {
  company: "",
  contact_name: "",
  address: "",
  zip_code: "",
  city: "",
  province: "",
  phone: "",
  reference: "",
}

export function AddressCombobox({
  addresses,
  selectedAddress,
  onSelect,
  onManualEntry,
  onOpenDrawer,
  onSaveAndUse,
  onClearSelection,
  isLoading,
}: AddressComboboxProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [manualMode, setManualMode] = useState(false)
  const [manualForm, setManualForm] = useState<ManualAddressData>(EMPTY_MANUAL)
  const [manualName, setManualName] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setQuery("")
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const filtered = addresses.filter((a) => {
    if (!query) return true
    const q = query.toLowerCase()
    return (
      a.name.toLowerCase().includes(q) ||
      a.company.toLowerCase().includes(q) ||
      a.street.toLowerCase().includes(q) ||
      a.city.toLowerCase().includes(q)
    )
  })

  const handleSelect = useCallback(
    (addr: Address) => {
      onSelect(addr)
      setOpen(false)
      setQuery("")
    },
    [onSelect],
  )

  const handleManualUpdate = (key: keyof ManualAddressData, value: string) => {
    setManualForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleUseWithoutSaving = () => {
    onManualEntry(manualForm)
    setManualMode(false)
    setManualForm(EMPTY_MANUAL)
    setManualName("")
  }

  const handleSaveAndUse = async () => {
    if (!onSaveAndUse) return
    setIsSaving(true)
    try {
      await onSaveAndUse({
        name: manualName || manualForm.company || "Nuovo indirizzo",
        company: manualForm.company,
        contact_name: manualForm.contact_name || undefined,
        street: manualForm.address,
        zip_code: manualForm.zip_code,
        city: manualForm.city,
        province: manualForm.province || undefined,
        phone: manualForm.phone || undefined,
        reference: manualForm.reference || undefined,
      })
      setManualMode(false)
      setManualForm(EMPTY_MANUAL)
      setManualName("")
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Caricamento indirizzi...</p>
  }

  // Manual entry mode
  if (manualMode) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => setManualMode(false)}
          className="text-sm text-primary font-medium hover:underline flex items-center gap-1"
        >
          <ChevronLeft className="size-4" />
          Torna alla rubrica
        </button>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Label className="text-xs text-muted-foreground">Nome indirizzo</Label>
            <Input
              value={manualName}
              onChange={(e) => setManualName(e.target.value)}
              placeholder="es. Ufficio Roma"
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Azienda</Label>
            <Input
              value={manualForm.company}
              onChange={(e) => handleManualUpdate("company", e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Contatto</Label>
            <Input
              value={manualForm.contact_name}
              onChange={(e) => handleManualUpdate("contact_name", e.target.value)}
              className="mt-1"
            />
          </div>
          <div className="col-span-2">
            <Label className="text-xs text-muted-foreground">Indirizzo</Label>
            <Input
              value={manualForm.address}
              onChange={(e) => handleManualUpdate("address", e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">CAP</Label>
            <Input
              value={manualForm.zip_code}
              onChange={(e) => handleManualUpdate("zip_code", e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Citta</Label>
            <Input
              value={manualForm.city}
              onChange={(e) => handleManualUpdate("city", e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Provincia</Label>
            <Input
              value={manualForm.province}
              onChange={(e) => handleManualUpdate("province", e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Telefono</Label>
            <Input
              value={manualForm.phone}
              onChange={(e) => handleManualUpdate("phone", e.target.value)}
              placeholder="Es. 0212345678"
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">Riferimento</Label>
            <Input
              value={manualForm.reference}
              onChange={(e) => handleManualUpdate("reference", e.target.value)}
              className="mt-1"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleUseWithoutSaving}
            disabled={!manualForm.company || !manualForm.address || !manualForm.city}
          >
            Usa senza salvare
          </Button>
          {onSaveAndUse && (
            <Button
              type="button"
              onClick={handleSaveAndUse}
              disabled={
                isSaving ||
                !manualForm.company ||
                !manualForm.address ||
                !manualForm.city ||
                !manualForm.zip_code
              }
              className="bg-primary hover:bg-primary/90 text-white"
            >
              {isSaving ? "Salvataggio..." : "Salva in rubrica e usa"}
            </Button>
          )}
        </div>
      </div>
    )
  }

  // Combobox mode
  return (
    <div className="space-y-3">
      <div ref={containerRef} className="relative">
        {/* Input trigger */}
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            className={cn(
              "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 pr-8 text-sm transition-colors outline-none",
              "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
              "placeholder:text-muted-foreground",
            )}
            placeholder="Seleziona indirizzo..."
            value={open ? query : selectedAddress?.name ?? ""}
            onChange={(e) => {
              setQuery(e.target.value)
              if (!open) setOpen(true)
            }}
            onFocus={() => {
              setOpen(true)
              setQuery("")
            }}
          />
          <button
            type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            onClick={() => {
              setOpen(!open)
              if (!open) {
                setQuery("")
                inputRef.current?.focus()
              }
            }}
            tabIndex={-1}
          >
            <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
          </button>
        </div>

        {/* Dropdown */}
        {open && (
          <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg max-h-72 overflow-y-auto">
            {filtered.length === 0 && query && (
              <div className="px-3 py-2 text-sm text-muted-foreground">Nessun risultato</div>
            )}
            {filtered.map((addr) => (
              <button
                key={addr.id}
                type="button"
                className={cn(
                  "w-full text-left px-3 py-2.5 hover:bg-primary/5 transition-colors flex flex-col gap-0.5",
                  selectedAddress?.id === addr.id && "border-l-2 border-l-primary bg-primary/5",
                  addr.is_default && "bg-amber-50/50 dark:bg-amber-950/10",
                )}
                onClick={() => handleSelect(addr)}
              >
                <span className="text-sm font-medium text-foreground">
                  {addr.is_default && <span className="mr-1">&#11088;</span>}
                  {addr.name}
                </span>
                <span className="text-xs text-muted-foreground">
                  {addr.company} &mdash; {addr.street}, {addr.zip} {addr.city}
                  {addr.province ? ` (${addr.province})` : ""}
                </span>
              </button>
            ))}

            <Separator />
            <button
              type="button"
              className="w-full text-left px-3 py-2.5 hover:bg-primary/5 transition-colors text-sm text-primary font-medium"
              onClick={() => {
                setOpen(false)
                setQuery("")
                setManualMode(true)
                onClearSelection?.()
              }}
            >
              Inserisci indirizzo manualmente
            </button>
          </div>
        )}
      </div>

      {/* Preview card */}
      {selectedAddress && !open && (
        <div className="rounded-lg bg-primary/5 border border-primary/10 px-4 py-3">
          <div className="flex items-start gap-3">
            <MapPin className="size-4 text-primary mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0 space-y-0.5">
              <p className="text-sm font-medium text-foreground">{selectedAddress.name}</p>
              <p className="text-xs text-muted-foreground">{selectedAddress.company}</p>
              {selectedAddress.contact_name && (
                <p className="text-xs text-muted-foreground">{selectedAddress.contact_name}</p>
              )}
              <p className="text-xs text-muted-foreground">
                {selectedAddress.street}, {selectedAddress.zip} {selectedAddress.city}
                {selectedAddress.province ? ` (${selectedAddress.province})` : ""}
              </p>
              {selectedAddress.phone && (
                <p className="text-xs text-muted-foreground">Tel: {selectedAddress.phone}</p>
              )}
              {selectedAddress.reference && (
                <p className="text-xs text-muted-foreground">{selectedAddress.reference}</p>
              )}
            </div>
          </div>
          <div className="flex justify-end mt-2">
            <button
              type="button"
              onClick={onOpenDrawer}
              className="text-xs text-primary font-medium hover:underline"
            >
              Gestisci rubrica &rarr;
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// Inline SVG icon components to avoid external dependencies
function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

function ChevronLeft({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="m15 18-6-6 6-6" />
    </svg>
  )
}

function MapPin({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  )
}
