import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import type { Address, AddressCreate } from "@/lib/types"

interface AddressDrawerProps {
  open: boolean
  onClose: () => void
  addresses: Address[]
  onAdd: (data: AddressCreate) => Promise<void>
  onUpdate: (id: string, data: Partial<AddressCreate>) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onSetDefault: (id: string) => Promise<void>
}

const EMPTY_FORM: AddressCreate = {
  name: "",
  company: "",
  contact_name: "",
  street: "",
  zip_code: "",
  city: "",
  province: "",
  reference: "",
  is_default: false,
}

export function AddressDrawer({
  open,
  onClose,
  addresses,
  onAdd,
  onUpdate,
  onDelete,
  onSetDefault,
}: AddressDrawerProps) {
  const [mode, setMode] = useState<"list" | "add" | "edit">("list")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<AddressCreate>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Reset state when drawer closes
  useEffect(() => {
    if (!open) {
      setMode("list")
      setEditingId(null)
      setForm(EMPTY_FORM)
      setConfirmDeleteId(null)
    }
  }, [open])

  const updateForm = (key: keyof AddressCreate, value: string | boolean) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (mode === "add") {
        await onAdd(form)
      } else if (mode === "edit" && editingId) {
        await onUpdate(editingId, form)
      }
      setMode("list")
      setEditingId(null)
      setForm(EMPTY_FORM)
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (addr: Address) => {
    setEditingId(addr.id)
    setForm({
      name: addr.name,
      company: addr.company,
      contact_name: addr.contact_name || "",
      street: addr.street,
      zip_code: addr.zip,
      city: addr.city,
      province: addr.province || "",
      reference: addr.reference || "",
      is_default: addr.is_default,
    })
    setMode("edit")
  }

  const handleDelete = async (id: string) => {
    setDeleting(true)
    try {
      await onDelete(id)
      setConfirmDeleteId(null)
    } finally {
      setDeleting(false)
    }
  }

  const handleCancel = () => {
    setMode("list")
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  return (
    <>
      {/* Overlay */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/40 transition-opacity duration-300",
          open ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className={cn(
          "fixed top-0 right-0 z-50 h-full w-[400px] max-w-[90vw] bg-card border-l border-border shadow-xl transition-transform duration-300 ease-in-out flex flex-col",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <h2 className="text-base font-semibold text-foreground">Rubrica indirizzi</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <XIcon className="size-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {mode === "list" && (
            <div className="space-y-3">
              <Button
                type="button"
                variant="outline"
                className="w-full justify-center"
                onClick={() => {
                  setForm(EMPTY_FORM)
                  setMode("add")
                }}
              >
                + Aggiungi indirizzo
              </Button>

              {addresses.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-6">
                  Nessun indirizzo salvato.
                </p>
              )}

              {addresses.map((addr) => (
                <div
                  key={addr.id}
                  className={cn(
                    "rounded-lg border border-border p-3 space-y-1",
                    addr.is_default && "border-primary/30 bg-primary/5",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">
                        {addr.is_default && <span className="mr-1">&#11088;</span>}
                        {addr.name}
                      </p>
                      <p className="text-xs text-muted-foreground">{addr.company}</p>
                      <p className="text-xs text-muted-foreground">
                        {addr.street}, {addr.zip} {addr.city}
                        {addr.province ? ` (${addr.province})` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {!addr.is_default && (
                        <button
                          type="button"
                          title="Imposta come predefinito"
                          className="p-1 text-muted-foreground hover:text-amber-500 transition-colors"
                          onClick={() => onSetDefault(addr.id)}
                        >
                          <StarIcon className="size-4" />
                        </button>
                      )}
                      <button
                        type="button"
                        title="Modifica"
                        className="p-1 text-muted-foreground hover:text-primary transition-colors"
                        onClick={() => handleEdit(addr)}
                      >
                        <PencilIcon className="size-4" />
                      </button>
                      {confirmDeleteId === addr.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            className="p-1 text-destructive hover:text-destructive/80 text-xs font-medium"
                            onClick={() => handleDelete(addr.id)}
                            disabled={deleting}
                          >
                            {deleting ? "..." : "Conferma"}
                          </button>
                          <button
                            type="button"
                            className="p-1 text-muted-foreground hover:text-foreground text-xs"
                            onClick={() => setConfirmDeleteId(null)}
                          >
                            Annulla
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          title="Elimina"
                          className="p-1 text-muted-foreground hover:text-destructive transition-colors"
                          onClick={() => setConfirmDeleteId(addr.id)}
                        >
                          <TrashIcon className="size-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {(mode === "add" || mode === "edit") && (
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-foreground">
                {mode === "add" ? "Nuovo indirizzo" : "Modifica indirizzo"}
              </h3>

              <div>
                <Label className="text-xs text-muted-foreground">Nome</Label>
                <Input
                  value={form.name}
                  onChange={(e) => updateForm("name", e.target.value)}
                  placeholder="es. Magazzino Milano"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Azienda</Label>
                <Input
                  value={form.company}
                  onChange={(e) => updateForm("company", e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Contatto</Label>
                <Input
                  value={form.contact_name ?? ""}
                  onChange={(e) => updateForm("contact_name", e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Indirizzo</Label>
                <Input
                  value={form.street}
                  onChange={(e) => updateForm("street", e.target.value)}
                  className="mt-1"
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs text-muted-foreground">CAP</Label>
                  <Input
                    value={form.zip_code}
                    onChange={(e) => updateForm("zip_code", e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Citta</Label>
                  <Input
                    value={form.city}
                    onChange={(e) => updateForm("city", e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Prov.</Label>
                  <Input
                    value={form.province ?? ""}
                    onChange={(e) => updateForm("province", e.target.value)}
                    className="mt-1"
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Riferimento / Telefono</Label>
                <Input
                  value={form.reference ?? ""}
                  onChange={(e) => updateForm("reference", e.target.value)}
                  className="mt-1"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_default"
                  checked={form.is_default ?? false}
                  onChange={(e) => updateForm("is_default", e.target.checked)}
                  className="rounded border-border"
                />
                <Label htmlFor="is_default" className="text-xs text-muted-foreground cursor-pointer">
                  Imposta come predefinito
                </Label>
              </div>

              <Separator />

              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  onClick={handleSave}
                  disabled={saving || !form.name || !form.company || !form.street || !form.city || !form.zip_code}
                  className="bg-primary hover:bg-primary/90 text-white"
                >
                  {saving ? "Salvataggio..." : "Salva"}
                </Button>
                <Button type="button" variant="outline" onClick={handleCancel}>
                  Annulla
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// Inline SVG icons
function XIcon({ className }: { className?: string }) {
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
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  )
}

function StarIcon({ className }: { className?: string }) {
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
      <path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a.53.53 0 0 0 .4.29l5.16.753a.53.53 0 0 1 .294.904l-3.732 3.638a.53.53 0 0 0-.153.47l.882 5.14a.53.53 0 0 1-.77.56l-4.614-2.427a.53.53 0 0 0-.494 0L7.14 18.73a.53.53 0 0 1-.77-.56l.882-5.14a.53.53 0 0 0-.153-.47L3.365 8.921a.53.53 0 0 1 .294-.905l5.16-.752a.53.53 0 0 0 .4-.29z" />
    </svg>
  )
}

function PencilIcon({ className }: { className?: string }) {
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
      <path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" />
    </svg>
  )
}

function TrashIcon({ className }: { className?: string }) {
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
      <path d="M3 6h18" />
      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
      <line x1="10" x2="10" y1="11" y2="17" />
      <line x1="14" x2="14" y1="11" y2="17" />
    </svg>
  )
}
