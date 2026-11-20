"""Generate realistic, intentionally messy business data for BizPulse demos."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from faker import Faker


def generate_sample_data(num_rows: int = 450, seed: int = 42) -> pd.DataFrame:
    """Create a realistic sales & inventory dataset with common spreadsheet flaws."""
    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    catalog = {
        "Electronics": [
            ("ProBook 14 Laptop", 1150.0, 780.0, 18),
            ("NoiseCancel Headphones", 280.0, 145.0, 42),
            ("4K UltraWide Monitor", 540.0, 340.0, 9),   # Low stock
            ("USB-C Docking Station", 130.0, 62.0, 55),
        ],
        "Office Furniture": [
            ("ErgoMesh Executive Chair", 420.0, 230.0, 11),  # Low stock
            ("Standing Desk Pro", 680.0, 410.0, 24),
            ("Acoustic Desk Divider", 190.0, 95.0, 38),
        ],
        "Software & SaaS": [
            ("CloudSync Annual License", 360.0, 65.0, 999),
            ("TeamAnalytics Pro Seat", 240.0, 45.0, 999),
            ("SecureVault Enterprise", 890.0, 160.0, 999),
        ],
        "Accessories": [
            ("Mechanical Keyboard", 145.0, 68.0, 6),   # Low stock
            ("Wireless Precision Mouse", 75.0, 30.0, 70),
            ("Laptop Travel Sleeve", 48.0, 16.0, 120),
        ],
    }

    regions = ["North America", "Europe", "Asia-Pacific", "Latin America"]
    region_weights = [0.42, 0.28, 0.20, 0.10]

    statuses = ["Paid", "Pending", "Overdue", "Refunded"]
    status_weights = [0.76, 0.13, 0.07, 0.04]

    customers = [fake.company() for _ in range(45)]

    end_date = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=179)

    date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d"]

    rows = []
    for i in range(num_rows):
        order_dt = start_date + timedelta(days=random.randint(0, 179))
        # Inject a natural revenue spike on a few specific promotional days
        is_promo_day = order_dt.day in (15, 28)

        category = random.choices(
            list(catalog.keys()),
            weights=[0.35, 0.22, 0.25, 0.18],
            k=1,
        )[0]
        product, unit_price, unit_cost, stock_level = random.choice(catalog[category])

        qty = random.randint(1, 5)
        if is_promo_day:
            qty += random.randint(2, 6)

        discount = random.choice([0.0, 0.0, 0.05, 0.10, 0.15])
        revenue = round(unit_price * qty * (1 - discount), 2)
        profit = round((unit_price * (1 - discount) - unit_cost) * qty, 2)

        region = random.choices(regions, weights=region_weights, k=1)[0]
        status = random.choices(statuses, weights=status_weights, k=1)[0]
        customer = random.choice(customers)

        # Intentionally introduce messy formatting for the cleaner to catch
        raw_date = order_dt.strftime(random.choice(date_formats))
        raw_revenue = f"${revenue:,.2f}" if random.random() < 0.22 else revenue
        raw_profit = f"${profit:,.2f}" if random.random() < 0.15 else profit

        if random.random() < 0.12:
            category = f"  {category.lower()}  "
        if random.random() < 0.10:
            customer = f"  {customer} "
        if random.random() < 0.03:
            region = None
        if random.random() < 0.025:
            status = None
        if random.random() < 0.02:
            raw_profit = None

        rows.append(
            {
                "Order ID": f"ORD-{10000 + i}",
                "Order Date": raw_date,
                "Customer": customer,
                "Category": category,
                "Product": product,
                "Region": region,
                "Payment Status": status,
                "Quantity": qty,
                "Revenue": raw_revenue,
                "Profit": raw_profit,
                "Stock Level": stock_level,
            }
        )

    df = pd.DataFrame(rows)

    # Inject 18 exact duplicate rows to test deduplication
    duplicates = df.sample(n=18, random_state=seed)
    df = pd.concat([df, duplicates], ignore_index=True)

    # Shuffle rows
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return df