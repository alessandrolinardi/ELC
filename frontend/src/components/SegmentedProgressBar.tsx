import { colors } from "@/lib/colors"

interface Segment {
  value: number
  color: string
  label: string
}

interface SegmentedProgressBarProps {
  segments: Segment[]
  total: number
}

export function SegmentedProgressBar({ segments, total }: SegmentedProgressBarProps) {
  if (total === 0) return null

  return (
    <div>
      {/* Bar */}
      <div className="h-4 rounded-full overflow-hidden flex bg-muted">
        {segments.map((seg, i) => {
          const pct = (seg.value / total) * 100
          if (pct === 0) return null
          return (
            <div
              key={i}
              className="h-full transition-all duration-500"
              style={{ width: `${pct}%`, backgroundColor: seg.color }}
              title={`${seg.label}: ${seg.value} (${pct.toFixed(1)}%)`}
            />
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: seg.color }}
            />
            {seg.label}: <span className="font-semibold text-foreground">{seg.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Helper to build the standard validator segments.
 */
export function buildValidatorSegments(result: {
  valid_count: number
  corrected_count: number
  review_count: number
}): Segment[] {
  return [
    { value: result.valid_count, color: colors.success, label: "Verificati" },
    { value: result.corrected_count, color: colors.primary, label: "Corretti" },
    { value: result.review_count, color: colors.warning, label: "Da verificare" },
  ]
}
