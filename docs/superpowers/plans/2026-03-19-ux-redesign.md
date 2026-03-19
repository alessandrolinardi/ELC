# ELC Tools UX/UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign ELC Tools from default Streamlit to a professional AI-service UI with Cool Indigo palette, horizontal top-nav, step wizards, and card-based layouts.

**Architecture:** Pure CSS + `st.markdown(unsafe_allow_html=True)` approach — no custom Streamlit components. All changes in `app.py` and CSS injection. Backend logic (`src/`) untouched. UI helper functions extracted into `src/ui_components.py`.

**Tech Stack:** Streamlit, Python, custom HTML/CSS via st.markdown

**Spec:** `docs/superpowers/specs/2026-03-19-ux-redesign-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ui_components.py` | Create | Reusable UI helpers: nav bar, step indicator, cards, download buttons, progress bar, dev mode |
| `tests/test_ui_components.py` | Create | Unit tests for UI component HTML generation |
| `app.py:116-121` | Modify | Update `set_page_config` (layout, sidebar state) |
| `app.py:124-148` | Modify | Replace CSS block with new theme |
| `app.py:1537-1609` | Modify | Replace `main()` — remove sidebar, add top-nav routing |
| `app.py:178-512` | Modify | Redesign `label_sorter_page()` |
| `app.py:515-914` | Modify | Redesign `zip_validator_page()` |
| `app.py:1146-1534` | Modify | Redesign `pickup_request_page()` |
| `app.py:1056-1143` | Modify | Simplify `address_book_management()` into modal-style link |

---

## Phase 1: Foundation (CSS Theme + UI Components)

### Task 1: Create UI components module

**Files:**
- Create: `src/ui_components.py`
- Create: `tests/test_ui_components.py`

- [ ] **Step 1: Write failing tests for color system and nav bar**

```python
# tests/test_ui_components.py
import pytest
from src.ui_components import COLORS, TOOLS, render_nav_header, get_nav_css, render_step_indicator, render_card_open, render_card_close, render_download_card, render_success_banner, render_progress_bar, get_theme_css


class TestColors:
    def test_primary_color_is_indigo(self):
        assert COLORS["primary"] == "#6366f1"

    def test_all_required_tokens_exist(self):
        required = ["primary", "primary_light", "primary_border", "success", "warning", "error",
                     "background", "card", "border", "text_primary", "text_secondary", "text_muted"]
        for token in required:
            assert token in COLORS, f"Missing color token: {token}"


class TestNavHeader:
    def test_render_nav_header_contains_brand(self):
        html = render_nav_header(dev_mode=False)
        assert "ELC" in html
        assert "Tools" in html

    def test_render_nav_header_dev_toggle_link(self):
        html = render_nav_header(dev_mode=False)
        assert "⚙️" in html
        assert "?dev=1" in html

    def test_render_nav_header_dev_active(self):
        html = render_nav_header(dev_mode=True)
        assert "?dev=0" in html
        assert COLORS["primary"] in html


class TestNavCSS:
    def test_get_nav_css_hides_radio_circles(self):
        css = get_nav_css()
        assert 'input[type="radio"]' in css
        assert "display: none" in css

    def test_get_nav_css_styles_active_tab(self):
        css = get_nav_css()
        assert COLORS["primary"] in css


class TestToolsOrder:
    def test_tools_order_ritiro_first(self):
        assert TOOLS[0]["key"] == "ritiro"
        assert TOOLS[1]["key"] == "validator"
        assert TOOLS[2]["key"] == "label_sorter"


class TestStepIndicator:
    def test_render_step_indicator_current_step(self):
        steps = ["Carica", "Configura", "Elabora", "Scarica"]
        html = render_step_indicator(steps=steps, current=1)
        assert "Carica" in html
        assert "#6366f1" in html  # current step is indigo

    def test_render_step_indicator_completed_steps(self):
        steps = ["Carica", "Configura", "Elabora", "Scarica"]
        html = render_step_indicator(steps=steps, current=3)
        assert "#22c55e" in html  # completed steps are green
        assert "✓" in html


class TestCards:
    def test_render_card_open_returns_div(self):
        html = render_card_open()
        assert "<div" in html

    def test_render_card_close_returns_closing_div(self):
        html = render_card_close()
        assert "</div>" in html


class TestDownloadCard:
    def test_render_download_card_primary(self):
        html = render_download_card(label="Scarica PDF", primary=True)
        assert "#6366f1" in html
        assert "Scarica PDF" in html

    def test_render_download_card_secondary(self):
        html = render_download_card(label="Report CSV", primary=False)
        assert "Scarica PDF" not in html
        assert "Report CSV" in html

    def test_render_download_card_disabled(self):
        html = render_download_card(label="Scarica PDF", primary=True, disabled=True)
        assert "🔒" in html


class TestSuccessBanner:
    def test_render_success_banner(self):
        html = render_success_banner(message="338 di 342 matchate")
        assert "338 di 342 matchate" in html
        assert "#f0fdf4" in html  # green bg


class TestProgressBar:
    def test_render_progress_bar_percentages(self):
        html = render_progress_bar(verified=82, corrected=15, review=3)
        assert "82%" in html
        assert "#22c55e" in html  # green segment

    def test_render_progress_bar_empty(self):
        html = render_progress_bar(verified=0, corrected=0, review=0)
        assert html == ""

    def test_render_progress_bar_all_verified(self):
        html = render_progress_bar(verified=100, corrected=0, review=0)
        assert "100%" in html


class TestThemeCSS:
    def test_get_theme_css_hides_sidebar(self):
        css = get_theme_css()
        assert '[data-testid="stSidebar"]' in css
        assert "display: none" in css

    def test_get_theme_css_sets_background(self):
        css = get_theme_css()
        assert "#f8f9fc" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest tests/test_ui_components.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.ui_components'`

- [ ] **Step 3: Implement ui_components.py**

```python
# src/ui_components.py
"""
Reusable UI components for ELC Tools.
Generates HTML/CSS strings for st.markdown(unsafe_allow_html=True).
"""

COLORS = {
    "primary": "#6366f1",
    "primary_light": "#eef2ff",
    "primary_border": "#c7d2fe",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#dc2626",
    "background": "#f8f9fc",
    "card": "#ffffff",
    "border": "#e5e7eb",
    "text_primary": "#0f172a",
    "text_secondary": "#64748b",
    "text_muted": "#9ca3af",
}

TOOLS = [
    {"key": "ritiro", "icon": "🚚", "label": "Ritiro"},
    {"key": "validator", "icon": "📍", "label": "Address Validator"},
    {"key": "label_sorter", "icon": "📦", "label": "Label Sorter"},
]


def get_theme_css() -> str:
    """Return the global CSS theme that replaces default Streamlit styling."""
    return f"""
    <style>
        /* Hide sidebar */
        [data-testid="stSidebar"] {{ display: none; }}
        section[data-testid="stSidebar"] {{ display: none; }}

        /* Page background */
        .stApp {{ background-color: {COLORS['background']}; }}

        /* Centered content */
        .block-container {{
            max-width: 780px;
            padding-top: 1rem;
        }}

        /* Card styling for st.container */
        div[data-testid="stVerticalBlock"] > div.elc-card {{
            background: {COLORS['card']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}

        /* Primary button override */
        .stButton > button[kind="primary"] {{
            background-color: {COLORS['primary']};
            border: none;
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: #4f46e5;
        }}

        /* Download button styling */
        .stDownloadButton > button {{
            width: 100%;
            border-radius: 8px;
        }}

        /* Hide Streamlit header/footer chrome */
        header[data-testid="stHeader"] {{ background: transparent; }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
    </style>
    """


def render_nav_header(dev_mode: bool = False) -> str:
    """Render the brand header above the radio nav (logo + dev toggle)."""
    dev_style = f"color: {COLORS['primary']}; font-weight: 600;" if dev_mode else f"color: {COLORS['text_muted']};"
    return f"""
    <div style="background: white; padding: 12px 24px 0 24px; display: flex; align-items: center;
                justify-content: space-between; margin: -1rem -1rem 0 -1rem;">
        <div style="font-size: 16px; font-weight: 800; letter-spacing: -0.5px;">
            ELC <span style="color: {COLORS['primary']};">Tools</span>
        </div>
        <a href="?dev={'0' if dev_mode else '1'}" target="_self"
           style="font-size: 12px; text-decoration: none; {dev_style}">⚙️</a>
    </div>
    """


def get_nav_css() -> str:
    """CSS to restyle st.radio(horizontal=True) as a tab navigation bar."""
    return f"""
    <style>
        div[data-testid="stRadio"][aria-label="nav"] {{
            background: white;
            padding: 0 24px;
            margin: 0 -1rem 1.5rem -1rem;
            border-bottom: 1px solid {COLORS['border']};
        }}
        div[data-testid="stRadio"][aria-label="nav"] label {{
            padding: 10px 16px;
            font-size: 13px;
            cursor: pointer;
            color: {COLORS['text_muted']};
            border-bottom: 2px solid transparent;
        }}
        div[data-testid="stRadio"][aria-label="nav"] label[data-checked="true"] {{
            color: {COLORS['text_primary']};
            font-weight: 600;
            border-bottom: 2px solid {COLORS['primary']};
        }}
        div[data-testid="stRadio"][aria-label="nav"] input[type="radio"] {{
            display: none;
        }}
        div[data-testid="stRadio"][aria-label="nav"] > label:first-child {{
            display: none;
        }}
    </style>
    """


def render_step_indicator(steps: list[str], current: int) -> str:
    """
    Render a horizontal step indicator.
    steps: list of step labels, e.g. ["Carica", "Configura", "Elabora", "Scarica"]
    current: 1-indexed current step number
    """
    parts = []
    for i, label in enumerate(steps):
        step_num = i + 1
        if step_num < current:
            # Completed
            circle = (f'<div style="background: {COLORS["success"]}; color: white; '
                      f'width: 22px; height: 22px; border-radius: 50%; display: flex; '
                      f'align-items: center; justify-content: center; font-size: 11px;">✓</div>')
            text = f'<span style="font-size: 11px; color: {COLORS["success"]}; margin-left: 6px;">{label}</span>'
        elif step_num == current:
            # Current
            circle = (f'<div style="background: {COLORS["primary"]}; color: white; '
                      f'width: 22px; height: 22px; border-radius: 50%; display: flex; '
                      f'align-items: center; justify-content: center; font-size: 11px; font-weight: 700;">{step_num}</div>')
            text = f'<span style="font-size: 11px; font-weight: 600; margin-left: 6px;">{label}</span>'
        else:
            # Future
            circle = (f'<div style="background: {COLORS["border"]}; color: {COLORS["text_muted"]}; '
                      f'width: 22px; height: 22px; border-radius: 50%; display: flex; '
                      f'align-items: center; justify-content: center; font-size: 11px;">{step_num}</div>')
            text = f'<span style="font-size: 11px; color: {COLORS["text_muted"]}; margin-left: 6px;">{label}</span>'

        parts.append(f'<div style="display: flex; align-items: center;">{circle}{text}</div>')
        if i < len(steps) - 1:
            line_color = COLORS["success"] if step_num < current else COLORS["border"]
            parts.append(f'<div style="flex: 1; height: 2px; background: {line_color}; margin: 0 12px;"></div>')

    inner = "".join(parts)
    return (f'<div style="display: flex; align-items: center; padding: 12px 16px; '
            f'background: white; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); '
            f'margin-bottom: 16px;">{inner}</div>')


def render_card_open() -> str:
    """Open a card container div."""
    return (f'<div style="background: {COLORS["card"]}; border: 1px solid {COLORS["border"]}; '
            f'border-radius: 12px; padding: 20px; margin-bottom: 12px; '
            f'box-shadow: 0 1px 3px rgba(0,0,0,0.06);">')


def render_card_close() -> str:
    """Close a card container div."""
    return "</div>"


def render_success_banner(message: str) -> str:
    """Render a green success banner with a message."""
    return (f'<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; '
            f'padding: 12px 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 10px;">'
            f'<div style="font-size: 20px;">✅</div>'
            f'<div style="font-weight: 600; font-size: 13px;">{message}</div></div>')


def render_download_card(label: str, subtitle: str = "", primary: bool = True, disabled: bool = False) -> str:
    """Render a styled download card (visual only — actual download uses st.download_button)."""
    if disabled:
        return (f'<div style="background: {COLORS["border"]}; color: {COLORS["text_muted"]}; '
                f'border-radius: 8px; padding: 14px; text-align: center;">'
                f'<div style="font-size: 12px; font-weight: 600;">{label}</div>'
                f'<div style="font-size: 10px; margin-top: 4px;">🔒 Sblocca con PO validi</div></div>')
    if primary:
        return (f'<div style="background: {COLORS["primary"]}; color: white; '
                f'border-radius: 8px; padding: 14px; text-align: center;">'
                f'<div style="font-size: 12px; font-weight: 700;">{label}</div>'
                f'<div style="font-size: 10px; opacity: 0.8; margin-top: 4px;">{subtitle}</div></div>')
    return (f'<div style="background: white; border: 1px solid {COLORS["border"]}; '
            f'border-radius: 8px; padding: 14px; text-align: center;">'
            f'<div style="font-size: 12px; font-weight: 600;">{label}</div>'
            f'<div style="font-size: 10px; color: {COLORS["text_muted"]}; margin-top: 4px;">{subtitle}</div></div>')


def render_progress_bar(verified: int, corrected: int, review: int) -> str:
    """Render a segmented progress bar for Address Validator results."""
    total = verified + corrected + review
    if total == 0:
        return ""
    v_pct = round(verified / total * 100)
    c_pct = round(corrected / total * 100)
    r_pct = round(review / total * 100)

    return f"""
    <div style="margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; font-size: 11px;
                    color: {COLORS['text_secondary']}; margin-bottom: 4px;">
            <span>{total} indirizzi analizzati</span>
            <span>{verified} OK • {corrected} corretti • {review} da verificare</span>
        </div>
        <div style="background: #f1f5f9; border-radius: 4px; height: 10px; overflow: hidden; display: flex;">
            <div style="background: {COLORS['success']}; width: {v_pct}%;"></div>
            <div style="background: {COLORS['primary']}; width: {c_pct}%;"></div>
            <div style="background: {COLORS['warning']}; width: {r_pct}%;"></div>
        </div>
        <div style="display: flex; gap: 16px; margin-top: 6px; font-size: 10px;">
            <span><span style="display:inline-block;width:10px;height:10px;background:{COLORS['success']};
                   border-radius:2px;vertical-align:middle;margin-right:4px;"></span>Verificati ({v_pct}%)</span>
            <span><span style="display:inline-block;width:10px;height:10px;background:{COLORS['primary']};
                   border-radius:2px;vertical-align:middle;margin-right:4px;"></span>Auto-corretti ({c_pct}%)</span>
            <span><span style="display:inline-block;width:10px;height:10px;background:{COLORS['warning']};
                   border-radius:2px;vertical-align:middle;margin-right:4px;"></span>Da verificare ({r_pct}%)</span>
        </div>
    </div>
    """
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest tests/test_ui_components.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add src/ui_components.py tests/test_ui_components.py
git commit -m "feat: add UI components module with nav, steps, cards, progress bar"
```

---

### Task 2: Apply global CSS theme and hide sidebar

**Files:**
- Modify: `app.py:116-121` (set_page_config)
- Modify: `app.py:124-148` (CSS block)

- [ ] **Step 1: Update set_page_config**

In `app.py`, change the `st.set_page_config` call (line 116-121) to:

```python
st.set_page_config(
    page_title="ELC Tools",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="collapsed"
)
```

- [ ] **Step 2: Replace CSS block with theme CSS**

Replace the existing `st.markdown` CSS block (lines 124-148) with:

```python
from src.ui_components import get_theme_css
st.markdown(get_theme_css(), unsafe_allow_html=True)
```

Move the import to the top of the file with the other `src` imports.

- [ ] **Step 3: Run the app to verify sidebar is hidden and background color applies**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && streamlit run app.py`
Expected: Sidebar hidden, background is #f8f9fc, content still works

- [ ] **Step 4: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py
git commit -m "feat: apply indigo theme CSS and hide sidebar"
```

---

### Task 3: Replace sidebar navigation with top nav bar

**Files:**
- Modify: `app.py:1537-1609` (main function)

- [ ] **Step 1: Rewrite main() to use styled st.radio as the navigation mechanism**

The approach: Use `st.radio(horizontal=True)` as the actual clickable navigation control, then apply heavy CSS to restyle it to look like the designed top nav bar. This avoids JavaScript (which Streamlit strips) and hidden-button fragility.

Replace the entire `main()` function with:

```python
def main():
    from src.ui_components import render_nav_header, get_nav_css, TOOLS

    # Dev mode via query params (?dev=1)
    dev_mode = st.query_params.get("dev", "0") == "1"
    st.session_state.dev_mode = dev_mode

    # Render the brand header (ELC Tools logo + dev toggle)
    st.markdown(render_nav_header(dev_mode=dev_mode), unsafe_allow_html=True)

    # Inject CSS to restyle st.radio as a tab bar
    st.markdown(get_nav_css(), unsafe_allow_html=True)

    # Actual navigation control — st.radio styled as tabs
    tool_labels = [f'{t["icon"]} {t["label"]}' for t in TOOLS]
    selected_label = st.radio(
        "nav",
        options=tool_labels,
        horizontal=True,
        label_visibility="collapsed",
        key="nav_radio"
    )

    # Map selected label back to tool key
    selected_index = tool_labels.index(selected_label)
    active_tool = TOOLS[selected_index]["key"]

    # Route to selected feature
    if active_tool == "ritiro":
        pickup_request_page()
    elif active_tool == "validator":
        zip_validator_page()
    elif active_tool == "label_sorter":
        label_sorter_page()

    # Dev mode: log viewer at bottom of page
    if dev_mode:
        st.markdown("---")
        with st.expander("📋 Log Viewer", expanded=False):
            log_handler = get_streamlit_handler()
            logs = log_handler.get_logs()
            log_level = st.selectbox("Livello:", ["Tutti", "DEBUG", "INFO", "WARNING", "ERROR"], key="log_filter")
            if log_level != "Tutti":
                logs = [l for l in logs if l['level'] == log_level]
            if logs:
                for log in reversed(logs[-20:]):
                    level_color = {'DEBUG': '🔵', 'INFO': '🟢', 'WARNING': '🟡', 'ERROR': '🔴'}.get(log['level'], '⚪')
                    st.markdown(f"<small>{level_color} <code>{log['timestamp'][-8:]}</code> "
                                f"<b>{log['module']}</b>: {log['message'][:80]}</small>", unsafe_allow_html=True)
                if st.button("🗑️ Pulisci log", key="clear_logs"):
                    log_handler.clear()
                    st.rerun()
            else:
                st.info("Nessun log disponibile")
```

Also add these two new functions to `src/ui_components.py`:

```python
def render_nav_header(dev_mode: bool = False) -> str:
    """Render the brand header above the radio nav (logo + dev toggle)."""
    dev_style = f"color: {COLORS['primary']}; font-weight: 600;" if dev_mode else f"color: {COLORS['text_muted']};"
    return f"""
    <div style="background: white; padding: 12px 24px 0 24px; display: flex; align-items: center;
                justify-content: space-between; margin: -1rem -1rem 0 -1rem;">
        <div style="font-size: 16px; font-weight: 800; letter-spacing: -0.5px;">
            ELC <span style="color: {COLORS['primary']};">Tools</span>
        </div>
        <a href="?dev={'0' if dev_mode else '1'}" target="_self"
           style="font-size: 12px; text-decoration: none; {dev_style}">⚙️</a>
    </div>
    """


def get_nav_css() -> str:
    """CSS to restyle st.radio(horizontal=True) as a tab navigation bar."""
    return f"""
    <style>
        /* Restyle the nav radio as a tab bar */
        div[data-testid="stRadio"][aria-label="nav"] {{
            background: white;
            padding: 0 24px 0 24px;
            margin: 0 -1rem 1.5rem -1rem;
            border-bottom: 1px solid {COLORS['border']};
        }}
        div[data-testid="stRadio"][aria-label="nav"] label {{
            padding: 10px 16px;
            font-size: 13px;
            cursor: pointer;
            color: {COLORS['text_muted']};
            border-bottom: 2px solid transparent;
        }}
        div[data-testid="stRadio"][aria-label="nav"] label[data-checked="true"] {{
            color: {COLORS['text_primary']};
            font-weight: 600;
            border-bottom: 2px solid {COLORS['primary']};
        }}
        /* Hide radio circles */
        div[data-testid="stRadio"][aria-label="nav"] input[type="radio"] {{
            display: none;
        }}
        /* Hide the label text "nav" */
        div[data-testid="stRadio"][aria-label="nav"] > label:first-child {{
            display: none;
        }}
    </style>
    """
```

Note: The dev toggle uses an `<a>` tag linking to `?dev=1` / `?dev=0` — this works because Streamlit preserves `st.query_params` across navigation and `<a>` tags with `target="_self"` are not stripped by Streamlit's HTML sanitizer.

If the CSS selectors for `st.radio` prove fragile across Streamlit versions, fallback: use a plain `st.selectbox` in the header area. The CSS approach works well with Streamlit 1.28+ (the project's minimum version per requirements.txt).

- [ ] **Step 2: Add render_nav_header and get_nav_css to ui_components.py and tests**

Add the two functions above to `src/ui_components.py`. Add tests:

```python
class TestNavHeader:
    def test_render_nav_header_contains_brand(self):
        html = render_nav_header(dev_mode=False)
        assert "ELC" in html
        assert "Tools" in html

    def test_render_nav_header_dev_toggle(self):
        html = render_nav_header(dev_mode=False)
        assert "⚙️" in html
        assert "?dev=1" in html

    def test_render_nav_header_dev_active(self):
        html = render_nav_header(dev_mode=True)
        assert "?dev=0" in html
        assert COLORS["primary"] in html


class TestNavCSS:
    def test_get_nav_css_hides_radio_circles(self):
        css = get_nav_css()
        assert 'input[type="radio"]' in css
        assert "display: none" in css

    def test_get_nav_css_styles_active_tab(self):
        css = get_nav_css()
        assert COLORS["primary"] in css
```

- [ ] **Step 3: Remove all sidebar code from old main()**

Delete all `st.sidebar.*` calls including the log viewer expander and version footer. The log viewer is now at the bottom of the page gated behind `dev_mode`.

- [ ] **Step 4: Test navigation between all 3 tools**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && streamlit run app.py`
Expected: Brand header renders, radio tabs look like nav tabs, clicking switches pages, `?dev=1` shows log viewer at bottom

- [ ] **Step 5: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py src/ui_components.py tests/test_ui_components.py
git commit -m "feat: replace sidebar with horizontal top nav bar using styled st.radio"
```

---

## Phase 2: Pickup Request Redesign

### Task 4: Redesign Pickup Request page with card layout

**Files:**
- Modify: `app.py:1146-1534` (pickup_request_page)
- Modify: `app.py:1056-1143` (address_book_management)

- [ ] **Step 1: Rewrite pickup_request_page() — top section**

Replace the page header, info box, and carrier/date sections with:
- Page title via `st.markdown` (no emoji prefix)
- Card 1: Carrier tiles using `st.columns(3)` with `st.button` per carrier + date/time pickers. Carrier selection stored in `st.session_state.carrier`. Selected tile gets conditional indigo styling via CSS class injection.

- [ ] **Step 2: Rewrite address section**

Replace the `address_book_management()` expander with:
- Card 2: Address as a compact summary when selected from book (display-only markdown). "Cambia ▾" rendered as `st.selectbox`. "📒 Gestisci rubrica" as a link that opens the address book management in a separate expander or dialog.
- When "Nuovo indirizzo" is selected, show inline form fields within the card.

- [ ] **Step 3: Rewrite package details section**

Card 3:
- Quantity + Weight as `st.columns(2)` with `st.number_input`
- Dimensions as `st.columns([2, 0.3, 2, 0.3, 2, 0.5])` — 3 number inputs with × separators and "cm" label. Wrap in CSS to merge visually.
- Pallet as `st.toggle` (Streamlit 1.33+) or `st.checkbox` styled as toggle

- [ ] **Step 4: Rewrite summary + submit section**

- Summary bar: `st.columns([3, 1])` — left col shows weight/type summary, right col has submit button
- Notes: hidden by default, "+ Aggiungi note" checkbox reveals `st.text_area`
- Keep existing `send_pickup_request()` function call unchanged

- [ ] **Step 5: Test the full pickup request flow**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && streamlit run app.py`
Expected: Card-based layout, carrier tiles work, address book works, form submits correctly

- [ ] **Step 6: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py
git commit -m "feat: redesign Pickup Request page with card-based layout"
```

---

## Phase 3: Address Validator Redesign

### Task 5: Redesign Address Validator — upload + processing

**Files:**
- Modify: `app.py:515-670` (zip_validator_page, upload + processing section)

- [ ] **Step 1: Add step indicator to Address Validator**

At the top of `zip_validator_page()`, render the 3-step indicator:
```python
from src.ui_components import render_step_indicator
current_step = 1  # or 2/3 based on session state
st.markdown(render_step_indicator(["Carica", "Valida", "Risultato"], current_step), unsafe_allow_html=True)
```

- [ ] **Step 2: Redesign upload section**

- Single full-width upload card with dashed border
- Usage bar: `st.caption` with remaining validations
- Advanced options remain in `st.expander` but with cleaner label

- [ ] **Step 3: Test upload flow**

Run app, upload an Excel file, verify step indicator updates and processing begins.

- [ ] **Step 4: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py
git commit -m "feat: redesign Address Validator upload with step indicator"
```

---

### Task 6: Redesign Address Validator — results page

**Files:**
- Modify: `app.py:670-914` (zip_validator_page, results section)

- [ ] **Step 1: Replace 7 metric boxes with progress bar**

Use `render_progress_bar()` from ui_components. Calculate verified/corrected/review counts from `report` object. Add breakdown chips via `st.markdown`.

- [ ] **Step 2: Redesign PO warning**

Replace error/warning blocks with a single red banner using `st.markdown`:
```python
if report.po_invalid_count > 0 and not pin_valid:
    st.markdown(f"""
    <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px;
                padding: 12px 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 10px;">
        <div style="font-size: 18px;">🚨</div>
        <div>
            <div style="font-weight: 700; color: #dc2626;">{report.po_invalid_count} PO non validi — download bloccato</div>
            <div style="font-size: 12px; color: #991b1b;">Correggi i PO nel file originale oppure inserisci il PIN nelle opzioni avanzate</div>
        </div>
    </div>""", unsafe_allow_html=True)
```

- [ ] **Step 3: Add filter tabs to results table**

Use `st.radio(horizontal=True)` or `st.segmented_control` to toggle "Tutti" / "⚠️ Solo problemi". Filter the `simple_data` list based on selection before passing to `st.dataframe`.

- [ ] **Step 4: Redesign results table rows**

Replace emoji status with color-coded HTML dots. Show inline corrections in the table. Wrap table in a card.

- [ ] **Step 5: Conditionalize debug sections on dev mode**

```python
if st.session_state.get("dev_mode", False):
    # Show debug expanders (existing code)
    with st.expander("🔍 Debug: Testo estratto..."):
        ...
```

- [ ] **Step 6: Test full Address Validator flow**

Run app, upload file, verify progress bar, PO warning, filter tabs, download cards all work.

- [ ] **Step 7: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py
git commit -m "feat: redesign Address Validator results with progress bar and filter tabs"
```

---

## Phase 4: Label Sorter Redesign

### Task 7: Redesign Label Sorter page

**Files:**
- Modify: `app.py:178-512` (label_sorter_page)

- [ ] **Step 1: Add step indicator**

4-step indicator: Carica → Configura → Elabora → Scarica. Step advances based on session state (files uploaded → method selected → processing complete → results ready).

- [ ] **Step 2: Redesign upload section**

Two upload cards side by side with dashed borders. Replace the `st.expander` help guide with a `st.markdown` help link. Step indicator shows step 1.

- [ ] **Step 3: Redesign sort method section**

Show only after files uploaded (step 2). Sort options as styled radio cards.

- [ ] **Step 4: Redesign results section**

- Success banner via `render_success_banner()`
- Download cards: primary (PDF) indigo filled, secondary (CSV) outline
- Unmatched table in a clean card with "Mostra dettagli ▾"
- Debug sections gated behind `dev_mode`

- [ ] **Step 5: Test full Label Sorter flow**

Run app, upload PDF + Excel, process, verify results display correctly.

- [ ] **Step 6: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py
git commit -m "feat: redesign Label Sorter with step wizard and clean results"
```

---

## Phase 5: Final Polish

### Task 8: Dev Mode log viewer + final cleanup

**Files:**
- Modify: `app.py` (main function, bottom of each page)

- [ ] **Step 1: Add log viewer to dev mode**

When `dev_mode` is active, render a collapsible log viewer at the bottom of the page (move existing sidebar log viewer code here).

- [ ] **Step 2: Clean up dead code**

Remove any remaining `st.sidebar` references. Remove old CSS classes. Ensure no sidebar elements leak through.

- [ ] **Step 3: Run full smoke test of all 3 tools**

Test each tool end-to-end: upload, process, results, download. Verify dev mode toggle works via `?dev=1`.

- [ ] **Step 4: Commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add app.py src/ui_components.py
git commit -m "feat: add dev mode log viewer and final cleanup"
```

- [ ] **Step 5: Run all existing tests**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest tests/ -v`
Expected: ALL PASS (existing tests should not break since backend logic is untouched)

- [ ] **Step 6: Final commit**

```bash
cd /Users/alessandrolinardi/Desktop/ELC
git add -A
git commit -m "chore: UX redesign complete — Cool Indigo theme with top nav"
```
