"""User-configured LTCG and return-fee estimates for FIRE projections."""

from __future__ import annotations

from math import isfinite


def return_after_fee_drag(gross_annual_return: float, annual_fee_drag_pct_points: float) -> float:
    """Subtract an explicitly entered annual fee drag from a gross return."""
    if not -1 <= gross_annual_return <= 10:
        raise ValueError("Gross return must be between -100% and 1000%")
    drag = annual_fee_drag_pct_points / 100
    if not 0 <= drag <= 1:
        raise ValueError("Annual fee drag must be between 0 and 100 percentage points")
    return max(-1.0, gross_annual_return - drag)


def gross_withdrawal_for_net_spending(
    net_spending: float,
    gain_fraction: float,
    exemption_remaining: float,
    tax_rate: float,
) -> float:
    """Estimate a gross SWP withdrawal needed to net spending after LTCG tax."""
    if not isfinite(net_spending) or not isfinite(exemption_remaining) or net_spending < 0 or exemption_remaining < 0:
        raise ValueError("Spending and remaining exemption cannot be negative")
    if not isfinite(gain_fraction) or not isfinite(tax_rate) or not 0 <= gain_fraction <= 1 or not 0 <= tax_rate <= 1:
        raise ValueError("Gain fraction and tax rate must be between 0 and 100%")
    if net_spending == 0 or gain_fraction == 0 or tax_rate == 0:
        return net_spending
    tax_free_gross_limit = exemption_remaining / gain_fraction
    if net_spending <= tax_free_gross_limit:
        return net_spending
    net_retention_rate = 1 - gain_fraction * tax_rate
    if net_retention_rate <= 0:
        raise ValueError("The tax assumptions leave no net amount from a withdrawal")
    gross = (net_spending - exemption_remaining * tax_rate) / net_retention_rate
    return max(net_spending, gross)


def tax_on_realized_ltcg(
    realized_gain: float,
    exemption_remaining: float,
    tax_rate: float,
) -> tuple[float, float]:
    """Return tax on gains above the remaining annual exemption and exemption left."""
    if not isfinite(realized_gain) or not isfinite(exemption_remaining) or realized_gain < 0 or exemption_remaining < 0:
        raise ValueError("Realized gains and remaining exemption cannot be negative")
    if not isfinite(tax_rate) or not 0 <= tax_rate <= 1:
        raise ValueError("LTCG tax rate must be between 0 and 100%")
    exemption_used = min(realized_gain, exemption_remaining)
    taxable_gain = max(0.0, realized_gain - exemption_remaining)
    return taxable_gain * tax_rate, exemption_remaining - exemption_used
