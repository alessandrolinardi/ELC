import { Routes, Route, Navigate } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"

// Placeholder pages -- replaced in Tasks 6-8
function PickupRequestPage() {
  return (
    <div className="max-w-[var(--max-width-content)] mx-auto px-4 py-8">
      <h1 className="text-xl font-bold">Ritiro (coming soon)</h1>
    </div>
  )
}
function AddressValidatorPage() {
  return (
    <div className="max-w-[var(--max-width-content)] mx-auto px-4 py-8">
      <h1 className="text-xl font-bold">Validator (coming soon)</h1>
    </div>
  )
}
function LabelSorterPage() {
  return (
    <div className="max-w-[var(--max-width-content)] mx-auto px-4 py-8">
      <h1 className="text-xl font-bold">Label Sorter (coming soon)</h1>
    </div>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-background">
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
