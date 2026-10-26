import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lakehouse.sample import REGIONS, revenue_by_region, sample_orders  # noqa: E402


def test_sample_orders_are_deterministic():
    assert sample_orders(5) == sample_orders(5)
    assert [o["order_id"] for o in sample_orders(5)] == [1, 2, 3, 4, 5]


def test_every_region_appears():
    assert {o["region"] for o in sample_orders(8)} == set(REGIONS)


def test_revenue_by_region_adds_up():
    orders = sample_orders(100)
    totals = revenue_by_region(orders)
    assert set(totals) == set(REGIONS)
    assert round(sum(totals.values()), 2) == round(sum(o["amount"] for o in orders), 2)
