import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query"
import { api, cancelPickup } from "@/api/client"
import type { PickupListResponse } from "@/lib/types"

const PICKUPS_KEY = "pickups"

export function usePickupHistory(upcoming: boolean, limit: number = 50, offset: number = 0) {
  const query = useQuery({
    queryKey: [PICKUPS_KEY, upcoming, limit, offset],
    queryFn: () =>
      api.get<PickupListResponse>(
        `/api/v1/pickup/history?upcoming=${upcoming}&limit=${limit}&offset=${offset}`
      ),
  })

  return {
    data: query.data,
    pickups: query.data?.pickups ?? [],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    error: query.error,
  }
}

/** Call after a successful pickup submission to refresh the history cache. */
export function useInvalidatePickupHistory() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: [PICKUPS_KEY] })
}

/** Mutation hook for cancelling a pickup. Invalidates history cache on success. */
export function useCancelPickup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pickupId, reason }: { pickupId: string; reason?: string | null }) =>
      cancelPickup(pickupId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [PICKUPS_KEY] })
    },
  })
}
