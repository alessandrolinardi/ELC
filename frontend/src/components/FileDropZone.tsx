import { useCallback, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface FileDropZoneProps {
  /** Label shown above the drop zone */
  label: string
  /** Subtitle with format info */
  subtitle?: string
  /** Accepted MIME types (e.g., ".pdf", ".xlsx,.xls") */
  accept: string
  /** Allow multiple files */
  multiple?: boolean
  /** Max file size in MB (client-side UX check only -- server enforces) */
  maxSizeMB?: number
  /** Large icon/emoji */
  icon?: string
  /** Callback when files are selected */
  onFilesSelected: (files: File[]) => void
  /** Current selected files (for display) */
  selectedFiles?: File[]
  /** Error message to display */
  error?: string
}

export function FileDropZone({
  label,
  subtitle,
  accept,
  multiple = false,
  maxSizeMB = 50,
  icon = "\uD83D\uDCC4",
  onFilesSelected,
  selectedFiles = [],
  error,
}: FileDropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return
      const files = Array.from(fileList)

      // Client-side size check (UX convenience only)
      const oversized = files.filter(
        (f) => f.size / (1024 * 1024) > maxSizeMB
      )
      if (oversized.length > 0) {
        // Still pass through -- server will reject
        console.warn(`Files exceed ${maxSizeMB}MB:`, oversized.map((f) => f.name))
      }

      onFilesSelected(files)
    },
    [maxSizeMB, onFilesSelected]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles]
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (containerRef.current && containerRef.current.contains(e.relatedTarget as Node)) return
    setIsDragging(false)
  }, [])

  const hasFiles = selectedFiles.length > 0

  return (
    <div>
      <div
        ref={containerRef}
        role="button"
        tabIndex={0}
        aria-label={label}
        className={cn(
          "relative rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors",
          isDragging && "bg-indigo-light border-primary",
          !isDragging && !hasFiles && "border-indigo-border hover:bg-indigo-light",
          hasFiles && "border-success bg-success-light",
          error && "border-error"
        )}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />

        {!hasFiles ? (
          <>
            <div className="text-4xl mb-3">{icon}</div>
            <p className="font-semibold text-foreground">{label}</p>
            {subtitle && (
              <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
            )}
            <p className="text-xs text-muted-foreground mt-2">
              Max {maxSizeMB} MB
            </p>
          </>
        ) : (
          <>
            <div className="text-4xl mb-3">{"\u2705"}</div>
            {selectedFiles.map((f, i) => (
              <p key={i} className="text-sm font-medium text-foreground">
                {f.name}{" "}
                <span className="text-muted-foreground">
                  ({(f.size / (1024 * 1024)).toFixed(1)} MB)
                </span>
              </p>
            ))}
            <p className="text-xs text-muted-foreground mt-2">
              Clicca per sostituire
            </p>
          </>
        )}
      </div>

      {error && (
        <p className="mt-1.5 text-sm text-error">{error}</p>
      )}
    </div>
  )
}
