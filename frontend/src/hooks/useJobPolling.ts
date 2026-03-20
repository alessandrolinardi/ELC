import { useQuery } from "@tanstack/react-query"
import { api, ApiRequestError } from "@/api/client"
import type { JobStatus } from "@/lib/types"

interface UseJobPollingOptions {
  /** Polling interval in milliseconds. Default: 3000 */
  interval?: number
}

interface UseJobPollingResult<T> {
  /** Current job status: "processing" | "complete" | "failed" | null */
  status: string | null
  /** Progress info (current, total, message) -- only during processing */
  progress: { current: number; total: number; message: string } | null
  /** Job result -- only when status is "complete" */
  result: T | null
  /** Error message -- either job error or network error */
  error: string | null
  /** Whether we are actively polling */
  isPolling: boolean
  /** Whether the job was not found (expired / server restarted) */
  isExpired: boolean
}

/**
 * Poll GET /api/v1/jobs/{jobId}/status every `interval` ms.
 * Stops polling when status is "complete" or "failed".
 * Returns null status if jobId is null (hook disabled).
 *
 * Usage:
 *   const { status, progress, result, error, isPolling } = useJobPolling<LabelJobResult>(jobId)
 */
export function useJobPolling<T = unknown>(
  jobId: string | null,
  options: UseJobPollingOptions = {}
): UseJobPollingResult<T> {
  const { interval = 3000 } = options

  const query = useQuery({
    queryKey: ["job-status", jobId],
    queryFn: async (): Promise<JobStatus<T>> => {
      return api.get<JobStatus<T>>(`/api/v1/jobs/${jobId}/status`)
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      // Stop polling once terminal
      const data = query.state.data
      if (data?.status === "complete" || data?.status === "failed") {
        return false
      }
      return interval
    },
    retry: (failureCount, error) => {
      // Don't retry 404s (job expired)
      if (error instanceof ApiRequestError && error.status === 404) {
        return false
      }
      return failureCount < 2
    },
  })

  // Detect expired job (404)
  const isExpired =
    query.error instanceof ApiRequestError && query.error.status === 404

  return {
    status: query.data?.status ?? null,
    progress: query.data?.progress ?? null,
    result: query.data?.result ?? null,
    error:
      query.data?.error ??
      (isExpired
        ? "Job scaduto o server riavviato. Riprova."
        : query.error
          ? String(query.error)
          : null),
    isPolling:
      !!jobId &&
      query.data?.status !== "complete" &&
      query.data?.status !== "failed" &&
      !isExpired,
    isExpired,
  }
}
