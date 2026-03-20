# ELC Frontend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React + Vite + TypeScript frontend for ELC Tools that consumes the FastAPI backend API.

**Architecture:** SPA with React Router for navigation, TanStack Query for API state management, Tailwind CSS + shadcn/ui for styling. Cool Indigo (#6366f1) design system.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router v6, TanStack Query v5

**Spec:** `docs/superpowers/specs/2026-03-19-fastapi-react-migration-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/package.json` | Create | Dependencies and scripts |
| `frontend/tsconfig.json` | Create | TypeScript config |
| `frontend/tsconfig.app.json` | Create | App-specific TS config |
| `frontend/tsconfig.node.json` | Create | Node-specific TS config |
| `frontend/vite.config.ts` | Create | Vite build config with API proxy |
| `frontend/tailwind.config.ts` | Create | Tailwind + Cool Indigo design tokens |
| `frontend/postcss.config.js` | Create | PostCSS for Tailwind |
| `frontend/index.html` | Create | HTML entry point |
| `frontend/.env` | Create | VITE_API_URL dev default |
| `frontend/src/main.tsx` | Create | React entry point |
| `frontend/src/App.tsx` | Create | Router + QueryClient + layout |
| `frontend/src/index.css` | Create | Tailwind directives + base styles |
| `frontend/src/api/client.ts` | Create | Typed fetch wrapper |
| `frontend/src/lib/types.ts` | Create | TypeScript types matching backend schemas |
| `frontend/src/lib/colors.ts` | Create | Design token constants |
| `frontend/src/hooks/useDevMode.ts` | Create | ?dev=1 query param context |
| `frontend/src/hooks/useJobPolling.ts` | Create | Poll /jobs/{id}/status every 3s |
| `frontend/src/hooks/useAddresses.ts` | Create | Address CRUD via TanStack Query |
| `frontend/src/components/layout/NavBar.tsx` | Create | Top nav with tool tabs, dev toggle |
| `frontend/src/components/layout/PageShell.tsx` | Create | Page title + step indicator + children |
| `frontend/src/components/StepIndicator.tsx` | Create | Horizontal step breadcrumb |
| `frontend/src/components/FileDropZone.tsx` | Create | Drag-and-drop file upload |
| `frontend/src/components/ResultsTable.tsx` | Create | Filterable data table with status dots |
| `frontend/src/components/SegmentedProgressBar.tsx` | Create | Green/indigo/amber segments |
| `frontend/src/components/DownloadCard.tsx` | Create | Primary/secondary/disabled download |
| `frontend/src/components/SuccessBanner.tsx` | Create | Green success notification |
| `frontend/src/components/CarrierTile.tsx` | Create | Clickable carrier selection card |
| `frontend/src/components/DimensionsInput.tsx` | Create | L x W x H inline triple input |
| `frontend/src/pages/PickupRequest.tsx` | Create | Pickup Request form page |
| `frontend/src/pages/AddressValidator.tsx` | Create | Address Validator step-wizard page |
| `frontend/src/pages/LabelSorter.tsx` | Create | Label Sorter step-wizard page |
| `frontend/components.json` | Create | shadcn/ui config |

---

## Task 1: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `frontend/` directory with Vite scaffold
- Create: `frontend/tailwind.config.ts` with Cool Indigo tokens
- Create: `frontend/.env`
- Modify: `frontend/package.json` (add deps)
- Modify: `frontend/src/index.css` (Tailwind directives)

- [ ] **Step 1: Create Vite project**

```bash
cd /path/to/ELC
npm create vite@latest frontend -- --template react-ts
```

This creates the base scaffold with `src/main.tsx`, `src/App.tsx`, `index.html`, `vite.config.ts`, `tsconfig.json`, etc.

- [ ] **Step 2: Install core dependencies**

```bash
cd frontend
npm install react-router-dom @tanstack/react-query tailwindcss @tailwindcss/vite
npm install -D @types/node
```

- [ ] **Step 3: Install shadcn/ui**

shadcn/ui requires a specific setup. Run the init command:

```bash
cd frontend
npx shadcn@latest init
```

When prompted, select:
- Style: **Default**
- Base color: **Slate**
- CSS variables: **Yes**

This creates `components.json` and `src/components/ui/` directory. It also adds path aliases to `tsconfig.json`.

Then install the shadcn/ui components we need:

```bash
npx shadcn@latest add button card input label select switch table tabs badge separator toast dialog dropdown-menu toggle-group radio-group
```

- [ ] **Step 4: Configure Tailwind with Cool Indigo design tokens**

Replace the generated `frontend/tailwind.config.ts`:

```typescript
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Cool Indigo design system
        primary: {
          DEFAULT: "#6366f1",
          light: "#eef2ff",
          border: "#c7d2fe",
          foreground: "#ffffff",
        },
        success: {
          DEFAULT: "#22c55e",
          light: "#f0fdf4",
        },
        warning: {
          DEFAULT: "#f59e0b",
          light: "#fffbeb",
        },
        error: {
          DEFAULT: "#dc2626",
          light: "#fef2f2",
        },
        surface: "#f8f9fc",
        card: "#ffffff",
        border: "#e5e7eb",
        text: {
          primary: "#0f172a",
          secondary: "#64748b",
          muted: "#9ca3af",
        },
      },
      maxWidth: {
        content: "780px",
      },
      borderRadius: {
        card: "12px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0, 0, 0, 0.06)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}

export default config
```

- [ ] **Step 5: Update Vite config with API proxy**

```typescript
// frontend/vite.config.ts
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
})
```

Note: The proxy is for development convenience only. In production, `VITE_API_URL` points to the backend service directly.

- [ ] **Step 6: Set up CSS with Tailwind directives**

Replace `frontend/src/index.css`:

```css
/* frontend/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-surface text-text-primary antialiased;
    font-family: "Inter", system-ui, -apple-system, sans-serif;
  }
}

@layer components {
  .elc-card {
    @apply bg-card rounded-card border border-border shadow-card p-6;
  }
}
```

- [ ] **Step 7: Create .env file**

```bash
# frontend/.env
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 8: Clean up Vite scaffold**

Delete the default Vite boilerplate files that we don't need:

```bash
rm frontend/src/App.css
rm frontend/src/assets/react.svg
rm frontend/public/vite.svg
```

- [ ] **Step 9: Create minimal App.tsx to verify setup**

Replace `frontend/src/App.tsx` with a minimal placeholder:

```tsx
// frontend/src/App.tsx
function App() {
  return (
    <div className="min-h-screen bg-surface">
      <div className="max-w-content mx-auto p-8">
        <h1 className="text-2xl font-bold text-primary">ELC Tools</h1>
        <p className="text-text-secondary mt-2">Frontend scaffold is working.</p>
      </div>
    </div>
  )
}

export default App
```

- [ ] **Step 10: Verify dev server starts**

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. You should see "ELC Tools" in indigo with a cool off-white background. Verify:
- Tailwind classes apply (indigo text, gray background)
- No console errors
- TypeScript compiles cleanly

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Vite + React + TypeScript frontend with Tailwind and shadcn/ui

Cool Indigo design tokens, API proxy for dev, shadcn/ui initialized.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: API client + TypeScript types

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/colors.ts`

- [ ] **Step 1: Create API client**

The client is a thin typed wrapper around `fetch`. It reads `VITE_API_URL` for the base URL. In development with the Vite proxy, we can use relative paths (`/api/v1/...`), but in production the full URL is needed.

```typescript
// frontend/src/api/client.ts

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

  const json: ApiResponse<T> = await response.json()

  if (!json.ok || json.error) {
    const err = (json as ApiError).error
    throw new ApiRequestError(
      err?.code || "UNKNOWN",
      err?.message || "Unknown error",
      response.status
    )
  }

  return (json as ApiSuccess<T>).data
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
```

- [ ] **Step 2: Create TypeScript types matching backend schemas**

These types mirror the Pydantic schemas defined in `backend/app/schemas/`. Refer to the backend plan Task 4 for the exact schema definitions.

```typescript
// frontend/src/lib/types.ts

// --- Common ---

export interface JobCreatedResponse {
  job_id: string
}

export interface JobProgress {
  current: number
  total: number
  message: string
}

export interface JobStatus<T = unknown> {
  status: "processing" | "complete" | "failed"
  job_type: string
  progress: JobProgress | null
  result: T | null
  error: string | null
}

// --- Label Sorter ---

export interface LabelUnmatchedDetail {
  page: number
  tracking: string
  carrier: string
  reason: string
}

export interface LabelJobResult {
  total_pages: number
  matched: number
  unmatched: number
  match_rate: number
  unmatched_details: LabelUnmatchedDetail[]
  files: {
    pdf: string
    csv: string
  }
}

export type LabelJobStatus = JobStatus<LabelJobResult>

// --- Address Validator ---

export interface ValidatorResultRow {
  status: "verified" | "corrected" | "review"
  city: string
  street: string
  original_zip: string
  suggested_zip: string | null
  suggested_street: string | null
  corrections: string[]
}

export interface ValidatorJobResult {
  total_rows: number
  valid_count: number
  corrected_count: number
  review_count: number
  skipped_count: number
  street_verified_count: number
  street_corrected_count: number
  po_invalid_count: number
  results: ValidatorResultRow[]
  files: {
    corrected: string
    review: string
  }
}

export type ValidatorJobStatus = JobStatus<ValidatorJobResult>

// --- Address Book ---

export interface Address {
  id: string
  name: string
  company: string
  contact_name: string
  street: string
  zip: string
  city: string
  province: string
  reference: string
  is_default: boolean
}

export interface AddressCreate {
  name: string
  company: string
  contact_name?: string
  street: string
  zip_code: string
  city: string
  province?: string
  reference?: string
  is_default?: boolean
}

export interface AddressUpdate {
  name?: string
  company?: string
  contact_name?: string
  street?: string
  zip_code?: string
  city?: string
  province?: string
  reference?: string
}

// --- Pickup Request ---

export interface PickupRequestData {
  carrier: "FedEx" | "DHL" | "UPS"
  pickup_date: string          // ISO date: "2026-03-20"
  time_start: string           // ISO time: "09:00:00"
  time_end: string             // ISO time: "17:00:00"
  company: string
  contact_name: string
  address: string
  zip_code: string
  city: string
  province: string
  reference: string
  num_packages: number
  weight_per_package: number
  length: number
  width: number
  height: number
  use_pallet: boolean
  num_pallets: number
  pallet_length: number
  pallet_width: number
  pallet_height: number
  notes: string
}

export interface PickupResponse {
  message: string
}

// --- Health ---

export interface HealthData {
  version: string
}

// --- Usage Stats (Address Validator) ---

export interface UsageStats {
  rows_used: number
  rows_limit: number
  rows_remaining: number
  reset_at: string             // ISO datetime
}
```

- [ ] **Step 3: Create design token constants**

These mirror the Tailwind config but are available as runtime JS values for dynamic styling (e.g., chart libraries, inline styles on progress bars).

```typescript
// frontend/src/lib/colors.ts

export const colors = {
  primary: "#6366f1",
  primaryLight: "#eef2ff",
  primaryBorder: "#c7d2fe",

  success: "#22c55e",
  successLight: "#f0fdf4",

  warning: "#f59e0b",
  warningLight: "#fffbeb",

  error: "#dc2626",
  errorLight: "#fef2f2",

  surface: "#f8f9fc",
  card: "#ffffff",
  border: "#e5e7eb",

  textPrimary: "#0f172a",
  textSecondary: "#64748b",
  textMuted: "#9ca3af",
} as const

/**
 * Status color mapping for result tables and progress bars.
 * Maps validation status → color token.
 */
export const statusColors = {
  verified: colors.success,
  corrected: colors.primary,
  review: colors.warning,
} as const

/**
 * Status background tints for table rows.
 */
export const statusBgColors = {
  verified: "transparent",
  corrected: "#fafaff",    // subtle indigo tint
  review: colors.warningLight,
} as const
```

- [ ] **Step 4: Create the api directory**

```bash
mkdir -p frontend/src/api frontend/src/lib
```

- [ ] **Step 5: Verify TypeScript compilation**

```bash
cd frontend
npx tsc --noEmit
```

Expected: No errors. If there are import resolution errors, verify the `@/` alias is configured in both `tsconfig.json` and `vite.config.ts`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/ frontend/src/lib/
git commit -m "feat: add API client, TypeScript types, and design token constants

Typed fetch wrapper with error handling, all types matching backend
Pydantic schemas, Cool Indigo color constants.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Layout shell + NavBar + routing

**Files:**
- Create: `frontend/src/components/layout/NavBar.tsx`
- Create: `frontend/src/components/layout/PageShell.tsx`
- Create: `frontend/src/hooks/useDevMode.ts`
- Modify: `frontend/src/App.tsx` (full rewrite with routing)
- Modify: `frontend/src/main.tsx` (add QueryClientProvider)

- [ ] **Step 1: Create useDevMode hook**

This hook reads and writes the `?dev=1` query parameter. It uses `useSearchParams` from React Router so the state persists across page navigations and reloads.

```typescript
// frontend/src/hooks/useDevMode.ts
import { useSearchParams } from "react-router-dom"
import { useCallback } from "react"

/**
 * Dev Mode hook — reads ?dev=1 from URL.
 * Returns [isDevMode, toggleDevMode].
 */
export function useDevMode(): [boolean, () => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const isDevMode = searchParams.get("dev") === "1"

  const toggleDevMode = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (next.get("dev") === "1") {
        next.delete("dev")
      } else {
        next.set("dev", "1")
      }
      return next
    })
  }, [setSearchParams])

  return [isDevMode, toggleDevMode]
}
```

- [ ] **Step 2: Create NavBar component**

```tsx
// frontend/src/components/layout/NavBar.tsx
import { NavLink } from "react-router-dom"
import { useDevMode } from "@/hooks/useDevMode"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/pickup", label: "Ritiro" },
  { to: "/validator", label: "Validator" },
  { to: "/labels", label: "Label Sorter" },
]

export function NavBar() {
  const [isDevMode, toggleDevMode] = useDevMode()

  return (
    <header className="sticky top-0 z-50 bg-card border-b border-border">
      <div className="max-w-content mx-auto flex items-center justify-between h-14 px-4">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-primary">ELC Tools</span>
          {isDevMode && (
            <Badge variant="outline" className="text-xs border-warning text-warning">
              DEV
            </Badge>
          )}
        </div>

        {/* Tool tabs */}
        <nav className="flex items-center gap-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "px-4 py-2 text-sm font-medium rounded-md transition-colors",
                  isActive
                    ? "text-primary bg-primary-light"
                    : "text-text-muted hover:text-text-primary hover:bg-gray-50"
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Dev toggle */}
        <button
          onClick={toggleDevMode}
          className={cn(
            "p-2 rounded-md text-sm transition-colors",
            isDevMode
              ? "text-warning bg-warning-light"
              : "text-text-muted hover:text-text-secondary hover:bg-gray-50"
          )}
          title={isDevMode ? "Disabilita Dev Mode" : "Abilita Dev Mode"}
        >
          ⚙️
        </button>
      </div>
    </header>
  )
}
```

- [ ] **Step 3: Create PageShell component**

```tsx
// frontend/src/components/layout/PageShell.tsx
import { ReactNode } from "react"

interface PageShellProps {
  title: string
  subtitle?: string
  stepIndicator?: ReactNode
  children: ReactNode
}

/**
 * Page wrapper — title, optional subtitle, optional step indicator, then children.
 * Centered at max-width 780px matching the design spec.
 */
export function PageShell({ title, subtitle, stepIndicator, children }: PageShellProps) {
  return (
    <main className="max-w-content mx-auto px-4 py-8">
      {/* Step indicator (above title) */}
      {stepIndicator && <div className="mb-8">{stepIndicator}</div>}

      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-text-primary">{title}</h1>
        {subtitle && (
          <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>
        )}
      </div>

      {/* Page content */}
      {children}
    </main>
  )
}
```

- [ ] **Step 4: Update main.tsx with providers**

```tsx
// frontend/src/main.tsx
import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import App from "./App"
import "./index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
```

- [ ] **Step 5: Update App.tsx with routing**

```tsx
// frontend/src/App.tsx
import { Routes, Route, Navigate } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"

// Placeholder pages — replaced in Tasks 6-8
function PickupRequestPage() {
  return <div className="max-w-content mx-auto px-4 py-8"><h1 className="text-xl font-bold">Ritiro (coming soon)</h1></div>
}
function AddressValidatorPage() {
  return <div className="max-w-content mx-auto px-4 py-8"><h1 className="text-xl font-bold">Validator (coming soon)</h1></div>
}
function LabelSorterPage() {
  return <div className="max-w-content mx-auto px-4 py-8"><h1 className="text-xl font-bold">Label Sorter (coming soon)</h1></div>
}

export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <NavBar />
      <Routes>
        <Route path="/" element={<Navigate to="/pickup" replace />} />
        <Route path="/pickup" element={<PickupRequestPage />} />
        <Route path="/validator" element={<AddressValidatorPage />} />
        <Route path="/labels" element={<LabelSorterPage />} />
      </Routes>
    </div>
  )
}
```

- [ ] **Step 6: Create layout directories**

```bash
mkdir -p frontend/src/components/layout frontend/src/hooks frontend/src/pages
```

- [ ] **Step 7: Verify routing works**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`. Verify:
- Redirects from `/` to `/pickup`
- NavBar renders with "ELC Tools" logo, three tabs, and gear icon
- Clicking tabs navigates between pages (URL changes, active tab highlights indigo)
- Clicking gear toggles `?dev=1` in URL and shows "DEV" badge
- No console errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/
git commit -m "feat: add NavBar, PageShell, routing, dev mode toggle

React Router with 3 routes, NavBar with active tab highlighting,
dev mode via ?dev=1 URL param, TanStack Query provider.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Shared components

**Files:**
- Create: `frontend/src/components/StepIndicator.tsx`
- Create: `frontend/src/components/FileDropZone.tsx`
- Create: `frontend/src/components/SuccessBanner.tsx`
- Create: `frontend/src/components/DownloadCard.tsx`
- Create: `frontend/src/components/SegmentedProgressBar.tsx`
- Create: `frontend/src/components/CarrierTile.tsx`
- Create: `frontend/src/components/DimensionsInput.tsx`
- Create: `frontend/src/components/ResultsTable.tsx`

- [ ] **Step 1: StepIndicator**

Horizontal breadcrumb with numbered circles connected by lines. Used by Label Sorter (4 steps) and Address Validator (3 steps).

```tsx
// frontend/src/components/StepIndicator.tsx
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
                  isCurrent && "bg-primary border-primary text-white",
                  isFuture && "bg-white border-border text-text-muted"
                )}
              >
                {isCompleted ? "✓" : index + 1}
              </div>
              <span
                className={cn(
                  "mt-1.5 text-xs font-medium whitespace-nowrap",
                  isCompleted && "text-success",
                  isCurrent && "text-primary font-bold",
                  isFuture && "text-text-muted"
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
```

- [ ] **Step 2: FileDropZone**

Drag-and-drop file upload with client-side validation. Supports single or multiple files.

```tsx
// frontend/src/components/FileDropZone.tsx
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
  /** Max file size in MB (client-side UX check only — server enforces) */
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
  icon = "📄",
  onFilesSelected,
  selectedFiles = [],
  error,
}: FileDropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return
      const files = Array.from(fileList)

      // Client-side size check (UX convenience only)
      const oversized = files.filter(
        (f) => f.size / (1024 * 1024) > maxSizeMB
      )
      if (oversized.length > 0) {
        // Still pass through — server will reject
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

  const handleDragLeave = useCallback(() => {
    setIsDragging(false)
  }, [])

  const hasFiles = selectedFiles.length > 0

  return (
    <div>
      <div
        className={cn(
          "relative rounded-card border-2 border-dashed p-8 text-center cursor-pointer transition-colors",
          isDragging && "bg-primary-light border-primary",
          !isDragging && !hasFiles && "border-primary-border hover:bg-primary-light",
          hasFiles && "border-success bg-success-light",
          error && "border-error"
        )}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
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
            <p className="font-semibold text-text-primary">{label}</p>
            {subtitle && (
              <p className="text-sm text-text-secondary mt-1">{subtitle}</p>
            )}
            <p className="text-xs text-text-muted mt-2">
              Max {maxSizeMB} MB
            </p>
          </>
        ) : (
          <>
            <div className="text-4xl mb-3">✅</div>
            {selectedFiles.map((f, i) => (
              <p key={i} className="text-sm font-medium text-text-primary">
                {f.name}{" "}
                <span className="text-text-muted">
                  ({(f.size / (1024 * 1024)).toFixed(1)} MB)
                </span>
              </p>
            ))}
            <p className="text-xs text-text-muted mt-2">
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
```

- [ ] **Step 3: SuccessBanner**

Green notification banner shown after successful operations.

```tsx
// frontend/src/components/SuccessBanner.tsx
interface SuccessBannerProps {
  message: string
  details?: string
}

export function SuccessBanner({ message, details }: SuccessBannerProps) {
  return (
    <div className="rounded-card bg-success-light border border-success/20 px-5 py-4">
      <p className="text-sm font-semibold text-green-800">{message}</p>
      {details && (
        <p className="text-sm text-green-700 mt-1">{details}</p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: DownloadCard**

Download button styled as a card. Three variants: primary (filled indigo), secondary (outlined), disabled (gray with lock icon).

```tsx
// frontend/src/components/DownloadCard.tsx
import { cn } from "@/lib/utils"

interface DownloadCardProps {
  /** File display name */
  label: string
  /** Subtitle (e.g., file format info) */
  subtitle?: string
  /** Download URL */
  href: string
  /** Visual variant */
  variant: "primary" | "secondary" | "disabled"
  /** File icon/emoji */
  icon?: string
}

export function DownloadCard({
  label,
  subtitle,
  href,
  variant,
  icon,
}: DownloadCardProps) {
  const isDisabled = variant === "disabled"

  return (
    <a
      href={isDisabled ? undefined : href}
      download
      className={cn(
        "block rounded-card p-5 transition-all",
        variant === "primary" &&
          "bg-primary text-white hover:bg-primary/90 shadow-card",
        variant === "secondary" &&
          "bg-card border border-border text-text-primary hover:border-primary hover:shadow-card",
        variant === "disabled" &&
          "bg-gray-100 text-text-muted cursor-not-allowed opacity-60"
      )}
      onClick={(e) => isDisabled && e.preventDefault()}
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">
          {isDisabled ? "🔒" : icon || "📥"}
        </span>
        <div>
          <p className={cn(
            "font-semibold text-sm",
            variant === "primary" && "text-white",
          )}>
            {label}
          </p>
          {subtitle && (
            <p className={cn(
              "text-xs mt-0.5",
              variant === "primary" ? "text-white/80" : "text-text-secondary",
            )}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </a>
  )
}
```

- [ ] **Step 5: SegmentedProgressBar**

Horizontal bar with green (verified), indigo (corrected), amber (review) segments. Used by Address Validator results.

```tsx
// frontend/src/components/SegmentedProgressBar.tsx
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
      <div className="h-4 rounded-full overflow-hidden flex bg-gray-100">
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
          <div key={i} className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: seg.color }}
            />
            {seg.label}: <span className="font-semibold text-text-primary">{seg.value}</span>
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
```

- [ ] **Step 6: CarrierTile**

Clickable carrier selection card for Pickup Request.

```tsx
// frontend/src/components/CarrierTile.tsx
import { cn } from "@/lib/utils"

interface CarrierTileProps {
  carrier: string
  icon: string
  selected: boolean
  onClick: () => void
}

const carrierIcons: Record<string, string> = {
  FedEx: "📦",
  DHL: "✈️",
  UPS: "🚚",
}

export function CarrierTile({ carrier, icon, selected, onClick }: CarrierTileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center justify-center rounded-card border-2 p-5 transition-all cursor-pointer w-full",
        selected
          ? "border-primary bg-primary-light shadow-card"
          : "border-border bg-card hover:border-primary-border hover:shadow-card"
      )}
    >
      <span className="text-3xl mb-2">{icon || carrierIcons[carrier] || "📦"}</span>
      <span
        className={cn(
          "text-sm font-semibold",
          selected ? "text-primary" : "text-text-primary"
        )}
      >
        {carrier}
      </span>
    </button>
  )
}
```

- [ ] **Step 7: DimensionsInput**

Inline triple input: L x W x H with "cm" suffix. Used for both package and pallet dimensions.

```tsx
// frontend/src/components/DimensionsInput.tsx
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
        <span className="flex-1 text-xs font-medium text-text-secondary pl-3">Lunghezza</span>
        <span className="w-6" />
        <span className="flex-1 text-xs font-medium text-text-secondary pl-3">Larghezza</span>
        <span className="w-6" />
        <span className="flex-1 text-xs font-medium text-text-secondary pl-3">Altezza</span>
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
        <span className="text-text-muted text-sm px-1">×</span>
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
        <span className="text-text-muted text-sm px-1">×</span>
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
        <span className="text-text-muted text-xs font-medium px-3">cm</span>
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
```

- [ ] **Step 8: ResultsTable**

Filterable data table with colored status dots and row tinting. Used by Address Validator results.

```tsx
// frontend/src/components/ResultsTable.tsx
import { useState } from "react"
import { cn } from "@/lib/utils"
import { statusColors, statusBgColors } from "@/lib/colors"
import type { ValidatorResultRow } from "@/lib/types"

interface ResultsTableProps {
  rows: ValidatorResultRow[]
  devMode?: boolean
}

type FilterMode = "all" | "problems"

export function ResultsTable({ rows, devMode = false }: ResultsTableProps) {
  const [filter, setFilter] = useState<FilterMode>("all")
  const [showAll, setShowAll] = useState(false)

  const filteredRows =
    filter === "problems"
      ? rows.filter((r) => r.status !== "verified")
      : rows

  const displayRows = showAll ? filteredRows : filteredRows.slice(0, 10)
  const hasMore = filteredRows.length > 10

  const statusLabels: Record<string, string> = {
    verified: "Verificato",
    corrected: "Corretto",
    review: "Da verificare",
  }

  return (
    <div className="elc-card overflow-hidden">
      {/* Filter tabs */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-border">
        <button
          onClick={() => { setFilter("all"); setShowAll(false) }}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
            filter === "all"
              ? "bg-primary text-white"
              : "text-text-secondary hover:bg-gray-100"
          )}
        >
          Tutti ({rows.length})
        </button>
        <button
          onClick={() => { setFilter("problems"); setShowAll(false) }}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
            filter === "problems"
              ? "bg-warning text-white"
              : "text-text-secondary hover:bg-gray-100"
          )}
        >
          Solo problemi ({rows.filter((r) => r.status !== "verified").length})
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-text-secondary border-b border-border">
              <th className="px-5 py-3 font-medium">Stato</th>
              <th className="px-5 py-3 font-medium">Citta</th>
              <th className="px-5 py-3 font-medium">Indirizzo</th>
              <th className="px-5 py-3 font-medium">CAP</th>
              {devMode && <th className="px-5 py-3 font-medium">Correzioni</th>}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-border last:border-b-0"
                style={{ backgroundColor: statusBgColors[row.status] }}
              >
                {/* Status dot + label */}
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: statusColors[row.status] }}
                    />
                    <span className="text-xs font-medium">
                      {statusLabels[row.status]}
                    </span>
                  </div>
                </td>

                {/* City */}
                <td className="px-5 py-3 text-text-primary">{row.city}</td>

                {/* Street — show correction inline */}
                <td className="px-5 py-3">
                  {row.suggested_street ? (
                    <span>
                      <span className="text-text-muted line-through">{row.street}</span>
                      {" → "}
                      <span className="font-semibold text-text-primary">{row.suggested_street}</span>
                    </span>
                  ) : (
                    <span className="text-text-primary">{row.street}</span>
                  )}
                </td>

                {/* ZIP — show correction inline */}
                <td className="px-5 py-3">
                  {row.suggested_zip ? (
                    <span>
                      <span className="text-text-muted line-through">{row.original_zip}</span>
                      {" → "}
                      <span className="font-semibold text-text-primary">{row.suggested_zip}</span>
                    </span>
                  ) : (
                    <span className="text-text-primary">{row.original_zip}</span>
                  )}
                </td>

                {/* Corrections (dev mode only) */}
                {devMode && (
                  <td className="px-5 py-3 text-xs text-text-secondary">
                    {row.corrections.join(", ") || "-"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Show more */}
      {hasMore && !showAll && (
        <div className="px-5 py-3 text-center border-t border-border">
          <button
            onClick={() => setShowAll(true)}
            className="text-xs text-primary font-medium hover:underline"
          >
            Mostra tutte le {filteredRows.length} righe ▾
          </button>
        </div>
      )}

      {/* Row count */}
      <div className="px-5 py-2 text-xs text-text-muted border-t border-border">
        {displayRows.length} di {filteredRows.length} righe
      </div>
    </div>
  )
}
```

- [ ] **Step 9: Verify all components compile**

```bash
cd frontend
npx tsc --noEmit
```

Expected: No TypeScript errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add shared UI components

StepIndicator, FileDropZone, SuccessBanner, DownloadCard,
SegmentedProgressBar, CarrierTile, DimensionsInput, ResultsTable.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: useJobPolling hook

**Files:**
- Create: `frontend/src/hooks/useJobPolling.ts`

- [ ] **Step 1: Implement the hook**

This hook uses TanStack Query's `refetchInterval` to poll the backend every 3 seconds. It stops when the job completes or fails. It also handles the 404 case (job expired / server restarted).

```typescript
// frontend/src/hooks/useJobPolling.ts
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
  /** Progress info (current, total, message) — only during processing */
  progress: { current: number; total: number; message: string } | null
  /** Job result — only when status is "complete" */
  result: T | null
  /** Error message — either job error or network error */
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useJobPolling.ts
git commit -m "feat: add useJobPolling hook with TanStack Query

Polls /api/v1/jobs/{id}/status every 3s, stops on complete/failed,
handles 404 (job expired) gracefully.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Pickup Request page

**Files:**
- Create: `frontend/src/hooks/useAddresses.ts`
- Create: `frontend/src/pages/PickupRequest.tsx`
- Modify: `frontend/src/App.tsx` (swap placeholder)

- [ ] **Step 1: Create useAddresses hook**

CRUD operations for the address book via TanStack Query.

```typescript
// frontend/src/hooks/useAddresses.ts
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
```

- [ ] **Step 2: Create PickupRequest page**

This is the most complex form page. It has 4 card sections: Carrier + Date/Time, Address, Packages, Notes. Plus a sticky summary bar at the bottom.

```tsx
// frontend/src/pages/PickupRequest.tsx
import { useState, useMemo } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { CarrierTile } from "@/components/CarrierTile"
import { DimensionsInput } from "@/components/DimensionsInput"
import { SuccessBanner } from "@/components/SuccessBanner"
import { useAddresses } from "@/hooks/useAddresses"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import type { PickupRequestData, PickupResponse, Address } from "@/lib/types"

const CARRIERS = [
  { name: "FedEx", icon: "📦" },
  { name: "DHL", icon: "✈️" },
  { name: "UPS", icon: "🚚" },
] as const

const DEFAULT_FORM: PickupRequestData = {
  carrier: "FedEx",
  pickup_date: new Date().toISOString().split("T")[0],
  time_start: "09:00:00",
  time_end: "17:00:00",
  company: "",
  contact_name: "",
  address: "",
  zip_code: "",
  city: "",
  province: "",
  reference: "",
  num_packages: 1,
  weight_per_package: 5,
  length: 40,
  width: 30,
  height: 20,
  use_pallet: false,
  num_pallets: 0,
  pallet_length: 120,
  pallet_width: 80,
  pallet_height: 100,
  notes: "",
}

export default function PickupRequest() {
  const [isDevMode] = useDevMode()
  const [form, setForm] = useState<PickupRequestData>(DEFAULT_FORM)
  const [showNotes, setShowNotes] = useState(false)
  const [selectedAddressId, setSelectedAddressId] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const { addresses, isLoading: addressesLoading } = useAddresses()

  // Auto-populate from selected address
  const selectAddress = (addr: Address) => {
    setSelectedAddressId(addr.id)
    setForm((prev) => ({
      ...prev,
      company: addr.company,
      contact_name: addr.contact_name,
      address: addr.street,
      zip_code: addr.zip,
      city: addr.city,
      province: addr.province,
      reference: addr.reference,
    }))
  }

  // Auto-select default address on load
  useMemo(() => {
    if (addresses.length > 0 && !selectedAddressId) {
      const defaultAddr = addresses.find((a) => a.is_default) || addresses[0]
      selectAddress(defaultAddr)
    }
  }, [addresses])

  // Computed summary
  const totalWeight = form.num_packages * form.weight_per_package
  const shipmentType = totalWeight > 70 ? "FREIGHT" : "NORMAL"

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: (data: PickupRequestData) =>
      api.post<PickupResponse>("/api/v1/pickup/request", data),
    onSuccess: (result) => {
      setSuccessMessage(result.message)
    },
  })

  const handleSubmit = () => {
    setSuccessMessage(null)
    submitMutation.mutate(form)
  }

  const update = <K extends keyof PickupRequestData>(
    key: K,
    value: PickupRequestData[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  if (successMessage) {
    return (
      <PageShell title="Richiesta Ritiro">
        <SuccessBanner message={successMessage} />
        <div className="mt-6 text-center">
          <Button
            variant="outline"
            onClick={() => {
              setSuccessMessage(null)
              setForm(DEFAULT_FORM)
              setSelectedAddressId(null)
            }}
          >
            Nuova richiesta
          </Button>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell title="Richiesta Ritiro" subtitle="Compila il modulo e invia la richiesta di ritiro.">
      <div className="space-y-6">
        {/* Card 1: Carrier + Date/Time */}
        <div className="elc-card">
          <div className="grid grid-cols-2 gap-6">
            {/* Carrier tiles */}
            <div>
              <Label className="text-sm font-semibold text-text-primary mb-3 block">
                Corriere
              </Label>
              <div className="grid grid-cols-3 gap-3">
                {CARRIERS.map((c) => (
                  <CarrierTile
                    key={c.name}
                    carrier={c.name}
                    icon={c.icon}
                    selected={form.carrier === c.name}
                    onClick={() => update("carrier", c.name as PickupRequestData["carrier"])}
                  />
                ))}
              </div>
            </div>

            {/* Date + Time */}
            <div className="space-y-4">
              <div>
                <Label htmlFor="pickup_date" className="text-sm font-semibold text-text-primary">
                  Data ritiro
                </Label>
                <Input
                  id="pickup_date"
                  type="date"
                  value={form.pickup_date}
                  onChange={(e) => update("pickup_date", e.target.value)}
                  className="mt-1.5"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="time_start" className="text-sm text-text-secondary">Dalle</Label>
                  <Input
                    id="time_start"
                    type="time"
                    value={form.time_start.slice(0, 5)}
                    onChange={(e) => update("time_start", e.target.value + ":00")}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="time_end" className="text-sm text-text-secondary">Alle</Label>
                  <Input
                    id="time_end"
                    type="time"
                    value={form.time_end.slice(0, 5)}
                    onChange={(e) => update("time_end", e.target.value + ":00")}
                    className="mt-1"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: Address */}
        <div className="elc-card">
          <div className="flex items-center justify-between mb-4">
            <Label className="text-sm font-semibold text-text-primary">
              Indirizzo ritiro
            </Label>
            {/* TODO: Address book manager dialog */}
          </div>

          {/* Address selector */}
          {addressesLoading ? (
            <p className="text-sm text-text-muted">Caricamento indirizzi...</p>
          ) : addresses.length > 0 ? (
            <div className="space-y-3">
              <select
                value={selectedAddressId || ""}
                onChange={(e) => {
                  const addr = addresses.find((a) => a.id === e.target.value)
                  if (addr) selectAddress(addr)
                }}
                className="w-full rounded-md border border-border px-3 py-2 text-sm bg-card"
              >
                {addresses.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} — {a.company}, {a.street}, {a.zip} {a.city}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            /* Manual entry fallback */
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-text-secondary">Azienda</Label>
                <Input value={form.company} onChange={(e) => update("company", e.target.value)} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs text-text-secondary">Contatto</Label>
                <Input value={form.contact_name} onChange={(e) => update("contact_name", e.target.value)} className="mt-1" />
              </div>
              <div className="col-span-2">
                <Label className="text-xs text-text-secondary">Indirizzo</Label>
                <Input value={form.address} onChange={(e) => update("address", e.target.value)} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs text-text-secondary">CAP</Label>
                <Input value={form.zip_code} onChange={(e) => update("zip_code", e.target.value)} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs text-text-secondary">Citta</Label>
                <Input value={form.city} onChange={(e) => update("city", e.target.value)} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs text-text-secondary">Provincia</Label>
                <Input value={form.province} onChange={(e) => update("province", e.target.value)} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs text-text-secondary">Riferimento</Label>
                <Input value={form.reference} onChange={(e) => update("reference", e.target.value)} className="mt-1" />
              </div>
            </div>
          )}
        </div>

        {/* Card 3: Packages */}
        <div className="elc-card">
          <Label className="text-sm font-semibold text-text-primary mb-4 block">
            Dettagli colli
          </Label>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-text-secondary">Numero colli</Label>
                <Input
                  type="number"
                  min={1}
                  value={form.num_packages}
                  onChange={(e) => update("num_packages", Number(e.target.value))}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-text-secondary">Peso per collo (kg)</Label>
                <Input
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={form.weight_per_package}
                  onChange={(e) => update("weight_per_package", Number(e.target.value))}
                  className="mt-1"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs text-text-secondary mb-1 block">Dimensioni collo</Label>
              <DimensionsInput
                length={form.length}
                width={form.width}
                height={form.height}
                onChange={(dims) =>
                  setForm((prev) => ({ ...prev, ...dims }))
                }
              />
            </div>

            {/* Pallet toggle */}
            <div className="flex items-center gap-3 pt-2">
              <Switch
                checked={form.use_pallet}
                onCheckedChange={(checked) => update("use_pallet", checked)}
              />
              <Label className="text-sm text-text-primary">Bancale / Pallet</Label>
            </div>

            {form.use_pallet && (
              <div className="pl-1 space-y-4 border-l-2 border-primary-border ml-4 pl-4">
                <div>
                  <Label className="text-xs text-text-secondary">Numero pallet</Label>
                  <Input
                    type="number"
                    min={1}
                    value={form.num_pallets}
                    onChange={(e) => update("num_pallets", Number(e.target.value))}
                    className="mt-1 max-w-[120px]"
                  />
                </div>
                <div>
                  <Label className="text-xs text-text-secondary mb-1 block">Dimensioni pallet</Label>
                  <DimensionsInput
                    length={form.pallet_length}
                    width={form.pallet_width}
                    height={form.pallet_height}
                    onChange={(dims) =>
                      setForm((prev) => ({
                        ...prev,
                        pallet_length: dims.length,
                        pallet_width: dims.width,
                        pallet_height: dims.height,
                      }))
                    }
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Card 4: Notes (optional, hidden by default) */}
        {!showNotes ? (
          <button
            onClick={() => setShowNotes(true)}
            className="text-sm text-primary font-medium hover:underline"
          >
            + Aggiungi note
          </button>
        ) : (
          <div className="elc-card">
            <Label className="text-sm font-semibold text-text-primary mb-2 block">
              Note
            </Label>
            <textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={3}
              className="w-full rounded-md border border-border px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              placeholder="Note aggiuntive per il corriere..."
            />
          </div>
        )}

        {/* Sticky Summary Bar */}
        <div className="sticky bottom-0 bg-card border-t border-border px-6 py-4 -mx-4 rounded-t-card shadow-card">
          <div className="flex items-center justify-between max-w-content mx-auto">
            <div className="flex items-center gap-3 text-sm text-text-secondary">
              <span>{form.num_packages} colli</span>
              <span className="text-border">|</span>
              <span>{totalWeight.toFixed(1)} kg</span>
              <span className="text-border">|</span>
              <Badge
                variant={shipmentType === "FREIGHT" ? "destructive" : "secondary"}
                className="text-xs"
              >
                {shipmentType}
              </Badge>
              {shipmentType === "FREIGHT" && (
                <span className="text-xs text-error">Peso > 70 kg</span>
              )}
            </div>
            <Button
              onClick={handleSubmit}
              disabled={submitMutation.isPending}
              className="bg-primary hover:bg-primary/90 text-white px-6"
            >
              {submitMutation.isPending ? "Invio..." : "Invia Richiesta"}
            </Button>
          </div>
        </div>

        {/* Error */}
        {submitMutation.error && (
          <div className="rounded-card bg-error-light border border-error/20 px-5 py-4">
            <p className="text-sm text-red-800">
              {submitMutation.error instanceof Error
                ? submitMutation.error.message
                : "Errore durante l'invio"}
            </p>
          </div>
        )}

        {/* Dev mode debug */}
        {isDevMode && (
          <details className="elc-card">
            <summary className="text-sm font-medium text-text-secondary cursor-pointer">
              Debug: Form State
            </summary>
            <pre className="mt-3 text-xs overflow-auto p-3 bg-surface rounded-md">
              {JSON.stringify(form, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </PageShell>
  )
}
```

- [ ] **Step 3: Update App.tsx to use real page**

In `frontend/src/App.tsx`, replace the `PickupRequestPage` placeholder import:

```tsx
// frontend/src/App.tsx — update the imports and routes
import { Routes, Route, Navigate } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"
import PickupRequest from "@/pages/PickupRequest"

// Keep placeholders for pages not yet built
function AddressValidatorPage() {
  return <div className="max-w-content mx-auto px-4 py-8"><h1 className="text-xl font-bold">Validator (coming soon)</h1></div>
}
function LabelSorterPage() {
  return <div className="max-w-content mx-auto px-4 py-8"><h1 className="text-xl font-bold">Label Sorter (coming soon)</h1></div>
}

export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <NavBar />
      <Routes>
        <Route path="/" element={<Navigate to="/pickup" replace />} />
        <Route path="/pickup" element={<PickupRequest />} />
        <Route path="/validator" element={<AddressValidatorPage />} />
        <Route path="/labels" element={<LabelSorterPage />} />
      </Routes>
    </div>
  )
}
```

- [ ] **Step 4: Verify the page renders**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/pickup`. Verify:
- Four card sections render (Carrier, Address, Packages, Notes link)
- Carrier tiles are clickable, selected shows indigo border
- Date/time inputs work
- Pallet toggle reveals extra fields
- DimensionsInput shows L x W x H in one row
- Summary bar at bottom shows weight + NORMAL/FREIGHT badge
- "+ Aggiungi note" reveals a text area
- No console errors

Note: The submit button will fail because the backend isn't running yet. That's expected.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PickupRequest.tsx frontend/src/hooks/useAddresses.ts frontend/src/App.tsx
git commit -m "feat: add Pickup Request page with carrier tiles, address book, summary bar

Card-based form with carrier selection, address CRUD hook,
package dimensions, pallet toggle, sticky summary bar.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Address Validator page

**Files:**
- Create: `frontend/src/pages/AddressValidator.tsx`
- Modify: `frontend/src/App.tsx` (swap placeholder)

- [ ] **Step 1: Implement AddressValidator page**

This page has 3 steps: Upload, Processing (polling), Results.

```tsx
// frontend/src/pages/AddressValidator.tsx
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { StepIndicator } from "@/components/StepIndicator"
import { FileDropZone } from "@/components/FileDropZone"
import { SegmentedProgressBar, buildValidatorSegments } from "@/components/SegmentedProgressBar"
import { DownloadCard } from "@/components/DownloadCard"
import { ResultsTable } from "@/components/ResultsTable"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import type { ValidatorJobResult, JobCreatedResponse } from "@/lib/types"
import { colors } from "@/lib/colors"

const STEPS = [
  { label: "Carica" },
  { label: "Valida" },
  { label: "Risultato" },
]

export default function AddressValidator() {
  const [isDevMode] = useDevMode()
  const [currentStep, setCurrentStep] = useState(0)
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [confidence, setConfidence] = useState(90)
  const [streetConfidence, setStreetConfidence] = useState(85)
  const [bypassPin, setBypassPin] = useState("")

  // Job polling
  const {
    status: jobStatus,
    progress,
    result,
    error: jobError,
    isPolling,
    isExpired,
  } = useJobPolling<ValidatorJobResult>(jobId)

  // Move to results when job completes
  if (jobStatus === "complete" && currentStep === 1) {
    setCurrentStep(2)
  }

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData()
      formData.append("excel_file", excelFile!)
      formData.append("confidence_threshold", String(confidence))
      formData.append("street_confidence_threshold", String(streetConfidence))
      if (bypassPin) formData.append("bypass_pin", bypassPin)
      return api.postForm<JobCreatedResponse>("/api/v1/jobs/validator", formData)
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
      setCurrentStep(1)
    },
  })

  // Reset to start
  const handleReset = () => {
    setCurrentStep(0)
    setExcelFile(null)
    setJobId(null)
    setShowAdvanced(false)
    setBypassPin("")
  }

  return (
    <PageShell
      title="Address Validator"
      subtitle="Valida e correggi indirizzi italiani da file Excel."
      stepIndicator={<StepIndicator steps={STEPS} currentStep={currentStep} />}
    >
      <div className="space-y-6">

        {/* === STEP 0: Upload === */}
        {currentStep === 0 && (
          <>
            <FileDropZone
              label="Carica file Excel"
              subtitle="Formato .xlsx o .xls con colonne indirizzo"
              accept=".xlsx,.xls"
              icon="📊"
              maxSizeMB={50}
              onFilesSelected={(files) => setExcelFile(files[0] || null)}
              selectedFiles={excelFile ? [excelFile] : []}
            />

            {/* Usage stats placeholder — could be fetched from a /api/v1/validator/usage endpoint */}
            <div className="text-sm text-text-secondary">
              Validazioni disponibili: <span className="font-semibold">1000</span> righe / 12 ore
            </div>

            {/* Advanced options */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-sm text-primary font-medium hover:underline"
            >
              {showAdvanced ? "Nascondi opzioni avanzate ▴" : "Opzioni avanzate ▾"}
            </button>

            {showAdvanced && (
              <div className="elc-card space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs text-text-secondary">
                      Soglia confidenza CAP (%)
                    </Label>
                    <Input
                      type="number"
                      min={50}
                      max={100}
                      value={confidence}
                      onChange={(e) => setConfidence(Number(e.target.value))}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-text-secondary">
                      Soglia confidenza via (%)
                    </Label>
                    <Input
                      type="number"
                      min={50}
                      max={100}
                      value={streetConfidence}
                      onChange={(e) => setStreetConfidence(Number(e.target.value))}
                      className="mt-1"
                    />
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-text-secondary">PIN bypass (opzionale)</Label>
                  <Input
                    type="password"
                    value={bypassPin}
                    onChange={(e) => setBypassPin(e.target.value)}
                    className="mt-1 max-w-[200px]"
                    placeholder="PIN per bypassare il limite"
                  />
                </div>
              </div>
            )}

            <Button
              onClick={() => submitMutation.mutate()}
              disabled={!excelFile || submitMutation.isPending}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              {submitMutation.isPending ? "Avvio..." : "Avvia Validazione"}
            </Button>

            {submitMutation.error && (
              <p className="text-sm text-error">
                {submitMutation.error instanceof Error
                  ? submitMutation.error.message
                  : "Errore durante l'invio"}
              </p>
            )}
          </>
        )}

        {/* === STEP 1: Processing === */}
        {currentStep === 1 && (
          <div className="elc-card text-center py-12">
            {isExpired ? (
              <>
                <p className="text-lg font-semibold text-text-primary mb-2">
                  Job scaduto
                </p>
                <p className="text-sm text-text-secondary mb-6">
                  Il server e stato riavviato. Riprova.
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </>
            ) : jobStatus === "failed" ? (
              <>
                <p className="text-lg font-semibold text-error mb-2">
                  Errore
                </p>
                <p className="text-sm text-text-secondary mb-6">
                  {jobError}
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </>
            ) : (
              <>
                {/* Spinner */}
                <div className="inline-block w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4" />
                <p className="text-lg font-semibold text-text-primary">
                  Validazione in corso...
                </p>
                {progress && (
                  <div className="mt-4 max-w-xs mx-auto">
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div
                        className="bg-primary h-2 rounded-full transition-all duration-300"
                        style={{
                          width: `${(progress.current / progress.total) * 100}%`,
                        }}
                      />
                    </div>
                    <p className="text-xs text-text-muted mt-2">
                      {progress.message || `${progress.current} / ${progress.total}`}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* === STEP 2: Results === */}
        {currentStep === 2 && result && (
          <>
            {/* Progress bar */}
            <div className="elc-card">
              <SegmentedProgressBar
                segments={buildValidatorSegments(result)}
                total={result.total_rows}
              />

              {/* Breakdown chips */}
              <div className="flex flex-wrap gap-3 mt-4">
                <Badge variant="outline" className="text-xs px-3 py-1">
                  CAP: {result.valid_count} ✓ · {result.corrected_count} corretti · {result.review_count} ⚠
                </Badge>
                <Badge variant="outline" className="text-xs px-3 py-1">
                  Vie: {result.street_verified_count} ✓ · {result.street_corrected_count} corrette
                </Badge>
                {result.skipped_count > 0 && (
                  <Badge variant="outline" className="text-xs px-3 py-1">
                    {result.skipped_count} non-IT saltati
                  </Badge>
                )}
                {result.po_invalid_count > 0 && (
                  <Badge variant="destructive" className="text-xs px-3 py-1">
                    {result.po_invalid_count} PO non validi
                  </Badge>
                )}
              </div>
            </div>

            {/* PO warning */}
            {result.po_invalid_count > 0 && (
              <div className="rounded-card bg-error-light border border-error/20 px-5 py-4">
                <p className="text-sm font-semibold text-red-800">
                  Attenzione: {result.po_invalid_count} PO non validi trovati
                </p>
                <p className="text-sm text-red-700 mt-1">
                  Correggi i PO nel file originale oppure inserisci il PIN per scaricare comunque.
                </p>
              </div>
            )}

            {/* Download cards */}
            <div className="grid grid-cols-2 gap-4">
              <DownloadCard
                label="File corretto"
                subtitle="Excel con correzioni applicate"
                href={api.fileUrl(jobId!, "corrected.xlsx")}
                variant="primary"
                icon="📊"
              />
              <DownloadCard
                label="Report revisione"
                subtitle="Dettaglio righe da verificare"
                href={api.fileUrl(jobId!, "review.xlsx")}
                variant={result.review_count > 0 ? "secondary" : "disabled"}
                icon="📋"
              />
            </div>

            {/* Results table */}
            <ResultsTable rows={result.results} devMode={isDevMode} />

            {/* Reset button */}
            <div className="text-center">
              <Button variant="outline" onClick={handleReset}>
                Nuova validazione
              </Button>
            </div>

            {/* Dev mode debug */}
            {isDevMode && (
              <details className="elc-card">
                <summary className="text-sm font-medium text-text-secondary cursor-pointer">
                  Debug: Raw Result
                </summary>
                <pre className="mt-3 text-xs overflow-auto p-3 bg-surface rounded-md">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
```

- [ ] **Step 2: Update App.tsx**

Replace the `AddressValidatorPage` placeholder:

```tsx
// In frontend/src/App.tsx — add import and update route
import AddressValidator from "@/pages/AddressValidator"

// In Routes:
<Route path="/validator" element={<AddressValidator />} />
```

- [ ] **Step 3: Verify the page renders**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/validator`. Verify:
- Step indicator shows 3 steps with "Carica" active
- File drop zone renders with drag-and-drop area
- "Opzioni avanzate" toggles show/hide
- "Avvia Validazione" button is disabled until a file is selected
- No console errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/AddressValidator.tsx frontend/src/App.tsx
git commit -m "feat: add Address Validator page with 3-step wizard

Upload + polling + results with segmented progress bar, breakdown chips,
results table with filter tabs and inline corrections.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Label Sorter page

**Files:**
- Create: `frontend/src/pages/LabelSorter.tsx`
- Modify: `frontend/src/App.tsx` (swap placeholder)

- [ ] **Step 1: Implement LabelSorter page**

This page has 4 steps: Upload, Configure, Process, Download.

```tsx
// frontend/src/pages/LabelSorter.tsx
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageShell } from "@/components/layout/PageShell"
import { StepIndicator } from "@/components/StepIndicator"
import { FileDropZone } from "@/components/FileDropZone"
import { SuccessBanner } from "@/components/SuccessBanner"
import { DownloadCard } from "@/components/DownloadCard"
import { useJobPolling } from "@/hooks/useJobPolling"
import { useDevMode } from "@/hooks/useDevMode"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import type { LabelJobResult, JobCreatedResponse } from "@/lib/types"

const STEPS = [
  { label: "Carica" },
  { label: "Configura" },
  { label: "Elabora" },
  { label: "Scarica" },
]

type SortMethod = "excel_order" | "order_id_numeric"

export default function LabelSorter() {
  const [isDevMode] = useDevMode()
  const [currentStep, setCurrentStep] = useState(0)
  const [pdfFiles, setPdfFiles] = useState<File[]>([])
  const [excelFile, setExcelFile] = useState<File | null>(null)
  const [sortMethod, setSortMethod] = useState<SortMethod>("order_id_numeric")
  const [jobId, setJobId] = useState<string | null>(null)

  // Job polling
  const {
    status: jobStatus,
    progress,
    result,
    error: jobError,
    isPolling,
    isExpired,
  } = useJobPolling<LabelJobResult>(jobId)

  // Transition to download step when complete
  if (jobStatus === "complete" && currentStep === 2) {
    setCurrentStep(3)
  }

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData()
      pdfFiles.forEach((f) => formData.append("pdf_files", f))
      formData.append("excel_file", excelFile!)
      formData.append("sort_method", sortMethod)
      return api.postForm<JobCreatedResponse>("/api/v1/jobs/labels", formData)
    },
    onSuccess: (data) => {
      setJobId(data.job_id)
      setCurrentStep(2)
    },
  })

  // Reset
  const handleReset = () => {
    setCurrentStep(0)
    setPdfFiles([])
    setExcelFile(null)
    setSortMethod("order_id_numeric")
    setJobId(null)
  }

  // Can advance from upload to configure?
  const canConfigure = pdfFiles.length > 0 && excelFile !== null

  return (
    <PageShell
      title="Label Sorter"
      subtitle="Riordina le etichette PDF in base all'ordine dell'export Excel."
      stepIndicator={<StepIndicator steps={STEPS} currentStep={currentStep} />}
    >
      <div className="space-y-6">

        {/* === STEP 0: Upload === */}
        {currentStep === 0 && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <FileDropZone
                label="PDF Etichette"
                subtitle="Uno o piu file PDF con le etichette"
                accept=".pdf"
                multiple
                icon="📄"
                maxSizeMB={50}
                onFilesSelected={(files) => setPdfFiles(files)}
                selectedFiles={pdfFiles}
              />
              <FileDropZone
                label="Export Excel ShippyPro"
                subtitle="File .xlsx con l'elenco ordini"
                accept=".xlsx,.xls"
                icon="📊"
                maxSizeMB={50}
                onFilesSelected={(files) => setExcelFile(files[0] || null)}
                selectedFiles={excelFile ? [excelFile] : []}
              />
            </div>

            <Button
              onClick={() => setCurrentStep(1)}
              disabled={!canConfigure}
              className="bg-primary hover:bg-primary/90 text-white w-full"
            >
              Continua
            </Button>
          </>
        )}

        {/* === STEP 1: Configure === */}
        {currentStep === 1 && (
          <>
            <div className="elc-card">
              <Label className="text-sm font-semibold text-text-primary mb-4 block">
                Metodo di ordinamento
              </Label>
              <div className="grid grid-cols-2 gap-4">
                {/* Sort method cards */}
                <button
                  type="button"
                  onClick={() => setSortMethod("order_id_numeric")}
                  className={cn(
                    "rounded-card border-2 p-5 text-left transition-all",
                    sortMethod === "order_id_numeric"
                      ? "border-primary bg-primary-light"
                      : "border-border hover:border-primary-border"
                  )}
                >
                  <p className="font-semibold text-sm text-text-primary">
                    Ordine numerico ID
                  </p>
                  <p className="text-xs text-text-secondary mt-1">
                    Ordina per numero d'ordine crescente
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setSortMethod("excel_order")}
                  className={cn(
                    "rounded-card border-2 p-5 text-left transition-all",
                    sortMethod === "excel_order"
                      ? "border-primary bg-primary-light"
                      : "border-border hover:border-primary-border"
                  )}
                >
                  <p className="font-semibold text-sm text-text-primary">
                    Ordine Excel
                  </p>
                  <p className="text-xs text-text-secondary mt-1">
                    Mantieni l'ordine delle righe nel file Excel
                  </p>
                </button>
              </div>
            </div>

            {/* File summary */}
            <div className="text-sm text-text-secondary">
              <span className="font-medium">{pdfFiles.length}</span> PDF
              {pdfFiles.length > 1 ? " files" : ""} +{" "}
              <span className="font-medium">{excelFile?.name}</span>
            </div>

            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setCurrentStep(0)}>
                Indietro
              </Button>
              <Button
                onClick={() => submitMutation.mutate()}
                disabled={submitMutation.isPending}
                className="bg-primary hover:bg-primary/90 text-white flex-1"
              >
                {submitMutation.isPending ? "Avvio..." : "Avvia Elaborazione"}
              </Button>
            </div>

            {submitMutation.error && (
              <p className="text-sm text-error">
                {submitMutation.error instanceof Error
                  ? submitMutation.error.message
                  : "Errore durante l'invio"}
              </p>
            )}
          </>
        )}

        {/* === STEP 2: Processing === */}
        {currentStep === 2 && (
          <div className="elc-card text-center py-12">
            {isExpired ? (
              <>
                <p className="text-lg font-semibold text-text-primary mb-2">
                  Job scaduto
                </p>
                <p className="text-sm text-text-secondary mb-6">
                  Il server e stato riavviato. Riprova.
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </>
            ) : jobStatus === "failed" ? (
              <>
                <p className="text-lg font-semibold text-error mb-2">
                  Errore
                </p>
                <p className="text-sm text-text-secondary mb-6">
                  {jobError}
                </p>
                <Button variant="outline" onClick={handleReset}>
                  Ricomincia
                </Button>
              </>
            ) : (
              <>
                <div className="inline-block w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4" />
                <p className="text-lg font-semibold text-text-primary">
                  Elaborazione in corso...
                </p>
                {progress && (
                  <p className="text-sm text-text-muted mt-2">
                    {progress.message || `${progress.current} / ${progress.total}`}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {/* === STEP 3: Download === */}
        {currentStep === 3 && result && (
          <>
            {/* Success banner */}
            <SuccessBanner
              message={`${result.matched} di ${result.total_pages} matchate (${result.match_rate.toFixed(1)}%)`}
              details={
                result.unmatched > 0
                  ? `${result.unmatched} non matchate in fondo al PDF`
                  : undefined
              }
            />

            {/* Download cards */}
            <div className="grid grid-cols-2 gap-4">
              <DownloadCard
                label="PDF Riordinato"
                subtitle="Etichette ordinate pronte per la stampa"
                href={api.fileUrl(jobId!, "reordered.pdf")}
                variant="primary"
                icon="📄"
              />
              <DownloadCard
                label="Report CSV"
                subtitle="Dettaglio etichette non matchate"
                href={api.fileUrl(jobId!, "unmatched.csv")}
                variant={result.unmatched > 0 ? "secondary" : "disabled"}
                icon="📋"
              />
            </div>

            {/* Unmatched table (if any) */}
            {result.unmatched > 0 && (
              <details className="elc-card">
                <summary className="text-sm font-medium text-text-secondary cursor-pointer">
                  Mostra dettagli ({result.unmatched} non matchate) ▾
                </summary>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-text-secondary border-b border-border">
                        <th className="px-4 py-2 font-medium">Pag.</th>
                        <th className="px-4 py-2 font-medium">Tracking</th>
                        <th className="px-4 py-2 font-medium">Corriere</th>
                        <th className="px-4 py-2 font-medium">Motivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.unmatched_details.map((row, i) => (
                        <tr key={i} className="border-b border-border last:border-b-0">
                          <td className="px-4 py-2">{row.page}</td>
                          <td className="px-4 py-2 font-mono text-xs">{row.tracking}</td>
                          <td className="px-4 py-2">{row.carrier}</td>
                          <td className="px-4 py-2 text-text-secondary">{row.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}

            {/* Reset */}
            <div className="text-center">
              <Button variant="outline" onClick={handleReset}>
                Nuova elaborazione
              </Button>
            </div>

            {/* Dev mode debug */}
            {isDevMode && (
              <details className="elc-card">
                <summary className="text-sm font-medium text-text-secondary cursor-pointer">
                  Debug: Raw Result
                </summary>
                <pre className="mt-3 text-xs overflow-auto p-3 bg-surface rounded-md">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
```

- [ ] **Step 2: Update App.tsx**

Replace the `LabelSorterPage` placeholder:

```tsx
// In frontend/src/App.tsx — final version with all real pages
import { Routes, Route, Navigate } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"
import PickupRequest from "@/pages/PickupRequest"
import AddressValidator from "@/pages/AddressValidator"
import LabelSorter from "@/pages/LabelSorter"

export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <NavBar />
      <Routes>
        <Route path="/" element={<Navigate to="/pickup" replace />} />
        <Route path="/pickup" element={<PickupRequest />} />
        <Route path="/validator" element={<AddressValidator />} />
        <Route path="/labels" element={<LabelSorter />} />
      </Routes>
    </div>
  )
}
```

- [ ] **Step 3: Verify the page renders**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/labels`. Verify:
- Step indicator shows 4 steps with "Carica" active
- Two file drop zones render side by side (PDF + Excel)
- "Continua" button disabled until both files selected
- After selecting files, clicking "Continua" advances to step 2 (sort method selection)
- Sort method cards are clickable with indigo highlight
- "Indietro" returns to step 1
- No console errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LabelSorter.tsx frontend/src/App.tsx
git commit -m "feat: add Label Sorter page with 4-step wizard

Dual file upload, sort method card selection, processing spinner
with progress, success banner + download cards + unmatched table.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Render deployment config

**Files:**
- Modify: `render.yaml` (add elc-frontend service)
- Verify: `npm run build` succeeds

- [ ] **Step 1: Update render.yaml**

The `render.yaml` should already have the `elc-api` service from the backend migration. Add the `elc-frontend` service.

If `render.yaml` does not exist yet, create it. The full file:

```yaml
# render.yaml
services:
  - type: web
    name: elc-api
    runtime: python
    plan: starter
    region: frankfurt
    buildCommand: cd backend && pip install -r requirements.txt
    startCommand: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/v1/health
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: GOOGLE_ADDRESS_VALIDATION_API_KEY
        sync: false
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: ZAPIER_WEBHOOK_URL
        sync: false
      - key: BYPASS_PIN
        sync: false
      - key: FRONTEND_URL
        sync: false

  - type: web
    name: elc-frontend
    runtime: static
    buildCommand: cd frontend && npm ci && npm run build
    staticPublishPath: frontend/dist
    headers:
      - path: /*
        name: Cache-Control
        value: public, max-age=3600
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
    envVars:
      - key: VITE_API_URL
        sync: false
```

Key details:
- `VITE_API_URL` is a **build-time** env var — Vite inlines it during `npm run build`. Set it on Render to the `elc-api` service URL (e.g., `https://elc-api.onrender.com`).
- The `rewrite` rule sends all paths to `index.html` for React Router's client-side routing.
- `Cache-Control` header set to 1 hour for static assets.

- [ ] **Step 2: Verify production build**

```bash
cd frontend
npm run build
```

Expected output:
- `dist/` directory created with `index.html`, `assets/` (JS/CSS bundles)
- No TypeScript or build errors
- Build completes in under 30 seconds

```bash
ls -la frontend/dist/
ls -la frontend/dist/assets/
```

Verify `dist/index.html` exists and `dist/assets/` contains `.js` and `.css` files.

- [ ] **Step 3: Test production build locally**

```bash
cd frontend
npx serve dist -p 4173
```

Open `http://localhost:4173`. Verify:
- App loads (you should see the NavBar and tool pages)
- Navigating to `/pickup`, `/validator`, `/labels` works
- Refreshing a page (e.g., `/validator`) loads correctly (SPA fallback works)

Note: API calls will fail without the backend running — that's expected.

- [ ] **Step 4: Add frontend/dist to .gitignore**

Ensure the build output is not committed:

```bash
echo "dist/" >> frontend/.gitignore
```

- [ ] **Step 5: Commit**

```bash
git add render.yaml frontend/.gitignore
git commit -m "feat: add Render deployment config for frontend static site

render.yaml with elc-frontend service, SPA rewrite rule,
VITE_API_URL build-time env var, Cache-Control headers.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Summary

After completing all 9 tasks, the frontend directory structure will be:

```
frontend/
├── .env                           # VITE_API_URL=http://localhost:8000
├── .gitignore                     # includes dist/
├── components.json                # shadcn/ui config
├── index.html                     # HTML entry point
├── package.json                   # deps: react, react-router, tanstack-query, tailwind, shadcn
├── postcss.config.js              # PostCSS config
├── tailwind.config.ts             # Cool Indigo design tokens
├── tsconfig.json                  # TypeScript config
├── tsconfig.app.json              # App TS config
├── tsconfig.node.json             # Node TS config
├── vite.config.ts                 # Vite + API proxy + path alias
├── public/
└── src/
    ├── main.tsx                   # Entry: React + QueryClient + BrowserRouter
    ├── App.tsx                    # Routes: / → /pickup, /validator, /labels
    ├── index.css                  # Tailwind directives + .elc-card utility
    ├── api/
    │   └── client.ts              # Typed fetch wrapper (get, post, postForm, put, delete, fileUrl)
    ├── lib/
    │   ├── types.ts               # All TS types: Job*, Label*, Validator*, Address*, Pickup*
    │   ├── colors.ts              # Runtime color constants + statusColors map
    │   └── utils.ts               # cn() helper (from shadcn)
    ├── hooks/
    │   ├── useDevMode.ts          # ?dev=1 URL param read/toggle
    │   ├── useJobPolling.ts       # TanStack Query polling hook (3s interval)
    │   └── useAddresses.ts        # Address CRUD via TanStack Query mutations
    ├── components/
    │   ├── layout/
    │   │   ├── NavBar.tsx         # Logo + tab nav + dev toggle
    │   │   └── PageShell.tsx      # Page title + step indicator + children
    │   ├── ui/                    # shadcn/ui primitives (auto-generated)
    │   ├── StepIndicator.tsx      # Numbered step circles + connector lines
    │   ├── FileDropZone.tsx       # Drag-and-drop with client validation
    │   ├── SuccessBanner.tsx      # Green success notification
    │   ├── DownloadCard.tsx       # Primary/secondary/disabled download link
    │   ├── SegmentedProgressBar.tsx # Multi-color horizontal bar + legend
    │   ├── CarrierTile.tsx        # Selectable carrier card (FedEx/DHL/UPS)
    │   ├── DimensionsInput.tsx    # L × W × H inline triple input
    │   └── ResultsTable.tsx       # Filterable table with status dots + corrections
    └── pages/
        ├── PickupRequest.tsx      # 4-card form: carrier, address, packages, notes
        ├── AddressValidator.tsx   # 3-step wizard: upload → poll → results
        └── LabelSorter.tsx        # 4-step wizard: upload → configure → poll → download
```

**Total components:** 11 custom + shadcn/ui primitives
**Total hooks:** 3
**Total pages:** 3
**Estimated implementation time:** 45-60 minutes following this plan task-by-task
