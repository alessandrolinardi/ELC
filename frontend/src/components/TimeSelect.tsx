import { useState, useRef, useEffect, useCallback } from "react"
import { Clock } from "lucide-react"

interface TimeSelectProps {
  value: string // "HH:MM" format
  onChange: (time: string) => void
  label?: string // e.g., "Dalle" or "Alle"
  min?: string // minimum time, e.g., "06:00"
  max?: string // maximum time, e.g., "20:00"
}

function generateTimeSlots(min = "06:00", max = "20:00"): string[] {
  const slots: string[] = []
  const [minH, minM] = min.split(":").map(Number)
  const [maxH, maxM] = max.split(":").map(Number)
  for (let h = minH; h <= maxH; h++) {
    for (const m of [0, 30]) {
      if (h === minH && m < minM) continue
      if (h === maxH && m > maxM) continue
      slots.push(
        `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`
      )
    }
  }
  return slots
}

function isValidTime(value: string): boolean {
  if (!/^\d{2}:\d{2}$/.test(value)) return false
  const [h, m] = value.split(":").map(Number)
  return h >= 0 && h <= 23 && m >= 0 && m <= 59
}

function findNearestSlotIndex(slots: string[], time: string): number {
  if (!isValidTime(time)) return 0
  const [h, m] = time.split(":").map(Number)
  const timeMinutes = h * 60 + m
  let closest = 0
  let closestDiff = Infinity
  for (let i = 0; i < slots.length; i++) {
    const [sh, sm] = slots[i].split(":").map(Number)
    const diff = Math.abs(sh * 60 + sm - timeMinutes)
    if (diff < closestDiff) {
      closestDiff = diff
      closest = i
    }
  }
  return closest
}

export function TimeSelect({
  value,
  onChange,
  label,
  min = "06:00",
  max = "20:00",
}: TimeSelectProps) {
  const [open, setOpen] = useState(false)
  const [inputValue, setInputValue] = useState(value)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const slots = generateTimeSlots(min, max)

  // Sync inputValue when value prop changes externally
  useEffect(() => {
    setInputValue(value)
  }, [value])

  // Click outside closes dropdown
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside)
      return () => document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [open])

  // Scroll to nearest slot when dropdown opens
  useEffect(() => {
    if (open && listRef.current) {
      const nearestIdx = findNearestSlotIndex(slots, value)
      setHighlightedIndex(nearestIdx)
      const item = listRef.current.children[nearestIdx] as HTMLElement
      if (item) {
        item.scrollIntoView({ block: "center" })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const selectSlot = useCallback(
    (slot: string) => {
      onChange(slot)
      setInputValue(slot)
      setOpen(false)
      // Don't call blur() here — it triggers handleBlur with stale closure
      // state, which resets the value back to the old one. The dropdown is
      // already closed by setOpen(false).
    },
    [onChange]
  )

  const handleBlur = useCallback(() => {
    // Small delay to allow click on dropdown items
    setTimeout(() => {
      if (
        containerRef.current &&
        containerRef.current.contains(document.activeElement)
      ) {
        return
      }
      // Validate input
      if (isValidTime(inputValue)) {
        onChange(inputValue)
      } else {
        setInputValue(value)
      }
      setOpen(false)
    }, 150)
  }, [inputValue, value, onChange])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault()
        setOpen(true)
        return
      }
      return
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault()
        setHighlightedIndex((prev) => {
          const next = Math.min(prev + 1, slots.length - 1)
          const item = listRef.current?.children[next] as HTMLElement
          item?.scrollIntoView({ block: "nearest" })
          return next
        })
        break
      case "ArrowUp":
        e.preventDefault()
        setHighlightedIndex((prev) => {
          const next = Math.max(prev - 1, 0)
          const item = listRef.current?.children[next] as HTMLElement
          item?.scrollIntoView({ block: "nearest" })
          return next
        })
        break
      case "Enter":
        e.preventDefault()
        if (highlightedIndex >= 0 && highlightedIndex < slots.length) {
          selectSlot(slots[highlightedIndex])
        }
        break
      case "Escape":
        e.preventDefault()
        setOpen(false)
        setInputValue(value)
        inputRef.current?.blur()
        break
    }
  }

  return (
    <div ref={containerRef} className="relative inline-block w-[100px]">
      {label && (
        <label className="text-sm text-muted-foreground block mb-1">
          {label}
        </label>
      )}
      <div className="relative">
        <Clock className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value)
            if (!open) setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          placeholder="HH:MM"
          maxLength={5}
          className="h-8 w-full rounded-lg border border-input bg-transparent pl-7 pr-2 py-1 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 tabular-nums"
        />
      </div>

      {open && (
        <div
          ref={listRef}
          className="absolute z-50 mt-1 w-full max-h-[200px] overflow-y-auto rounded-lg border border-border bg-card shadow-md"
          role="listbox"
        >
          {slots.map((slot, i) => {
            const isSelected = slot === value
            const isHighlighted = i === highlightedIndex
            return (
              <div
                key={slot}
                role="option"
                aria-selected={isSelected}
                onMouseDown={(e) => {
                  e.preventDefault()
                  selectSlot(slot)
                }}
                onMouseEnter={() => setHighlightedIndex(i)}
                className={[
                  "px-3 py-1.5 text-sm cursor-pointer tabular-nums transition-colors",
                  isSelected
                    ? "text-indigo-600 dark:text-indigo-400 font-medium bg-indigo-50 dark:bg-indigo-950/40 border-l-2 border-indigo-500"
                    : "border-l-2 border-transparent",
                  isHighlighted && !isSelected
                    ? "bg-indigo-50/60 dark:bg-indigo-950/20"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {slot}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
