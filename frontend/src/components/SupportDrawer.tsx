import { useState, useEffect } from "react"
import { useMutation } from "@tanstack/react-query"
import { useLocation } from "react-router-dom"
import { api } from "@/api/client"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface SupportDrawerProps {
  open: boolean
  onClose: () => void
}

export function SupportDrawer({ open, onClose }: SupportDrawerProps) {
  const [message, setMessage] = useState("")
  const [sent, setSent] = useState(false)
  const location = useLocation()

  // Reset on close
  useEffect(() => {
    if (!open) {
      setMessage("")
      setSent(false)
      mutation.reset()
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Escape key to close
  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [open, onClose])

  const mutation = useMutation({
    mutationFn: async ({ urgent }: { urgent: boolean }) => {
      return api.post<{ sent: boolean; category: string; urgent: boolean }>(
        "/api/v1/support",
        { message: message.trim(), urgent, page: location.pathname },
      )
    },
    onSuccess: () => {
      setSent(true)
    },
  })

  const handleSend = (urgent: boolean) => {
    if (!message.trim()) return
    mutation.mutate({ urgent })
  }

  const handleAnother = () => {
    setSent(false)
    setMessage("")
    mutation.reset()
  }

  return (
    <>
      {/* Overlay */}
      {open && (
        <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      )}

      {/* Drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-[380px] max-w-[90vw] bg-card border-l border-border shadow-xl z-50 transition-transform duration-200 flex flex-col",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Supporto</h2>
            <p className="text-xs text-muted-foreground">Il team riceverà il tuo messaggio</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 flex flex-col justify-end p-5">
          {sent ? (
            /* Success state */
            <div className="text-center space-y-4 py-8">
              <div className="text-4xl">&#9989;</div>
              <div>
                <p className="text-sm font-semibold text-foreground">Inviato!</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Il team riceverà il tuo messaggio su Trello
                  {mutation.data?.urgent ? " e Discord" : ""}.
                </p>
              </div>
              <Button variant="outline" onClick={handleAnother} className="text-sm">
                Invia un altro messaggio
              </Button>
            </div>
          ) : (
            /* Composer */
            <div className="space-y-4">
              <textarea
                className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary resize-none"
                rows={5}
                placeholder="Scrivi un messaggio..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                disabled={mutation.isPending}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend(false)
                }}
              />

              {mutation.error && (
                <p className="text-xs text-destructive text-center">
                  {mutation.error instanceof Error ? mutation.error.message : "Errore di invio. Riprova."}
                </p>
              )}

              <div className="flex gap-2">
                <Button
                  onClick={() => handleSend(false)}
                  disabled={!message.trim() || mutation.isPending}
                  className="flex-1 bg-primary hover:bg-primary/90 text-white"
                >
                  {mutation.isPending ? "Invio..." : "Invia"}
                </Button>
                <Button
                  onClick={() => handleSend(true)}
                  disabled={!message.trim() || mutation.isPending}
                  variant="outline"
                  className="border-destructive text-destructive hover:bg-destructive/10"
                >
                  Urgente
                </Button>
              </div>

              <p className="text-[10px] text-muted-foreground text-center">
                Cmd/Ctrl+Invio per inviare
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
