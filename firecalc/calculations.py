"""Deterministic, currency-agnostic FIRE planning calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class Expense:
    category: str
    amount: float
    frequency: str
    essential: bool = True
    annual_inflation: float | None = None
    replacement_years: int | None = None

    def annual_amount(self) -> float:
        """Return annual spending; one-time purchases are averaged over replacement life."""
        if self.amount < 0:
            raise ValueError("Expense amount cannot be negative")
        multipliers = {
            "weekly": 52.0,
            "monthly": 12.0,
            "quarterly": 4.0,
            "yearly": 1.0,
            "one-time": None,
        }
        try:
            multiplier = multipliers[self.frequency]
        except KeyError as exc:
            raise ValueError(f"Unsupported expense frequency: {self.frequency}") from exc
        if self.frequency == "one-time":
            if self.replacement_years is None or self.replacement_years < 1:
                raise ValueError("One-time purchases need a replacement interval of at least one year")
            return self.amount / self.replacement_years
        return self.amount * multiplier


@dataclass(frozen=True)
class SwpYear:
    year: int
    opening_balance: float
    withdrawal: float
    investment_growth: float
    closing_balance: float
    shortfall: float


@dataclass(frozen=True)
class SwpMonth:
    month: int
    year: int
    opening_balance: float
    withdrawal_required: float
    withdrawal_paid: float
    investment_growth: float
    closing_balance: float
    shortfall: float
    realized_gain: float
    tax_paid: float
    net_withdrawal_paid: float
    net_spending_required: float


def annual_expense_total(expenses: Iterable[Expense], essential_only: bool = False) -> float:
    return sum(
        expense.annual_amount()
        for expense in expenses
        if not essential_only or expense.essential
    )


def projected_annual_expense(
    expenses: Iterable[Expense], years: float, general_inflation: float, essential_only: bool = False,
    inflation_adjustment: float = 0.0,
) -> float:
    """Project recurring categories separately; each may override general inflation."""
    _validate_nonnegative("years", years)
    _validate_rate("general inflation", general_inflation, lower_bound=-1.0)
    total = 0.0
    for expense in expenses:
        if essential_only and not expense.essential:
            continue
        rate = general_inflation if expense.annual_inflation is None else expense.annual_inflation
        rate = max(-1.0, rate + inflation_adjustment)
        _validate_rate(f"{expense.category} inflation", rate, lower_bound=-1.0)
        total += expense.annual_amount() * (1 + rate) ** years
    return total


def future_value_lump_sum(principal: float, annual_return: float, years: float) -> float:
    _validate_nonnegative("principal", principal)
    _validate_rate("annual return", annual_return, lower_bound=-1.0)
    _validate_nonnegative("years", years)
    if annual_return == -1 and years > 0:
        return 0.0
    return principal * (1 + annual_return) ** years


def future_value_monthly_sip(
    monthly_contribution: float,
    annual_return: float,
    years: float,
    annual_step_up: float = 0.0,
) -> float:
    """FV of month-end contributions, with step-up applied each 12 months."""
    _validate_nonnegative("monthly contribution", monthly_contribution)
    _validate_rate("annual return", annual_return, lower_bound=-1.0)
    _validate_nonnegative("years", years)
    _validate_rate("annual step-up", annual_step_up, lower_bound=-1.0)
    months = round(years * 12)
    monthly_rate = (1 + annual_return) ** (1 / 12) - 1 if annual_return > -1 else -1
    balance = 0.0
    contribution = monthly_contribution
    for month in range(1, months + 1):
        balance *= 1 + monthly_rate
        balance += contribution
        if month % 12 == 0:
            contribution *= 1 + annual_step_up
    return balance


def project_portfolio(
    current_balance: float,
    monthly_sip: float,
    years: float,
    annual_return: float,
    annual_step_up: float = 0.0,
    annual_lump_sum: float = 0.0,
) -> float:
    _validate_nonnegative("current balance", current_balance)
    _validate_nonnegative("annual lump sum", annual_lump_sum)
    years_whole = int(years)
    fraction = years - years_whole
    balance = current_balance
    for year in range(years_whole):
        balance = future_value_lump_sum(balance, annual_return, 1)
        balance += annual_lump_sum
    if fraction:
        balance = future_value_lump_sum(balance, annual_return, fraction)
    sip = future_value_monthly_sip(monthly_sip, annual_return, years, annual_step_up)
    return balance + sip


def cagr(start_value: float, end_value: float, years: float) -> float:
    _validate_nonnegative("start value", start_value)
    _validate_nonnegative("end value", end_value)
    _validate_nonnegative("years", years)
    if start_value == 0 or years == 0:
        raise ValueError("CAGR requires a positive starting value and non-zero duration")
    if end_value == 0:
        return -1.0
    return (end_value / start_value) ** (1 / years) - 1


def xirr(cash_flows: Iterable[tuple[date, float]]) -> float:
    """Estimate annualized return for dated cash flows using a bracketed solve."""
    flows = sorted(cash_flows, key=lambda item: item[0])
    if len(flows) < 2:
        raise ValueError("XIRR needs at least two dated cash flows")
    if not any(amount < 0 for _, amount in flows) or not any(amount > 0 for _, amount in flows):
        raise ValueError("XIRR needs both investments (negative) and proceeds (positive)")
    start = flows[0][0]
    years = [(day - start).days / 365.0 for day, _ in flows]
    if years[-1] <= 0:
        raise ValueError("XIRR cash flows must span at least one day")

    def npv(rate: float) -> float:
        if rate <= -1:
            return float("inf")
        return sum(amount / (1 + rate) ** year for year, (_, amount) in zip(years, flows))

    # Scan for a sign-changing interval, then bisect; this avoids an unbounded Newton step.
    grid = [-0.9999, -0.99, -0.9, -0.5, 0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
    previous_rate, previous_value = grid[0], npv(grid[0])
    bracket: tuple[float, float] | None = None
    for rate in grid[1:]:
        value = npv(rate)
        if value == 0 or previous_value == 0 or (value < 0) != (previous_value < 0):
            bracket = previous_rate, rate
            break
        previous_rate, previous_value = rate, value
    if bracket is None:
        raise ValueError("No XIRR solution was bracketed; check cash flows or use a wider return range")
    low, high = bracket
    low_value = npv(low)
    for _ in range(200):
        mid = (low + high) / 2
        mid_value = npv(mid)
        if abs(mid_value) < 1e-9 or high - low < 1e-12:
            return mid
        if (mid_value < 0) == (low_value < 0):
            low, low_value = mid, mid_value
        else:
            high = mid
    return (low + high) / 2


def fire_corpus(annual_spending: float, withdrawal_rate: float) -> float:
    _validate_nonnegative("annual spending", annual_spending)
    _validate_rate("withdrawal rate", withdrawal_rate)
    if withdrawal_rate == 0:
        raise ValueError("Withdrawal rate must be greater than zero")
    return annual_spending / withdrawal_rate


def monthly_return_from_annual(annual_rate: float) -> float:
    _validate_rate("annual rate", annual_rate, lower_bound=-1.0)
    if annual_rate == -1:
        raise ValueError("A -100% annual rate cannot support a monthly drawdown plan")
    return (1 + annual_rate) ** (1 / 12) - 1


def required_monthly_swp_corpus(
    monthly_expense_streams: Iterable[tuple[float, float]],
    annual_return: float,
    months: int,
    annual_ltcg_exemption: float = 0.0,
    ltcg_tax_rate: float = 0.0,
    starting_cost_basis_fraction: float = 1.0,
) -> float:
    """Find the corpus that funds net SWP spending after estimated annual LTCG tax."""
    if months < 0:
        raise ValueError("months cannot be negative")
    if not isfinite(annual_ltcg_exemption) or annual_ltcg_exemption < 0:
        raise ValueError("Annual LTCG exemption cannot be negative")
    _validate_rate("LTCG tax rate", ltcg_tax_rate)
    _validate_rate("starting cost-basis fraction", starting_cost_basis_fraction)
    if ltcg_tax_rate > 1 or starting_cost_basis_fraction > 1:
        raise ValueError("LTCG tax rate and cost-basis fraction cannot exceed 100%")
    streams = list(monthly_expense_streams)
    total = 0.0
    monthly_return = monthly_return_from_annual(annual_return)
    for first_withdrawal, annual_inflation in streams:
        _validate_nonnegative("first monthly withdrawal", first_withdrawal)
        _validate_rate("annual inflation", annual_inflation, lower_bound=-1.0)
        monthly_inflation = (1 + annual_inflation) ** (1 / 12) - 1 if annual_inflation > -1 else -1
        total += sum(
            first_withdrawal * (1 + monthly_inflation) ** (month - 1) / (1 + monthly_return) ** month
            for month in range(1, months + 1)
        )
    if months == 0 or total == 0:
        return 0.0
    if annual_ltcg_exemption == 0 and ltcg_tax_rate == 0:
        return total

    def covers_spending(starting_balance: float) -> bool:
        rows = project_monthly_swp(
            starting_balance,
            streams,
            annual_return,
            months,
            annual_ltcg_exemption=annual_ltcg_exemption,
            ltcg_tax_rate=ltcg_tax_rate,
            starting_cost_basis_fraction=starting_cost_basis_fraction,
        )
        return all(row.shortfall <= 0.01 for row in rows)

    low, high = 0.0, max(total, 1.0)
    for _ in range(40):
        if covers_spending(high):
            break
        high *= 2
    else:
        return high
    for _ in range(45):
        middle = (low + high) / 2
        if covers_spending(middle):
            high = middle
        else:
            low = middle
    return high


def project_monthly_swp(
    starting_balance: float,
    monthly_expense_streams: Iterable[tuple[float, float]],
    annual_return: float,
    months: int,
    annual_ltcg_exemption: float = 0.0,
    ltcg_tax_rate: float = 0.0,
    starting_cost_basis_fraction: float = 1.0,
) -> list[SwpMonth]:
    """Apply monthly growth, then fund net spending and estimate tax on realized gains."""
    from firecalc.tax import gross_withdrawal_for_net_spending, tax_on_realized_ltcg

    _validate_nonnegative("starting balance", starting_balance)
    if months < 0:
        raise ValueError("months cannot be negative")
    _validate_nonnegative("annual LTCG exemption", annual_ltcg_exemption)
    _validate_rate("LTCG tax rate", ltcg_tax_rate)
    _validate_rate("starting cost-basis fraction", starting_cost_basis_fraction)
    if ltcg_tax_rate > 1 or starting_cost_basis_fraction > 1:
        raise ValueError("LTCG tax rate and cost-basis fraction cannot exceed 100%")
    monthly_return = monthly_return_from_annual(annual_return)
    streams: list[tuple[float, float]] = []
    for first_withdrawal, annual_inflation in monthly_expense_streams:
        _validate_nonnegative("first monthly withdrawal", first_withdrawal)
        _validate_rate("annual inflation", annual_inflation, lower_bound=-1.0)
        monthly_inflation = (1 + annual_inflation) ** (1 / 12) - 1 if annual_inflation > -1 else -1
        streams.append((first_withdrawal, monthly_inflation))
    balance = starting_balance
    cost_basis = starting_balance * starting_cost_basis_fraction
    exemption_remaining = annual_ltcg_exemption
    rows: list[SwpMonth] = []
    for month in range(1, months + 1):
        if (month - 1) % 12 == 0:
            exemption_remaining = annual_ltcg_exemption
        opening = balance
        growth = opening * monthly_return
        available = max(0.0, opening + growth)
        net_required = sum(first * (1 + monthly_inflation) ** (month - 1) for first, monthly_inflation in streams)
        gain_fraction = min(1.0, max(0.0, available - cost_basis) / available) if available > 0 else 0.0
        gross_required = gross_withdrawal_for_net_spending(
            net_required, gain_fraction, exemption_remaining, ltcg_tax_rate
        )
        paid = min(available, gross_required)
        realized_gain = paid * gain_fraction
        tax_paid, exemption_remaining = tax_on_realized_ltcg(
            realized_gain, exemption_remaining, ltcg_tax_rate
        )
        net_paid = paid - tax_paid
        shortfall = max(0.0, net_required - net_paid)
        balance = max(0.0, available - paid)
        cost_basis = max(0.0, cost_basis - max(0.0, paid - realized_gain))
        rows.append(SwpMonth(
            month, (month - 1) // 12 + 1, opening, gross_required, paid,
            growth, balance, shortfall, realized_gain, tax_paid, net_paid, net_required,
        ))
    return rows


def project_swp(
    starting_balance: float,
    annual_withdrawal: float,
    annual_return: float,
    inflation: float,
    years: int,
) -> list[SwpYear]:
    """Withdraw at the start of each year, then apply that year's return."""
    _validate_nonnegative("starting balance", starting_balance)
    _validate_nonnegative("annual withdrawal", annual_withdrawal)
    _validate_rate("annual return", annual_return, lower_bound=-1.0)
    _validate_rate("inflation", inflation, lower_bound=-1.0)
    if years < 0:
        raise ValueError("years cannot be negative")
    balance = starting_balance
    withdrawal = annual_withdrawal
    rows: list[SwpYear] = []
    for year in range(1, years + 1):
        opening = balance
        paid = min(opening, withdrawal)
        shortfall = max(0.0, withdrawal - opening)
        invested = max(0.0, opening - paid)
        growth = invested * annual_return
        balance = max(0.0, invested + growth)
        rows.append(SwpYear(year, opening, paid, growth, balance, shortfall))
        withdrawal *= 1 + inflation
    return rows


def goal_future_cost(current_cost: float, years: float, inflation: float) -> float:
    return future_value_lump_sum(current_cost, inflation, years)


def monthly_sip_for_target(target: float, years: float, annual_return: float) -> float:
    """Constant month-end contribution needed to reach a future target from zero."""
    _validate_nonnegative("target", target)
    _validate_nonnegative("years", years)
    _validate_rate("annual return", annual_return, lower_bound=-1.0)
    months = round(years * 12)
    if months == 0:
        if target == 0:
            return 0.0
        raise ValueError("A positive target needs a non-zero savings period")
    monthly_rate = (1 + annual_return) ** (1 / 12) - 1 if annual_return > -1 else -1
    if monthly_rate == 0:
        return target / months
    if monthly_rate == -1:
        raise ValueError("A -100% return cannot fund a goal through monthly contributions")
    accumulation_factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
    return target / accumulation_factor


def _validate_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _validate_rate(name: str, value: float, lower_bound: float = -1.0) -> None:
    if not isfinite(value) or value < lower_bound:
        raise ValueError(f"{name} must be finite and at least {lower_bound:.0%}")


@dataclass(frozen=True)
class EmiRow:
    month: int
    opening_balance: float
    emi: float
    principal: float
    interest: float
    closing_balance: float


def emi_payment(principal: float, annual_rate: float, months: int) -> float:
    """Standard reducing-balance monthly EMI payment."""
    _validate_nonnegative("principal", principal)
    _validate_nonnegative("months", months)
    _validate_rate("annual rate", annual_rate, lower_bound=0.0)
    if months == 0:
        return 0.0
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def emi_schedule(principal: float, annual_rate: float, months: int) -> list[EmiRow]:
    """Full reducing-balance monthly amortization schedule."""
    _validate_nonnegative("principal", principal)
    _validate_nonnegative("months", months)
    _validate_rate("annual rate", annual_rate, lower_bound=0.0)
    rows: list[EmiRow] = []
    if months == 0 or principal == 0:
        return rows
    emi = emi_payment(principal, annual_rate, months)
    r = annual_rate / 12
    balance = principal
    for month in range(1, int(months) + 1):
        opening = balance
        interest = opening * r
        principal_part = emi - interest
        if month == int(months) or principal_part >= opening:
            principal_part = opening
            emi_actual = opening + interest
            balance = 0.0
            rows.append(EmiRow(month, opening, emi_actual, principal_part, interest, balance))
            break
        else:
            emi_actual = emi
            balance = max(0.0, opening - principal_part)
            rows.append(EmiRow(month, opening, emi_actual, principal_part, interest, balance))
    return rows


def prepayment_savings(
    principal: float,
    annual_rate: float,
    original_months: int,
    prepayment_amount: float,
    at_month: int,
    reduce_emi: bool = False,
) -> dict:
    """Calculate interest savings and tenure reduction from a lump-sum prepayment."""
    _validate_nonnegative("principal", principal)
    _validate_nonnegative("original_months", original_months)
    _validate_rate("annual rate", annual_rate, lower_bound=0.0)
    _validate_nonnegative("prepayment_amount", prepayment_amount)
    if original_months == 0:
        return {
            "original_total_interest": 0.0,
            "new_total_interest": 0.0,
            "interest_saved": 0.0,
            "months_saved": 0,
            "new_tenure_months": 0,
            "new_emi": 0.0,
            "balance_after_prepayment": 0.0,
        }
    if at_month < 1 or at_month > original_months:
        raise ValueError("Prepayment month must be between 1 and original tenure months")

    schedule_no_prep = emi_schedule(principal, annual_rate, original_months)
    total_interest_no_prep = sum(row.interest for row in schedule_no_prep)
    balance_at_prepayment = schedule_no_prep[at_month - 1].closing_balance
    balance_after_prepayment = max(0.0, balance_at_prepayment - prepayment_amount)
    remaining_months = original_months - at_month

    if balance_after_prepayment == 0 or remaining_months == 0:
        interest_after = 0.0
        new_months = 0
        new_emi = 0.0
    elif reduce_emi:
        new_emi = emi_payment(balance_after_prepayment, annual_rate, remaining_months)
        new_schedule = emi_schedule(balance_after_prepayment, annual_rate, remaining_months)
        interest_after = sum(row.interest for row in new_schedule)
        new_months = remaining_months
    else:
        original_emi = schedule_no_prep[0].emi
        new_emi = original_emi
        r = annual_rate / 12
        if r == 0:
            new_months = int(math.ceil(balance_after_prepayment / original_emi))
        else:
            if original_emi > balance_after_prepayment * r:
                new_months = int(math.ceil(
                    math.log(original_emi / (original_emi - balance_after_prepayment * r))
                    / math.log(1 + r)
                ))
            else:
                new_months = remaining_months
        new_schedule = emi_schedule(balance_after_prepayment, annual_rate, new_months)
        interest_after = sum(row.interest for row in new_schedule)

    interest_before_prepayment = sum(row.interest for row in schedule_no_prep[:at_month])
    total_interest_with_prep = interest_before_prepayment + interest_after
    months_saved = max(0, remaining_months - new_months) if not reduce_emi else 0
    return {
        "original_total_interest": total_interest_no_prep,
        "new_total_interest": total_interest_with_prep,
        "interest_saved": max(0.0, total_interest_no_prep - total_interest_with_prep),
        "months_saved": months_saved,
        "new_tenure_months": at_month + new_months,
        "new_emi": new_emi,
        "balance_after_prepayment": balance_after_prepayment,
    }


def home_loan_tax_benefit(
    annual_interest: float,
    annual_principal: float,
    gross_income: float,
    regime: str = "new",
) -> dict:
    """Estimate annual tax benefit from home loan under Indian tax regimes."""
    if regime == "new":
        return {
            "section_24b_deduction": 0.0,
            "section_80c_deduction": 0.0,
            "total_deduction": 0.0,
            "estimated_tax_saved": 0.0,
            "marginal_rate_used": 0.0,
            "note": "Home loan deductions are not available under the New Tax Regime for self-occupied properties.",
        }
    sec_24b = min(annual_interest, 200_000.0)
    sec_80c = min(annual_principal, 150_000.0)
    total_deduction = sec_24b + sec_80c
    if gross_income <= 250_000:
        marginal_rate = 0.0
    elif gross_income <= 500_000:
        marginal_rate = 0.05
    elif gross_income <= 1_000_000:
        marginal_rate = 0.20
    else:
        marginal_rate = 0.30
    tax_saved = total_deduction * marginal_rate
    return {
        "section_24b_deduction": sec_24b,
        "section_80c_deduction": sec_80c,
        "total_deduction": total_deduction,
        "estimated_tax_saved": tax_saved,
        "marginal_rate_used": marginal_rate,
        "note": "Old Tax Regime: Sec 24(b) interest deduction up to ₹2L, Sec 80C principal deduction up to ₹1.5L.",
    }


def wealth_multiplier_table(
    cagr_pct: float,
    periods: list[int] | None = None,
    target_year: int = 25,
) -> list[dict]:
    """Return wealth multiplier comparison table between Lump Sum and SIP.

    Calculates exact metrics matching Indian investor standard conventions:
    - Lump Sum: (1 + r)^n
    - SIP: ((1 + rm)^m - 1) / rm / m  where rm = r/12 and m = n*12
    - Lump Sum ÷ SIP: Lump Sum / SIP multiplier
    - SIP -> Lump Sum to Year target_year: SIP multiplier * (1 + r)^(target_year - n)
    """
    _validate_rate("CAGR", cagr_pct / 100, lower_bound=-0.99)
    if periods is None:
        periods = [5, 8, 10, 12, 15, 18, 20, 22, 24, 25]
    r = cagr_pct / 100
    rm = r / 12
    rows = []
    for n in periods:
        lump = (1 + r) ** n
        m = n * 12
        if rm == 0:
            sip_mult = 1.0
        else:
            sip_mult = ((1 + rm) ** m - 1) / rm / m
        efficiency = lump / sip_mult if sip_mult > 0 else 0.0
        remaining = target_year - n
        if remaining >= 0:
            sip_to_lump = sip_mult * ((1 + r) ** remaining)
        else:
            sip_to_lump = sip_mult

        rows.append({
            "Period": f"{n} years",
            "Lump Sum": f"{lump:.2f}×",
            "SIP": f"{sip_mult:.2f}×",
            "Lump Sum ÷ SIP": f"{efficiency:.2f}×",
            f"SIP → Lump Sum to Year {target_year}": f"{sip_to_lump:.2f}×",
            "_period_years": n,
            "_lump_num": lump,
            "_sip_num": sip_mult,
            "_efficiency_num": efficiency,
            "_sip_to_lump_num": sip_to_lump,
        })
    return rows


@dataclass(frozen=True)
class FireAgeRow:
    age: int
    years_to_fire: int
    projected_portfolio: float
    corpus_needed: float
    coverage_pct: float
    surplus_or_gap: float


def earliest_fire_age_trajectory(
    current_age: int,
    max_retirement_age: int,
    current_portfolio: float,
    monthly_sip: float,
    annual_lump_sum: float,
    annual_step_up: float,
    pre_return: float,
    post_return: float,
    expense_streams_now: list[tuple[float, float]],
    lifestyle_pct: float,
    retirement_years: int,
    annual_ltcg_exemption: float = 0.0,
    ltcg_tax_rate: float = 0.0,
) -> tuple[int | None, list[FireAgeRow]]:
    """Sweep retirement ages and find earliest age where portfolio meets required corpus."""
    _validate_nonnegative("current_portfolio", current_portfolio)
    _validate_nonnegative("monthly_sip", monthly_sip)
    _validate_nonnegative("annual_lump_sum", annual_lump_sum)
    if current_age >= max_retirement_age:
        return None, []
    rows: list[FireAgeRow] = []
    fire_age: int | None = None
    for age in range(current_age + 1, max_retirement_age + 1):
        years = age - current_age
        portfolio = project_portfolio(
            current_portfolio, monthly_sip, years, pre_return, annual_step_up, annual_lump_sum
        )
        future_streams: list[tuple[float, float]] = []
        for monthly_now, ann_inf in expense_streams_now:
            rate = max(-1.0, ann_inf)
            future_monthly = monthly_now * ((1 + rate) ** years) * (lifestyle_pct / 100)
            future_streams.append((future_monthly, rate))
        corpus = required_monthly_swp_corpus(
            future_streams,
            post_return,
            retirement_years * 12,
            annual_ltcg_exemption=annual_ltcg_exemption,
            ltcg_tax_rate=ltcg_tax_rate,
        )
        coverage = (portfolio / corpus * 100) if corpus > 0 else float("inf")
        surplus = portfolio - corpus
        rows.append(FireAgeRow(age, years, portfolio, corpus, coverage, surplus))
        if fire_age is None and portfolio >= corpus:
            fire_age = age
    return fire_age, rows
