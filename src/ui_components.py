"""
Reusable UI components for ELC Tools.

All functions return HTML strings meant for st.markdown(unsafe_allow_html=True).
Color palette: Cool Indigo (#6366f1).
"""

# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------
COLORS = {
    "primary": "#6366f1",
    "primary_light": "#eef2ff",
    "primary_border": "#c7d2fe",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "background": "#f8f9fc",
    "card": "#ffffff",
    "border": "#e5e7eb",
    "text_primary": "#1e293b",
    "text_secondary": "#475569",
    "text_muted": "#94a3b8",
}

# ---------------------------------------------------------------------------
# Tool definitions (order matters for the nav bar)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "key": "ritiro",
        "label": "📦 Ritiro Merce",
        "description": "Genera documenti di ritiro merce",
    },
    {
        "key": "validator",
        "label": "✅ Validatore Indirizzi",
        "description": "Valida e correggi indirizzi italiani",
    },
    {
        "key": "label_sorter",
        "label": "🏷️ Ordina Etichette",
        "description": "Ordina etichette per CAP / zona",
    },
]


# ---------------------------------------------------------------------------
# Theme CSS — global styles injected once at app start
# ---------------------------------------------------------------------------
def get_theme_css() -> str:
    """Return a <style> block that hides the Streamlit sidebar and applies
    the Cool Indigo theme to the whole page."""
    return f"""<style>
    /* Hide default Streamlit sidebar */
    [data-testid="stSidebar"] {{
        display: none;
    }}

    /* Page background */
    .stApp {{
        background: {COLORS["background"]};
    }}

    /* General button styling */
    .stButton > button {{
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s ease;
    }}

    /* Primary buttons */
    .stButton > button[kind="primary"] {{
        background: {COLORS["primary"]};
        color: white;
        border: none;
    }}

    /* File uploader */
    [data-testid="stFileUploader"] {{
        border: 2px dashed {COLORS["primary_border"]};
        border-radius: 12px;
        padding: 1rem;
    }}

    /* Expander styling */
    .streamlit-expanderHeader {{
        font-weight: 600;
        color: {COLORS["text_primary"]};
    }}
</style>"""


# ---------------------------------------------------------------------------
# Nav header — brand bar at the top
# ---------------------------------------------------------------------------
def render_nav_header(dev_mode: bool = False) -> str:
    """Return an HTML brand header with a dev-mode toggle link."""
    toggle_url = "?dev=0" if dev_mode else "?dev=1"
    dev_indicator = (
        f' <span style="background:{COLORS["primary"]};color:#fff;'
        f'padding:2px 8px;border-radius:4px;font-size:0.7rem;">DEV</span>'
        if dev_mode
        else ""
    )
    return f"""
    <div style="display:flex;align-items:center;justify-content:space-between;
                padding:0.75rem 1rem;background:{COLORS["card"]};
                border-bottom:1px solid {COLORS["border"]};margin-bottom:1rem;">
        <div style="display:flex;align-items:center;gap:0.5rem;">
            <span style="font-size:1.4rem;font-weight:700;color:{COLORS["text_primary"]};">
                📋 ELC Tools
            </span>
            {dev_indicator}
        </div>
        <a href="{toggle_url}" target="_self"
           style="text-decoration:none;font-size:1.1rem;color:{COLORS["text_muted"]};"
           title="{'Disattiva' if dev_mode else 'Attiva'} modalità sviluppatore">⚙️</a>
    </div>
    """


# ---------------------------------------------------------------------------
# Nav CSS — restyle st.radio as a tab bar
# ---------------------------------------------------------------------------
def get_nav_css() -> str:
    """Return a <style> block that turns st.radio into a horizontal tab bar."""
    return f"""<style>
    /* Hide radio circles */
    div[data-testid="stRadio"] input[type="radio"] {{
        display: none;
    }}

    /* Radio labels as tabs */
    div[data-testid="stRadio"] label {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.5rem 1.2rem;
        margin-right: 0.25rem;
        border-radius: 8px 8px 0 0;
        cursor: pointer;
        font-weight: 500;
        color: {COLORS["text_secondary"]};
        border: 1px solid transparent;
        border-bottom: 2px solid transparent;
        transition: all 0.15s ease;
    }}

    div[data-testid="stRadio"] label:hover {{
        background: {COLORS["primary_light"]};
        color: {COLORS["primary"]};
    }}

    /* Active tab */
    div[data-testid="stRadio"] label[data-checked="true"],
    div[data-testid="stRadio"] label:has(input:checked) {{
        color: {COLORS["primary"]};
        border-bottom: 2px solid {COLORS["primary"]};
        background: {COLORS["primary_light"]};
    }}
</style>"""


# ---------------------------------------------------------------------------
# Step indicator — horizontal breadcrumb
# ---------------------------------------------------------------------------
def render_step_indicator(steps: list[str], current: int) -> str:
    """Render a horizontal step indicator.

    Parameters
    ----------
    steps : list[str]
        Labels for each step (e.g. ["Carica", "Configura", "Elabora", "Scarica"]).
    current : int
        1-based index of the current step.
    """
    parts: list[str] = []
    for i, label in enumerate(steps, start=1):
        if i < current:
            # completed
            color = COLORS["success"]
            circle = f'<span style="width:24px;height:24px;border-radius:50%;background:{color};color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:0.75rem;">✓</span>'
        elif i == current:
            # active
            color = COLORS["primary"]
            circle = f'<span style="width:24px;height:24px;border-radius:50%;background:{color};color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:0.75rem;">{i}</span>'
        else:
            # upcoming
            color = COLORS["text_muted"]
            circle = f'<span style="width:24px;height:24px;border-radius:50%;background:{COLORS["border"]};color:{color};display:inline-flex;align-items:center;justify-content:center;font-size:0.75rem;">{i}</span>'

        text_color = color if i <= current else COLORS["text_muted"]
        step_html = (
            f'<span style="display:inline-flex;align-items:center;gap:0.35rem;">'
            f'{circle}'
            f'<span style="font-size:0.85rem;font-weight:{"600" if i == current else "400"};color:{text_color};">{label}</span>'
            f'</span>'
        )
        parts.append(step_html)

        # connector line (except after last step)
        if i < len(steps):
            line_color = COLORS["success"] if i < current else COLORS["border"]
            parts.append(
                f'<span style="flex:1;height:2px;background:{line_color};margin:0 0.5rem;"></span>'
            )

    return (
        f'<div style="display:flex;align-items:center;padding:0.75rem 0;margin-bottom:1rem;">'
        + "".join(parts)
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Card open / close
# ---------------------------------------------------------------------------
def render_card_open(padding: str = "1.5rem") -> str:
    """Return the opening <div> for a card container."""
    return (
        f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};'
        f'border-radius:12px;padding:{padding};margin-bottom:1rem;">'
    )


def render_card_close() -> str:
    """Return the closing </div> for a card container."""
    return "</div>"


# ---------------------------------------------------------------------------
# Success banner
# ---------------------------------------------------------------------------
def render_success_banner(message: str) -> str:
    """Render a green success banner with a checkmark."""
    return (
        f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
        f'padding:0.75rem 1rem;display:flex;align-items:center;gap:0.5rem;margin-bottom:1rem;">'
        f'<span style="font-size:1.2rem;">✅</span>'
        f'<span style="color:#166534;font-weight:500;">{message}</span>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Download card
# ---------------------------------------------------------------------------
def render_download_card(
    label: str,
    subtitle: str = "",
    primary: bool = True,
    disabled: bool = False,
) -> str:
    """Render a styled download card.

    Parameters
    ----------
    label : str
        Main button/card label.
    subtitle : str
        Optional secondary text below the label.
    primary : bool
        If True, use primary colour styling; otherwise neutral.
    disabled : bool
        If True, grey out the card and show a lock icon.
    """
    if disabled:
        return (
            f'<div style="background:{COLORS["card"]};border:1px solid {COLORS["border"]};'
            f'border-radius:10px;padding:1rem;text-align:center;opacity:0.55;cursor:not-allowed;">'
            f'<div style="font-size:1.5rem;">🔒</div>'
            f'<div style="font-weight:600;color:{COLORS["text_muted"]};margin-top:0.3rem;">{label}</div>'
            f'{"<div style=font-size:0.8rem;color:" + COLORS["text_muted"] + ";>" + subtitle + "</div>" if subtitle else ""}'
            f'</div>'
        )

    bg = COLORS["primary"] if primary else COLORS["card"]
    text = "#ffffff" if primary else COLORS["text_primary"]
    border = COLORS["primary"] if primary else COLORS["border"]
    icon = "⬇️"

    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:10px;'
        f'padding:1rem;text-align:center;cursor:pointer;transition:transform 0.15s ease;"'
        f' onmouseover="this.style.transform=\'scale(1.02)\'"'
        f' onmouseout="this.style.transform=\'scale(1)\'">'
        f'<div style="font-size:1.5rem;">{icon}</div>'
        f'<div style="font-weight:600;color:{text};margin-top:0.3rem;">{label}</div>'
        f'{"<div style=font-size:0.8rem;color:" + (COLORS["primary_light"] if primary else COLORS["text_secondary"]) + ";>" + subtitle + "</div>" if subtitle else ""}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Progress bar (segmented)
# ---------------------------------------------------------------------------
def render_progress_bar(verified: int, corrected: int, review: int) -> str:
    """Render a segmented horizontal progress bar.

    Parameters
    ----------
    verified : int
        Percentage of verified items (green).
    corrected : int
        Percentage of auto-corrected items (amber).
    review : int
        Percentage of items needing review (red).

    Returns an empty string when all values are zero.
    """
    total = verified + corrected + review
    if total == 0:
        return ""

    segments: list[str] = []
    if verified > 0:
        segments.append(
            f'<div style="width:{verified}%;background:{COLORS["success"]};height:100%;'
            f'border-radius:4px 0 0 4px;display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-size:0.7rem;font-weight:600;">{verified}%</div>'
        )
    if corrected > 0:
        segments.append(
            f'<div style="width:{corrected}%;background:{COLORS["warning"]};height:100%;'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-size:0.7rem;font-weight:600;">{corrected}%</div>'
        )
    if review > 0:
        segments.append(
            f'<div style="width:{review}%;background:{COLORS["error"]};height:100%;'
            f'border-radius:0 4px 4px 0;display:flex;align-items:center;justify-content:center;'
            f'color:#fff;font-size:0.7rem;font-weight:600;">{review}%</div>'
        )

    bar = "".join(segments)

    return (
        f'<div style="margin-bottom:1rem;">'
        f'<div style="display:flex;height:22px;border-radius:4px;overflow:hidden;'
        f'background:{COLORS["border"]};">{bar}</div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:0.35rem;font-size:0.75rem;">'
        f'<span style="color:{COLORS["success"]};">✅ Verificati {verified}%</span>'
        f'<span style="color:{COLORS["warning"]};">🔧 Corretti {corrected}%</span>'
        f'<span style="color:{COLORS["error"]};">⚠️ Da rivedere {review}%</span>'
        f'</div></div>'
    )
