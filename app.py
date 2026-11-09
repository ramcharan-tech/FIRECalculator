from __future__ import annotations

from datetime import date
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from firecalc.calculations import (
    Expense,
    annual_expense_total,
    cagr,
    earliest_fire_age_trajectory,
    emi_payment,
    emi_schedule,
    goal_future_cost,
    home_loan_tax_benefit,
    monthly_sip_for_target,
    prepayment_savings,
    project_portfolio,
    projected_annual_expense,
    project_monthly_swp,
    required_monthly_swp_corpus,
    wealth_multiplier_table,
    xirr,
)
from firecalc.india_presets import (
    get_indian_expense_presets,
    get_indian_goal_presets,
    epf_projected_balance,
    nps_projected_corpus,
    ppf_projected_balance,
)
from firecalc.assistant import build_assistant_graph
from firecalc.tax import return_after_fee_drag
from firecalc.storage import DATABASE_PATH, load_expenses, save_expenses, load_goals, save_goals


st.set_page_config(page_title="India FIRE Planner", page_icon="🌱", layout="wide")
load_dotenv(Path(__file__).with_name(".env"))
st.title("India FIRE Planner")
st.caption("A transparent planning calculator for Indian households, INR spending, and a comfortable retirement.")

FREQUENCIES = ["monthly", "quarterly", "yearly", "weekly", "one-time"]
DEFAULTS_PATH = Path(__file__).with_name(".firecalc_defaults.json")
DEFAULT_ASSUMPTION_KEYS = [
    "current_portfolio", "monthly_sip", "annual_lump_sum", "annual_step_up_pct",
    "pre_retirement_return_pct", "annual_fee_drag_pct", "post_retirement_return_pct",
    "annual_ltcg_exemption", "ltcg_tax_rate_pct", "general_inflation_pct",
    "investment_monthly_expenses", "retirement_lifestyle_pct", "retirement_years",
    "investment_expense_basis", "current_age", "retirement_age",
    "cagr_change_pct", "inflation_change_pct",
]

# Edit these lists to change the model choices shown in the provider dropdown.
# Matching *_MODELS variables in .env can override each list with comma-separated IDs.
DEFAULT_MODELS = {
    "Gemini": ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"],
    "OpenRouter": ["openrouter/free", "nvidia/nemotron-3.5-lightning:free", "nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3.5-super-vl:free"],
    "OpenCode": ["deepseek-v4.1-flash-free", "glm-5.3-flash-free", "nemotron-3.5-lightning-free"],
}
MODEL_LIST_ENV = {
    "Gemini": "GEMINI_MODELS",
    "OpenRouter": "OPENROUTER_MODELS",
    "OpenCode": "OPENCODE_MODELS",
}


@st.cache_resource(show_spinner=False)
def get_cached_assistant_graph(provider: str, model_name: str, api_key: str, base_url: str | None = None):
    return build_assistant_graph(provider, model_name, api_key, base_url=base_url)


def provider_models(provider: str) -> tuple[list[str], str]:
    configured = os.getenv(MODEL_LIST_ENV[provider], "")
    options = [item.strip() for item in configured.split(",") if item.strip()] or DEFAULT_MODELS[provider].copy()
    preferred = {
        "Gemini": os.getenv("GEMINI_MODEL", ""),
        "OpenRouter": os.getenv("OPENROUTER_MODEL", ""),
        "OpenCode": os.getenv("OPENCODE_MODEL", ""),
    }[provider]
    if preferred and preferred not in options:
        options.insert(0, preferred)
    return options, preferred or options[0]

if "expenses" not in st.session_state:
    try:
        st.session_state.expenses = load_expenses()
        st.session_state.expense_db_load_error = None
        if st.session_state.expenses:
            st.session_state.investment_expense_basis = "All categorized expenses"
    except sqlite3.Error as exc:
        st.session_state.expenses = []
        st.session_state.expense_db_load_error = str(exc)
if "cash_flows" not in st.session_state:
    st.session_state.cash_flows = []
for state_key, state_default in {
    "current_portfolio": 0.0,
    "monthly_sip": 0.0,
    "annual_lump_sum": 0.0,
    "annual_step_up_pct": 0.0,
    "pre_retirement_return_pct": 8.0,
    "annual_fee_drag_pct": 0.0,
    "post_retirement_return_pct": 5.0,
    "annual_ltcg_exemption": 125000,
    "ltcg_tax_rate_pct": 12.5,
    "general_inflation_pct": 6.0,
    "investment_monthly_expenses": 0.0,
    "retirement_lifestyle_pct": 100,
    "retirement_years": 30,
    "cagr_change_pct": 2.0,
    "inflation_change_pct": 1.0,
    "expense_category_input": "",
    "expense_amount_input": 0,
    "expense_frequency_input": "monthly",
    "expense_replacement_years_input": 5,
    "expense_essential_input": True,
    "expense_inflation_input_pct": 6.0,
    "expense_projection_years": 10,
    "investment_expense_basis": "Manual monthly expenses",
    "current_age": 35,
    "retirement_age": 60,
    "planner_section": "Investments & Retirement",
}.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = state_default
if "goals" not in st.session_state:
    try:
        st.session_state.goals = load_goals()
    except sqlite3.Error as exc:
        st.session_state.goals = []
        st.session_state.goal_db_load_error = str(exc)


def load_saved_investment_defaults() -> None:
    """Populate calculator assumptions once when the Investments page is opened."""
    st.session_state.investment_defaults_load_error = None
    if not DEFAULTS_PATH.exists():
        return
    try:
        saved = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
        assumptions = saved.get("assumptions", {}) if isinstance(saved, dict) else {}
        if not isinstance(assumptions, dict):
            raise ValueError("Saved defaults must contain an assumptions object.")
        legacy_keys = {
            "return_drag_pct": "annual_fee_drag_pct",
            "scenario_return_swing_pct": "cagr_change_pct",
            "scenario_inflation_swing_pct": "inflation_change_pct",
        }
        for key in DEFAULT_ASSUMPTION_KEYS:
            if key in assumptions:
                st.session_state[key] = assumptions[key]
            else:
                legacy_key = next((old for old, new in legacy_keys.items() if new == key and old in assumptions), None)
                if legacy_key:
                    st.session_state[key] = assumptions[legacy_key]
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        st.session_state.investment_defaults_load_error = str(exc)


current_page_before_render = st.session_state.get("planner_section", "Investments & Retirement")
last_page_before_render = st.session_state.get("_last_planner_section")
force_load_investment_defaults = st.session_state.pop("load_investment_defaults_on_open", False)
if current_page_before_render == "Investments & Retirement" and (
    last_page_before_render != current_page_before_render
    or force_load_investment_defaults
):
    load_saved_investment_defaults()
st.session_state._last_planner_section = current_page_before_render

export_data = {
    "expenses": st.session_state.expenses,
    "assumptions": {key: st.session_state[key] for key in DEFAULT_ASSUMPTION_KEYS},
    "goals": st.session_state.goals,
}
def select_page(section: str) -> None:
    st.session_state.planner_section = section
    if section == "Investments & Retirement":
        st.session_state.load_investment_defaults_on_open = True


if st.session_state.planner_section == "Overview":
    st.session_state.planner_section = "Investments & Retirement"

st.sidebar.markdown("### 🌱 FIRE Planner")
st.sidebar.markdown("<div style='font-size:0.72rem;font-weight:700;letter-spacing:.12em;color:var(--text-color);opacity:.8;margin:0.5rem 0 .7rem'>PLANNING</div>", unsafe_allow_html=True)
st.sidebar.markdown(
    """
    <style>
      [data-testid="stSidebar"] [data-testid="stButton"] button {
        justify-content: flex-start; text-align: left; border-radius: 12px;
        min-height: 2.75rem; transition: all 140ms ease-in-out;
      }
      [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
        border: 1px solid color-mix(in srgb, var(--text-color) 18%, transparent);
        background: color-mix(in srgb, var(--secondary-background-color) 82%, transparent);
        color: var(--text-color) !important;
      }
      [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
        border-color: #54b7bd; background: color-mix(in srgb, #168b91 24%, var(--secondary-background-color));
        color: var(--text-color) !important;
      }
      [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
        border: 1px solid #1a7f8e; color: #ffffff !important;
        background: linear-gradient(115deg, #176b80, #238b78);
        box-shadow: 0 4px 12px rgba(23,107,128,.18);
      }
      [data-testid="stSidebar"] [data-testid="stButton"] button p { color: inherit !important; }
    </style>
    """,
    unsafe_allow_html=True,
)
nav_items = [
    ("Investments & Retirement", "📈", "nav_investments"),
    ("Wealth Multiplier", "🚀", "nav_wealth"),
    ("Loans & EMI", "🏦", "nav_emi"),
    ("Spending", "🧾", "nav_spending"),
    ("Goals", "🎯", "nav_goals"),
]
for section, icon, button_key in nav_items:
    st.sidebar.button(
        f"{icon}   {section}",
        key=button_key,
        type="primary" if st.session_state.planner_section == section else "secondary",
        use_container_width=True,
        on_click=select_page,
        args=(section,),
    )
page = st.session_state.planner_section
st.sidebar.caption("Currency: INR · Investment defaults load when that section opens.")
with st.sidebar.expander("Portable plan backup", expanded=False):
    st.caption("Optional: export a plan to move it between devices or keep a separate backup. Local defaults and SQLite already save your working data on this computer.")
    st.download_button("Export plan JSON", json.dumps(export_data, indent=2), "fire-scenario.json", "application/json")
    uploaded_data = st.file_uploader("Import plan JSON", type=["json"])
    if uploaded_data is not None and st.button("Import plan file"):
        try:
            imported = json.loads(uploaded_data.getvalue())
            if not isinstance(imported, dict):
                raise ValueError("Scenario must be a JSON object")
            imported_expenses = imported.get("expenses", [])
            imported_goals = imported.get("goals", [])
            imported_assumptions = imported.get("assumptions", {})
            if not isinstance(imported_expenses, list) or not all(isinstance(x, dict) for x in imported_expenses):
                raise ValueError("Expenses must be a list")
            if not isinstance(imported_goals, list) or not all(isinstance(x, dict) for x in imported_goals):
                raise ValueError("Goals must be a list")
            if not isinstance(imported_assumptions, dict):
                raise ValueError("Assumptions must be an object")
            for item in imported_expenses:
                if not all(key in item for key in ("category", "amount", "frequency", "essential")):
                    raise ValueError("Each expense needs category, amount, frequency, and essential fields")
                if not isinstance(item["category"], str) or not item["category"].strip() or not isinstance(item["essential"], bool):
                    raise ValueError("Expense category and essential flag have invalid types")
                if item["frequency"] not in FREQUENCIES or isinstance(item["amount"], bool) or not isinstance(item["amount"], (int, float)) or not math.isfinite(item["amount"]):
                    raise ValueError("Expense frequency or amount is invalid")
                category_rate = item.get("annual_inflation", 0.06)
                if isinstance(category_rate, bool) or not isinstance(category_rate, (int, float)) or not math.isfinite(category_rate) or not -0.99 <= category_rate <= 1.0:
                    raise ValueError("Expense inflation assumption is invalid")
                replacement_years = item.get("replacement_years", 1 if item["frequency"] == "one-time" else None)
                if item["frequency"] == "one-time" and (isinstance(replacement_years, bool) or not isinstance(replacement_years, int) or replacement_years < 1):
                    raise ValueError("One-time expenses need a whole-number replacement interval of at least one year")
                item["amount"] = int(round(item["amount"]))
                item["replacement_years"] = replacement_years
                Expense(item["category"], item["amount"], item["frequency"], item["essential"], float(category_rate), replacement_years).annual_amount()
            goal_fields = {"name", "category", "beneficiary", "cost", "years", "inflation", "return"}
            for item in imported_goals:
                if not goal_fields.issubset(item):
                    raise ValueError("Each goal needs name, category, beneficiary, cost, years, inflation, and return fields")
                if not isinstance(item["name"], str) or not isinstance(item["category"], str) or not isinstance(item["beneficiary"], str):
                    raise ValueError("Goal labels must be text")
                for key in ("cost", "years", "inflation", "return"):
                    if isinstance(item[key], bool) or not isinstance(item[key], (int, float)) or not math.isfinite(item[key]):
                        raise ValueError(f"Goal {key} must be a finite number")
                if item["cost"] < 0 or item["years"] < 0 or not -0.99 <= item["inflation"] <= 1 or not -0.99 <= item["return"] <= 1:
                    raise ValueError("Goal amount, date, inflation, or return is outside its allowed range")
            legacy_keys = {
                "return_drag_pct": "annual_fee_drag_pct",
                "scenario_return_swing_pct": "cagr_change_pct",
                "scenario_inflation_swing_pct": "inflation_change_pct",
            }
            imported_assumptions = dict(imported_assumptions)
            for old_key, new_key in legacy_keys.items():
                if new_key not in imported_assumptions and old_key in imported_assumptions:
                    imported_assumptions[new_key] = imported_assumptions[old_key]
                imported_assumptions.pop(old_key, None)
            for obsolete_key in ("emergency_reserve", "withdrawal_tax_pct", "manual_tax_year"):
                imported_assumptions.pop(obsolete_key, None)
            bounds = {
                "current_portfolio": (0, float("inf")), "monthly_sip": (0, float("inf")), "annual_lump_sum": (0, float("inf")),
                "annual_step_up_pct": (-99, 100), "pre_retirement_return_pct": (-99, 100), "post_retirement_return_pct": (-99, 100),
                "annual_fee_drag_pct": (0, 100), "annual_ltcg_exemption": (0, float("inf")),
                "ltcg_tax_rate_pct": (0, 100), "general_inflation_pct": (-99, 100),
                "investment_monthly_expenses": (0, float("inf")), "retirement_lifestyle_pct": (50, 150),
                "current_age": (18, 100), "retirement_age": (18, 100),
                "retirement_years": (1, 80),
                "cagr_change_pct": (0, 20), "inflation_change_pct": (0, 20),
            }
            for key, value in imported_assumptions.items():
                if key in bounds:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        raise ValueError(f"{key} must be a finite number")
                    if not bounds[key][0] <= value <= bounds[key][1]:
                        raise ValueError(f"{key} is outside its allowed range")
                    if key in {"current_age", "retirement_age"} and not float(value).is_integer():
                        raise ValueError(f"{key} must be a whole number")
            if "investment_expense_basis" in imported_assumptions and imported_assumptions["investment_expense_basis"] not in {"All categorized expenses", "Essential expenses only", "Manual monthly expenses"}:
                raise ValueError("investment_expense_basis is invalid")
            st.session_state.expenses = imported_expenses
            if "investment_expense_basis" not in imported_assumptions and imported_expenses:
                st.session_state.investment_expense_basis = "All categorized expenses"
            if imported_assumptions.get("retirement_age", st.session_state.retirement_age) < imported_assumptions.get("current_age", st.session_state.current_age):
                raise ValueError("Retirement age cannot be lower than current age")
            allowed_assumptions = set(DEFAULT_ASSUMPTION_KEYS)
            for key, value in imported_assumptions.items():
                if key in allowed_assumptions:
                    st.session_state[key] = value
            st.session_state.goals = imported_goals
            st.session_state.planner_section = "Investments & Retirement"
            st.rerun()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            st.error(f"Could not load scenario: {exc}")

def indian_grouping(value: float) -> str:
    rounded = int(round(abs(value)))
    digits = str(rounded)
    if len(digits) <= 3:
        grouped = digits
    else:
        tail = digits[-3:]
        head = digits[:-3]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        grouped = ",".join(groups + [tail])
    return f"-{grouped}" if value < 0 else grouped


def fmt_inr(value: float) -> str:
    return f"₹{indian_grouping(value)}"


def parse_indian_amount(raw_value: str) -> int:
    """Parse a whole-rupee value with optional Indian or western grouping commas."""
    cleaned = raw_value.strip().replace(",", "").replace("₹", "").replace(" ", "")
    if not cleaned:
        return 0
    return int(round(float(cleaned)))


def _commit_rupee_input(display_key: str, state_key: str, minimum: int | None, maximum: int | None) -> None:
    try:
        amount = parse_indian_amount(st.session_state[display_key])
    except (KeyError, TypeError, ValueError):
        st.session_state[f"{state_key}__error"] = "Enter a valid whole-rupee amount."
        st.session_state[display_key] = indian_grouping(st.session_state.get(state_key, 0))
        return
    if minimum is not None and amount < minimum:
        st.session_state[f"{state_key}__error"] = f"Amount must be at least {indian_grouping(minimum)}."
        st.session_state[display_key] = indian_grouping(st.session_state.get(state_key, minimum))
        return
    if maximum is not None and amount > maximum:
        st.session_state[f"{state_key}__error"] = f"Amount must not exceed {indian_grouping(maximum)}."
        st.session_state[display_key] = indian_grouping(st.session_state.get(state_key, maximum))
        return
    st.session_state[state_key] = amount
    st.session_state[display_key] = indian_grouping(amount)
    st.session_state.pop(f"{state_key}__error", None)


def rupee_input(
    label: str,
    *,
    key: str,
    container: Any = st,
    min_value: int | None = None,
    max_value: int | None = None,
    value: int | None = None,
    help: str | None = None,
) -> int:
    """Text amount input that keeps rupees readable with Indian digit grouping."""
    if key not in st.session_state:
        initial = value if value is not None else (min_value if min_value is not None else 0)
        st.session_state[key] = int(initial)
    display_key = f"{key}__indian_display"
    if display_key not in st.session_state:
        st.session_state[display_key] = indian_grouping(st.session_state[key])
    else:
        try:
            if parse_indian_amount(st.session_state[display_key]) != int(st.session_state[key]):
                st.session_state[display_key] = indian_grouping(st.session_state[key])
        except (TypeError, ValueError):
            st.session_state[display_key] = indian_grouping(st.session_state[key])
    raw = container.text_input(
        label,
        key=display_key,
        placeholder="e.g. 1,23,45,678",
        help=help or "Type the amount; commas are added in Indian number format when you commit the field.",
        on_change=_commit_rupee_input,
        args=(display_key, key, min_value, max_value),
    )
    error = st.session_state.get(f"{key}__error")
    if error:
        container.caption(error)
    # Text may be uncommitted while the user is editing; use the last committed number.
    try:
        return parse_indian_amount(raw)
    except (TypeError, ValueError):
        return int(st.session_state[key])


def chart_ticks(maximum: float) -> tuple[list[float], list[str]]:
    maximum = max(0.0, maximum)
    values = [maximum * fraction for fraction in (0, 0.25, 0.5, 0.75, 1)]
    return values, [fmt_inr(value) for value in values]


def expense_objects() -> list[Expense]:
    return [Expense(x["category"], x["amount"], x["frequency"], x["essential"], x.get("annual_inflation"), x.get("replacement_years") or (1 if x["frequency"] == "one-time" else None)) for x in st.session_state.expenses]


def selected_expense_model() -> tuple[list[Expense], float]:
    basis = st.session_state.get("investment_expense_basis", "Manual monthly expenses")
    if basis == "Manual monthly expenses":
        manual = st.session_state.investment_monthly_expenses
        return [Expense("Current expenses", manual * 12, "yearly")], manual * 12
    all_expenses = expense_objects()
    if basis == "Essential expenses only":
        all_expenses = [expense for expense in all_expenses if expense.essential]
    return all_expenses, annual_expense_total(all_expenses)


def invested_principal_at_year(
    current_portfolio: float,
    monthly_sip: float,
    years: int,
    annual_step_up: float,
    annual_lump_sum: float,
) -> float:
    """Track current value as starting basis plus future invested contributions."""
    principal = current_portfolio
    contribution = monthly_sip
    for month in range(1, int(round(years * 12)) + 1):
        principal += contribution
        if month % 12 == 0:
            principal += annual_lump_sum
            contribution *= 1 + annual_step_up
    return principal


def cost_basis_fraction(invested_principal: float, portfolio_value: float) -> float:
    """Estimate the cost-basis share of a balance; unknown historic gain is excluded."""
    if portfolio_value <= 0:
        return 1.0
    return min(1.0, max(0.0, invested_principal / portfolio_value))


def monthly_swp_streams(
    expenses: list[Expense], years_until_retirement: float, general_inflation: float,
    lifestyle_pct: float, inflation_adjustment: float = 0.0,
) -> list[tuple[float, float]]:
    """Return net first-month spending needs and each category's annual inflation."""
    streams = []
    for expense in expenses:
        annual = expense.annual_amount()
        if annual <= 0:
            continue
        rate = general_inflation if expense.annual_inflation is None else expense.annual_inflation
        rate = max(-1.0, rate + inflation_adjustment)
        net_monthly = annual * (1 + rate) ** years_until_retirement / 12 * lifestyle_pct / 100
        streams.append((net_monthly, rate))
    return streams


def add_expense_callback() -> None:
    category = st.session_state.expense_category_input.strip()
    amount = int(st.session_state.expense_amount_input)
    frequency = st.session_state.expense_frequency_input
    replacement_years = int(st.session_state.expense_replacement_years_input) if frequency == "one-time" else None
    if not category:
        st.session_state.expense_form_error = "Enter an expense category."
        return
    if frequency == "one-time" and replacement_years < 1:
        st.session_state.expense_form_error = "Replacement interval must be at least one year."
        return
    if not st.session_state.expenses:
        st.session_state.investment_expense_basis = "All categorized expenses"
    st.session_state.expenses.append({
        "category": category,
        "amount": amount,
        "frequency": frequency,
        "essential": bool(st.session_state.expense_essential_input),
        "annual_inflation": float(st.session_state.expense_inflation_input_pct) / 100,
        "replacement_years": replacement_years,
    })
    st.session_state.expense_category_input = ""
    st.session_state.expense_amount_input = 0
    st.session_state.expense_amount_input__indian_display = "0"
    st.session_state.expense_frequency_input = "monthly"
    st.session_state.expense_replacement_years_input = 5
    st.session_state.expense_essential_input = True
    st.session_state.expense_inflation_input_pct = 6.0
    st.session_state.expense_form_error = ""


def add_goal_callback() -> None:
    name = st.session_state.goal_name_input.strip()
    cost = int(st.session_state.goal_cost_input)
    if not name or cost <= 0:
        st.session_state.goal_form_error = "Enter a goal name and a positive cost."
        return
    st.session_state.goals.append({
        "name": name,
        "category": st.session_state.goal_category_input,
        "beneficiary": st.session_state.goal_beneficiary_input.strip(),
        "cost": cost,
        "years": st.session_state.goal_years_input,
        "inflation": st.session_state.goal_inflation_input_pct / 100,
        "return": st.session_state.goal_return_input_pct / 100,
    })
    st.session_state.goal_name_input = ""
    st.session_state.goal_beneficiary_input = ""
    st.session_state.goal_cost_input = 0
    st.session_state.goal_cost_input__indian_display = "0"
    st.session_state.goal_form_error = ""


def inflation_input(container: Any = st) -> float:
    return container.number_input(
        "General annual inflation (%)", min_value=-99.0, max_value=100.0, step=0.5,
        help="Illustrative input only. Set your own planning assumption; individual spending categories can use their own rates.", key="general_inflation_pct",
    ) / 100


st.markdown(
    """
    <style>
      [data-testid="stChatInput"] textarea {
        min-height: 3.5rem !important; font-size: 0.95rem !important; line-height: 1.4;
      }
      [data-testid="stChatMessage"] { padding: .4rem .2rem; }

      /* Floating Docked Widget at Bottom-Right (Exact Ask ILA Layout) */
      div[data-testid="stVerticalBlock"]:has(> div#floating-assistant-anchor) {
        position: fixed !important;
        bottom: 0px !important;
        right: 24px !important;
        z-index: 9999999 !important;
        background: #ffffff !important;
        border-top-left-radius: 12px !important;
        border-top-right-radius: 12px !important;
        border-bottom-left-radius: 0px !important;
        border-bottom-right-radius: 0px !important;
        box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.20), -2px 0 10px rgba(0, 0, 0, 0.08) !important;
        border: 1px solid rgba(0, 114, 206, 0.3) !important;
        border-bottom: none !important;
        overflow: hidden !important;
        transition: height 0.22s ease-in-out, width 0.22s ease-in-out !important;
      }

      /* Dark mode adaptation */
      @media (prefers-color-scheme: dark) {
        div[data-testid="stVerticalBlock"]:has(> div#floating-assistant-anchor) {
          background: #0f172a !important;
          border-color: rgba(2, 132, 199, 0.4) !important;
          box-shadow: 0 -4px 32px rgba(0, 0, 0, 0.6) !important;
        }
      }

      /* Ask ILA Style Blue Header Banner */
      .ask-ila-header {
        background: #0072ce !important;
        color: #ffffff !important;
        padding: 8px 14px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        font-family: inherit !important;
      }
      .ask-ila-title {
        font-size: 1.05rem !important;
        font-weight: 800 !important;
        letter-spacing: 0.05em !important;
        color: #ffffff !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
      }
      .ask-ila-actions button {
        background: transparent !important;
        border: none !important;
        color: #ffffff !important;
        font-size: 1.1rem !important;
        padding: 0 4px !important;
        min-height: 24px !important;
        line-height: 1 !important;
        cursor: pointer !important;
      }
      .ask-ila-actions button:hover {
        opacity: 0.8 !important;
      }

      /* Quick suggestion chips (Ask ILA pills) */
      .quick-chips-row {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 8px !important;
        padding: 10px 0 !important;
      }
      .quick-chip-btn button {
        border-radius: 20px !important;
        border: 1.5px solid #0072ce !important;
        color: #0072ce !important;
        background: #ffffff !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        padding: 3px 12px !important;
        min-height: 30px !important;
      }
      .quick-chip-btn button:hover {
        background: #0072ce !important;
        color: #ffffff !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def toggle_assistant() -> None:
    st.session_state.assistant_open = not st.session_state.assistant_open
    if st.session_state.assistant_open:
        st.session_state.assistant_minimized = False


def close_assistant() -> None:
    st.session_state.assistant_open = False
    st.session_state.assistant_minimized = True


def toggle_minimize_assistant() -> None:
    st.session_state.assistant_minimized = not st.session_state.assistant_minimized


def toggle_maximize_assistant() -> None:
    st.session_state.assistant_maximized = not st.session_state.assistant_maximized
    if st.session_state.assistant_maximized:
        st.session_state.assistant_minimized = False


def set_overall_assistant() -> None:
    st.session_state.assistant_mode = "Overall"
    st.session_state.assistant_open = True
    st.session_state.assistant_minimized = False


if "assistant_open" not in st.session_state:
    st.session_state.assistant_open = True  # Always present at bottom right like Ask ILA
if "assistant_mode" not in st.session_state:
    st.session_state.assistant_mode = "Section"
if "assistant_minimized" not in st.session_state:
    st.session_state.assistant_minimized = True  # Starts minimized at bottom right by default
if "assistant_maximized" not in st.session_state:
    st.session_state.assistant_maximized = False

# The page is 100% full width, never squished
main_col = st.container()
with main_col:
    if page == "Spending":
        st.subheader("Spending by category")
        st.write("Enter each expense as a free-text category. One-time purchases are averaged across the years until you expect to replace them.")
        if st.session_state.get("expense_db_load_error"):
            st.warning(f"Could not read saved expenses from SQLite: {st.session_state.expense_db_load_error}")
        col1, col2, col3 = st.columns([2, 1, 1])
        col1.text_input("Expense category", key="expense_category_input", placeholder="For example, rent, school fees, annual travel, jewellery")
        rupee_input("Amount (₹)", min_value=0, key="expense_amount_input", container=col2)
        col3.selectbox("Frequency", FREQUENCIES, key="expense_frequency_input")
        if st.session_state.expense_frequency_input == "one-time":
            replacement_col, _, _ = st.columns(3)
            replacement_col.number_input("Years until next purchase", min_value=1, max_value=100, step=1, key="expense_replacement_years_input", help="The amount is divided across this many years to calculate its yearly average.")
        col1, col2 = st.columns(2)
        col1.checkbox("Essential need", key="expense_essential_input")
        col2.number_input("Annual inflation for this category (%)", min_value=-99.0, max_value=100.0, step=0.5, key="expense_inflation_input_pct", help="Used in the future-expense table and graph.")
        st.button("Add expense", type="primary", on_click=add_expense_callback)
        if st.session_state.get("expense_form_error"):
            st.error(st.session_state.expense_form_error)

        with st.expander("🇮🇳 Load Typical Indian Household Expense Presets", expanded=False):
            st.caption("One-click populate your spending table with realistic Indian household cost structures:")
            active_expense_presets = get_indian_expense_presets()
            preset_choice = st.selectbox("Select Preset Basket", list(active_expense_presets.keys()), key="preset_expense_select")
            st.write(active_expense_presets[preset_choice]["description"])
            if st.button("Apply Selected Basket to Expenses", type="secondary"):
                chosen_items = active_expense_presets[preset_choice]["expenses"]
                st.session_state.expenses = [dict(item) for item in chosen_items]
                st.session_state.investment_expense_basis = "All categorized expenses"
                st.success(f"Loaded {len(chosen_items)} expense items from '{preset_choice}'!")
                st.rerun()
        save_col, reload_col = st.columns(2)
        if save_col.button("Save expenses permanently", type="primary"):
            try:
                save_expenses(st.session_state.expenses)
                st.session_state.expense_db_load_error = None
                st.success(f"Saved {len(st.session_state.expenses)} expense entries to the local SQLite database.")
            except (OSError, sqlite3.Error) as exc:
                st.error(f"Could not save expenses: {exc}")
        if reload_col.button("Reload saved expenses"):
            try:
                st.session_state.expenses = load_expenses()
                st.session_state.expense_db_load_error = None
                st.rerun()
            except sqlite3.Error as exc:
                st.error(f"Could not reload saved expenses: {exc}")
        if st.session_state.expenses:
            try:
                saved_expenses = load_expenses()
            except sqlite3.Error as exc:
                saved_expenses = []
                st.session_state.expense_db_load_error = str(exc)
            if st.session_state.expenses == saved_expenses:
                st.caption(f"{len(saved_expenses)} expense entries loaded from the local SQLite database at {DATABASE_PATH.name}.")
            else:
                st.info("You have unsaved expense changes. Save them to keep these entries after restarting the app.")
            st.markdown("#### Current expenses (Editable)")
            st.caption("💡 Select frequency from the dropdown (`monthly`, `yearly`, `quarterly`, `weekly`, or `one-time`). For **one-time** purchases, enter replacement years in **Lifetime / Replace (Yrs)**.")

            # Prepare data editor dataframe
            import pandas as pd

            expense_rows_data = []
            for item in st.session_state.expenses:
                f = str(item.get("frequency", "monthly"))
                repl = item.get("replacement_years")
                expense_rows_data.append({
                    "Category": str(item.get("category", "")),
                    "Amount (₹)": int(item.get("amount", 0)),
                    "Frequency": f if f in FREQUENCIES else "monthly",
                    "Lifetime / Replace (Yrs)": int(repl) if f == "one-time" and repl else (1 if f == "one-time" else None),
                    "Essential": bool(item.get("essential", True)),
                    "Annual Inflation (%)": round(float(item.get("annual_inflation", 0.06)) * 100, 1),
                })

            df_expenses = pd.DataFrame(expense_rows_data)
            edited_df = st.data_editor(
                df_expenses,
                column_config={
                    "Category": st.column_config.TextColumn("Expense Category", required=True, width="medium"),
                    "Amount (₹)": st.column_config.NumberColumn("Amount (₹)", min_value=0, step=500, format="₹ %,d", width="medium"),
                    "Frequency": st.column_config.SelectboxColumn(
                        "Frequency",
                        options=FREQUENCIES,
                        required=True,
                        width="small",
                    ),
                    "Lifetime / Replace (Yrs)": st.column_config.NumberColumn(
                        "Lifetime / Replace (Yrs)",
                        help="Active only for one-time frequency: purchase amount is divided by this value for annual budget impact",
                        min_value=1,
                        max_value=100,
                        step=1,
                        format="%d",
                        width="small",
                    ),
                    "Essential": st.column_config.CheckboxColumn("Essential", width="small"),
                    "Annual Inflation (%)": st.column_config.NumberColumn("Annual Inflation (%)", min_value=-99.0, max_value=100.0, step=0.5, format="%.1f%%", width="small"),
                },
                num_rows="dynamic",
                use_container_width=True,
                key="expenses_data_editor",
            )

            # Sync edits back to session state
            updated_expenses = []
            for _, row in edited_df.iterrows():
                cat = str(row["Category"]).strip()
                if not cat:
                    continue
                f = str(row["Frequency"])
                raw_repl = row.get("Lifetime / Replace (Yrs)")
                repl_val = None
                if f == "one-time":
                    try:
                        repl_val = int(raw_repl) if pd.notna(raw_repl) and int(raw_repl) >= 1 else 1
                    except (ValueError, TypeError):
                        repl_val = 1
                updated_expenses.append({
                    "category": cat,
                    "amount": int(round(float(row["Amount (₹)"]))),
                    "frequency": f,
                    "essential": bool(row["Essential"]),
                    "annual_inflation": float(row["Annual Inflation (%)"]) / 100.0,
                    "replacement_years": repl_val,
                })
            st.session_state.expenses = updated_expenses

            total = annual_expense_total(expense_objects())
            essentials = annual_expense_total(expense_objects(), essential_only=True)
            col1, col2, col3 = st.columns(3)
            col1.metric("Average annual total", fmt_inr(total))
            col2.metric("Essential annual average", fmt_inr(essentials))
            col3.metric("Monthly equivalent", fmt_inr(total / 12))
        else:
            st.info("No expenses added yet. Add entries for home or rent, healthcare, insurance, education, travel, and other needs.")
        projection_col, _, _ = st.columns(3)
        projection_years = projection_col.number_input("Show inflation impact after years", min_value=0, max_value=100, step=1, key="expense_projection_years")
        expenses = expense_objects()
        projection_table = []
        trajectory_by_category: dict[str, list[float]] = {}
        for expense in expenses:
            annual_now = expense.annual_amount()
            rate = st.session_state.general_inflation_pct / 100 if expense.annual_inflation is None else expense.annual_inflation
            trajectory = [annual_now * (1 + rate) ** year for year in range(projection_years + 1)]
            trajectory_by_category.setdefault(expense.category, [0.0] * (projection_years + 1))
            trajectory_by_category[expense.category] = [x + y for x, y in zip(trajectory_by_category[expense.category], trajectory)]
            projection_table.append({
                "Category": expense.category,
                "Frequency": "One-time / replacement average" if expense.frequency == "one-time" else expense.frequency.title(),
                "Current yearly average": fmt_inr(annual_now),
                "Annual inflation": f"{rate:.1%}",
                "Projected yearly average": fmt_inr(annual_now * (1 + rate) ** projection_years),
            })
        if projection_table:
            st.markdown(f"#### Expenses after {projection_years} years")
            st.dataframe(projection_table, hide_index=True, use_container_width=True)
            years_axis = list(range(projection_years + 1))
            projection_fig = go.Figure()
            palette = ["#7656c9", "#df8a19", "#168f78", "#da4d70", "#2483b4", "#97732c", "#5e8e3e", "#ca5c2c"]
            for index, (category_name, values) in enumerate(trajectory_by_category.items()):
                projection_fig.add_trace(go.Scatter(
                    x=years_axis, y=values, name=category_name, mode="lines+markers",
                    line={"color": palette[index % len(palette)], "width": 2},
                    hovertext=[fmt_inr(value) for value in values],
                    hovertemplate=f"{category_name}<br>Year %{{x}}<br>%{{hovertext}}<extra></extra>",
                ))
            total_trajectory = [sum(values[year] for values in trajectory_by_category.values()) for year in years_axis]
            projection_fig.add_trace(go.Scatter(
                x=years_axis, y=total_trajectory, name="Total", mode="lines+markers",
                line={"color": "#202a44", "width": 4},
                hovertext=[fmt_inr(value) for value in total_trajectory],
                hovertemplate="Total<br>Year %{x}<br>%{hovertext}<extra></extra>",
            ))
            ticks, tick_labels = chart_ticks(max(total_trajectory + [1.0]))
            projection_fig.update_layout(title="Expense growth trajectory by category", xaxis_title="Years from now", yaxis_title="Yearly average (INR)", template="plotly_white", hovermode="x unified", legend={"orientation": "h", "y": 1.15}, margin={"t": 90, "b": 40})
            projection_fig.update_yaxes(tickmode="array", tickvals=ticks, ticktext=tick_labels, rangemode="tozero")
            st.plotly_chart(projection_fig, use_container_width=True)
   
    elif page == "Investments & Retirement":
        st.subheader("Investments & Retirement")
        st.caption("Portfolio-level estimate. Set current spending and a retirement lifestyle below to compare your projected portfolio with the corpus needed to sustain it.")
        basis_col, age_col, retirement_col = st.columns(3)
        expense_basis = basis_col.selectbox(
            "Current expense basis",
            ["All categorized expenses", "Essential expenses only", "Manual monthly expenses"],
            key="investment_expense_basis",
        )
        current_age = age_col.number_input("Current age", min_value=18, max_value=100, key="current_age")
        if st.session_state.retirement_age < current_age:
            st.session_state.retirement_age = current_age
        retirement_age = retirement_col.number_input("Target retirement age", min_value=current_age, max_value=100, key="retirement_age")
        years = retirement_age - current_age
        if expense_basis == "Manual monthly expenses":
            monthly_expense_col, _, _ = st.columns(3)
            monthly_expense = rupee_input("Current monthly expenses (₹)", min_value=0, key="investment_monthly_expenses", container=monthly_expense_col)
            current_expense_items = [Expense("Current expenses", monthly_expense * 12, "yearly")]
            current_annual_expense = monthly_expense * 12
        else:
            current_expense_items, current_annual_expense = selected_expense_model()
            monthly_expense = current_annual_expense / 12
            st.write(f"Current monthly expenses from selection: **{fmt_inr(monthly_expense)}** · annual: **{fmt_inr(current_annual_expense)}**")
        lifestyle_col, inflation_col, swp_years_col = st.columns(3)
        lifestyle_pct = lifestyle_col.slider("Retirement lifestyle (%)", min_value=50, max_value=150, step=5, key="retirement_lifestyle_pct", help="100% keeps the selected lifestyle; adjust to model a simpler or higher-spend retirement.")
        inflation = inflation_input(inflation_col)
        retirement_years = swp_years_col.number_input("Years to fund retirement SWP", min_value=1, max_value=80, key="retirement_years")
        st.caption(f"Accumulation horizon: {years} years, aligned to your retirement age.")
        col1, col2, col3 = st.columns(3)
        current = rupee_input("Current investable portfolio (₹)", min_value=0, key="current_portfolio", container=col1)
        sip = rupee_input("Monthly SIP (₹)", min_value=0, key="monthly_sip", container=col2)
        lump_annual = rupee_input("Additional lump sum each year-end (₹)", min_value=0, key="annual_lump_sum", container=col3)
        return_col, pre_return_col, step_up_col = st.columns(3)
        post_return = return_col.number_input("Post-retirement return (%)", min_value=-99.0, max_value=100.0, step=0.5, key="post_retirement_return_pct") / 100
        pre_return = pre_return_col.number_input("Pre-retirement return (%)", min_value=-99.0, max_value=100.0, step=0.5, key="pre_retirement_return_pct") / 100
        step_up = step_up_col.number_input("Annual SIP step-up (%)", min_value=-99.0, max_value=100.0, step=1.0, key="annual_step_up_pct") / 100
        fee_col, exemption_col, tax_rate_col = st.columns(3)
        annual_fee_drag_pct = fee_col.number_input("Annual fee drag (pp)", min_value=0.0, max_value=100.0, step=0.1, key="annual_fee_drag_pct", help="Optional annual investment-fee estimate subtracted from returns; tax is modeled separately below.")
        annual_ltcg_exemption = rupee_input("Tax exemption (₹ per year)", min_value=0, key="annual_ltcg_exemption", container=exemption_col, help="Annual exemption applied to realized gains from SWP withdrawals, not to principal. Editable for your tax situation.")
        ltcg_tax_rate_pct = tax_rate_col.number_input("Tax rate (%)", min_value=0.0, max_value=100.0, step=0.5, key="ltcg_tax_rate_pct", help="Applied only to realized withdrawal gains above the annual exemption. Default is the Section 112A listed-equity assumption; actual rates differ by asset and tax status.")
        ltcg_tax_rate = ltcg_tax_rate_pct / 100
        investable_now = current
        scenario_col1, scenario_col2, _ = st.columns(3)
        cagr_change = scenario_col1.number_input("CAGR change", min_value=0.0, max_value=20.0, step=0.5, key="cagr_change_pct", help="Changes the pre-retirement CAGR in the comparison scenarios.") / 100
        inflation_change = scenario_col2.number_input("Inflation change", min_value=0.0, max_value=20.0, step=0.5, key="inflation_change_pct") / 100
        net_pre_return = return_after_fee_drag(pre_return, annual_fee_drag_pct)
        net_post_return = return_after_fee_drag(post_return, annual_fee_drag_pct)
        st.caption("LTCG estimate: each SWP withdrawal is split between principal and estimated gains using the portfolio cost-basis share. The exemption resets every modeled 12 months and applies only to realized gains; tax applies to gains above it. Current portfolio value is treated as invested principal because its original purchase cost is not entered. Defaults reflect the current Section 112A listed-equity exemption and rate; actual LTCG treatment varies by asset, holding period, and tax status.")
        if st.session_state.get("investment_defaults_load_error"):
            st.warning(f"Saved investment defaults could not be loaded: {st.session_state.investment_defaults_load_error}")
        if st.button("Save", type="primary", key="save_investment_defaults"):
            try:
                payload = {"assumptions": {key: st.session_state[key] for key in DEFAULT_ASSUMPTION_KEYS}}
                temp_path = DEFAULTS_PATH.with_suffix(".tmp")
                temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                temp_path.replace(DEFAULTS_PATH)
                st.success("Saved. These values will load automatically when you open Investments & Retirement.")
            except OSError as exc:
                st.error(f"Could not save defaults: {exc}")
        projected = project_portfolio(investable_now, sip, years, net_pre_return, step_up, lump_annual)
        contributed = investable_now + sip * round(years * 12) + lump_annual * int(years)
        st.metric("Projected portfolio value", fmt_inr(projected))
        st.write(f"Approximate contributions, excluding any step-up effect: {fmt_inr(contributed)}")
        st.caption(f"Accumulation uses a {net_pre_return:.2%} annual return after the manual drag. Monthly SWP sustainability uses a {net_post_return:.2%} post-retirement annual return after the same drag.")
        yearly_expenses: list[float] = []
        yearly_corpora: list[float] = []
        yearly_portfolios: list[float] = []
        yearly_principal_bases: list[float] = []
        for year in range(years + 1):
            future_expense = projected_annual_expense(current_expense_items, year, inflation) * lifestyle_pct / 100
            streams = monthly_swp_streams(current_expense_items, year, inflation, lifestyle_pct)
            portfolio_value = project_portfolio(investable_now, sip, year, net_pre_return, step_up, lump_annual)
            principal_basis = invested_principal_at_year(current, sip, year, step_up, lump_annual)
            basis_fraction = cost_basis_fraction(principal_basis, portfolio_value)
            required_corpus = required_monthly_swp_corpus(
                streams, net_post_return, retirement_years * 12,
                annual_ltcg_exemption=annual_ltcg_exemption,
                ltcg_tax_rate=ltcg_tax_rate,
                starting_cost_basis_fraction=basis_fraction,
            )
            yearly_expenses.append(future_expense)
            yearly_corpora.append(required_corpus)
            yearly_portfolios.append(portfolio_value)
            yearly_principal_bases.append(principal_basis)
        final_expense = yearly_expenses[-1]
        final_corpus = yearly_corpora[-1]
        final_portfolio = yearly_portfolios[-1]
        coverage_pct = 100.0 if final_corpus == 0 else final_portfolio / final_corpus * 100
        surplus = final_portfolio - final_corpus
        first_goal_year = next((year for year, balance, target in zip(range(years + 1), yearly_portfolios, yearly_corpora) if target == 0 or balance >= target), None)
        ready = final_corpus == 0 or final_portfolio >= final_corpus
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Current monthly expenses", fmt_inr(monthly_expense))
        m2.metric(f"Annual expenses at age {retirement_age}", fmt_inr(final_expense), delta=f"{(final_expense / (current_annual_expense * lifestyle_pct / 100) - 1):.1%} from current" if current_annual_expense else None, delta_color="inverse")
        m3.metric("Corpus needed", fmt_inr(final_corpus))
        m4.metric("Projected portfolio", fmt_inr(final_portfolio))
        st.metric("Corpus coverage at target year", f"{coverage_pct:.1f}%", delta=fmt_inr(surplus), delta_color="normal")
        if current_annual_expense == 0:
            st.warning("Enter categorized or monthly expenses to see whether the selected lifestyle can be funded.")
        elif ready:
            st.success(f"At age {retirement_age}, the projected portfolio meets or exceeds the estimated corpus for this lifestyle. First modeled year meeting the target: {first_goal_year} (age {current_age + first_goal_year if first_goal_year is not None else '—'}).")
        else:
            st.warning(f"At age {retirement_age}, the projected portfolio covers {coverage_pct:.1f}% of the estimated corpus. It is short by {fmt_inr(-surplus)} under these assumptions.")
   
        year_axis = list(range(years + 1))
        age_axis = [current_age + year for year in year_axis]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=age_axis, y=yearly_portfolios, name="Projected portfolio", mode="lines+markers",
            line={"color": "#0f9d76", "width": 3}, fill="tozeroy", fillcolor="rgba(15,157,118,0.12)",
            hovertext=[fmt_inr(value) for value in yearly_portfolios], hovertemplate="Age %{x}<br>Portfolio %{hovertext}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=age_axis, y=yearly_corpora, name="FIRE corpus needed", mode="lines+markers",
            line={"color": "#d94f70", "width": 3, "dash": "dash"},
            hovertext=[fmt_inr(value) for value in yearly_corpora], hovertemplate="Age %{x}<br>Corpus %{hovertext}<extra></extra>",
        ))
        max_balance = max(yearly_portfolios + yearly_corpora + [1.0])
        tickvals, ticktext = chart_ticks(max_balance)
        fig.update_layout(
            title="Portfolio growth vs corpus needed to keep this lifestyle",
            xaxis_title="Age", yaxis_title="INR (Indian lakh/crore scale)",
            legend={"orientation": "h", "y": 1.12}, hovermode="x unified",
            template="plotly_white", margin={"t": 70, "b": 40},
        )
        fig.update_yaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext, rangemode="tozero")
        st.plotly_chart(fig, use_container_width=True)
        expense_fig = go.Figure(go.Scatter(
            x=age_axis, y=yearly_expenses, name="Annual expenses", mode="lines+markers",
            line={"color": "#7656c9", "width": 3}, fill="tozeroy", fillcolor="rgba(118,86,201,0.13)",
            hovertext=[fmt_inr(value) for value in yearly_expenses], hovertemplate="Age %{x}<br>Annual spending %{hovertext}<extra></extra>",
        ))
        expense_ticks, expense_ticktext = chart_ticks(max(yearly_expenses + [1.0]))
        expense_fig.update_layout(title="Future annual expenses with inflation", xaxis_title="Age", yaxis_title="INR", template="plotly_white", margin={"t": 60, "b": 40})
        expense_fig.update_yaxes(tickmode="array", tickvals=expense_ticks, ticktext=expense_ticktext, rangemode="tozero")
        st.plotly_chart(expense_fig, use_container_width=True)
        st.caption(f"Uses {lifestyle_pct}% of selected spending, category inflation, a {retirement_years}-year monthly SWP, and post-retirement returns after the fee drag.")

        # --- Early Retirement Age Analysis ---
        st.markdown("### 🎯 When Can You Retire Early? (FIRE Age Calculator)")
        st.caption("Automatically analyzes every future age to show when your compounding portfolio overtakes the required corpus.")
        base_expense_tuples = [(e.annual_amount() / 12, inflation if e.annual_inflation is None else e.annual_inflation) for e in current_expense_items]
        fire_age_found, fire_age_rows = earliest_fire_age_trajectory(
            current_age=int(current_age),
            max_retirement_age=int(max(retirement_age, current_age + 30)),
            current_portfolio=investable_now,
            monthly_sip=sip,
            annual_lump_sum=lump_annual,
            annual_step_up=step_up,
            pre_return=net_pre_return,
            post_return=net_post_return,
            expense_streams_now=base_expense_tuples,
            lifestyle_pct=lifestyle_pct,
            retirement_years=int(retirement_years),
            annual_ltcg_exemption=annual_ltcg_exemption,
            ltcg_tax_rate=ltcg_tax_rate,
        )
        if fire_age_found is not None:
            years_early = retirement_age - fire_age_found
            if years_early > 0:
                st.success(f"🎉 **Earliest Possible Retirement Age: {fire_age_found}** ({years_early} years earlier than your target age {retirement_age})! At age {fire_age_found}, your projected portfolio will fully fund your retirement.")
            elif years_early == 0:
                st.success(f"✅ **You can retire right on schedule at age {fire_age_found}!** Your projected portfolio matches the required corpus at your target age.")
            else:
                st.info(f"💡 You achieve FIRE readiness at age {fire_age_found} (target age {retirement_age} was short of full corpus).")
        else:
            st.warning(f"⚠️ Based on the current SIP and return rates, the portfolio does not reach 100% corpus before age {max(retirement_age, current_age + 30)}. Consider stepping up your SIP, increasing monthly savings, or rationalizing post-retirement expenses.")

        if fire_age_rows:
            with st.expander("📊 View Age-by-Age FIRE Readiness Breakdown", expanded=False):
                fire_table = [
                    {
                        "Age": r.age,
                        "Years away": f"{r.years_to_fire} yrs",
                        "Projected portfolio": fmt_inr(r.projected_portfolio),
                        "Corpus needed": fmt_inr(r.corpus_needed),
                        "Coverage": f"{r.coverage_pct:.1f}%",
                        "Surplus / Deficit": fmt_inr(r.surplus_or_gap),
                        "Status": "✅ Ready to Retire" if r.coverage_pct >= 100 else f"⏳ Needs {fmt_inr(-r.surplus_or_gap)} more",
                    }
                    for r in fire_age_rows
                ]
                st.dataframe(fire_table, hide_index=True, use_container_width=True)

        st.markdown("### Monthly retirement withdrawal plan")
        retirement_spend = yearly_expenses[-1]
        swp_streams = monthly_swp_streams(current_expense_items, years, inflation, lifestyle_pct)
        retirement_corpus = yearly_corpora[-1]
        use_projected = st.checkbox("Use projected portfolio at retirement as SWP starting balance", value=True)
        if use_projected:
            swp_start = projected
            st.write(f"SWP starting portfolio: {fmt_inr(swp_start)}")
        else:
            swp_start = rupee_input("Manual portfolio at retirement (₹)", min_value=0, value=int(retirement_corpus), key="manual_swp_start")
        retirement_basis_fraction = cost_basis_fraction(yearly_principal_bases[-1], projected)
        swp_basis_fraction = retirement_basis_fraction
        months_to_fund = retirement_years * 12
        monthly_rows = project_monthly_swp(
            swp_start, swp_streams, net_post_return, months_to_fund,
            annual_ltcg_exemption=annual_ltcg_exemption,
            ltcg_tax_rate=ltcg_tax_rate,
            starting_cost_basis_fraction=swp_basis_fraction,
        )
        first_monthly_withdrawal = monthly_rows[0].withdrawal_required if monthly_rows else 0.0
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Monthly net spending", fmt_inr(retirement_spend / 12))
        m2.metric("Gross first monthly SWP", fmt_inr(first_monthly_withdrawal))
        m3.metric("Est. first-month tax", fmt_inr(monthly_rows[0].tax_paid if monthly_rows else 0.0))
        m4.metric("Corpus needed", fmt_inr(retirement_corpus))
        m5.metric("Portfolio coverage", f"{(100 if retirement_corpus == 0 else projected / retirement_corpus * 100):.1f}%")
        st.caption(f"Corpus estimate simulates {retirement_years} years of monthly net spending, portfolio growth, gain realization, and annual LTCG exemption. The exemption resets every 12 modeled months. Tax is user-configured and assumes realized gains qualify for LTCG treatment.")
        shortfall_month = next((row.month for row in monthly_rows if row.shortfall > 0), None)
        if shortfall_month:
            st.warning(f"The portfolio first falls short in retirement month {shortfall_month} (year {(shortfall_month - 1) // 12 + 1}).")
        else:
            st.success(f"The portfolio covers the monthly SWP through all {retirement_years} retirement years under these assumptions.")
        swp_chart = go.Figure(go.Scatter(
            x=[0] + [row.month for row in monthly_rows],
            y=[swp_start] + [row.closing_balance for row in monthly_rows],
            name="Portfolio balance", mode="lines", line={"color": "#087f8c", "width": 3},
            fill="tozeroy", fillcolor="rgba(8,127,140,0.12)",
            hovertext=[fmt_inr(value) for value in [swp_start] + [row.closing_balance for row in monthly_rows]],
            hovertemplate="Month %{x}<br>Balance %{hovertext}<extra></extra>",
        ))
        swp_ticks, swp_ticktext = chart_ticks(max([swp_start] + [row.closing_balance for row in monthly_rows] + [1.0]))
        swp_chart.update_layout(title="Monthly SWP portfolio balance", xaxis_title="Retirement month", yaxis_title="INR", template="plotly_white", margin={"t": 60, "b": 40})
        swp_chart.update_yaxes(tickmode="array", tickvals=swp_ticks, ticktext=swp_ticktext, rangemode="tozero")
        st.plotly_chart(swp_chart, use_container_width=True)
        yearly_swp_summary = []
        for retirement_year in range(1, retirement_years + 1):
            year_rows = [row for row in monthly_rows if row.year == retirement_year]
            yearly_swp_summary.append({
                "Retirement year": retirement_year,
                "Gross SWP paid": fmt_inr(sum(row.withdrawal_paid for row in year_rows)),
                "LTCG tax paid": fmt_inr(sum(row.tax_paid for row in year_rows)),
                "Ending balance": fmt_inr(year_rows[-1].closing_balance),
                "Net shortfall": fmt_inr(sum(row.shortfall for row in year_rows)),
            })
        st.dataframe(yearly_swp_summary, hide_index=True, use_container_width=True)
        with st.expander("View month-by-month SWP schedule"):
            st.dataframe([
                {"Month": row.month, "Net spend target": fmt_inr(row.net_spending_required),
                 "Gross SWP paid": fmt_inr(row.withdrawal_paid), "LTCG tax": fmt_inr(row.tax_paid),
                 "Closing balance": fmt_inr(row.closing_balance),
                 "Net shortfall": fmt_inr(row.shortfall)} for row in monthly_rows
            ], hide_index=True, use_container_width=True)
        st.session_state.latest_fire_summary = {
            "current_age": current_age, "retirement_age": retirement_age, "years_to_retirement": years,
            "annual_spending_at_retirement_inr": retirement_spend,
            "fire_corpus_inr": retirement_corpus,
            "projected_portfolio_at_retirement_inr": projected,
            "post_retirement_annual_return": net_post_return,
            "annual_ltcg_exemption_inr": annual_ltcg_exemption,
            "ltcg_tax_rate_pct": ltcg_tax_rate_pct,
            "annual_fee_drag_pct": annual_fee_drag_pct,
            "retirement_years": retirement_years,
            "first_monthly_swp_inr": first_monthly_withdrawal,
            "first_month_tax_inr": monthly_rows[0].tax_paid if monthly_rows else 0.0,
            "swp_shortfall_month": shortfall_month,
        }
        st.markdown("### Scenario comparison")
        scenario_rows = []
        for scenario_name, direction in [("Worst case", -1), ("Base case", 0), ("Best case", 1)]:
            inflation_delta = -direction * inflation_change
            scenario_expense = projected_annual_expense(current_expense_items, years, inflation, inflation_adjustment=inflation_delta) * lifestyle_pct / 100
            scenario_streams = monthly_swp_streams(current_expense_items, years, inflation, lifestyle_pct, inflation_adjustment=inflation_delta)
            scenario_pre_return = max(-0.99, pre_return + direction * cagr_change)
            scenario_net_pre = return_after_fee_drag(scenario_pre_return, annual_fee_drag_pct)
            scenario_net_post = return_after_fee_drag(post_return, annual_fee_drag_pct)
            scenario_portfolio = project_portfolio(investable_now, sip, years, scenario_net_pre, step_up, lump_annual)
            scenario_principal = invested_principal_at_year(current, sip, years, step_up, lump_annual)
            scenario_basis_fraction = cost_basis_fraction(scenario_principal, scenario_portfolio)
            scenario_corpus = required_monthly_swp_corpus(
                scenario_streams, scenario_net_post, months_to_fund,
                annual_ltcg_exemption=annual_ltcg_exemption,
                ltcg_tax_rate=ltcg_tax_rate,
                starting_cost_basis_fraction=scenario_basis_fraction,
            )
            scenario_plan = project_monthly_swp(
                scenario_portfolio, scenario_streams, scenario_net_post, months_to_fund,
                annual_ltcg_exemption=annual_ltcg_exemption,
                ltcg_tax_rate=ltcg_tax_rate,
                starting_cost_basis_fraction=scenario_basis_fraction,
            )
            scenario_rows.append({
                "Scenario": scenario_name,
                "Annual spending": fmt_inr(scenario_expense),
                "Corpus needed": fmt_inr(scenario_corpus),
                "Portfolio at retirement": fmt_inr(scenario_portfolio),
                "Surplus / shortfall": fmt_inr(scenario_portfolio - scenario_corpus),
            })
        st.dataframe(scenario_rows, hide_index=True, use_container_width=True)
        with st.expander("Historical return tools: CAGR and XIRR"):
            st.markdown("**CAGR** — for a single start value and end value over a known duration.")
            a, b, c = st.columns(3)
            start_value = rupee_input("Starting value (₹)", min_value=0, value=0, key="cagr_start", container=a)
            end_value = rupee_input("Ending value (₹)", min_value=0, value=0, key="cagr_end", container=b)
            duration = c.number_input("Elapsed years", min_value=0, value=1, step=1, key="cagr_years")
            if st.button("Calculate CAGR"):
                try:
                    st.success(f"CAGR: {cagr(start_value, end_value, duration):.2%}")
                except ValueError as exc:
                    st.error(str(exc))
            st.markdown("**XIRR** — for dated deposits and proceeds. Enter each investment as a negative amount and final/partial proceeds as positive amounts.")
            flow_col, flow_amount_col = st.columns([1, 2])
            flow_date = flow_col.date_input("Cash-flow date", value=date.today(), key="xirr_flow_date")
            flow_amount = rupee_input("Cash flow (₹; investment negative, proceeds positive)", key="xirr_flow_amount", container=flow_amount_col)
            if st.button("Add cash flow", key="add_xirr_flow"):
                st.session_state.cash_flows.append((flow_date, flow_amount))
                st.session_state.xirr_flow_amount = 0
                st.session_state.xirr_flow_amount__indian_display = "0"
                st.rerun()
            if st.session_state.cash_flows:
                st.dataframe([{"Date": d, "Cash flow": fmt_inr(amount)} for d, amount in st.session_state.cash_flows], hide_index=True)
                if st.button("Calculate XIRR"):
                    try:
                        st.success(f"XIRR: {xirr(st.session_state.cash_flows):.2%}")
                    except ValueError as exc:
                        st.error(str(exc))
                if st.button("Clear cash flows"):
                    st.session_state.cash_flows.clear()
                    st.rerun()

    elif page == "Wealth Multiplier":
        st.subheader("🚀 Wealth Multiplier — Lump Sum vs SIP Analysis")
        st.caption(
            "Understand the true power of compounding in India. Compare how ₹1 lump sum grows versus ₹1/month SIP, "
            "and see how stopping SIP after N years and leaving the corpus to compound to Year 25 multiplies your wealth."
        )

        wm_col1, wm_col2, wm_col3 = st.columns([1.5, 1.5, 2])
        multiplier_cagr = wm_col1.number_input(
            "Assumed Annual CAGR (%)",
            min_value=1.0,
            max_value=30.0,
            value=12.0,
            step=0.5,
            key="wm_cagr_input",
            help="Expected long-term equity or portfolio CAGR. 12% is widely considered the historical benchmark for Indian equity indices (Nifty 50 / Sensex).",
        )
        multiplier_target_year = wm_col2.number_input(
            "Terminal Comparison Year",
            min_value=10,
            max_value=50,
            value=25,
            step=1,
            key="wm_target_year_input",
            help="The benchmark year for the 'SIP → Lump Sum' column (default: 25 years).",
        )
        wm_col3.info("💡 **Formula insight**: Column 4 demonstrates that building a solid corpus in your 20s/30s and letting it compound without new additions can yield massive returns by retirement.")

        periods_to_show = [5, 8, 10, 12, 15, 18, 20, 22, 24, int(multiplier_target_year)]
        # Filter duplicates and sort
        periods_to_show = sorted(list(set(periods_to_show)))
        rows = wealth_multiplier_table(multiplier_cagr, periods_to_show, target_year=int(multiplier_target_year))

        # Display table formatted cleanly
        table_display = [
            {
                "Period": r["Period"],
                "Lump Sum": r["Lump Sum"],
                "SIP": r["SIP"],
                "Lump Sum ÷ SIP": r["Lump Sum ÷ SIP"],
                f"SIP → Lump Sum to Year {int(multiplier_target_year)}": r[f"SIP → Lump Sum to Year {int(multiplier_target_year)}"],
            }
            for r in rows
        ]
        st.dataframe(table_display, hide_index=True, use_container_width=True)

        # Multiplier bar/line chart
        wm_fig = go.Figure()
        periods_num = [r["_period_years"] for r in rows]
        lump_vals = [r["_lump_num"] for r in rows]
        sip_vals = [r["_sip_num"] for r in rows]
        sip_to_lump_vals = [r["_sip_to_lump_num"] for r in rows]

        wm_fig.add_trace(go.Bar(
            x=[f"{p} yrs" for p in periods_num],
            y=lump_vals,
            name="Lump Sum Multiplier",
            marker_color="#10b981",
        ))
        wm_fig.add_trace(go.Bar(
            x=[f"{p} yrs" for p in periods_num],
            y=sip_vals,
            name="SIP Multiplier",
            marker_color="#6366f1",
        ))
        wm_fig.add_trace(go.Scatter(
            x=[f"{p} yrs" for p in periods_num],
            y=sip_to_lump_vals,
            name=f"SIP → Lump Sum to Year {int(multiplier_target_year)}",
            mode="lines+markers",
            line={"color": "#f59e0b", "width": 3},
            yaxis="y",
        ))
        wm_fig.update_layout(
            title=f"Wealth Multiplier Comparison at {multiplier_cagr:.1f}% CAGR",
            xaxis_title="Investment Horizon",
            yaxis_title="Multiplier (×)",
            barmode="group",
            template="plotly_white",
            legend={"orientation": "h", "y": 1.15},
            margin={"t": 70, "b": 40},
        )
        st.plotly_chart(wm_fig, use_container_width=True)

        with st.expander("📖 How to read this table"):
            st.markdown(
                f"""
                - **Lump Sum**: If you invest ₹1,00,000 today at **{multiplier_cagr:.1f}% CAGR**, it multiplies by this factor. (e.g. after 25 years, ₹1 Lakh becomes ₹{rows[-1]['_lump_num']:.2f} Lakhs).
                - **SIP**: If you invest ₹10,000 every month for *N* years, your total invested capital grows by this factor.
                - **Lump Sum ÷ SIP**: Shows that lumpsum money deployed right at the beginning enjoys more compounding time than money drip-fed via SIP.
                - **SIP → Lump Sum to Year {int(multiplier_target_year)}**: The "Early Retirement / Coast FIRE" superpower. If you do an SIP for just 5 years, then **stop contributing entirely** and let the money sit for the remaining 20 years, your total invested money will multiply by **{rows[0]['_sip_to_lump_num']:.2f}×** by Year {int(multiplier_target_year)}!
                """
            )

    elif page == "Loans & EMI":
        st.subheader("🏦 Loans & EMI Calculator (Home, Car, Personal, Education)")
        st.caption("Calculate monthly EMIs, complete amortization schedules, prepayment savings, and tax deductions (Section 24b & 80C).")

        emi_t1, emi_t2, emi_t3 = st.tabs(["🧮 EMI Calculator & Schedule", "⚡ Prepayment & Interest Savings", "🏛️ Tax Deductions (Home Loan)"])

        with emi_t1:
            col_l1, col_l2, col_l3 = st.columns(3)
            loan_type = col_l1.selectbox(
                "Loan Type",
                ["Home Loan (Typical 8.5%)", "Car Loan (Typical 9.0%)", "Education Loan (Typical 10.5%)", "Personal / Gold Loan (Typical 11.5%)", "Custom"],
                key="loan_preset_type",
            )
            preset_rates = {
                "Home Loan (Typical 8.5%)": (5000000, 8.5, 20),
                "Car Loan (Typical 9.0%)": (1200000, 9.0, 5),
                "Education Loan (Typical 10.5%)": (2500000, 10.5, 10),
                "Personal / Gold Loan (Typical 11.5%)": (500000, 11.5, 3),
                "Custom": (3000000, 8.5, 15),
            }
            default_p, default_r, default_y = preset_rates[loan_type]

            loan_principal = rupee_input("Loan Amount (₹)", key="emi_loan_principal", value=default_p, min_value=1000, container=col_l1)
            loan_rate_annual = col_l2.number_input("Interest Rate (% per annum)", min_value=0.1, max_value=35.0, value=float(default_r), step=0.1, key="emi_loan_rate")
            loan_tenure_years = col_l3.number_input("Tenure (Years)", min_value=1, max_value=40, value=int(default_y), step=1, key="emi_loan_years")
            total_loan_months = int(loan_tenure_years * 12)

            calculated_emi = emi_payment(loan_principal, loan_rate_annual / 100, total_loan_months)
            full_sched = emi_schedule(loan_principal, loan_rate_annual / 100, total_loan_months)
            total_interest = sum(r.interest for r in full_sched)
            total_payable = loan_principal + total_interest

            ec1, ec2, ec3, ec4 = st.columns(4)
            ec1.metric("Monthly EMI", fmt_inr(calculated_emi))
            ec2.metric("Principal Amount", fmt_inr(loan_principal))
            ec3.metric("Total Interest", fmt_inr(total_interest))
            ec4.metric("Total Amount Payable", fmt_inr(total_payable))

            # Visual breakdown: Principal vs Interest
            emi_pie_col, emi_bar_col = st.columns([1, 2])
            with emi_pie_col:
                pie_fig = go.Figure(data=[go.Pie(
                    labels=["Principal", "Total Interest"],
                    values=[loan_principal, total_interest],
                    hole=0.45,
                    marker_colors=["#10b981", "#ef4444"],
                )])
                pie_fig.update_layout(title="Payment Breakdown", margin={"t": 40, "b": 20, "l": 20, "r": 20}, height=300)
                st.plotly_chart(pie_fig, use_container_width=True)

            with emi_bar_col:
                # Group schedule by year
                yearly_amort = []
                for yr in range(1, int(loan_tenure_years) + 1):
                    yr_rows = [r for r in full_sched if (r.month - 1) // 12 + 1 == yr]
                    if yr_rows:
                        yr_p = sum(r.principal for r in yr_rows)
                        yr_i = sum(r.interest for r in yr_rows)
                        yr_close = yr_rows[-1].closing_balance
                        yearly_amort.append({"Year": yr, "Principal": yr_p, "Interest": yr_i, "Balance": yr_close})

                bar_fig = go.Figure()
                bar_fig.add_trace(go.Bar(
                    x=[f"Yr {y['Year']}" for y in yearly_amort],
                    y=[y["Principal"] for y in yearly_amort],
                    name="Principal Repaid",
                    marker_color="#10b981",
                ))
                bar_fig.add_trace(go.Bar(
                    x=[f"Yr {y['Year']}" for y in yearly_amort],
                    y=[y["Interest"] for y in yearly_amort],
                    name="Interest Paid",
                    marker_color="#ef4444",
                ))
                bar_fig.update_layout(
                    title="Annual Principal vs Interest Repayment",
                    barmode="stack",
                    template="plotly_white",
                    margin={"t": 40, "b": 20},
                    height=300,
                    legend={"orientation": "h", "y": 1.15},
                )
                st.plotly_chart(bar_fig, use_container_width=True)

            with st.expander("📋 View Year-by-Year Amortization Schedule", expanded=False):
                amort_display = [
                    {
                        "Year": y["Year"],
                        "Annual Principal (₹)": fmt_inr(y["Principal"]),
                        "Annual Interest (₹)": fmt_inr(y["Interest"]),
                        "Total Paid in Year (₹)": fmt_inr(y["Principal"] + y["Interest"]),
                        "Ending Balance (₹)": fmt_inr(y["Balance"]),
                    }
                    for y in yearly_amort
                ]
                st.dataframe(amort_display, hide_index=True, use_container_width=True)

        with emi_t2:
            st.markdown("#### ⚡ Lump-Sum Prepayment Simulator")
            st.caption("See how much interest you can save and how many months you can knock off your loan by paying a lump-sum amount early.")
            prep_col1, prep_col2, prep_col3 = st.columns(3)
            prepay_amount = rupee_input("Prepayment Amount (₹)", min_value=10000, value=200000, key="emi_prepay_amount", container=prep_col1)
            prepay_month = prep_col2.number_input("Make prepayment after Month", min_value=1, max_value=max(1, total_loan_months - 1), value=min(12, total_loan_months), step=1, key="emi_prepay_month")
            prepay_mode = prep_col3.radio("Prepayment Goal", ["Reduce Tenure (Keep EMI Same - Recommended)", "Reduce EMI (Keep Tenure Same)"], key="emi_prepay_mode")
            reduce_emi_flag = (prepay_mode == "Reduce EMI (Keep Tenure Same)")

            prep_res = prepayment_savings(
                principal=loan_principal,
                annual_rate=loan_rate_annual / 100,
                original_months=total_loan_months,
                prepayment_amount=prepay_amount,
                at_month=int(prepay_month),
                reduce_emi=reduce_emi_flag,
            )

            p_m1, p_m2, p_m3 = st.columns(3)
            p_m1.metric("Total Interest Saved", fmt_inr(prep_res["interest_saved"]))
            if not reduce_emi_flag:
                p_m2.metric("Tenure Reduced By", f"{prep_res['months_saved']} months ({prep_res['months_saved'] / 12:.1f} yrs)")
                p_m3.metric("New Payoff Timeline", f"{prep_res['new_tenure_months']} months")
            else:
                p_m2.metric("New Reduced Monthly EMI", fmt_inr(prep_res["new_emi"]))
                p_m3.metric("Monthly EMI Saved", fmt_inr(calculated_emi - prep_res["new_emi"]))

            st.success(
                f"💡 By prepaying **{fmt_inr(prepay_amount)}** at Month {prepay_month}, you save a whopping "
                f"**{fmt_inr(prep_res['interest_saved'])}** in total interest!"
            )

        with emi_t3:
            st.markdown("#### 🏛️ Indian Income Tax Deductions on Home Loan")
            st.caption("Compare how much tax you save under the Old Tax Regime vs New Tax Regime.")
            tax_col1, tax_col2 = st.columns(2)
            est_gross_income = rupee_input("Annual Gross Income (₹)", min_value=0, value=1500000, key="emi_tax_gross_income", container=tax_col1)
            regime_choice = tax_col2.selectbox("Tax Regime", ["Old Tax Regime (with 80C & 24b deductions)", "New Tax Regime (default AY2024-25 onwards)"], key="emi_tax_regime_select")
            regime_str = "old" if "Old" in regime_choice else "new"

            # Use Year 1 interest and principal from schedule as benchmark
            y1_interest = yearly_amort[0]["Interest"] if yearly_amort else 0.0
            y1_principal = yearly_amort[0]["Principal"] if yearly_amort else 0.0

            tax_res = home_loan_tax_benefit(y1_interest, y1_principal, est_gross_income, regime=regime_str)

            tb1, tb2, tb3 = st.columns(3)
            tb1.metric("Section 24(b) Interest Deduction", fmt_inr(tax_res["section_24b_deduction"]), help="Up to ₹2,00,000 for self-occupied property")
            tb2.metric("Section 80C Principal Deduction", fmt_inr(tax_res["section_80c_deduction"]), help="Up to ₹1,50,000 (shared limit)")
            tb3.metric("Estimated Tax Saved", fmt_inr(tax_res["estimated_tax_saved"]))

            st.info(f"📌 {tax_res['note']}")
   
    elif page == "Goals":
        st.subheader("Future goals")
        st.write("Track multiple goals with independent target dates, inflation assumptions, and monthly savings estimates.")
        goal_categories = ["Education", "Car / transport", "Travel", "Gold / jewellery", "Electronics", "Home upgrade", "Medical", "Other"]
        col1, col2, col3 = st.columns(3)
        goal_name = col1.text_input("Goal name", placeholder="For example, college fees", key="goal_name_input")
        goal_category = col2.selectbox("Goal category", goal_categories, key="goal_category_input")
        beneficiary = col3.text_input("For whom (optional)", placeholder="Child / household", key="goal_beneficiary_input")
        col1, col2, col3 = st.columns(3)
        goal_cost = rupee_input("Cost in today's rupees (₹)", min_value=0, key="goal_cost_input", container=col1)
        goal_years = col2.number_input("Years until goal", min_value=0, max_value=100, value=10, step=1, key="goal_years_input")
        goal_inflation = col3.number_input("Goal inflation assumption (%)", min_value=-99.0, max_value=100.0, value=6.0, step=0.5, key="goal_inflation_input_pct") / 100
        goal_return_col, _, _ = st.columns(3)
        goal_return = goal_return_col.number_input("Return on savings toward goal (%)", min_value=-99.0, max_value=100.0, value=6.0, step=0.5, key="goal_return_input_pct") / 100
        st.button("Add goal", type="primary", on_click=add_goal_callback)
        if st.session_state.get("goal_form_error"):
            st.error(st.session_state.goal_form_error)

        with st.expander("🇮🇳 Add Goal from Indian Milestones (Education, Wedding, Gold, Real Estate)", expanded=False):
            st.caption("Select a milestone with realistic present-day costs and typical Indian inflation assumptions:")
            active_goal_presets = get_indian_goal_presets()
            goal_preset_names = [p["name"] for p in active_goal_presets]
            selected_preset_name = st.selectbox("Select Goal Template", goal_preset_names, key="preset_goal_select")
            chosen_goal_preset = next(p for p in active_goal_presets if p["name"] == selected_preset_name)
            st.write(f"ℹ️ {chosen_goal_preset.get('description', '')}")
            st.caption(f"Cost: {fmt_inr(chosen_goal_preset['cost'])} · Timeline: {chosen_goal_preset['years']} yrs · Inflation: {chosen_goal_preset['inflation']:.1%}")
            if st.button("Add This Goal to My Plan", type="secondary"):
                st.session_state.goals.append({
                    "name": chosen_goal_preset["name"],
                    "category": chosen_goal_preset["category"],
                    "beneficiary": chosen_goal_preset["beneficiary"],
                    "cost": chosen_goal_preset["cost"],
                    "years": chosen_goal_preset["years"],
                    "inflation": chosen_goal_preset["inflation"],
                    "return": chosen_goal_preset["return"],
                })
                st.success(f"Added '{chosen_goal_preset['name']}' to goals!")
                st.rerun()

        if st.session_state.goals:
            for index, goal in enumerate(st.session_state.goals):
                future_cost = goal_future_cost(goal["cost"], goal["years"], goal["inflation"])
                try:
                    monthly_needed = monthly_sip_for_target(future_cost, goal["years"], goal["return"])
                    monthly_text = fmt_inr(monthly_needed)
                except ValueError:
                    monthly_text = "Set a future date"
                cols = st.columns([1.5, 1, 1, 1, 1, 0.7])
                cols[0].write(f"**{goal['name']}**\n\n{goal['category']}" + (f" · {goal['beneficiary']}" if goal["beneficiary"] else ""))
                cols[1].write(f"Target in {goal['years']:g} years")
                cols[2].write(f"Future cost\n\n{fmt_inr(future_cost)}")
                cols[3].write(f"Inflation\n\n{goal['inflation']:.1%}")
                cols[4].write(f"Monthly SIP from zero\n\n{monthly_text}")
                if cols[5].button("Remove", key=f"remove_goal_{index}"):
                    st.session_state.goals.pop(index)
                    st.rerun()
        else:
            st.info("No goals added yet.")
        save_goal_col, reload_goal_col = st.columns(2)
        if save_goal_col.button("Save goals permanently", type="primary"):
            try:
                save_goals(st.session_state.goals)
                st.success(f"Saved {len(st.session_state.goals)} goals to the local SQLite database.")
            except (OSError, sqlite3.Error) as exc:
                st.error(f"Could not save goals: {exc}")
        if reload_goal_col.button("Reload saved goals"):
            try:
                st.session_state.goals = load_goals()
                st.rerun()
            except (OSError, sqlite3.Error, ValueError) as exc:
                st.error(f"Could not reload saved goals: {exc}")
   
# -------------------------------------------------------------
# FLOATING DOCKED ASSISTANT WIDGET (Exact Ask ILA layout)
# -------------------------------------------------------------
if st.session_state.get("assistant_open", True):
    is_min = st.session_state.get("assistant_minimized", True)
    is_max = st.session_state.get("assistant_maximized", False)

    # Size based on Ask ILA docking state
    if is_min:
        win_width = "300px"
        win_height = "52px"
    elif is_max:
        win_width = "min(920px, 94vw)"
        win_height = "90vh"
    else:
        # Standard open chat window matching Ask ILA screenshot
        win_width = "390px"
        win_height = "640px"

    chat_scope = "Overall" if st.session_state.assistant_mode == "Overall" else page

    st.markdown(
        f"""
        <div id="floating-assistant-anchor"></div>
        <style>
          div[data-testid="stVerticalBlock"]:has(> div#floating-assistant-anchor) {{
            width: {win_width} !important;
            height: {win_height} !important;
            max-height: 94vh !important;
            display: flex !important;
            flex-direction: column !important;
            padding: 0 !important;
            margin: 0 !important;
          }}
          div[data-testid="stVerticalBlock"]:has(> div#floating-assistant-anchor) > div:first-child {{
            display: none !important;
          }}
          .ila-brand-banner {{
            background: #0072ce;
            color: #ffffff;
            padding: 10px 14px;
            font-weight: 800;
            font-size: 1.15rem;
            letter-spacing: 0.04em;
            display: flex;
            align-items: center;
            justify-content: space-between;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        # Header Bar matching SBI Card Ask ILA
        if is_min:
            min_col1, min_col2 = st.columns([4.2, 1.8])
            with min_col1:
                st.markdown(
                    f"<div style='font-size:14px;font-weight:800;color:#0072ce;display:flex;align-items:center;gap:6px;padding-top:3px;'>"
                    f"<span style='background:#0072ce;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:900;'>ASK</span>"
                    f"<span style='letter-spacing:0.03em;'>ILA</span>"
                    f"<span style='font-size:11px;font-weight:600;color:#64748b;'>· {chat_scope}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with min_col2:
                st.button("💬 Chat", key="btn_open_docked_chat", help="Open Ask ILA Assistant", on_click=toggle_minimize_assistant, use_container_width=True)
        else:
            h_col1, h_col2, h_col3, h_col4 = st.columns([5.2, 1.2, 1.2, 1.2])
            with h_col1:
                st.markdown(
                    f"<div style='font-size:15px;font-weight:800;color:#0072ce;display:flex;align-items:center;gap:6px;padding-top:4px;'>"
                    f"<span style='background:#0072ce;color:#fff;padding:2px 7px;border-radius:4px;font-size:12px;font-weight:900;'>ASK</span>"
                    f"<span style='letter-spacing:0.02em;'>FIRE ILA</span>"
                    f"<span style='font-size:11px;font-weight:600;background:rgba(0,114,206,0.12);color:#0072ce;padding:2px 6px;border-radius:10px;'>{chat_scope}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with h_col2:
                st.button(
                    "🗕",
                    key="btn_win_minimize",
                    help="Minimize to bottom-right dock",
                    on_click=toggle_minimize_assistant,
                )
            with h_col3:
                st.button(
                    "⛶" if not is_max else "🗗",
                    key="btn_win_maximize",
                    help="Maximize / Restore size",
                    on_click=toggle_maximize_assistant,
                )
            with h_col4:
                st.button(
                    "✕",
                    key="btn_win_close",
                    help="Close / Dock Assistant",
                    on_click=close_assistant,
                )

        # Full Chat Body (only rendered when expanded)
        if not is_min:
            # Model selection row
            p_c1, p_c2 = st.columns([1, 1.5])
            with p_c1:
                provider = st.selectbox("Provider", ["Gemini", "OpenRouter", "OpenCode"], key="shared_chat_provider", label_visibility="collapsed")
            model_options, model_default = provider_models(provider)
            if provider == "Gemini":
                api_key = os.getenv("GEMINI_API_KEY") or ""
                secret_name = "GEMINI_API_KEY"
                model_help = "Choose a Gemini model ID. Update DEFAULT_MODELS or GEMINI_MODELS in .env."
                provider_base_url = None
            elif provider == "OpenRouter":
                api_key = os.getenv("OPENROUTER_API_KEY") or ""
                secret_name = "OPENROUTER_API_KEY"
                model_help = "Choose an OpenRouter model slug. Update DEFAULT_MODELS or OPENROUTER_MODELS in .env."
                provider_base_url = None
            else:
                api_key = os.getenv("OPENCODE_API_KEY") or ""
                secret_name = "OPENCODE_API_KEY"
                model_help = "Choose an OpenCode model ID. Update DEFAULT_MODELS or OPENCODE_MODELS in .env."
                provider_base_url = os.getenv("OPENCODE_BASE_URL") or "https://opencode.ai/inference/openai/v1"
            with p_c2:
                model_name = st.selectbox(
                    "Model", model_options, index=model_options.index(model_default),
                    help=model_help, key=f"shared_chat_model_{provider}",
                    label_visibility="collapsed",
                )

            chat_key = f"chat_history_{chat_scope}"
            if chat_key not in st.session_state:
                st.session_state[chat_key] = []
            history_for_chat = st.session_state[chat_key]

            # Chat messages area
            chat_container_height = 420 if is_max else 310
            pending_query = None
            with st.container(height=chat_container_height, border=True):
                if not history_for_chat:
                    st.markdown(
                        f"""
                        <div style='background:linear-gradient(135deg, #0072ce 0%, #38bdf8 100%);padding:14px;border-radius:12px;color:white;margin-bottom:12px;text-align:center;'>
                          <div style='font-size:1.6rem;'>👩‍💼 <b>ASK FIRE ILA</b></div>
                          <div style='font-size:0.85rem;margin-top:4px;opacity:0.95;'>Hello! I am ILA, your Indian FIRE & Financial Planning Live Assistant.</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    # Quick Suggestion Pills (matching Ask ILA image buttons)
                    st.caption("Quick actions:")
                    q_col1, q_col2 = st.columns(2)
                    if q_col1.button("🎯 Earliest Retirement Age?", key="quick_q1", use_container_width=True):
                        pending_query = "What is my earliest retirement age and how much corpus do I need?"
                    if q_col2.button("🏦 Loan Prepayment Impact?", key="quick_q2", use_container_width=True):
                        pending_query = "How much interest can I save by prepaying my loan early?"
                    q_col3, q_col4 = st.columns(2)
                    if q_col3.button("📈 Wealth Multiplier at 12%?", key="quick_q3", use_container_width=True):
                        pending_query = "Explain the wealth multiplier difference between Lump Sum and SIP over 25 years."
                    if q_col4.button("🧾 Essential vs Full Spend?", key="quick_q4", use_container_width=True):
                        pending_query = "What is the difference between my essential and discretionary expenses for Lean FIRE?"

                for message in history_for_chat:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

            prompt = st.chat_input("Type your query here…", key=f"chat_input_{chat_scope}")
            active_prompt = prompt or pending_query

            # Check if there is an unresponded user message in history
            if not active_prompt and history_for_chat and history_for_chat[-1].get("role") == "user":
                active_prompt = history_for_chat[-1].get("content")

            if active_prompt:
                # Add user message if not already recorded
                if not (history_for_chat and history_for_chat[-1].get("role") == "user" and history_for_chat[-1].get("content") == active_prompt):
                    history_for_chat.append({"role": "user", "content": active_prompt})

                expense_rows = expense_objects()
                annual_spend = annual_expense_total(expense_rows)
                spending_data = {
                    "expenses": [expense.__dict__ for expense in expense_rows],
                    "annual_spending_inr": annual_spend,
                    "monthly_spending_inr": annual_spend / 12,
                    "expense_projection_years": st.session_state.expense_projection_years,
                }
                investment_data = {
                    "assumptions": {key: st.session_state.get(key) for key in ["current_age", "retirement_age", "current_portfolio", "monthly_sip", "annual_lump_sum", "annual_step_up_pct", "pre_retirement_return_pct", "post_retirement_return_pct", "annual_fee_drag_pct", "general_inflation_pct", "retirement_lifestyle_pct", "retirement_years", "annual_ltcg_exemption", "ltcg_tax_rate_pct"]},
                    "expense_basis": st.session_state.investment_expense_basis,
                    "latest_fire_calculation": st.session_state.get("latest_fire_summary"),
                }
                goals_data = []
                for goal in st.session_state.goals:
                    future_cost = goal_future_cost(goal["cost"], goal["years"], goal["inflation"])
                    try:
                        goal_monthly = monthly_sip_for_target(future_cost, goal["years"], goal["return"])
                    except ValueError:
                        goal_monthly = None
                    goals_data.append({**goal, "future_cost_inr": future_cost, "monthly_sip_inr": goal_monthly})
                all_context = {"spending": spending_data, "investments": investment_data, "goals": {"goals": goals_data}}
                if chat_scope == "Overall":
                    section_prompt = "Compare spending, investment and retirement projections, and future goals. Identify relationships, trade-offs, gaps and useful sensitivity questions. Use context tools to retrieve relevant saved values from all sections before drawing conclusions."
                    section_data = all_context
                elif page == "Spending":
                    section_prompt = "Explain current and projected category expenses, frequency, category inflation and practical spending scenarios."
                    section_data = spending_data
                elif page == "Goals":
                    section_prompt = "Discuss saved goals, future costs, timeline, goal inflation and monthly savings estimates."
                    section_data = all_context["goals"]
                else:
                    section_prompt = "Discuss FIRE corpus coverage, portfolio projection, monthly SWP and assumptions."
                    section_data = investment_data
                context = json.dumps({"section": chat_scope, "section_prompt_template": section_prompt, "data": section_data, "disclaimer": "Planning estimates and user-entered assumptions."}, indent=2, default=str)

                if not api_key:
                    err_msg = f"⚠️ Set `{secret_name}` in the .env file before sending questions to {provider}."
                    history_for_chat.append({"role": "assistant", "content": err_msg})
                elif not model_name.strip():
                    history_for_chat.append({"role": "assistant", "content": "⚠️ Please select a model name."})
                else:
                    try:
                        available_tools_context = all_context if chat_scope == "Overall" else {
                            "Spending": {"spending": spending_data},
                            "Investments & Retirement": {"investments": investment_data},
                            "Goals": {"goals": all_context["goals"]},
                        }.get(page, all_context)
                        graph = get_cached_assistant_graph(
                            provider, model_name, api_key,
                            base_url=provider_base_url,
                        )
                        prior_history = [m for m in history_for_chat if m != history_for_chat[-1]]
                        with st.spinner(f"Waiting for {provider} ({model_name})…"):
                            result = graph.invoke({
                                "history": prior_history,
                                "question": active_prompt,
                                "context": context,
                                "answer": "",
                                "messages": [],
                            })
                        ans_text = result.get("answer") or ""
                        if not ans_text and result.get("messages"):
                            last_msg = result["messages"][-1]
                            ans_text = str(getattr(last_msg, "content", ""))
                        if not ans_text:
                            ans_text = "I have reviewed your financial plan. Feel free to ask any question about your corpus or expenses."
                        history_for_chat.append({"role": "assistant", "content": ans_text})
                    except Exception as exc:
                        detail = str(exc).strip() or type(exc).__name__
                        err_msg = (
                            f"⚠️ **{provider} Error ({model_name})**: {detail}\n\n"
                            f"*Tip: You can switch provider to OpenRouter or choose another model above.*"
                        )
                        history_for_chat.append({"role": "assistant", "content": err_msg})
                st.rerun()

            f_c1, f_c2 = st.columns(2)
            with f_c1:
                if st.button("Clear conversation", key=f"clear_chat_{chat_scope}", use_container_width=True):
                    st.session_state[chat_key] = []
                    st.rerun()
