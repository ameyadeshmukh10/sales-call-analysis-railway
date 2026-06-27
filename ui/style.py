"""EverWorker-branded styling helpers for the dashboard.

Light theme: white background, near-black text, emerald accents. Deeper accent
tones so color reads on white. No bright red — crimson only for the "lost"
semantic; amber for caution; slate for neutral/insufficient.
"""
from __future__ import annotations

# --- palette (light) ---
BG = "#ffffff"          # page background
PANEL = "#f8fafc"       # cards / panels
BORDER = "#e2e8f0"
TEXT = "#0f172a"        # near-black
MUTED = "#64748b"
EMERALD = "#059669"     # deeper than dark-mode emerald, reads on white
MINT = "#34d399"
AMBER = "#d97706"
SLATE = "#64748b"
ROSE = "#e11d48"        # crimson, for the "lost" semantic only
INFO = "#2563eb"

# tier badge colors (good / caution / bad / unknown)
GREEN = EMERALD
YELLOW = AMBER
RED = ROSE
GREY = SLATE

OUTCOME_COLOR = {"won": EMERALD, "open": SLATE, "lost": ROSE, "no_deal": "#94a3b8"}
ICP_COLOR = {"1": EMERALD, "2": AMBER, "deprioritize": SLATE, "None": "#94a3b8"}
OBJECTION_COLOR = {"fit": INFO, "risk": AMBER, "price": ROSE,
                   "quality": EMERALD, "other": SLATE}
SENTIMENT_COLOR = {"pos": EMERALD, "positive": EMERALD, "neu": SLATE,
                   "neutral": SLATE, "neg": ROSE, "negative": ROSE, "none": "#94a3b8"}

# emerald-forward categorical sequence for charts
SEQ = [EMERALD, MINT, INFO, AMBER, "#7c3aed", ROSE, SLATE]


def badge(label: str, color: str = EMERALD) -> str:
    return (f'<span style="background:{color};color:#ffffff;border-radius:6px;'
            f'padding:2px 9px;font-size:0.82em;font-weight:600;">{label}</span>')


def tier_badge(covered: int, total: int) -> str:
    pct = covered / total if total else 0
    color = GREEN if pct >= 0.95 else (YELLOW if pct >= 0.5 else (GREY if pct == 0 else RED))
    return badge(f"{covered}/{total}", color)


def score_color(score: float | None) -> str:
    if score is None:
        return GREY
    if score >= 70:
        return GREEN
    if score >= 45:
        return YELLOW
    return ROSE


def fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0f}%"


def fmt_money(x: float | None) -> str:
    return "—" if x in (None, "") else f"${float(x):,.0f}"


# CSS injected once in app.py for the branded shell.
GLOBAL_CSS = f"""
<style>
  .stApp {{ background: {BG}; }}
  h1, h2, h3 {{ color: {TEXT}; letter-spacing: -0.01em; }}
  .ew-hero {{
    background: linear-gradient(135deg, #ecfdf5 0%, #f8fafc 65%);
    border: 1px solid #d1fae5; border-radius: 14px; padding: 18px 22px; margin-bottom: 6px;
  }}
  .ew-hero h1 {{ margin: 0; font-size: 1.5rem; color: {TEXT}; }}
  .ew-hero p {{ margin: 4px 0 0; color: {MUTED}; font-size: 0.9rem; }}
  .ew-card {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 12px;
  }}
  .ew-pill {{ display:inline-block; background:#ecfdf5; color:#047857;
    border:1px solid #a7f3d0; border-radius:999px; padding:2px 10px; font-size:0.78em; margin-right:6px; }}
  div[data-testid="stMetricValue"] {{ color: {EMERALD}; }}
  .ew-turn-rep {{ padding: 5px 12px; margin: 3px 0; background:rgba(5,150,105,0.08); border-radius:8px; }}
  .ew-turn-cust {{ padding: 5px 12px; margin: 3px 0; background:rgba(217,119,6,0.09); border-radius:8px; }}
  .ew-turn-unk {{ padding: 5px 12px; margin: 3px 0; background:rgba(100,116,139,0.07); border-radius:8px; opacity:0.7; }}
  .ew-role {{ font-size:0.72em; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; color:{MUTED}; }}
  .ew-turn-rep .ew-role {{ color:{EMERALD}; }}
  .ew-turn-cust .ew-role {{ color:{AMBER}; }}
  /* Insight cards: bold tone via tinted fill + tone border + tone numeral. No side stripes. */
  .ew-insight {{ border-radius:16px; padding:20px 22px; margin-bottom:14px; border:1px solid {BORDER}; background:#ffffff; }}
  .ew-insight.bad {{ background:linear-gradient(180deg, rgba(225,29,72,0.06), rgba(225,29,72,0.01)); border-color:rgba(225,29,72,0.30); }}
  .ew-insight.good {{ background:linear-gradient(180deg, rgba(5,150,105,0.07), rgba(5,150,105,0.01)); border-color:rgba(5,150,105,0.30); }}
  .ew-insight.info {{ background:linear-gradient(180deg, rgba(37,99,235,0.06), rgba(37,99,235,0.01)); border-color:rgba(37,99,235,0.25); }}
  .ew-insight .ew-stat {{ font-size:2.6rem; font-weight:800; line-height:1; color:{EMERALD}; }}
  .ew-insight.bad .ew-stat {{ color:{ROSE}; }}
  .ew-insight.good .ew-stat {{ color:{EMERALD}; }}
  .ew-insight.info .ew-stat {{ color:{INFO}; }}
  .ew-insight .ew-claim {{ color:{TEXT}; font-size:1.02rem; margin-top:6px; }}
  .ew-insight .ew-src {{ color:{MUTED}; font-size:0.74em; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; }}
  .ew-eg {{ color:{MUTED}; font-size:0.85em; }}
  /* Neutralize Streamlit's default blockquote side-stripe -> tinted block. */
  [data-testid="stMarkdownContainer"] blockquote {{
    border-left: none !important; background: rgba(148,163,184,0.12);
    border-radius: 8px; padding: 8px 14px; color:{TEXT}; }}
</style>
"""


def tone_color(tone: str) -> str:
    return {"bad": ROSE, "good": EMERALD, "info": INFO}.get(tone, SLATE)


def safe_md(text: str) -> str:
    """Escape '$' so Streamlit markdown doesn't render it as LaTeX math."""
    return (text or "").replace("$", "\\$")
