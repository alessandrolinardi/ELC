interface SuccessBannerProps {
  message: string
  details?: string
}

export function SuccessBanner({ message, details }: SuccessBannerProps) {
  return (
    <div className="rounded-lg bg-success-light border border-success/20 px-5 py-4">
      <p className="text-sm font-semibold text-green-800">{message}</p>
      {details && (
        <p className="text-sm text-green-700 mt-1">{details}</p>
      )}
    </div>
  )
}
