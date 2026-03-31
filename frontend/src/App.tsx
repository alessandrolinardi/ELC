import { Routes, Route, Navigate, Link } from "react-router-dom"
import { NavBar } from "@/components/layout/NavBar"
import { useCrispTicket } from "@/hooks/useCrispTicket"
import PickupRequest from "@/pages/PickupRequest"
import AddressValidator from "@/pages/AddressValidator"
import LabelSorter from "@/pages/LabelSorter"
import ShipmentsQuotation from "@/pages/ShipmentsQuotation"
import ProofOfDelivery from "@/pages/ProofOfDelivery"

function CrispToast() {
  const { toast } = useCrispTicket()
  if (!toast) return null
  return (
    <div className="fixed bottom-20 right-6 z-50 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2.5 shadow-md">
        <p className="text-sm text-emerald-800">Il team è stato notificato.</p>
      </div>
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
        <Route path="/labels" element={<LabelSorter />} />
        <Route path="/quotation" element={<ShipmentsQuotation />} />
        <Route path="/pod" element={<ProofOfDelivery />} />
        <Route path="*" element={
          <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
            <h1 className="text-2xl font-semibold">Pagina non trovata</h1>
            <p className="text-muted-foreground">L'indirizzo richiesto non esiste.</p>
            <Link to="/" className="text-primary underline hover:no-underline">Torna alla home</Link>
          </div>
        } />
      </Routes>
      <CrispToast />
    </div>
  )
}
