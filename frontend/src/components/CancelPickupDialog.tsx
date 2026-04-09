import { useState } from "react"
import { Button } from "@/components/ui/button"
import { formatDateIT } from "@/lib/utils"
import type { PickupRecord } from "@/lib/types"

interface CancelPickupDialogProps {
  pickup: PickupRecord
  isLoading: boolean
  onConfirm: (reason: string | null) => void
  onClose: () => void
}

export function CancelPickupDialog({ pickup, isLoading, onConfirm, onClose }: CancelPickupDialogProps) {
  const [reason, setReason] = useState("")

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Dialog */}
      <div className="relative bg-background border border-border rounded-xl shadow-lg px-6 py-5 w-full max-w-md mx-4">
        <h3 className="text-base font-semibold">Annulla ritiro</h3>
        <p className="text-sm text-muted-foreground mt-1">
          {pickup.carrier} — {formatDateIT(pickup.pickup_date)} — {pickup.company}
        </p>

        <div className="mt-4">
          <label className="block text-sm text-muted-foreground mb-1.5">
            Motivo (opzionale)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value.slice(0, 500))}
            placeholder="Es. cambio data, ordine annullato..."
            className="w-full border border-border rounded-lg px-3 py-2 text-sm resize-y min-h-[60px] bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            disabled={isLoading}
          />
          <p className="text-xs text-muted-foreground mt-1 text-right">
            {reason.length}/500
          </p>
        </div>

        <div className="flex gap-2 justify-end mt-4">
          <Button variant="outline" size="sm" onClick={onClose} disabled={isLoading}>
            Indietro
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => onConfirm(reason.trim() || null)}
            disabled={isLoading}
          >
            {isLoading ? "Annullamento..." : "Conferma annullamento"}
          </Button>
        </div>
      </div>
    </div>
  )
}
