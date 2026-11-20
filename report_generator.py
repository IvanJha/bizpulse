"""Excel (.xlsx) and branded Executive PDF (.pdf) report generation for BizPulse."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd
import plotly.graph_objects as go
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _style_header_row(ws, row_idx: int, col_count: int) -> None:
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    for col_idx in range(1, col_count + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _autofit_columns(ws, max_width: int = 38) -> None:
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        longest = 0
        for cell in col:
            val = "" if cell.value is None else str(cell.value)
            longest = max(longest, len(val))
        ws.column_dimensions[col_letter].width = min(max(longest + 4, 12), max_width)


def build_excel_report(df: pd.DataFrame, kpis: Dict[str, object]) -> bytes:
    """Create a multi-sheet styled Excel workbook (Cleaned Data + Summary Pivots)."""
    wb = Workbook()

    # ── Sheet 1: Cleaned Data ──────────────────────────────────────────────
    ws_data = wb.active
    ws_data.title = "Cleaned Data"

    export_df = df.copy()
    export_df["date"] = pd.to_datetime(export_df["date"]).dt.strftime("%Y-%m-%d")

    headers = [c.replace("_", " ").title() for c in export_df.columns]
    ws_data.append(headers)
    _style_header_row(ws_data, 1, len(headers))

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    thin_border = Border(
        bottom=Side(style="thin", color="E2E8F0"),
    )

    currency_cols = {
        idx + 1
        for idx, c in enumerate(export_df.columns)
        if c in ("revenue", "profit")
    }

    for r_idx, row in enumerate(export_df.itertuples(index=False), start=2):
        ws_data.append(list(row))
        for c_idx in range(1, len(headers) + 1):
            cell = ws_data.cell(row=r_idx, column=c_idx)
            cell.border = thin_border
            if r_idx % 2 == 1:
                cell.fill = zebra_fill
            if c_idx in currency_cols:
                cell.number_format = "$#,##0.00"

    ws_data.freeze_panes = "A2"
    ws_data.auto_filter.ref = ws_data.dimensions
    _autofit_columns(ws_data)

    # ── Sheet 2: Summary Pivots ────────────────────────────────────────────
    ws_piv = wb.create_sheet(title="Summary Pivots")
    title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    section_font = Font(name="Calibri", size=12, bold=True, color="1E293B")

    ws_piv["A1"] = "BizPulse Executive Summary & Pivot Tables"
    ws_piv["A1"].font = title_font

    # KPI Overview Table
    ws_piv["A3"] = "Key Performance Indicators"
    ws_piv["A3"].font = section_font
    ws_piv.append(["Metric", "Value", "Period Growth"])
    _style_header_row(ws_piv, 4, 3)

    kpi_rows = [
        ("Total Revenue", kpis["total_revenue"], f"{kpis['revenue_growth']:+.1f}%"),
        ("Total Profit", kpis["total_profit"], f"{kpis['profit_margin']:.1f}% margin"),
        ("Total Orders", kpis["total_orders"], f"{kpis['orders_growth']:+.1f}%"),
        ("Average Order Value", kpis["aov"], f"{kpis['aov_growth']:+.1f}%"),
        ("Top Category", kpis["top_category"], f"{kpis['top_category_growth']:+.1f}%"),
    ]
    for offset, (metric, val, growth) in enumerate(kpi_rows, start=5):
        ws_piv.cell(row=offset, column=1, value=metric)
        val_cell = ws_piv.cell(row=offset, column=2, value=val)
        if metric in ("Total Revenue", "Total Profit", "Average Order Value"):
            val_cell.number_format = "$#,##0.00"
        ws_piv.cell(row=offset, column=3, value=growth)

    def _write_pivot_section(start_row: int, heading: str, pivot_df: pd.DataFrame) -> int:
        ws_piv.cell(row=start_row, column=1, value=heading).font = section_font
        header_row = start_row + 1
        for c_idx, col_name in enumerate(pivot_df.columns, start=1):
            ws_piv.cell(row=header_row, column=c_idx, value=col_name)
        _style_header_row(ws_piv, header_row, len(pivot_df.columns))

        curr_row = header_row + 1
        for row_vals in pivot_df.itertuples(index=False):
            for c_idx, val in enumerate(row_vals, start=1):
                cell = ws_piv.cell(row=curr_row, column=c_idx, value=val)
                col_title = str(pivot_df.columns[c_idx - 1]).lower()
                if "revenue" in col_title or "profit" in col_title or "aov" in col_title:
                    cell.number_format = "$#,##0.00"
                elif "margin" in col_title or "share" in col_title:
                    cell.number_format = "0.0%"
            curr_row += 1
        return curr_row + 2

    # Pivot 1: Category Breakdown
    cat_piv = (
        df.groupby("category", as_index=False)
        .agg(Orders=("order_id", "nunique"), Revenue=("revenue", "sum"), Profit=("profit", "sum"))
        .sort_values("Revenue", ascending=False)
    )
    cat_piv["Profit Margin"] = (cat_piv["Profit"] / cat_piv["Revenue"].replace(0, 1)).fillna(0)
    cat_piv = cat_piv.rename(columns={"category": "Category"})
    next_row = _write_pivot_section(12, "Revenue & Profit by Category", cat_piv)

    # Pivot 2: Regional Breakdown
    reg_piv = (
        df.groupby("region", as_index=False)
        .agg(Orders=("order_id", "nunique"), Revenue=("revenue", "sum"), Profit=("profit", "sum"))
        .sort_values("Revenue", ascending=False)
    )
    total_rev = float(df["revenue"].sum()) or 1.0
    reg_piv["Revenue Share"] = reg_piv["Revenue"] / total_rev
    reg_piv = reg_piv.rename(columns={"region": "Region"})
    next_row = _write_pivot_section(next_row, "Performance by Region", reg_piv)

    # Pivot 3: Monthly Trend
    monthly = (
        df.assign(Month=pd.to_datetime(df["date"]).dt.to_period("M").astype(str))
        .groupby("Month", as_index=False)
        .agg(Orders=("order_id", "nunique"), Revenue=("revenue", "sum"), Profit=("profit", "sum"))
        .sort_values("Month")
    )
    _write_pivot_section(next_row, "Monthly Performance Summary", monthly)
    _autofit_columns(ws_piv)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def _figure_to_png_bytes(fig: go.Figure, width: int = 760, height: int = 420) -> bytes | None:
    """Export a Plotly figure to PNG bytes using Kaleido, returning None if unavailable."""
    try:
        return fig.to_image(format="png", width=width, height=height, scale=2)
    except Exception:
        return None


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(0.6 * inch, 0.45 * inch, "Generated automatically by BizPulse Analytics")
    canvas.drawRightString(letter[0] - 0.6 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf_report(
    company_name: str,
    date_range_label: str,
    kpis: Dict[str, object],
    insights: List[Tuple[str, str]],
    charts: List[Tuple[str, go.Figure]],
) -> bytes:
    """Generate a clean, branded Executive PDF report with KPI table, insights, and charts."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BizTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=colors.white,
        alignment=0,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "BizSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#DBEAFE"),
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=14,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=5,
    )

    story = []

    # 1. Branded Header Banner
    banner_content = [
        [
            Paragraph(f"{company_name} — Executive Analytics Report", title_style),
        ],
        [
            Paragraph(
                f"Reporting Period: {date_range_label} &nbsp;|&nbsp; Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}",
                subtitle_style,
            )
        ],
    ]
    banner = Table(banner_content, colWidths=[7.3 * inch])
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E3A8A")),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, 0), 14),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
            ]
        )
    )
    story.append(banner)
    story.append(Spacer(1, 0.2 * inch))

    # 2. KPI Summary Table
    story.append(Paragraph("Executive KPI Summary", section_style))
    kpi_data = [
        ["Metric", "Value", "Trend / Context"],
        ["Total Revenue", f"${kpis['total_revenue']:,.2f}", f"{kpis['revenue_growth']:+.1f}% vs. prior half"],
        ["Total Profit", f"${kpis['total_profit']:,.2f}", f"{kpis['profit_margin']:.1f}% net margin"],
        ["Total Orders", f"{kpis['total_orders']:,}", f"{kpis['orders_growth']:+.1f}% vs. prior half"],
        ["Average Order Value", f"${kpis['aov']:,.2f}", f"{kpis['aov_growth']:+.1f}% vs. prior half"],
        [
            "Top Performing Category",
            str(kpis["top_category"]),
            f"${kpis['top_category_revenue']:,.2f} ({kpis['top_category_growth']:+.1f}%)",
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[2.4 * inch, 2.2 * inch, 2.7 * inch])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(kpi_table)
    story.append(Spacer(1, 0.15 * inch))

    # 3. Automated Insights & Alerts
    story.append(Paragraph("Key Automated Insights & Anomaly Alerts", section_style))
    for severity, message in insights:
        prefix = "[ALERT]" if severity == "warning" else "[HIGHLIGHT]"
        story.append(Paragraph(f"<b>{prefix}</b> {message}", body_style))

    # 4. Embedded Chart Snapshots
    rendered_charts: List[Tuple[str, bytes]] = []
    for chart_title, fig in charts:
        png_bytes = _figure_to_png_bytes(fig)
        if png_bytes:
            rendered_charts.append((chart_title, png_bytes))

    if rendered_charts:
        story.append(PageBreak())
        story.append(Paragraph("Visual Analytics Breakdown", section_style))
        for idx, (chart_title, png_bytes) in enumerate(rendered_charts):
            img_stream = io.BytesIO(png_bytes)
            rl_img = RLImage(img_stream, width=6.9 * inch, height=3.8 * inch)
            story.append(rl_img)
            story.append(Spacer(1, 0.18 * inch))
            if idx == 1 and len(rendered_charts) > 2:
                story.append(PageBreak())
    else:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(
                "Note: Chart images require the 'kaleido' package to render static PNG snapshots.",
                body_style,
            )
        )

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    buffer.seek(0)
    return buffer.getvalue()