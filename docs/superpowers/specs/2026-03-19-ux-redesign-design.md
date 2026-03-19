# ELC Tools — UX/UI Redesign Spec

## Context

ELC Tools is a Streamlit app (v2.0) for Estee Lauder logistics with 3 features (Label Sorter, Address Validator, Pickup Request) and plans to grow to 6-10+ tools. Users are office/operations staff with moderate technical comfort. The current UI suffers from default Streamlit aesthetics, confusing navigation, and information overload from always-visible debug sections.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Layout approach | Light top-nav with centered content | Familiar SaaS feel, max content width, no sidebar |
| Color palette | Cool Indigo (#6366f1) on #f8f9fc | Professional AI-service identity |
| Tab order | Ritiro → Validator → Label Sorter | Reflects usage frequency |
| Scalability | "Altro" overflow dropdown for 4+ tools | Handles growth without crowding nav |
| Debug/logs | Hidden behind Dev Mode toggle | Clean by default, available when needed |
| Platform | Desktop only | No mobile responsive constraints |

## 1. Navigation & Page Structure

### Top Navigation Bar
- **Remove Streamlit sidebar entirely** — hide via CSS/config
- Horizontal top bar with: `ELC Tools` logo (left), tool tabs (center), Dev Mode toggle (right)
- Active tool gets indigo underline (#6366f1), inactive tabs are gray (#9ca3af)
- When tools exceed ~5, overflow into a categorized "Altro ▾" dropdown
- Dev Mode toggle (top-right, ⚙️ icon) controls visibility of: log viewer, debug expanders, raw text panels, fuzzy match details

### Page Layout
- **Centered content**: max-width ~780px, auto margins
- **Background**: #f8f9fc (cool off-white)
- **Cards**: white background, 1px #e5e7eb border, 10-12px border-radius, subtle shadow (0 1px 3px rgba(0,0,0,0.06))
- Each tool page has a **step indicator** at the top showing progress through the workflow

### Step Indicator
- Horizontal breadcrumb with numbered circles connected by lines
- Current step: indigo circle (#6366f1) with bold label
- Completed steps: green circle (#22c55e) with checkmark
- Future steps: gray circle (#e5e7eb) with gray label
- Applies to Label Sorter (4 steps) and Address Validator (3 steps)
- Pickup Request has no steps — it's a single form submission, so no step indicator is shown

## 2. Color System

| Token | Value | Usage |
|-------|-------|-------|
| Primary | #6366f1 | Active tabs, buttons, step indicators, links |
| Primary light | #eef2ff | Selected states, hover backgrounds |
| Primary border | #c7d2fe | Dashed upload borders |
| Success | #22c55e | Completed steps, verified items, progress bar (OK) |
| Warning | #f59e0b | Items needing review, caution states |
| Error | #dc2626 | Validation errors, PO warnings, blocked states |
| Background | #f8f9fc | Page background |
| Card | #ffffff | Card backgrounds |
| Border | #e5e7eb | Card borders, dividers |
| Text primary | #0f172a | Headings, body text |
| Text secondary | #64748b | Labels, descriptions |
| Text muted | #9ca3af | Inactive tabs, placeholders |

## 3. Label Sorter Redesign

### Step Flow
1. **Carica file** — Upload PDF + Excel
2. **Configura** — Sort method selection
3. **Elabora** — Processing with progress
4. **Scarica** — Results + downloads

### Upload Step
- Two large upload cards side by side (flex, equal width)
- Dashed border (#c7d2fe), 12px border-radius
- Large icon (32px emoji), bold title, subtitle with format info, size limit caption
- Help link below: "📖 Come esportare da ShippyPro?" — opens inline help or modal (not an expander block)

### Sort Method
- Shown in step 2 after files are uploaded
- Radio options styled as selectable cards (not plain radio buttons)

### Processing
- Step indicator shows step 3 active
- Streamlit status blocks for each sub-step (keep existing 5-step progress)
- Remove verbose debug output from default view

### Results Step
- **Success banner**: green background (#f0fdf4), single line with key stats ("338 di 342 matchate (98.8%) • 4 non matchate in fondo al PDF")
- **Download cards**: Primary (PDF) gets filled indigo background with white text. Secondary (CSV report) gets white with outline. Both full-width within their column.
- **Unmatched table**: inside a clean white card, collapsible with "Mostra dettagli ▾" link. Simplified columns: Pag, Tracking, Motivo
- **Debug sections** (raw text, fuzzy matches): only visible when Dev Mode is active
- **"Nuova elaborazione"** button: outline style, centered below results

## 4. Address Validator Redesign

### Step Flow
1. **Carica** — Upload Excel
2. **Valida** — Processing with progress bar + ETA
3. **Risultato** — Results + downloads

### Upload Step
- Single upload card (full width)
- Usage bar below: "Validazioni disponibili: **887** di 1000 | Reset: 00:00"
- Advanced options (confidence thresholds, PIN) remain in a collapsible section

### Results Step
- **Consolidated progress bar** replaces 7 separate metric boxes:
  - Single horizontal bar with green (verified), indigo (auto-corrected), amber (needs review) segments
  - Legend below with colored dots
  - Breakdown chips: "CAP: 82 ✓ • 12 corretti • 3 ⚠️" | "Vie: 78 ✓ • 8 corrette • 14 ⚠️" | "3 non-IT saltati"
- **PO warning** (when applicable): red banner (#fef2f2) with actionable text explaining what to do ("Correggi i PO nel file originale oppure inserisci il PIN")
- **Download cards**: same pattern as Label Sorter (primary filled, secondary outline). Disabled state: gray background with 🔒 icon
- **Results table**:
  - Filter tabs at top: "Tutti" | "⚠️ Solo problemi"
  - Color-coded status dots (green ● / indigo ● / amber ●) instead of emoji
  - Inline corrections shown as "Via Turti → **Via Turati**" directly in the row
  - Auto-corrected rows get subtle indigo background (#fafaff)
  - Warning rows get subtle amber background (#fffbeb)
  - Pagination: "3 di 100 righe" with "Mostra tutte ▾" link
  - Full detail view (all columns) only visible in Dev Mode

## 5. Pickup Request Redesign

### Card-Based Form Layout
Replace the single long scroll with visually grouped cards:

#### Card 1: Carrier + Date/Time
- **Left half**: Carrier selection as visual tiles (not radio buttons). Selected carrier gets indigo border + light indigo background (#eef2ff). Each tile: icon + carrier name.
- **Right half**: Date picker + two time inputs (Dalle/Alle) in a compact layout

#### Card 2: Address
- Header with "Indirizzo ritiro" label + "📒 Gestisci rubrica" link (replaces the expander)
- Selected address shown as a compact summary card: icon + name + full address + contact info + "Cambia ▾" dropdown
- If "Nuovo indirizzo" selected: inline form fields appear within the card

#### Card 3: Package Details
- **Row 1**: Quantity + Weight per package (two inputs side by side)
- **Row 2**: Dimensions as **inline triple input**:
  - Single visual container with 3 number inputs separated by × characters
  - Labels above each: Lunghezza / Larghezza / Altezza
  - "cm" unit label at end
  - Per-field validation (only the invalid dimension highlights red)
  - Tab key navigates L → W → H
- **Pallet toggle**: clean switch toggle (not checkbox). When enabled, reveals pallet count + dimensions (same inline triple input pattern)

#### Card 4 (optional): Notes
- Not shown by default
- "+ Aggiungi note" link reveals a text area
- Reduces default form length

#### Sticky Summary + Submit Bar
- Bottom of the form, always visible
- Left: "3 colli • 15.0 kg • NORMAL" summary
- Right: "📧 Invia Richiesta" indigo primary button
- FREIGHT warning appears inline if weight > 70kg

## 6. Dev Mode

A global toggle accessible from the top-right corner of the nav bar.

**When OFF (default):**
- No log viewer
- No debug expanders
- No raw text panels
- No fuzzy match details
- Simplified result tables

**When ON:**
- Log viewer appears (collapsible panel, bottom of page or slide-out)
- Debug expanders visible in Label Sorter results
- Full detail columns visible in Address Validator table
- Usage/debug stats visible in Address Validator advanced section

State persisted via `st.query_params` (survives page reloads — `?dev=1` in URL).

## 7. Technical Considerations

### Streamlit Implementation Approach

**Sidebar hiding:** Use `[data-testid="stSidebar"] { display: none; }` in custom CSS (stable test ID selector, won't break across Streamlit versions). Combine with `initial_sidebar_state="collapsed"` in `set_page_config`.

**Top nav:** Implemented via `st.markdown(unsafe_allow_html=True)` with inline HTML/CSS. Navigation state managed through `st.query_params` or `st.session_state`. Tool switching triggers `st.rerun()`. The "Altro" dropdown is a future concern (not needed until tool count exceeds 5) — when needed, implement as a second row of tabs or a `st.selectbox` styled inline, avoiding JavaScript dependency.

**Step indicators:** Custom HTML via `st.markdown(unsafe_allow_html=True)`. Pure CSS, no JavaScript needed. Step state derived from session_state (which files are uploaded, whether processing is complete).

**Card layouts:** Use `st.container()` wrapped in custom CSS. Inject a `<style>` block via `st.markdown` that targets Streamlit containers with border, border-radius, padding, and background.

**Carrier tile selection:** Use `st.columns(3)` with `st.button()` in each column. Selected state tracked in `st.session_state.carrier`. Style the selected button's column with conditional CSS class injection. No custom component needed.

**Inline triple input (dimensions):** Use `st.columns([2, 0.3, 2, 0.3, 2, 0.5])` to create 3 `st.number_input` fields with × separator text in the narrow columns. CSS merges the visual appearance into one container by removing individual borders and wrapping in a shared border. Fallback: 3 standard `st.number_input` in `st.columns(3)` with labels L/W/H if CSS merge proves fragile.

**Sticky summary bar:** Implemented with CSS `position: sticky; bottom: 0;` on a `st.container()`. Graceful degradation: if sticky doesn't work in all Streamlit contexts, it simply scrolls normally at the bottom of the form (acceptable fallback).

**Results table filter tabs:** Use `st.segmented_control` (Streamlit 1.33+) or `st.radio(horizontal=True)` to toggle between "Tutti" and "Solo problemi". Each option renders a different filtered `st.dataframe`. No custom HTML table needed.

**Progress bar (Address Validator):** Custom HTML bar via `st.markdown` with inline `<div>` elements sized by percentage. Pure CSS, no JavaScript.

### Accessibility
- All color-coded indicators include a text label or symbol alongside the color (e.g., green dot + "✓ Verificato", amber dot + "⚠️ Da verificare") so status is never conveyed by color alone
- Primary indigo (#6366f1) on white meets WCAG AA contrast ratio (4.5:1+)
- Error red (#dc2626) on white meets WCAG AA

### Migration Path
- **Phase 1:** CSS theme + background color + sidebar hiding + centered content
- **Phase 2:** Top nav bar (replaces sidebar radio buttons)
- **Phase 3:** Page-by-page redesign (Pickup Request → Address Validator → Label Sorter, matching tab order)
- No backend changes required — all changes are in `app.py` and custom CSS
- Existing processing logic (src/) remains untouched
- This spec covers UI only. Any backend changes (e.g., Address Validator API rewrite) are separate scope.

## 8. Design Mockups

Visual mockups created during brainstorming are available in:
`.superpowers/brainstorm/` (two sessions: 62293-* and 70453-*)

Key mockup files:
- `design-approaches.html` — 3 initial approach options (B selected)
- `color-palettes.html` — 3 palette options (A: Cool Indigo selected)
- `navigation-detail.html` — Nav bar + page layout detail
- `results-design.html` — Label Sorter results before/after
- `address-validator-results.html` — Address Validator results before/after
- `pickup-request.html` — Pickup Request form before/after
- `dimensions-input.html` — Inline triple dimensions input detail
