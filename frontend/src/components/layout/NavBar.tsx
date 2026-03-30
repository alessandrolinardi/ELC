import { useState } from "react"
import { NavLink } from "react-router-dom"
import { useDevMode } from "@/hooks/useDevMode"
import { Badge } from "@/components/ui/badge"
import { SupportDrawer } from "@/components/SupportDrawer"
import { cn } from "@/lib/utils"
import { Settings, MessageCircle } from "lucide-react"

const navItems = [
  { to: "/pickup", label: "Ritiro" },
  { to: "/validator", label: "Validator" },
  { to: "/labels", label: "Label Sorter" },
  { to: "/quotation", label: "Quotazione" },
  { to: "/pod", label: "POD" },
]

export function NavBar() {
  const [isDevMode, toggleDevMode] = useDevMode()
  const [supportOpen, setSupportOpen] = useState(false)

  return (
    <>
      <header className="sticky top-0 z-50 bg-card border-b border-border">
        <div className="max-w-[var(--max-width-content)] mx-auto flex items-center justify-between h-14 px-4">
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
                      ? "text-primary bg-indigo-light"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
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
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            )}
            title={isDevMode ? "Disabilita Dev Mode" : "Abilita Dev Mode"}
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Floating support button — fixed bottom-right */}
      {!supportOpen && (
        <button
          onClick={() => setSupportOpen(true)}
          className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-primary text-white shadow-lg hover:bg-primary/90 hover:shadow-xl hover:scale-105 transition-all flex items-center justify-center"
          title="Supporto"
        >
          <MessageCircle className="h-6 w-6" />
        </button>
      )}

      <SupportDrawer open={supportOpen} onClose={() => setSupportOpen(false)} />
    </>
  )
}
