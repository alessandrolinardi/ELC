import { cn } from "@/lib/utils"

interface Step {
  label: string
}

interface StepIndicatorProps {
  steps: Step[]
  currentStep: number  // 0-indexed
}

export function StepIndicator({ steps, currentStep }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center gap-0">
      {steps.map((step, index) => {
        const isCompleted = index < currentStep
        const isCurrent = index === currentStep
        const isFuture = index > currentStep

        return (
          <div key={index} className="flex items-center">
            {/* Step circle + label */}
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium border-2 transition-colors",
                  isCompleted && "bg-success border-success text-white",
                  isCurrent && "bg-primary border-primary text-primary-foreground",
                  isFuture && "bg-card border-border text-muted-foreground"
                )}
              >
                {isCompleted ? "\u2713" : index + 1}
              </div>
              <span
                className={cn(
                  "mt-1.5 text-xs font-medium whitespace-nowrap",
                  isCompleted && "text-success",
                  isCurrent && "text-primary font-bold",
                  isFuture && "text-muted-foreground"
                )}
              >
                {step.label}
              </span>
            </div>

            {/* Connector line (except after last step) */}
            {index < steps.length - 1 && (
              <div
                className={cn(
                  "w-16 h-0.5 mx-2 mt-[-18px]",
                  index < currentStep ? "bg-success" : "bg-border"
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
