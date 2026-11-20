"""Multi-file ingestion, schema normalization, and automated data cleaning."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


STANDARD_COLUMNS = {
    "order_id": ["order id", "order_id", "invoice", "invoice id", "transaction id", "txn_id", "id"],
    "date": ["order date", "order_date", "date", "transaction date", "invoice date", "created_at", "timestamp"],
    "customer": ["customer", "customer name", "client", "client name", "account", "buyer", "company"],
    "category": ["category", "department", "product category", "segment", "line of business", "group"],
    "product": ["product", "product name", "item", "item name", "sku", "service", "description"],
    "region": ["region", "territory", "country", "location", "market", "area", "branch"],
    "status": ["payment status", "status", "order status", "payment_status", "state"],
    "quantity": ["quantity", "qty", "units", "units sold", "count", "volume"],
    "revenue": ["revenue", "sales", "total", "amount", "total sales", "gross revenue", "price", "net sales"],
    "profit": ["profit", "net profit", "margin", "gross profit", "earnings", "income"],
    "stock_level": ["stock level", "stock", "inventory", "stock_level", "qty on hand", "on hand", "available stock"],
}

REQUIRED_CANONICAL = ["date", "revenue"]


@dataclass
class CleaningReport:
    """Summary of all data quality fixes performed during cleaning."""

    files_loaded: int = 0
    raw_rows: int = 0
    cleaned_rows: int = 0
    duplicates_removed: int = 0
    whitespace_cells_cleaned: int = 0
    dates_standardized: int = 0
    invalid_dates_dropped: int = 0
    currency_cells_parsed: int = 0
    missing_values_filled: int = 0
    invalid_revenue_dropped: int = 0
    mapped_columns: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def total_issues_fixed(self) -> int:
        return (
            self.duplicates_removed
            + self.whitespace_cells_cleaned
            + self.dates_standardized
            + self.currency_cells_parsed
            + self.missing_values_filled
            + self.invalid_dates_dropped
            + self.invalid_revenue_dropped
        )

    @property
    def health_score(self) -> float:
        """Compute a 0-100 post-cleaning health score based on retained valid rows."""
        if self.raw_rows == 0:
            return 0.0
        retention = self.cleaned_rows / max(self.raw_rows - self.duplicates_removed, 1)
        return round(min(max(retention * 100.0, 0.0), 100.0), 1)


def _normalize_col_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


def load_uploaded_files(uploaded_files: List) -> Tuple[pd.DataFrame, List[str]]:
    """Read and concatenate multiple uploaded CSV/Excel files."""
    frames: List[pd.DataFrame] = []
    errors: List[str] = []

    for uploaded in uploaded_files:
        filename = uploaded.name
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        try:
            raw_bytes = uploaded.getvalue()
            buffer = io.BytesIO(raw_bytes)
            if ext == "csv":
                try:
                    df = pd.read_csv(buffer, encoding="utf-8")
                except UnicodeDecodeError:
                    buffer.seek(0)
                    df = pd.read_csv(buffer, encoding="latin-1")
            elif ext == "xlsx":
                df = pd.read_excel(buffer, engine="openpyxl")
            elif ext == "xls":
                df = pd.read_excel(buffer, engine="xlrd")
            else:
                errors.append(f"Unsupported file format: '{filename}'. Please upload .csv, .xlsx, or .xls.")
                continue

            if df.empty:
                errors.append(f"File '{filename}' is empty and was skipped.")
                continue

            df.columns = [str(c).strip() for c in df.columns]
            frames.append(df)
        except Exception as exc:
            errors.append(f"Failed to read '{filename}': {exc}")

    if not frames:
        raise ValueError("No valid data could be loaded. " + " ".join(errors))

    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined, errors


def detect_column_mapping(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Map canonical BizPulse fields to matching columns in the raw DataFrame."""
    normalized_cols = {_normalize_col_name(c): c for c in df.columns}
    mapping: Dict[str, Optional[str]] = {}

    for canonical, aliases in STANDARD_COLUMNS.items():
        matched = None
        for alias in aliases:
            if alias in normalized_cols:
                matched = normalized_cols[alias]
                break
        if matched is None:
            # Fallback to partial substring match
            for norm_col, orig_col in normalized_cols.items():
                if any(alias in norm_col for alias in aliases) and orig_col not in mapping.values():
                    matched = orig_col
                    break
        mapping[canonical] = matched

    return mapping


def _clean_currency_series(series: pd.Series) -> Tuple[pd.Series, int]:
    """Convert numeric or currency-formatted strings (e.g., '$1,250.50') to floats."""
    currency_pattern = re.compile(r"[^\d.\-]")
    parsed_count = 0

    def _parse_val(val):
        nonlocal parsed_count
        if pd.isna(val):
            return np.nan
        if isinstance(val, (int, float, np.number)):
            return float(val)
        text = str(val).strip()
        if not text:
            return np.nan
        # Handle accounting negatives like ($120.00)
        is_neg = text.startswith("(") and text.endswith(")")
        cleaned = currency_pattern.sub("", text)
        if cleaned != text:
            parsed_count += 1
        try:
            num = float(cleaned)
            return -abs(num) if is_neg else num
        except ValueError:
            return np.nan

    cleaned_series = series.map(_parse_val)
    return pd.to_numeric(cleaned_series, errors="coerce"), parsed_count


def clean_business_data(
    raw_df: pd.DataFrame,
    files_loaded: int = 1,
    custom_mapping: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[pd.DataFrame, CleaningReport]:
    """Clean, standardize, and validate a business DataFrame."""
    report = CleaningReport(files_loaded=files_loaded, raw_rows=len(raw_df))
    df = raw_df.copy()

    # 1. Trim whitespace and normalize text across all object columns
    obj_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()
    for col in obj_cols:
        original = df[col].astype("object")
        non_null_mask = original.notna()
        stripped = original.where(~non_null_mask, original.astype(str).str.strip())
        # Treat empty strings as NaN
        stripped = stripped.replace({"": np.nan, "nan": np.nan, "None": np.nan, "null": np.nan})
        changed = (non_null_mask & (original.astype(str) != stripped.astype(str))).sum()
        report.whitespace_cells_cleaned += int(changed)
        df[col] = stripped

    # 2. Remove exact duplicate rows
    before_dedup = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    report.duplicates_removed = before_dedup - len(df)

    # 3. Map columns to canonical names
    mapping = custom_mapping if custom_mapping is not None else detect_column_mapping(df)
    missing_req = [req for req in REQUIRED_CANONICAL if not mapping.get(req)]
    if missing_req:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_req)}. "
            "Please ensure your file contains at least a Date column and a Revenue/Sales column, "
            "or adjust the column mapping in the sidebar."
        )

    rename_dict = {orig: canonical for canonical, orig in mapping.items() if orig and orig in df.columns}
    report.mapped_columns = {canonical: orig for canonical, orig in mapping.items() if orig}
    df = df.rename(columns=rename_dict)

    # 4. Standardize Date column
    raw_dates = df["date"].astype(str)
    parsed_dates = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    standardized_mask = parsed_dates.notna() & (raw_dates != parsed_dates.dt.strftime("%Y-%m-%d"))
    report.dates_standardized = int(standardized_mask.sum())
    invalid_dates = int(parsed_dates.isna().sum())
    if invalid_dates > 0:
        report.invalid_dates_dropped = invalid_dates
        report.warnings.append(f"Dropped {invalid_dates} row(s) with unparseable dates.")
    df["date"] = parsed_dates
    df = df.dropna(subset=["date"]).copy()

    # 5. Clean Revenue (required)
    df["revenue"], rev_parsed = _clean_currency_series(df["revenue"])
    report.currency_cells_parsed += rev_parsed
    invalid_rev = int(df["revenue"].isna().sum())
    if invalid_rev > 0:
        report.invalid_revenue_dropped = invalid_rev
        report.warnings.append(f"Dropped {invalid_rev} row(s) with missing or invalid revenue.")
    df = df.dropna(subset=["revenue"]).copy()

    # 6. Clean or synthesize optional numeric columns
    if "profit" in df.columns:
        df["profit"], prof_parsed = _clean_currency_series(df["profit"])
        report.currency_cells_parsed += prof_parsed
        missing_profit = int(df["profit"].isna().sum())
        if missing_profit > 0:
            # Estimate missing profit using dataset's median profit margin (fallback 25%)
            valid_margins = (df["profit"] / df["revenue"].replace(0, np.nan)).dropna()
            median_margin = float(valid_margins.median()) if not valid_margins.empty else 0.25
            df["profit"] = df["profit"].fillna((df["revenue"] * median_margin).round(2))
            report.missing_values_filled += missing_profit
    else:
        df["profit"] = (df["revenue"] * 0.25).round(2)
        report.warnings.append("No Profit column detected; estimated Profit at 25% of Revenue.")

    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        missing_qty = int(df["quantity"].isna().sum())
        if missing_qty > 0:
            df["quantity"] = df["quantity"].fillna(1)
            report.missing_values_filled += missing_qty
        df["quantity"] = df["quantity"].astype(int)
    else:
        df["quantity"] = 1

    if "stock_level" in df.columns:
        df["stock_level"] = pd.to_numeric(df["stock_level"], errors="coerce")
        missing_stock = int(df["stock_level"].isna().sum())
        if missing_stock > 0:
            df["stock_level"] = df["stock_level"].fillna(df["stock_level"].median() if df["stock_level"].notna().any() else 50)
            report.missing_values_filled += missing_stock

    # 7. Clean and fill optional categorical columns
    categorical_defaults = {
        "order_id": None,
        "customer": "Walk-in / Unknown",
        "category": "Uncategorized",
        "product": "General Item",
        "region": "Unspecified",
        "status": "Paid",
    }
    for col, default_val in categorical_defaults.items():
        if col not in df.columns:
            if col == "order_id":
                df[col] = [f"TXN-{i + 1:05d}" for i in range(len(df))]
            else:
                df[col] = default_val
        else:
            missing_cnt = int(df[col].isna().sum())
            if missing_cnt > 0:
                if col == "order_id":
                    df[col] = df[col].fillna(pd.Series([f"TXN-{i + 1:05d}" for i in range(len(df))], index=df.index))
                else:
                    df[col] = df[col].fillna(default_val)
                report.missing_values_filled += missing_cnt

            # Normalize title casing for category, region, and status so "electronics" == "Electronics"
            if col in ("category", "region", "status"):
                df[col] = df[col].astype(str).str.strip().str.title()
                # Preserve common acronym casing
                df[col] = df[col].str.replace("Saas", "SaaS", regex=False)

    # Sort chronologically and finalize
    df = df.sort_values("date").reset_index(drop=True)
    report.cleaned_rows = len(df)
    return df, report