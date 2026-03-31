import { useEffect, useRef, useState, useCallback } from "react"
import { useLocation } from "react-router-dom"
import { api } from "@/api/client"
import { useDevMode } from "@/hooks/useDevMode"

/**
 * Listens for Crisp `message:sent` events and creates a Trello card
 * (via backend → Zapier) on the first message per page session.
 *
 * Dedup: one ticket per page path. Resets on navigation or page refresh.
 * Error recovery: no flag set on failure, auto-retry once after 2s.
 * Toast: shows "Il team è stato notificato" for 5s on success.
 */
export function useCrispTicket() {
  const location = useLocation()
  const [isDevMode] = useDevMode()
  const ticketedPage = useRef<string | null>(null)
  const [toast, setToast] = useState(false)
  const toastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Reset dedup flag on page navigation
  useEffect(() => {
    ticketedPage.current = null
  }, [location.pathname])

  // Clean up timeouts on unmount
  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current)
      if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current)
    }
  }, [])

  const postTicket = useCallback(
    async (message: string, attempt: number = 1) => {
      if (isDevMode) console.log(`Crisp ticket: posting (attempt ${attempt})...`)

      try {
        await api.post("/api/v1/support/ticket", {
          message,
          page: location.pathname,
        })
        ticketedPage.current = location.pathname
        setToast(true)
        if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current)
        toastTimeoutRef.current = setTimeout(() => setToast(false), 5000)
        if (isDevMode) console.log("Crisp ticket: success")
      } catch (err) {
        if (isDevMode) console.log("Crisp ticket: failed", err)
        // Auto-retry once after 2s
        if (attempt === 1) {
          if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current)
          retryTimeoutRef.current = setTimeout(() => postTicket(message, 2), 2000)
        }
      }
    },
    [location.pathname, isDevMode]
  )

  // Register Crisp event listener
  useEffect(() => {
    const w = window as unknown as {
      $crisp?: Array<unknown[]>
    }
    if (!w.$crisp) return

    const handler = (message: { content?: string; type?: string }) => {
      // Only handle text messages sent by the user
      if (!message?.content) return
      if (ticketedPage.current === location.pathname) return

      if (isDevMode) console.log("Crisp message:sent", message.content.slice(0, 50))
      postTicket(message.content)
    }

    w.$crisp.push(["on", "message:sent", handler])

    return () => {
      w.$crisp?.push(["off", "message:sent", handler])
    }
  }, [location.pathname, postTicket, isDevMode])

  return { toast }
}
