"""BizPulse: Interactive Business Analytics Dashboard & Automated Report Generator."""

from __future__ import annotations

from datetime import datetime
import pandas as pd
import streamlit as st

from analytics import (
    build_category_chart,
    build_share_donut_chart,
    build_top_entities_chart,
    build_trend_chart,
    compute_kpis,
    generate_automated_insights,
)
from data_cleaner import (
    STANDARD_COLUMNS,
    clean_business_data,
    detect_column_mapping,
    load_uploaded_files,
)
from report_generator import build_excel_report, build_pdf_report
from sample_data import generate_sample_data


st.set_page_config(
    page_title="BizPulse | Business Analytics & Reporting",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Subtle custom styling for KPI cards and headers
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    div[data-testid="stMetric"] {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 14px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_session_state() -> None:
    if "raw_df" not in st.session_state:
        st.session_state.raw_df = None
    if "files_loaded" not in st.session_state:
        st.session_state.files_loaded = 0
    if "data_source_label" not in st.session_state:
        st.session_state.data_source_label = ""


_init_session_state()

# ── Sidebar: Branding, Data Input & Filters ────────────────────────────────
with st.sidebar:
    st.title("📊 BizPulse")
    st.caption("Messy spreadsheets in. Executive insights out.")

    company_name = st.text_input("Company / Brand Name", value="Acme Commerce Inc.")
    st.divider()

    st.subheader("1. Upload Data")
    uploaded_files = st.file_uploader(
        "Upload one or more CSV / Excel files",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    col_load_a, col_load_b = st.columns(2)
    with col_load_a:
        if st.button("Load Sample Data", use_container_width=True, type="primary"):
            st.session_state.raw_df = generate_sample_data()
            st.session_state.files_loaded = 1
            st.session_state.data_source_label = "Built-in Sample Business Dataset (with intentional flaws)"
    with col_load_b:
        if st.button("Clear Data", use_container_width=True):
            st.session_state.raw_df = None
            st.session_state.files_loaded = 0
            st.session_state.data_source_label = ""
            st.rerun()

    if uploaded_files:
        try:
            loaded_df, load_warnings = load_uploaded_files(uploaded_files)
            st.session_state.raw_df = loaded_df
            st.session_state.files_loaded = len(uploaded_files)
            st.session_state.data_source_label = ", ".join(f.name for f in uploaded_files)
            for warn in load_warnings:
                st.warning(warn)
        except ValueError as exc:
            st.error(str(exc))

# ── Empty State Landing View ───────────────────────────────────────────────
if st.session_state.raw_df is None:
    st.title("Welcome to BizPulse")
    st.markdown(
        """
        Turn messy `.csv`, `.xlsx`, or `.xls` business exports into an interactive analytics dashboard
        and board-ready **Excel** & **PDF** reports in seconds.

        **What BizPulse does automatically:**
        - **Auto-Cleans Data:** Removes duplicate rows, trims whitespace, standardizes mixed date formats, parses currency strings, and handles missing values.
        - **Visualizes Performance:** Interactive KPI cards, time-series trends, category breakdowns, top products/customers, and regional/payment splits.
        - **Surfaces Insights:** Plain-English anomaly detection, peak revenue dates, growth leaders, and low-stock alerts.
        - **One-Click Exports:** Download a multi-sheet formatted Excel workbook or a branded Executive PDF report.
        """
    )
    st.info("Upload your spreadsheet(s) in the sidebar or click **Load Sample Data** to try it immediately.")
    st.stop()

# ── Optional Column Mapping Override in Sidebar ────────────────────────────
raw_df = st.session_state.raw_df
auto_mapping = detect_column_mapping(raw_df)
raw_cols_options = ["(None)"] + list(raw_df.columns)

with st.sidebar:
    with st.expander("Column Mapping (Auto-Detected)", expanded=False):
        st.caption("Adjust if your file uses non-standard headers.")
        custom_mapping = {}
        for canonical in STANDARD_COLUMNS.keys():
            default_col = auto_mapping.get(canonical)
            default_idx = raw_cols_options.index(default_col) if default_col in raw_cols_options else 0
            selected = st.selectbox(
                f"{canonical.replace('_', ' ').title()}",
                options=raw_cols_options,
                index=default_idx,
                key=f"map_{canonical}",
            )
            custom_mapping[canonical] = None if selected == "(None)" else selected

# ── Run Data Cleaner ───────────────────────────────────────────────────────
try:
    cleaned_df, health = clean_business_data(
        raw_df,
        files_loaded=st.session_state.files_loaded,
        custom_mapping=custom_mapping,
    )
except ValueError as exc:
    st.error(f"Data Validation Error: {exc}")
    st.stop()

if cleaned_df.empty:
    st.error("All rows were filtered out during cleaning due to invalid dates or revenue values.")
    st.stop()

# ── Sidebar Interactive Filters ────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.subheader("2. Dashboard Filters")

    min_date = cleaned_df["date"].min().date()
    max_date = cleaned_df["date"].max().date()
    date_selection = st.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_selection, tuple) and len(date_selection) == 2:
        start_dt, end_dt = date_selection
    else:
        start_dt, end_dt = min_date, max_date

    all_categories = sorted(cleaned_df["category"].unique().tolist())
    selected_categories = st.multiselect("Category / Department", all_categories, default=all_categories)

    all_regions = sorted(cleaned_df["region"].unique().tolist())
    selected_regions = st.multiselect("Region", all_regions, default=all_regions)

    all_statuses = sorted(cleaned_df["status"].unique().tolist())
    selected_statuses = st.multiselect("Payment Status", all_statuses, default=all_statuses)

    low_stock_threshold = st.number_input("Low Stock Alert Threshold", min_value=1, max_value=500, value=15)

# Apply filters
filtered_df = cleaned_df[
    (cleaned_df["date"].dt.date >= start_dt)
    & (cleaned_df["date"].dt.date <= end_dt)
    & (cleaned_df["category"].isin(selected_categories))
    & (cleaned_df["region"].isin(selected_regions))
    & (cleaned_df["status"].isin(selected_statuses))
].copy()

# ── Header & Data Health Summary ───────────────────────────────────────────
st.title(f"{company_name} — Analytics Dashboard")
st.caption(f"Source: {st.session_state.data_source_label}  |  Active Rows: {len(filtered_df):,} of {len(cleaned_df):,}")

with st.expander(
    f"🩺 Data Health Summary — Health Score: {health.health_score}% ({health.total_issues_fixed:,} issues automatically fixed)",
    expanded=False,
):
    h1, h2, h3, h4, h5 = st.columns(5)
    h1.metric("Raw Rows", f"{health.raw_rows:,}")
    h2.metric("Cleaned Rows", f"{health.cleaned_rows:,}")
    h3.metric("Duplicates Removed", f"{health.duplicates_removed:,}")
    h4.metric("Dates Standardized", f"{health.dates_standardized:,}")
    h5.metric("Missing / Text Fixes", f"{health.missing_values_filled + health.whitespace_cells_cleaned + health.currency_cells_parsed:,}")

    for warning_msg in health.warnings:
        st.warning(warning_msg)

if filtered_df.empty:
    st.warning("No records match your current sidebar filters. Broaden your date range or category selections.")
    st.stop()

# ── Top KPI Cards ──────────────────────────────────────────────────────────
kpis = compute_kpis(filtered_df)

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Total Revenue",
    f"${kpis['total_revenue']:,.2f}",
    f"{kpis['revenue_growth']:+.1f}% vs. prior half",
)
k2.metric(
    "Total Orders",
    f"{kpis['total_orders']:,}",
    f"{kpis['orders_growth']:+.1f}% vs. prior half",
)
k3.metric(
    "Average Order Value",
    f"${kpis['aov']:,.2f}",
    f"{kpis['aov_growth']:+.1f}% vs. prior half",
)
k4.metric(
    f"Top Category: {kpis['top_category']}",
    f"${kpis['top_category_revenue']:,.2f}",
    f"{kpis['top_category_growth']:+.1f}% vs. prior half",
)

st.divider()

# ── 4 Interactive Plotly Charts ────────────────────────────────────────────
row1_left, row1_right = st.columns([3, 2])

with row1_left:
    granularity = st.radio(
        "Trend Granularity",
        options=["Daily", "Weekly", "Monthly"],
        index=1,
        horizontal=True,
    )
    fig_trend = build_trend_chart(filtered_df, granularity=granularity)
    st.plotly_chart(fig_trend, use_container_width=True)

with row1_right:
    st.write("")
    st.write("")
    fig_category = build_category_chart(filtered_df)
    st.plotly_chart(fig_category, use_container_width=True)

row2_left, row2_right = st.columns([3, 2])

with row2_left:
    top_entity = st.radio(
        "Top 10 Breakdown",
        options=["Product", "Customer"],
        index=0,
        horizontal=True,
    )
    fig_top = build_top_entities_chart(filtered_df, entity=top_entity)
    st.plotly_chart(fig_top, use_container_width=True)

with row2_right:
    share_dim = st.radio(
        "Share Distribution",
        options=["Region", "Payment Status"],
        index=0,
        horizontal=True,
    )
    fig_donut = build_share_donut_chart(filtered_df, dimension=share_dim)
    st.plotly_chart(fig_donut, use_container_width=True)

st.divider()

# ── Automated Insights & Anomaly Alerts ────────────────────────────────────
st.subheader("Automated Insights & Anomaly Alerts")
insights = generate_automated_insights(filtered_df, low_stock_threshold=int(low_stock_threshold))

for severity, text in insights:
    if severity == "warning":
        st.warning(text)
    elif severity == "success":
        st.success(text)
    else:
        st.info(text)

st.divider()

# ── One-Click Exports (Excel + Branded PDF) ────────────────────────────────
st.subheader("Export Reports")
date_range_label = f"{start_dt.strftime('%b %d, %Y')} - {end_dt.strftime('%b %d, %Y')}"
file_stamp = datetime.now().strftime("%Y%m%d")

exp_col1, exp_col2 = st.columns(2)

with exp_col1:
    excel_bytes = build_excel_report(filtered_df, kpis)
    st.download_button(
        label="Download Cleaned Excel Report (.xlsx)",
        data=excel_bytes,
        file_name=f"BizPulse_Report_{file_stamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )

with exp_col2:
    if st.button("Prepare Executive PDF Report (.pdf)", use_container_width=True):
        with st.spinner("Rendering charts and compiling PDF..."):
            pdf_bytes = build_pdf_report(
                company_name=company_name,
                date_range_label=date_range_label,
                kpis=kpis,
                insights=insights,
                charts=[
                    ("Revenue & Profit Trend", fig_trend),
                    ("Sales by Category", fig_category),
                    (f"Top 10 {top_entity}s", fig_top),
                    (f"Share by {share_dim}", fig_donut),
                ],
            )
            st.session_state.pdf_bytes = pdf_bytes

    if "pdf_bytes" in st.session_state and st.session_state.pdf_bytes:
        st.download_button(
            label="Download Ready PDF Report",
            data=st.session_state.pdf_bytes,
            file_name=f"BizPulse_Executive_Summary_{file_stamp}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# ── Cleaned Data Preview ───────────────────────────────────────────────────
with st.expander("Preview Cleaned Dataset", expanded=False):
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)