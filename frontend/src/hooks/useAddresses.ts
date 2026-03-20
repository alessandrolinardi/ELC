import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/api/client"
import type { Address, AddressCreate, AddressUpdate } from "@/lib/types"

const ADDRESSES_KEY = ["addresses"]

export function useAddresses() {
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ADDRESSES_KEY,
    queryFn: () => api.get<Address[]>("/api/v1/addresses"),
  })

  const createMutation = useMutation({
    mutationFn: (data: AddressCreate) =>
      api.post<{ id: string }>("/api/v1/addresses", data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: AddressUpdate }) =>
      api.put<{ updated: boolean }>(`/api/v1/addresses/${id}`, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      api.delete<{ deleted: boolean }>(`/api/v1/addresses/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  })

  const setDefaultMutation = useMutation({
    mutationFn: (id: string) =>
      api.put<{ default: boolean }>(`/api/v1/addresses/${id}/default`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  })

  return {
    addresses: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    createAddress: createMutation.mutateAsync,
    updateAddress: updateMutation.mutateAsync,
    deleteAddress: deleteMutation.mutateAsync,
    setDefault: setDefaultMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}
