import { Routes, Route, Navigate } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"
import PickupRequest from "@/pages/PickupRequest"
import AddressValidator from "@/pages/AddressValidator"

// Placeholder page -- replaced in Task 8
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
        <Route path="/pickup" element={<PickupRequest />} />
        <Route path="/validator" element={<AddressValidator />} />
        <Route path="/labels" element={<LabelSorterPage />} />
      </Routes>
    </div>
  )
}
