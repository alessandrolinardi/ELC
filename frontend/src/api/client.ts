const BASE_URL = import.meta.env.VITE_API_URL || ""

// --- Generic response types ---

interface ApiSuccess<T> {
  ok: true
  data: T
}

interface ApiError {
  ok: false
  error: {
    code: string
    message: string
  }
}

type ApiResponse<T> = ApiSuccess<T> | ApiError

// --- Error class ---

export class ApiRequestError extends Error {
  code: string
  status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
    this.name = "ApiRequestError"
  }
}

// --- Core fetch helper ---

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`

  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
    },
  })

  // Handle non-JSON errors (e.g., 502 Bad Gateway)
  const contentType = response.headers.get("content-type")
  if (!contentType?.includes("application/json")) {
    if (!response.ok) {
      throw new ApiRequestError(
        "NETWORK_ERROR",
        `Server returned ${response.status}`,
        response.status
      )
    }
    // For file downloads, return the response itself
    return response as unknown as T
  }

  const json = await response.json()

  // Handle FastAPI error responses that use the `detail` field
  if (!response.ok && json.detail) {
    const detail = json.detail
    // Envelope-style detail: {"ok": false, "error": {"code": ..., "message": ...}}
    if (typeof detail === "object" && !Array.isArray(detail) && detail.error?.message) {
      throw new ApiRequestError(detail.error.code || "ERROR", detail.error.message, response.status)
    }
    // Pydantic validation errors (422 with detail array)
    if (Array.isArray(detail)) {
      const msg = detail.map((d: { msg?: string; loc?: string[] }) =>
        `${d.loc?.slice(-1)[0] || "field"}: ${d.msg || "invalid"}`
      ).join(", ")
      throw new ApiRequestError("VALIDATION_ERROR", msg, response.status)
    }
    // Plain string detail
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail)
    throw new ApiRequestError("ERROR", msg, response.status)
  }

  const typed = json as ApiResponse<T>
  if (!typed.ok) {
    const err = typed.error
    throw new ApiRequestError(
      err?.code || "UNKNOWN",
      err?.message || "Unknown error",
      response.status
    )
  }

  return typed.data
}

// --- Public API methods ---

export const api = {
  /** GET request returning parsed JSON data */
  get<T>(path: string): Promise<T> {
    return request<T>(path)
  },

  /** POST with JSON body */
  post<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  },

  /** POST with FormData (file uploads) */
  postForm<T>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: formData,
    })
  },

  /** PUT with JSON body */
  put<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  },

  /** DELETE request */
  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" })
  },

  /** Get download URL for a job file */
  fileUrl(jobId: string, filename: string): string {
    return `${BASE_URL}/api/v1/jobs/${jobId}/files/${filename}`
  },
}

// --- Convenience wrappers ---

import type { ConfirmRequest, CancelPickupResponse, FreightRequestResponse } from "@/lib/types"

/** Confirm validation: send edits and trigger Phase 2 (Google validation) */
export async function confirmValidation(
  jobId: string,
  body: ConfirmRequest
): Promise<{ status: string }> {
  return api.post<{ status: string }>(`/api/v1/jobs/${jobId}/confirm`, body)
}

export async function fetchBrands(): Promise<{ name: string }[]> {
  return api.get<{ name: string }[]>("/api/v1/brands")
}

export async function createBrand(name: string): Promise<{ name: string }> {
  return api.post<{ name: string }>("/api/v1/brands", { name })
}

export async function cancelPickup(
  pickupId: string,
  reason?: string | null
): Promise<CancelPickupResponse> {
  return api.post<CancelPickupResponse>(`/api/v1/pickup/${pickupId}/cancel`, { reason: reason ?? null })
}

export async function submitFreightRequest(formData: FormData): Promise<FreightRequestResponse> {
  return api.postForm<FreightRequestResponse>("/api/v1/freight/request", formData)
}
