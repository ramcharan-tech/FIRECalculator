"""India-specific presets, expense baskets, statutory instruments, and benchmark assumptions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRESETS_JSON_PATH = Path(__file__).resolve().parent.parent / "firecalc_presets.json"


def load_presets_from_json() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load expense and goal presets from external JSON file with fallback."""
    if PRESETS_JSON_PATH.exists():
        try:
            data = json.loads(PRESETS_JSON_PATH.read_text(encoding="utf-8"))
            exp_presets = data.get("expense_presets", {})
            goal_presets = data.get("goal_presets", [])
            if isinstance(exp_presets, dict) and isinstance(goal_presets, list):
                return exp_presets, goal_presets
        except Exception:
            pass
    # Fallback default presets
    return {}, []


def get_indian_expense_presets() -> dict[str, dict[str, Any]]:
    """Get active expense presets from JSON file (reloads dynamically)."""
    exp, _ = load_presets_from_json()
    return exp or INDIAN_EXPENSE_PRESETS_FALLBACK


def get_indian_goal_presets() -> list[dict[str, Any]]:
    """Get active goal presets from JSON file (reloads dynamically)."""
    _, goals = load_presets_from_json()
    return goals or INDIAN_GOAL_PRESETS_FALLBACK


# Fallback presets if JSON file is missing or unreadable
INDIAN_EXPENSE_PRESETS_FALLBACK: dict[str, dict[str, Any]] = {
    "Tier-1 Metro Family (4 Members - Renting)": {
        "description": "Family of 4 living in Bengaluru, Mumbai, NCR, or Hyderabad in rented accommodation.",
        "expenses": [
            {"category": "House Rent & Maintenance", "amount": 42000, "frequency": "monthly", "essential": True, "annual_inflation": 0.07},
            {"category": "Groceries, Milk & Vegetables", "amount": 25000, "frequency": "monthly", "essential": True, "annual_inflation": 0.06},
            {"category": "Children School Fees & Coaching", "amount": 200000, "frequency": "yearly", "essential": True, "annual_inflation": 0.10},
            {"category": "Maid / Cook / House Help", "amount": 8000, "frequency": "monthly", "essential": True, "annual_inflation": 0.07},
            {"category": "Utilities (Electricity, Gas, WiFi)", "amount": 6500, "frequency": "monthly", "essential": True, "annual_inflation": 0.05},
            {"category": "Health Insurance (Family Floater)", "amount": 35000, "frequency": "yearly", "essential": True, "annual_inflation": 0.12},
            {"category": "Routine Medical & Pharmacy", "amount": 4000, "frequency": "monthly", "essential": True, "annual_inflation": 0.10},
            {"category": "Car Fuel & Maintenance", "amount": 8500, "frequency": "monthly", "essential": False, "annual_inflation": 0.06},
            {"category": "Dining Out, Swiggy/Zomato & Movies", "amount": 10000, "frequency": "monthly", "essential": False, "annual_inflation": 0.06},
            {"category": "Annual Vacation & Festive Travel", "amount": 150000, "frequency": "yearly", "essential": False, "annual_inflation": 0.08},
            {"category": "Clothing & Festival Shopping", "amount": 60000, "frequency": "yearly", "essential": False, "annual_inflation": 0.06},
            {"category": "Car Purchase / Replacement", "amount": 1500000, "frequency": "one-time", "replacement_years": 15, "essential": False, "annual_inflation": 0.06},
            {"category": "Electronics & Appliance Replacement", "amount": 100000, "frequency": "one-time", "replacement_years": 4, "essential": False, "annual_inflation": 0.05},
        ],
    },
    "Tier-2 City Household (Self-Owned Home)": {
        "description": "Family living in cities like Pune, Jaipur, Kochi, Coimbatore with own house (no rent).",
        "expenses": [
            {"category": "Property Tax & Home Maintenance", "amount": 30000, "frequency": "yearly", "essential": True, "annual_inflation": 0.05},
            {"category": "Groceries, Milk & Provisions", "amount": 18000, "frequency": "monthly", "essential": True, "annual_inflation": 0.06},
            {"category": "Children School & College", "amount": 120000, "frequency": "yearly", "essential": True, "annual_inflation": 0.09},
            {"category": "Utilities (Power, Water, LPG, Internet)", "amount": 4500, "frequency": "monthly", "essential": True, "annual_inflation": 0.05},
            {"category": "Health Insurance Super Top-up", "amount": 25000, "frequency": "yearly", "essential": True, "annual_inflation": 0.12},
            {"category": "Routine Medical Out-of-Pocket", "amount": 3000, "frequency": "monthly", "essential": True, "annual_inflation": 0.10},
            {"category": "Fuel & Two-Wheeler / Car Upkeep", "amount": 5000, "frequency": "monthly", "essential": False, "annual_inflation": 0.06},
            {"category": "Leisure, Dining & Entertainment", "amount": 6000, "frequency": "monthly", "essential": False, "annual_inflation": 0.06},
            {"category": "Annual Pilgrimage & Family Trips", "amount": 80000, "frequency": "yearly", "essential": False, "annual_inflation": 0.07},
            {"category": "Gold / Jewellery for Festivals", "amount": 60000, "frequency": "yearly", "essential": False, "annual_inflation": 0.08},
            {"category": "Car Purchase / Replacement", "amount": 1200000, "frequency": "one-time", "replacement_years": 15, "essential": False, "annual_inflation": 0.06},
            {"category": "Two-Wheeler / Scooter Replacement", "amount": 100000, "frequency": "one-time", "replacement_years": 8, "essential": False, "annual_inflation": 0.06},
            {"category": "Home Appliance & White Goods", "amount": 80000, "frequency": "one-time", "replacement_years": 5, "essential": False, "annual_inflation": 0.05},
        ],
    },
    "Young Tech Professional (Single / DINK in Metro)": {
        "description": "Single or Double Income No Kids couple starting their FIRE journey in Bangalore or Hyderabad.",
        "expenses": [
            {"category": "Co-living / Flat Rent & Maintenance", "amount": 32000, "frequency": "monthly", "essential": True, "annual_inflation": 0.07},
            {"category": "Groceries & Instant Delivery (Blinkit/Zepto)", "amount": 14000, "frequency": "monthly", "essential": True, "annual_inflation": 0.06},
            {"category": "Cook & Domestic Maid", "amount": 6000, "frequency": "monthly", "essential": True, "annual_inflation": 0.07},
            {"category": "Cab Aggregators (Uber/Ola/Namma Yatri)", "amount": 6000, "frequency": "monthly", "essential": True, "annual_inflation": 0.06},
            {"category": "Personal Health & Term Insurance", "amount": 22000, "frequency": "yearly", "essential": True, "annual_inflation": 0.10},
            {"category": "Weekend Brunches, Cafes & Pubs", "amount": 12000, "frequency": "monthly", "essential": False, "annual_inflation": 0.07},
            {"category": "Gym, Badminton & Wellness", "amount": 3000, "frequency": "monthly", "essential": False, "annual_inflation": 0.05},
            {"category": "Weekend Getaways & Annual International Trip", "amount": 180000, "frequency": "yearly", "essential": False, "annual_inflation": 0.08},
            {"category": "Car Purchase / Replacement", "amount": 1400000, "frequency": "one-time", "replacement_years": 15, "essential": False, "annual_inflation": 0.06},
            {"category": "Gadgets, Phone & Tech Upgrades", "amount": 120000, "frequency": "one-time", "replacement_years": 3, "essential": False, "annual_inflation": 0.04},
        ],
    },
}

INDIAN_GOAL_PRESETS_FALLBACK: list[dict[str, Any]] = [
    {
        "name": "Undergraduate B.Tech / Private University",
        "category": "Education",
        "cost": 1800000,
        "years": 12,
        "inflation": 0.10,
        "return": 0.11,
        "beneficiary": "Child",
        "description": "4-year engineering/private university tuition & hostel in India with 10% educational inflation.",
    },
    {
        "name": "Overseas Master's Degree (US / Europe)",
        "category": "Education",
        "cost": 6500000,
        "years": 15,
        "inflation": 0.08,
        "return": 0.12,
        "beneficiary": "Child",
        "description": "Tuition, living expenses, and currency depreciation impact for a 2-year overseas MS/MBA.",
    },
    {
        "name": "MBBS Medical Seat (Private / Deemed)",
        "category": "Education",
        "cost": 8000000,
        "years": 14,
        "inflation": 0.11,
        "return": 0.12,
        "beneficiary": "Child",
        "description": "Full course fees, clinical training, and hostel at private Indian medical colleges.",
    },
    {
        "name": "Indian Wedding Celebration",
        "category": "Other",
        "cost": 2500000,
        "years": 16,
        "inflation": 0.08,
        "return": 0.10,
        "beneficiary": "Child / Family",
        "description": "Venue, catering, decor, and ceremonies over 3 days.",
    },
    {
        "name": "Gold / Jewellery Accumulation",
        "category": "Gold / jewellery",
        "cost": 1000000,
        "years": 10,
        "inflation": 0.07,
        "return": 0.08,
        "beneficiary": "Family",
        "description": "Purchase of physical gold/Sovereign Gold Bonds for long-term family milestone.",
    },
    {
        "name": "Home Down Payment (20% of 1.2 Crore flat)",
        "category": "Home upgrade",
        "cost": 2400000,
        "years": 5,
        "inflation": 0.06,
        "return": 0.08,
        "beneficiary": "Self",
        "description": "Down payment + stamp duty and registration for purchasing a residential apartment.",
    },
]


def epf_projected_balance(
    current_balance: float,
    monthly_basic_da: float,
    annual_salary_growth: float,
    epf_interest_rate: float,
    years: int,
) -> float:
    """Project Employee Provident Fund (EPF) accumulation up to retirement.

    Indian EPF rules:
    - Employee contribution: 12% of Basic + DA.
    - Employer contribution to EPF: 3.67% of Basic + DA (8.33% up to ceiling goes to EPS).
    - Total monthly EPF credit: 15.67% of Basic + DA.
    - Compounded monthly or annually at Government announced interest rate (e.g. 8.25%).
    """
    balance = current_balance
    monthly_rate = epf_interest_rate / 12
    basic = monthly_basic_da

    for yr in range(1, years + 1):
        for _ in range(12):
            monthly_contrib = basic * 0.1567
            balance = balance * (1 + monthly_rate) + monthly_contrib
        basic *= 1 + annual_salary_growth
    return balance


def ppf_projected_balance(
    current_balance: float,
    annual_deposit: float,
    ppf_interest_rate: float,
    years: int,
) -> float:
    """Project Public Provident Fund (PPF) accumulation.

    Rules:
    - Max deposit: ₹1,50,000 per financial year.
    - Compounded annually at Government declared rate (currently 7.1%).
    """
    annual_contrib = min(annual_deposit, 150000.0)
    balance = current_balance
    for _ in range(years):
        balance = (balance + annual_contrib) * (1 + ppf_interest_rate)
    return balance


def nps_projected_corpus(
    current_balance: float,
    monthly_contribution: float,
    annual_growth: float,
    years: int,
) -> dict[str, float]:
    """Project National Pension System (NPS Tier-I) corpus and retirement payout.

    At age 60:
    - Up to 60% can be withdrawn tax-free as a lump sum.
    - Minimum 40% must be used to purchase an annuity (annuity income is taxable).
    """
    months = years * 12
    monthly_r = (1 + annual_growth) ** (1 / 12) - 1 if annual_growth > 0 else 0.0
    balance = current_balance
    for _ in range(months):
        balance = balance * (1 + monthly_r) + monthly_contribution

    lump_sum_tax_free = balance * 0.60
    annuity_corpus = balance * 0.40
    # Assuming typical ~6.5% life annuity rate in India:
    est_monthly_annuity_pension = (annuity_corpus * 0.065) / 12

    return {
        "total_corpus": balance,
        "lump_sum_60_pct_tax_free": lump_sum_tax_free,
        "annuity_corpus_40_pct": annuity_corpus,
        "est_monthly_pension": est_monthly_annuity_pension,
    }

