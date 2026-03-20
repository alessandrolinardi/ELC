import { cn } from "@/lib/utils"

interface DimensionsInputProps {
  length: number
  width: number
  height: number
  onChange: (dims: { length: number; width: number; height: number }) => void
  errors?: { length?: string; width?: string; height?: string }
  disabled?: boolean
}

export function DimensionsInput({
  length,
  width,
  height,
  onChange,
  errors,
  disabled = false,
}: DimensionsInputProps) {
  return (
    <div>
      {/* Labels */}
      <div className="flex items-center gap-0 mb-1.5">
        <span className="flex-1 text-xs font-medium text-muted-foreground pl-3">Lunghezza</span>
        <span className="w-6" />
        <span className="flex-1 text-xs font-medium text-muted-foreground pl-3">Larghezza</span>
        <span className="w-6" />
        <span className="flex-1 text-xs font-medium text-muted-foreground pl-3">Altezza</span>
        <span className="w-10" />
      </div>

      {/* Input row */}
      <div className="flex items-center gap-0 rounded-md border border-border overflow-hidden bg-card">
        <input
          type="number"
          min={0}
          value={length || ""}
          onChange={(e) => onChange({ length: Number(e.target.value), width, height })}
          disabled={disabled}
          className={cn(
            "flex-1 px-3 py-2 text-sm text-center outline-none border-0",
            "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
            errors?.length && "bg-error-light"
          )}
          placeholder="0"
        />
        <span className="text-muted-foreground text-sm px-1">{"\u00D7"}</span>
        <input
          type="number"
          min={0}
          value={width || ""}
          onChange={(e) => onChange({ length, width: Number(e.target.value), height })}
          disabled={disabled}
          className={cn(
            "flex-1 px-3 py-2 text-sm text-center outline-none border-0",
            "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
            errors?.width && "bg-error-light"
          )}
          placeholder="0"
        />
        <span className="text-muted-foreground text-sm px-1">{"\u00D7"}</span>
        <input
          type="number"
          min={0}
          value={height || ""}
          onChange={(e) => onChange({ length, width, height: Number(e.target.value) })}
          disabled={disabled}
          className={cn(
            "flex-1 px-3 py-2 text-sm text-center outline-none border-0",
            "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
            errors?.height && "bg-error-light"
          )}
          placeholder="0"
        />
        <span className="text-muted-foreground text-xs font-medium px-3">cm</span>
      </div>

      {/* Per-field errors */}
      {(errors?.length || errors?.width || errors?.height) && (
        <div className="flex items-center gap-0 mt-1">
          <span className="flex-1 text-xs text-error">{errors?.length || ""}</span>
          <span className="w-6" />
          <span className="flex-1 text-xs text-error">{errors?.width || ""}</span>
          <span className="w-6" />
          <span className="flex-1 text-xs text-error">{errors?.height || ""}</span>
          <span className="w-10" />
        </div>
      )}
    </div>
  )
}
