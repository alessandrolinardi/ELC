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
        assert "#6366f1" in html

    def test_render_step_indicator_completed_steps(self):
        steps = ["Carica", "Configura", "Elabora", "Scarica"]
        html = render_step_indicator(steps=steps, current=3)
        assert "#22c55e" in html
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
        assert "Report CSV" in html

    def test_render_download_card_disabled(self):
        html = render_download_card(label="Scarica PDF", primary=True, disabled=True)
        assert "🔒" in html


class TestSuccessBanner:
    def test_render_success_banner(self):
        html = render_success_banner(message="338 di 342 matchate")
        assert "338 di 342 matchate" in html
        assert "#f0fdf4" in html


class TestProgressBar:
    def test_render_progress_bar_percentages(self):
        html = render_progress_bar(verified=82, corrected=15, review=3)
        assert "82%" in html
        assert "#22c55e" in html  # green for verified
        assert "#6366f1" in html  # indigo for corrected
        assert "#f59e0b" in html  # amber for review

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
