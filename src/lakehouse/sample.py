"""Sample data and logic for the starter job. Plain Python, so it can be unit tested without Spark."""
from datetime import date, timedelta

REGIONS = ("north", "south", "east", "west")


def sample_orders(n: int, start: date = date(2026, 1, 1)) -> list[dict]:
    """n deterministic orders, so every environment produces the same table."""
    return [
        {
            "order_id": i + 1,
            "order_date": start + timedelta(days=i % 30),
            "region": REGIONS[i % len(REGIONS)],
            "amount": round(10 + (i * 7.3) % 90, 2),
        }
        for i in range(n)
    ]


def revenue_by_region(orders: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for o in orders:
        totals[o["region"]] = round(totals.get(o["region"], 0.0) + o["amount"], 2)
    return totals
