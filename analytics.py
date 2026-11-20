"""KPI metrics, interactive Plotly visualizations, and automated business insights."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


BRAND_PALETTE = [
    "#1E3A8A",  # Deep Navy
    "#2563EB",  # Royal Blue
    "#0EA5E9",  # Sky Blue
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EF4444",  # Coral Red
    "#8B5CF6",  # Violet
    "#64748B",  # Slate
]


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return ((current - previous) / abs(previous)) * 100.0


def compute_kpis(df: pd.DataFrame) -> Dict[str, object]:
    """Compute core executive KPIs and period-over-period growth indicators."""
    if df.empty:
        return {
            "total_revenue": 0.0,
            "revenue_growth": 0.0,
            "total_profit": 0.0,
            "profit_margin": 0.0,
            "total_orders": 0,
            "orders_growth": 0.0,
            "aov": 0.0,
            "aov_growth": 0.0,
            "top_category": "N/A",
            "top_category_revenue": 0.0,
            "top_category_growth": 0.0,
        }

    total_revenue = float(df["revenue"].sum())
    total_profit = float(df["profit"].sum())
    profit_margin = (total_profit / total_revenue * 100.0) if total_revenue else 0.0
    total_orders = int(df["order_id"].nunique()) if "order_id" in df.columns else len(df)
    aov = total_revenue / total_orders if total_orders else 0.0

    # Split date range into equal first half vs. second half for growth indicators
    min_dt, max_dt = df["date"].min(), df["date"].max()
    mid_dt = min_dt + (max_dt - min_dt) / 2

    prev_df = df[df["date"] <= mid_dt]
    curr_df = df[df["date"] > mid_dt]

    prev_rev = float(prev_df["revenue"].sum())
    curr_rev = float(curr_df["revenue"].sum())
    revenue_growth = _pct_change(curr_rev, prev_rev)

    prev_orders = int(prev_df["order_id"].nunique()) if not prev_df.empty else 0
    curr_orders = int(curr_df["order_id"].nunique()) if not curr_df.empty else 0
    orders_growth = _pct_change(curr_orders, prev_orders)

    prev_aov = prev_rev / prev_orders if prev_orders else 0.0
    curr_aov = curr_rev / curr_orders if curr_orders else 0.0
    aov_growth = _pct_change(curr_aov, prev_aov)

    cat_totals = df.groupby("category")["revenue"].sum().sort_values(ascending=False)
    top_category = str(cat_totals.index[0]) if not cat_totals.empty else "N/A"
    top_category_rev = float(cat_totals.iloc[0]) if not cat_totals.empty else 0.0

    prev_cat_rev = float(prev_df.loc[prev_df["category"] == top_category, "revenue"].sum())
    curr_cat_rev = float(curr_df.loc[curr_df["category"] == top_category, "revenue"].sum())
    top_category_growth = _pct_change(curr_cat_rev, prev_cat_rev)

    return {
        "total_revenue": total_revenue,
        "revenue_growth": round(revenue_growth, 1),
        "total_profit": total_profit,
        "profit_margin": round(profit_margin, 1),
        "total_orders": total_orders,
        "orders_growth": round(orders_growth, 1),
        "aov": aov,
        "aov_growth": round(aov_growth, 1),
        "top_category": top_category,
        "top_category_revenue": top_category_rev,
        "top_category_growth": round(top_category_growth, 1),
    }


def build_trend_chart(df: pd.DataFrame, granularity: str = "Weekly") -> go.Figure:
    """Chart 1: Revenue & Profit trend over time (Daily / Weekly / Monthly)."""
    freq_map = {"Daily": "D", "Weekly": "W-MON", "Monthly": "ME"}
    freq = freq_map.get(granularity, "W-MON")

    trend = (
        df.set_index("date")[["revenue", "profit"]]
        .resample(freq)
        .sum()
        .reset_index()
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend["date"],
            y=trend["revenue"],
            name="Revenue",
            mode="lines+markers",
            line=dict(color="#2563EB", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(37, 99, 235, 0.12)",
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>Revenue: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=trend["date"],
            y=trend["profit"],
            name="Profit",
            mode="lines+markers",
            line=dict(color="#10B981", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.10)",
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>Profit: $%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=f"Revenue & Profit Trend ({granularity})",
        xaxis_title="Date",
        yaxis_title="Amount ($)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=55, b=20),
        template="plotly_white",
    )
    return fig


def build_category_chart(df: pd.DataFrame) -> go.Figure:
    """Chart 2: Sales breakdown by Category (vertical bar chart)."""
    cat_df = (
        df.groupby("category", as_index=False)
        .agg(revenue=("revenue", "sum"), profit=("profit", "sum"))
        .sort_values("revenue", ascending=False)
    )

    fig = px.bar(
        cat_df,
        x="category",
        y="revenue",
        color="category",
        text_auto=".2s",
        color_discrete_sequence=BRAND_PALETTE,
        title="Sales Breakdown by Category",
        labels={"category": "Category", "revenue": "Revenue ($)"},
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.2f}<extra></extra>",
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(l=20, r=20, t=55, b=20),
        template="plotly_white",
    )
    return fig


def build_top_entities_chart(df: pd.DataFrame, entity: str = "Product") -> go.Figure:
    """Chart 3: Top 10 Products or Customers (horizontal bar chart)."""
    col = "product" if entity == "Product" else "customer"
    top_df = (
        df.groupby(col, as_index=False)["revenue"]
        .sum()
        .sort_values("revenue", ascending=False)
        .head(10)
        .sort_values("revenue", ascending=True)
    )

    fig = px.bar(
        top_df,
        x="revenue",
        y=col,
        orientation="h",
        text_auto=".2s",
        title=f"Top 10 {entity}s by Revenue",
        labels={"revenue": "Revenue ($)", col: entity},
        color_discrete_sequence=["#1E3A8A"],
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Revenue: $%{x:,.2f}<extra></extra>",
    )
    fig.update_layout(
        margin=dict(l=20, r=40, t=55, b=20),
        template="plotly_white",
    )
    return fig


def build_share_donut_chart(df: pd.DataFrame, dimension: str = "Region") -> go.Figure:
    """Chart 4: Regional Share or Payment Status breakdown (donut chart)."""
    col = "region" if dimension == "Region" else "status"
    share_df = (
        df.groupby(col, as_index=False)["revenue"]
        .sum()
        .sort_values("revenue", ascending=False)
    )

    fig = px.pie(
        share_df,
        names=col,
        values="revenue",
        hole=0.52,
        title=f"Revenue Share by {dimension}",
        color_discrete_sequence=BRAND_PALETTE,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="<b>%{label}</b><br>Revenue: $%{value:,.2f} (%{percent})<extra></extra>",
    )
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=55, b=40),
        template="plotly_white",
    )
    return fig


def generate_automated_insights(
    df: pd.DataFrame,
    low_stock_threshold: int = 15,
) -> List[Tuple[str, str]]:
    """Produce plain-English business insights and anomaly alerts.

    Returns a list of tuples: (severity, message) where severity is
    one of 'info', 'success', or 'warning'.
    """
    if df.empty:
        return [("warning", "No records match the current filter selection.")]

    insights: List[Tuple[str, str]] = []

    # 1. Peak revenue date
    daily = df.groupby("date")["revenue"].sum()
    if not daily.empty:
        peak_date = daily.idxmax()
        peak_val = float(daily.max())
        insights.append(
            (
                "info",
                f"Revenue peaked on {peak_date.strftime('%B %d, %Y')} at ${peak_val:,.2f}.",
            )
        )

    # 2. Highest growth category (comparing second half vs. first half)
    min_dt, max_dt = df["date"].min(), df["date"].max()
    mid_dt = min_dt + (max_dt - min_dt) / 2
    first_half = df[df["date"] <= mid_dt].groupby("category")["revenue"].sum()
    second_half = df[df["date"] > mid_dt].groupby("category")["revenue"].sum()

    growth_rates = {}
    for cat in second_half.index:
        prev_val = float(first_half.get(cat, 0.0))
        curr_val = float(second_half.get(cat, 0.0))
        if prev_val > 0:
            growth_rates[cat] = ((curr_val - prev_val) / prev_val) * 100.0

    if growth_rates:
        best_cat = max(growth_rates, key=growth_rates.get)
        best_rate = growth_rates[best_cat]
        direction = "up" if best_rate >= 0 else "down"
        insights.append(
            (
                "success" if best_rate >= 0 else "warning",
                f"Highest growth category is {best_cat} ({direction} {abs(best_rate):.1f}% in the second half of the selected period).",
            )
        )

    # 3. Low stock inventory alert
    if "stock_level" in df.columns:
        product_stock = df.groupby("product")["stock_level"].min()
        low_stock_items = product_stock[product_stock < low_stock_threshold]
        if not low_stock_items.empty:
            item_names = ", ".join(
                f"{name} ({int(qty)} left)" for name, qty in low_stock_items.head(4).items()
            )
            insights.append(
                (
                    "warning",
                    f"{len(low_stock_items)} product(s) are below the minimum stock threshold of {low_stock_threshold} units: {item_names}.",
                )
            )

    # 4. Daily revenue anomaly detection (Z-score > 2.2)
    if len(daily) >= 10 and daily.std() > 0:
        z_scores = (daily - daily.mean()) / daily.std()
        spikes = daily[z_scores > 2.2]
        if not spikes.empty:
            top_spike_dt = spikes.idxmax()
            insights.append(
                (
                    "info",
                    f"Detected {len(spikes)} unusual daily revenue spike(s); largest anomaly occurred on {top_spike_dt.strftime('%b %d, %Y')} (${spikes.max():,.2f}, {z_scores[top_spike_dt]:.1f}x std above average).",
                )
            )

    # 5. Overdue / Pending payment exposure
    if "status" in df.columns:
        overdue_df = df[df["status"].str.lower().isin(["overdue", "pending", "unpaid"])]
        if not overdue_df.empty:
            at_risk = float(overdue_df["revenue"].sum())
            pct_risk = (at_risk / float(df["revenue"].sum())) * 100.0 if df["revenue"].sum() else 0.0
            insights.append(
                (
                    "warning",
                    f"${at_risk:,.2f} ({pct_risk:.1f}% of revenue) is currently in Pending or Overdue payment status across {len(overdue_df)} order(s).",
                )
            )

    # 6. Top 10 customer concentration
    top10_rev = float(df.groupby("customer")["revenue"].sum().nlargest(10).sum())
    total_rev = float(df["revenue"].sum())
    if total_rev > 0:
        share = (top10_rev / total_rev) * 100.0
        insights.append(
            (
                "info",
                f"Top 10 customers account for {share:.1f}% (${top10_rev:,.2f}) of total revenue.",
            )
        )

    return insights