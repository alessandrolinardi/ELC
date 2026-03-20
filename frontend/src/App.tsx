import { Routes, Route, Navigate } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"
import PickupRequest from "@/pages/PickupRequest"
import AddressValidator from "@/pages/AddressValidator"
import LabelSorter from "@/pages/LabelSorter"

export default function App() {
  return (
    <div className="min-h-screen bg-background">
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
