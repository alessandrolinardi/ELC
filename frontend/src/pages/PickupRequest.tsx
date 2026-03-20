import { useState, useMemo } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { CarrierTile } from "@/components/CarrierTile"
import { DimensionsInput } from "@/components/DimensionsInput"
import { SuccessBanner } from "@/components/SuccessBanner"
import { AddressCombobox } from "@/components/AddressCombobox"
import { AddressDrawer } from "@/components/AddressDrawer"
import { TimeSelect } from "@/components/TimeSelect"
import { useAddresses } from "@/hooks/useAddresses"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import type { PickupRequestData, PickupResponse, Address } from "@/lib/types"
import type { ManualAddressData } from "@/components/AddressCombobox"

const CARRIERS = [
  { name: "FedEx" },
  { name: "DHL" },
  { name: "UPS" },
] as const

const DEFAULT_FORM: PickupRequestData = {
  carrier: "FedEx",
  pickup_date: new Date().toISOString().split("T")[0],
  time_start: "09:00:00",
  time_end: "17:00:00",
  company: "",
  contact_name: "",
  address: "",
  zip_code: "",
  city: "",
  province: "",
  reference: "",
  num_packages: 1,
  weight_per_package: 5,
  length: 40,
  width: 30,
  height: 20,
  use_pallet: false,
  num_pallets: 0,
  pallet_length: 120,
  pallet_width: 80,
  pallet_height: 100,
  notes: "",
}

export default function PickupRequest() {
  const [isDevMode] = useDevMode()
  const [form, setForm] = useState<PickupRequestData>(DEFAULT_FORM)
  const [showNotes, setShowNotes] = useState(false)
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const {
    addresses,
    isLoading: addressesLoading,
    createAddress,
    updateAddress,
    deleteAddress,
    setDefault,
  } = useAddresses()

  // Auto-populate from selected address
  const selectAddress = (addr: Address) => {
    setSelectedAddress(addr)
    setForm((prev) => ({
      ...prev,
      company: addr.company,
      contact_name: addr.contact_name,
      address: addr.street,
      zip_code: addr.zip,
      city: addr.city,
      province: addr.province,
      reference: addr.reference,
    }))
  }

  // Handle manual address entry (use without saving)
  const handleManualEntry = (data: ManualAddressData) => {
    setSelectedAddress(null)
    setForm((prev) => ({
      ...prev,
      company: data.company,
      contact_name: data.contact_name,
      address: data.address,
      zip_code: data.zip_code,
      city: data.city,
      province: data.province,
      reference: data.reference,
    }))
  }

  // Handle save to address book and use
  const handleSaveAndUse = async (data: Parameters<typeof createAddress>[0]) => {
    const result = await createAddress(data)
    // After saving, the addresses list will refresh; find and select the new one
    // We use the returned id to find it once the query refreshes
    // For now, populate the form directly from the data
    setForm((prev) => ({
      ...prev,
      company: data.company,
      contact_name: data.contact_name ?? "",
      address: data.street,
      zip_code: data.zip_code,
      city: data.city,
      province: data.province ?? "",
      reference: data.reference ?? "",
    }))
    // The new address will appear after the query refetch; try to select it
    if (result && "id" in result) {
      const newAddr: Address = {
        id: result.id,
        name: data.name,
        company: data.company,
        contact_name: data.contact_name ?? "",
        street: data.street,
        zip: data.zip_code,
        city: data.city,
        province: data.province ?? "",
        reference: data.reference ?? "",
        is_default: data.is_default ?? false,
      }
      setSelectedAddress(newAddr)
    }
  }

  // Auto-select default address on load
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useMemo(() => {
    if (addresses.length > 0 && !selectedAddress) {
      const defaultAddr = addresses.find((a) => a.is_default) || addresses[0]
      selectAddress(defaultAddr)
    }
  }, [addresses]) // eslint-disable-line react-hooks/exhaustive-deps

  // Computed summary
  const totalWeight = form.num_packages * form.weight_per_package
  const shipmentType = totalWeight > 70 ? "FREIGHT" : "NORMAL"

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: (data: PickupRequestData) =>
      api.post<PickupResponse>("/api/v1/pickup/request", data),
    onSuccess: (result) => {
      setSuccessMessage(result.message)
    },
  })

  const handleSubmit = () => {
    setSuccessMessage(null)
    submitMutation.mutate(form)
  }

  const update = <K extends keyof PickupRequestData>(
    key: K,
    value: PickupRequestData[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  if (successMessage) {
    return (
      <PageShell title="Richiesta Ritiro">
        <SuccessBanner message={successMessage} />
        <div className="mt-6 text-center">
          <Button
            variant="outline"
            onClick={() => {
              setSuccessMessage(null)
              setForm(DEFAULT_FORM)
              setSelectedAddress(null)
            }}
          >
            Nuova richiesta
          </Button>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell title="Richiesta Ritiro" subtitle="Compila il modulo e invia la richiesta di ritiro.">
      <div className="space-y-6">
        {/* Card 1: Carrier + Date/Time */}
        <div className="elc-card">
          <div className="grid grid-cols-2 gap-6">
            {/* Carrier tiles */}
            <div>
              <Label className="text-sm font-semibold text-foreground mb-3 block">
                Corriere
              </Label>
              <div className="grid grid-cols-3 gap-3">
                {CARRIERS.map((c) => (
                  <CarrierTile
                    key={c.name}
                    carrier={c.name}
                    selected={form.carrier === c.name}
                    onClick={() => update("carrier", c.name as PickupRequestData["carrier"])}
                  />
                ))}
              </div>
            </div>

            {/* Date + Time */}
            <div className="space-y-4">
              <div>
                <Label htmlFor="pickup_date" className="text-sm font-semibold text-foreground">
                  Data ritiro
                </Label>
                <Input
                  id="pickup_date"
                  type="date"
                  value={form.pickup_date}
                  onChange={(e) => update("pickup_date", e.target.value)}
                  className="mt-1.5"
                />
              </div>
              <div className="flex gap-3">
                <TimeSelect
                  value={form.time_start.slice(0, 5)}
                  onChange={(t) => update("time_start", t + ":00")}
                  label="Dalle"
                />
                <TimeSelect
                  value={form.time_end.slice(0, 5)}
                  onChange={(t) => update("time_end", t + ":00")}
                  label="Alle"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: Address */}
        <div className="elc-card">
          <div className="flex items-center justify-between mb-4">
            <Label className="text-sm font-semibold text-foreground">
              Indirizzo ritiro
            </Label>
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

        {/* Card 3: Packages */}
        <div className="elc-card">
          <Label className="text-sm font-semibold text-foreground mb-4 block">
            Dettagli colli
          </Label>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-muted-foreground">Numero colli</Label>
                <Input
                  type="number"
                  min={1}
                  value={form.num_packages}
                  onChange={(e) => update("num_packages", Number(e.target.value))}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Peso per collo (kg)</Label>
                <Input
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={form.weight_per_package}
                  onChange={(e) => update("weight_per_package", Number(e.target.value))}
                  className="mt-1"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs text-muted-foreground mb-1 block">Dimensioni collo</Label>
              <DimensionsInput
                length={form.length}
                width={form.width}
                height={form.height}
                onChange={(dims) =>
                  setForm((prev) => ({ ...prev, ...dims }))
                }
              />
            </div>

            {/* Pallet toggle */}
            <div className="flex items-center gap-3 pt-2">
              <Switch
                checked={form.use_pallet}
                onCheckedChange={(checked) => update("use_pallet", checked)}
              />
              <Label className="text-sm text-foreground">Bancale / Pallet</Label>
            </div>

            {form.use_pallet && (
              <div className="space-y-4 border-l-2 border-indigo-border ml-4 pl-4">
                <div>
                  <Label className="text-xs text-muted-foreground">Numero pallet</Label>
                  <Input
                    type="number"
                    min={1}
                    value={form.num_pallets}
                    onChange={(e) => update("num_pallets", Number(e.target.value))}
                    className="mt-1 max-w-[120px]"
                  />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground mb-1 block">Dimensioni pallet</Label>
                  <DimensionsInput
                    length={form.pallet_length}
                    width={form.pallet_width}
                    height={form.pallet_height}
                    onChange={(dims) =>
                      setForm((prev) => ({
                        ...prev,
                        pallet_length: dims.length,
                        pallet_width: dims.width,
                        pallet_height: dims.height,
                      }))
                    }
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Card 4: Notes (optional, hidden by default) */}
        {!showNotes ? (
          <button
            onClick={() => setShowNotes(true)}
            className="text-sm text-primary font-medium hover:underline"
          >
            + Aggiungi note
          </button>
        ) : (
          <div className="elc-card">
            <Label className="text-sm font-semibold text-foreground mb-2 block">
              Note
            </Label>
            <textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={3}
              className="w-full rounded-md border border-border px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              placeholder="Note aggiuntive per il corriere..."
            />
          </div>
        )}

        {/* Sticky Summary Bar */}
        <div className="sticky bottom-0 bg-card border-t border-border px-6 py-4 -mx-4 rounded-t-lg shadow-[var(--shadow-card)]">
          <div className="flex items-center justify-between max-w-[var(--max-width-content)] mx-auto">
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>{form.num_packages} colli</span>
              <span className="text-border">|</span>
              <span>{totalWeight.toFixed(1)} kg</span>
              <span className="text-border">|</span>
              <Badge
                variant={shipmentType === "FREIGHT" ? "destructive" : "secondary"}
                className="text-xs"
              >
                {shipmentType}
              </Badge>
              {shipmentType === "FREIGHT" && (
                <span className="text-xs text-destructive">Peso &gt; 70 kg</span>
              )}
            </div>
            <Button
              onClick={handleSubmit}
              disabled={submitMutation.isPending}
              className="bg-primary hover:bg-primary/90 text-white px-6"
            >
              {submitMutation.isPending ? "Invio..." : "Invia Richiesta"}
            </Button>
          </div>
        </div>

        {/* Error */}
        {submitMutation.error && (
          <div className="rounded-lg bg-[#fef2f2] border border-destructive/20 px-5 py-4">
            <p className="text-sm text-red-800">
              {submitMutation.error instanceof Error
                ? submitMutation.error.message
                : "Errore durante l'invio"}
            </p>
          </div>
        )}

        {/* Dev mode debug */}
        {isDevMode && (
          <details className="elc-card">
            <summary className="text-sm font-medium text-muted-foreground cursor-pointer">
              Debug: Form State
            </summary>
            <pre className="mt-3 text-xs overflow-auto p-3 bg-[var(--color-surface)] rounded-md">
              {JSON.stringify(form, null, 2)}
            </pre>
          </details>
        )}
      </div>

      {/* Address Book Drawer */}
      <AddressDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        addresses={addresses}
        onAdd={async (data) => {
          await createAddress(data)
        }}
        onUpdate={async (id, data) => {
          await updateAddress({ id, data })
        }}
        onDelete={async (id) => {
          await deleteAddress(id)
          // If the deleted address was selected, clear selection
          if (selectedAddress?.id === id) {
            setSelectedAddress(null)
          }
        }}
        onSetDefault={async (id) => {
          await setDefault(id)
        }}
      />
    </PageShell>
  )
}
