# FIRE Calculator Web App — Plan

## Product goal

Build a Python web app that helps a person or household in India estimate whether their current savings and planned investments can fund a comfortable, needs-focused retirement. It should make assumptions visible and adjustable, model recurring and one-off expenses, and explain results in plain language. It is a planning and educational tool, not personalized investment or tax advice.

## Proposed first version

### 1. Household and timeline

- Current age, target retirement age, planning horizon/longevity, household members and dependents.
- Current savings by asset/account, existing income, pension or other retirement income, and expected future one-off income or expenses.
- Optional goals with dates and amounts, such as children's education, a car, home upgrades, electronics replacement, and travel.

### 2. Spending planner

- Category-based expense editor with monthly, quarterly, annual, and one-time schedules; convert entries to annual and monthly equivalents.
- Starter categories: home loan/rent and upkeep, food and household needs, utilities, transport/car, healthcare, insurance by type, education/children, travel, gold/jewellery, electronics, home improvements, personal care, and miscellaneous.
- Support current spending and retirement spending separately, including expense start/end dates and inflation assumptions by category.
- India-focused inflation assumptions should be editable, with separate rates for general expenses and categories that may rise differently (for example healthcare and education). Show the rate and source/date used; don't silently treat one inflation figure as certain.

### 3. Investment and retirement calculators

- Investment growth projections for SIP, lump sum, and combined contributions, with configurable contribution timing, step-ups, duration, and return assumptions.
- SWP/drawdown projections with withdrawal timing, inflation-linked withdrawals, other retirement income, taxes/fees assumptions, and a visible depletion/surplus outcome.
- Inputs for expected return as a planning assumption; XIRR for dated cash flows/portfolio history; CAGR for a simple start-to-end period. Keep historical return measurement distinct from future-return assumptions.
- FIRE target estimate from retirement spending and chosen withdrawal/return assumptions, plus the projected portfolio at retirement and estimated shortfall/surplus.
- Scenario comparisons (for example conservative/base/optimistic), sensitivity to retirement age, savings rate, inflation, and return, and a year-by-year projection table/chart.

### 4. Tax and assumptions layer

- Keep tax estimates modular, year-labelled, and configurable so annual Indian tax-rule changes can be updated without changing the projection engine.
- Separate accumulation, withdrawal, and income-tax assumptions where applicable; show which assumptions affect each result and allow a no-tax/rough-estimate mode when details are unavailable.
- Before presenting a result as India-specific tax output, verify the applicable tax year and rules from authoritative current sources and state the effective date. Do not hard-code a tax figure without its year/source.

### 5. Goals assistant

- Add a LangGraph chat assistant that can explain the user's current calculator inputs and results, answer “what if” questions, and suggest which assumptions to review.
- Support Gemini and OpenRouter through provider/model configuration, with credentials supplied through environment variables or Streamlit secrets (never stored in the repository).
- The assistant should use the calculator's structured results as context, distinguish estimates from facts, and avoid silently changing inputs. Any proposed changes should be previewed for the user to apply.
- Keep calculations deterministic in Python; the LLM explains and explores them rather than doing the financial arithmetic itself.

### 6. UX, storage, and privacy

- Streamlit is the recommended starting UI for a fast, usable Python app; use `uv` for project/dependency management.
- Organize the app into clear sections: Overview, Spending, Investments, Retirement/SWP, Scenarios, and Goals Chat.
- Validate inputs, show units and assumptions beside fields, provide sensible blank/starting examples, and make warnings understandable.
- Choose persistence only after deciding whether this is a personal local tool or a multi-user app. For an initial local version, SQLite or downloadable/uploadable JSON could retain scenarios; avoid collecting sensitive data that isn't needed.
- Keep provider keys and any personal financial data out of logs and source control.

## Suggested architecture

- `app.py` and Streamlit page/components for UI.
- `models/` for typed household, expense, goal, investment, and assumption data.
- `calculators/` for expense annualization, SIP/lump-sum growth, XIRR/CAGR, FIRE target, and SWP/year-by-year cash-flow projections.
- `tax/` for year-specific, replaceable tax assumptions/calculations.
- `assistant/` for LangGraph state, calculator-context tools, provider selection, and response guardrails.
- `data/` or a persistence adapter for optional local scenario storage.
- `tests/` for deterministic financial calculation cases, edge cases, and tax-year assumptions once implementation begins.

## Delivery sequence

1. Resolve the product, tax, and privacy questions below; confirm the first-release scope.
2. Define the calculation model and input/output units, including inflation, contribution timing, tax treatment, and scenario assumptions.
3. Build the expense planner and deterministic calculator functions; expose assumptions and year-by-year outputs.
4. Build the Streamlit sections and scenario comparison flow.
5. Add LangGraph with Gemini/OpenRouter configuration and a calculator-grounded chat flow.
6. Add the selected persistence/deployment approach, document setup and limitations, and verify calculations against hand-worked examples.

## Implementation progress

- **Feature 1 implemented:** Streamlit/uv scaffold, categorized expense annualization, SIP/lump-sum/combined growth, CAGR/XIRR helpers, future goal-cost estimate, configurable FIRE corpus estimate, and monthly SWP projection using post-retirement return.
- **Feature 2 implemented:** separate pre/post-retirement returns, an annual fee drag, per-category inflation, sensitivity scenarios, multi-goal tracking with monthly savings estimates, JSON import/export, and an optional LangGraph assistant with Gemini/OpenRouter/OpenCode adapters. Retirement SWP tax now estimates realized gains using the portfolio cost-basis share, applies an annual rupee exemption, and taxes only gains above it at the configured LTCG rate.
- **Feature 3 implemented:** current expenses in Investments, an adjustable retirement lifestyle percentage, color-coded portfolio-versus-required-corpus chart and future expense chart, funded percentage and first goal year, and INR display with Indian grouping plus lakh/crore labels.
- **Feature 4 implemented:** replaced the initial withdrawal-rate shortcut with a monthly SWP present-value corpus, month-by-month balance projection, and annual/monthly withdrawal schedule using post-retirement return.
- **Feature 5 implemented:** combined accumulation and retirement planning into one section; added local save/load defaults that restore expenses, goals, assumptions, and return to the combined calculator with charts recalculated.
- **Feature 6 implemented:** free-text spending categories, one-time replacement-life annualization, category inflation horizon table and trajectory chart, integer rupee inputs, and local SQLite expense persistence/reload.
- **Feature 7 implemented:** removed the low-value Overview page and replaced radio navigation with a styled active-state sidebar menu; moved JSON portability tools into an optional backup expander.
- **Still open:** statutory Indian tax rules, asset-class/account-level investment and tax treatment, household/dependent modeling beyond goal beneficiaries, and saved user profiles/cloud sync. Those need the tax profile, investment scope, and privacy/deployment decisions below.

## Decisions needed before implementation

1. **Audience and tax scope:** Is this only for your own use or for multiple users? Should tax calculations target Indian tax residents, and which tax year/regime and investment/account types should the first version cover? Tax rules change, so the app should label the year and source.
2. **Data handling:** Should scenarios stay only on your machine (recommended for a first version), or do you want accounts/cloud sync? Should chatbot calls receive financial inputs only after an explicit opt-in?
3. **Chat provider setup:** Should both Gemini and OpenRouter be supported from the first release, or should one be the default? Which model(s) do you want, and will you provide API keys through local secrets/environment variables?
4. **First-release investment scope:** Should projections cover only user-entered portfolio-level return assumptions, or also model asset classes (equity, debt, gold, EPF/PPF/NPS, etc.) with separate return/tax assumptions?
5. **Household and goals:** Should the first release support one individual or a household with spouse/dependents and child-specific education timelines? Any goal categories or expense types to add/remove?
6. **Tax and inflation sources:** Do you have preferred official sources or assumptions for inflation and tax, or should these be selected and cited during implementation?
7. **Use and deployment:** Is Streamlit acceptable, and should the target be local desktop use first or a hosted web app?
