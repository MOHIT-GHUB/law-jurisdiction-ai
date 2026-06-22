"""
utils/pdf_export.py — Generates a polished PDF legal report via HTML/CSS + WeasyPrint.

Why HTML/CSS instead of programmatic drawing: the report is mostly typographic
(headings, prose with linked case law, tables, a score gauge). Designing it as an
HTML template with real CSS is far more flexible and better-looking than ReportLab.

Flow:  conversation data → HTML string (this module) → WeasyPrint → PDF bytes.

Called from routers/conversations.py → export_conversation_pdf()
Endpoint: GET /conversations/{id}/export-pdf

Reads:
  conversation.intake_summary  → dict (incident, location, state, perpetrator, ...)
  conversation.research_result → dict (opinion [markdown], case_strength_score,
                                       referred_lawyers, legal_classification)
  conversation.id / created_at → matter reference + dates

NOTE: WeasyPrint requires Pango/cairo system libraries. It is imported lazily inside
generate_pdf() so the app still boots where those libs are absent — only the export
endpoint fails (with a clear error) instead of the whole server.
"""

import html as _html
from datetime import datetime

import markdown as _markdown

# ── Palette ─────────────────────────────────────────────────────────────────────
_NAVY = "#1e3a5f"
_NAVY_DARK = "#142943"
_GOLD = "#b8860b"
_TEXT = "#1e293b"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_BG_SOFT = "#f8fafc"
_LINK = "#2563eb"


def _esc(value) -> str:
    return _html.escape(str(value)) if value is not None else ""


def _score_meta(score: int) -> tuple[str, str]:
    if score >= 86:
        return "#15803d", "Very Strong"
    if score >= 61:
        return "#22c55e", "Strong"
    if score >= 31:
        return "#b45309", "Moderate"
    return "#b91c1c", "Weak"


def _score_gauge_svg(score: int, color: str) -> str:
    """An SVG donut gauge — WeasyPrint renders inline SVG cleanly."""
    radius = 52
    circ = 2 * 3.14159 * radius
    filled = circ * max(0, min(score, 100)) / 100
    return f"""
    <svg width="116" height="116" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="{radius}" fill="none" stroke="{_BORDER}" stroke-width="12"/>
      <circle cx="60" cy="60" r="{radius}" fill="none" stroke="{color}" stroke-width="12"
              stroke-linecap="round" stroke-dasharray="{filled:.1f} {circ:.1f}"
              transform="rotate(-90 60 60)"/>
      <text x="60" y="62" text-anchor="middle" font-size="30" font-weight="700"
            fill="{color}" font-family="Georgia, serif">{score}</text>
      <text x="60" y="80" text-anchor="middle" font-size="11" fill="{_MUTED}">/ 100</text>
    </svg>
    """


def _caption_html(conversation, intake: dict, research: dict) -> str:
    bucket = (research.get("legal_classification") or {}).get("bucket")
    created = getattr(conversation, "created_at", None)
    rows = [
        ("Matter Reference", str(getattr(conversation, "id", ""))[:8].upper()),
        ("Matter Type", bucket.replace("_", " ").title() if bucket else None),
        ("Jurisdiction", intake.get("state")),
        ("Date of Incident", intake.get("date_of_incident")),
        ("Date Opened", created.strftime("%B %d, %Y") if created else None),
        ("Report Generated", datetime.utcnow().strftime("%B %d, %Y")),
    ]
    cells = "".join(
        f'<div class="cap-item"><div class="cap-label">{_esc(label)}</div>'
        f'<div class="cap-value">{_esc(value)}</div></div>'
        for label, value in rows
        if value
    )
    return f'<div class="caption">{cells}</div>' if cells else ""


def _case_summary_html(intake: dict) -> str:
    fields = [
        ("Incident", intake.get("incident")),
        ("Location", intake.get("location")),
        ("State", intake.get("state")),
        ("Perpetrator / Respondent", intake.get("perpetrator")),
        ("Written Proof", intake.get("written_proof")),
        ("Date of Incident", intake.get("date_of_incident")),
    ]
    rows = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        for label, value in fields
        if value and str(value).strip() and str(value).strip() != "—"
    )
    if not rows:
        return ""
    return f'<section><h2>Case Summary</h2><table class="summary">{rows}</table></section>'


def _score_html(score: int) -> str:
    color, label = _score_meta(score)
    scale = "".join(
        f'<span class="band {"on" if lo <= score <= hi else ""}">'
        f'<i style="background:{c}"></i>{name}</span>'
        for lo, hi, name, c in [
            (0, 30, "Weak", "#b91c1c"),
            (31, 60, "Moderate", "#b45309"),
            (61, 85, "Strong", "#22c55e"),
            (86, 100, "Very Strong", "#15803d"),
        ]
    )
    return (
        "<section><h2>Case Strength Score</h2>"
        '<table class="score-row"><tr>'
        f'<td class="gauge">{_score_gauge_svg(score, color)}</td>'
        '<td class="score-meta">'
        f'<div class="score-label" style="color:{color}">{label}</div>'
        '<div class="score-sub">Overall assessment of the matter\'s legal merit.</div>'
        f'<div class="bands">{scale}</div>'
        "</td></tr></table></section>"
    )


def _analysis_html(opinion: str) -> str:
    if not opinion.strip():
        return ""
    body = _markdown.markdown(opinion, extensions=["extra", "sane_lists"])
    return f'<section><h2>Legal Analysis</h2><div class="analysis">{body}</div></section>'


def _resources_html(lawyers: list[dict]) -> str:
    if not lawyers:
        return ""
    cards = []
    for lw in lawyers[:10]:
        name = _esc(lw.get("name") or "Resource")
        url = lw.get("url")
        title = f'<a href="{_esc(url)}">{name}</a>' if url else name
        meta = [m for m in (lw.get("specialty"), lw.get("address"), lw.get("phone")) if m]
        if lw.get("rating"):
            meta.append(f"★ {lw['rating']}")
        meta_html = (
            f'<div class="res-meta">{_esc("  ·  ".join(str(m) for m in meta))}</div>'
            if meta
            else ""
        )
        cards.append(f'<div class="res-card"><div class="res-name">{title}</div>{meta_html}</div>')
    return "<section><h2>Attorney &amp; Referral Resources</h2>" + "".join(cards) + "</section>"


_CSS = f"""
@page {{
  size: Letter;
  margin: 1.5cm 1.6cm 1.9cm 1.6cm;
  @bottom-left {{
    content: "CONFIDENTIAL · Generated by LexAI";
    font-size: 7.5pt; color: {_MUTED};
  }}
  @bottom-right {{
    content: "Page " counter(page) " of " counter(pages);
    font-size: 7.5pt; color: {_MUTED};
  }}
}}

* {{ box-sizing: border-box; }}
body {{
  font-family: "Helvetica Neue", Arial, sans-serif;
  color: {_TEXT};
  font-size: 10.5pt;
  line-height: 1.5;
  margin: 0;
}}

.masthead {{
  background: {_NAVY};
  border-radius: 8px;
  padding: 20px 24px;
  color: #fff;
  border-left: 5px solid {_GOLD};
}}
.masthead .brand {{
  font-family: Georgia, serif;
  font-size: 26pt;
  font-weight: 700;
  letter-spacing: 0.5px;
}}
.masthead .brand span {{ color: {_GOLD}; }}
.masthead .subtitle {{
  font-size: 10.5pt;
  color: #cdd7e3;
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
}}

.caption {{
  margin-top: 14px;
  border: 1px solid {_BORDER};
  border-radius: 6px;
  background: {_BG_SOFT};
  padding: 4px 0;
}}
.cap-item {{
  display: inline-block;
  width: 33%;
  padding: 8px 14px;
  vertical-align: top;
}}
.cap-label {{
  font-size: 7.5pt;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: {_MUTED};
}}
.cap-value {{ font-size: 10pt; font-weight: 600; color: {_NAVY_DARK}; }}

.banner {{
  margin: 14px 0 4px;
  font-size: 8pt;
  color: {_MUTED};
  border-left: 3px solid {_GOLD};
  padding: 6px 10px;
  background: {_BG_SOFT};
}}

section {{ margin-top: 20px; }}
h2 {{
  font-family: Georgia, serif;
  font-size: 14pt;
  color: {_NAVY};
  margin: 0 0 8px;
  padding-bottom: 5px;
  border-bottom: 2px solid {_GOLD};
}}

table.summary {{ width: 100%; border-collapse: collapse; }}
table.summary th {{
  width: 32%;
  text-align: left;
  vertical-align: top;
  padding: 7px 10px;
  font-size: 8.5pt;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: {_MUTED};
  font-weight: 600;
  background: {_BG_SOFT};
  border: 1px solid {_BORDER};
}}
table.summary td {{
  padding: 7px 10px;
  border: 1px solid {_BORDER};
  vertical-align: top;
}}

.score-row {{ width: 100%; border-collapse: collapse; }}
.score-row .gauge {{ width: 130px; vertical-align: middle; }}
.score-meta {{ vertical-align: middle; padding-left: 12px; }}
.score-label {{ font-family: Georgia, serif; font-size: 20pt; font-weight: 700; }}
.score-sub {{ color: {_MUTED}; font-size: 9.5pt; margin-bottom: 8px; }}
.bands .band {{
  display: inline-block;
  margin-right: 14px;
  font-size: 8.5pt;
  color: {_MUTED};
}}
.bands .band i {{
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  margin-right: 4px; vertical-align: middle;
}}
.bands .band.on {{ color: {_TEXT}; font-weight: 700; }}

.analysis {{ font-size: 10.5pt; }}
.analysis h2 {{ font-size: 12.5pt; border: none; padding: 0; margin: 14px 0 4px; }}
.analysis h3 {{ font-size: 11pt; color: {_NAVY_DARK}; margin: 10px 0 3px; }}
.analysis p {{ margin: 5px 0; }}
.analysis ul, .analysis ol {{ margin: 5px 0 5px 18px; }}
.analysis li {{ margin: 2px 0; }}
.analysis a {{ color: {_LINK}; text-decoration: none; }}
.analysis strong {{ color: {_NAVY_DARK}; }}

.res-card {{
  border: 1px solid {_BORDER};
  border-left: 3px solid {_GOLD};
  border-radius: 5px;
  padding: 8px 12px;
  margin-bottom: 8px;
}}
.res-name {{ font-weight: 700; font-size: 10.5pt; }}
.res-name a {{ color: {_LINK}; text-decoration: none; }}
.res-meta {{ color: {_MUTED}; font-size: 9pt; margin-top: 2px; }}

.pending {{ color: {_MUTED}; font-style: italic; margin-top: 16px; }}
.disclaimer {{
  margin-top: 24px;
  border-top: 1px solid {_BORDER};
  padding-top: 8px;
  font-size: 8pt;
  color: #94a3b8;
  line-height: 1.45;
}}
"""


def _build_html(conversation, intake: dict, research: dict) -> str:
    score = research.get("case_strength_score") or 0
    opinion = (research.get("opinion") or "").strip()
    lawyers = research.get("referred_lawyers") or []

    parts = [
        '<div class="masthead">'
        '<div class="brand">Lex<span>AI</span></div>'
        '<div class="subtitle">Legal Case Analysis Report</div>'
        "</div>",
        _caption_html(conversation, intake, research),
        '<div class="banner"><b>Disclaimer:</b> Generated by an AI system for informational '
        "purposes only. Not legal advice; creates no attorney-client relationship. Verify all "
        "authorities with a licensed attorney before acting.</div>",
        _case_summary_html(intake),
    ]

    if opinion:
        parts.append(_score_html(score))
        parts.append(_analysis_html(opinion))
    else:
        parts.append(
            '<p class="pending">Analysis for this matter has not been completed yet. '
            "Once the research pipeline finishes, the full legal analysis will appear here.</p>"
        )

    parts.append(_resources_html(lawyers))
    parts.append(
        '<div class="disclaimer">LexAI is an AI-assisted legal research tool. This report is for '
        "informational purposes only and does not establish an attorney-client relationship. The "
        "laws and cases referenced may have changed or been superseded. Always verify with a "
        "licensed attorney before taking any legal action.</div>"
    )

    body = "".join(p for p in parts if p)
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{body}</body></html>"


def generate_pdf(conversation) -> bytes:
    """Render the conversation into a styled PDF and return the raw bytes."""
    intake: dict = conversation.intake_summary or {}
    research: dict = conversation.research_result or {}
    html_doc = _build_html(conversation, intake, research)

    # Lazy import: WeasyPrint needs Pango/cairo; keep the app bootable without them.
    from weasyprint import HTML

    return HTML(string=html_doc).write_pdf()
