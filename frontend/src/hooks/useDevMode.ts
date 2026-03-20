import { useSearchParams } from "react-router-dom"
import { useCallback } from "react"

/**
 * Dev Mode hook -- reads ?dev=1 from URL.
 * Returns [isDevMode, toggleDevMode].
 */
export function useDevMode(): [boolean, () => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const isDevMode = searchParams.get("dev") === "1"

  const toggleDevMode = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (next.get("dev") === "1") {
        next.delete("dev")
      } else {
        next.set("dev", "1")
      }
      return next
    })
  }, [setSearchParams])

  return [isDevMode, toggleDevMode]
}
