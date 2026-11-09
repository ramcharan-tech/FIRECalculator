# FIRE Calculator 🇮🇳

A transparent, configurable, India-focused **FIRE (Financial Independence, Retire Early)** planning application built with Python, Streamlit, and Plotly. 

Designed specifically for Indian investors and families, it models Indian rupee (INR) currency formatting (Lakhs and Crores), realistic category-specific inflation rates, Section 112A LTCG tax rules, and provides an optional AI-powered financial advisory assistant.

---

## ✨ Features

- **India-Centric Financial Modeling**:
  - Native INR formatting with Indian numbering conventions (`₹1,00,000` / Lakhs & Crores).
  - Indian tax modeling including Section 112A LTCG exemptions (₹1.25L annual gain exemption) and pro-rata cost-basis withdrawal tracking.
  - Category-level inflation rates (e.g., higher healthcare and education inflation vs. utility inflation).
  - Built-in expense archetypes for Tier-1 & Tier-2 cities (Metro Family, DINK, Young Professional, etc.).

- **Comprehensive Modules**:
  - **Spending & Lifestyle**: Categorized recurring and amortized one-time expenses, inflation trajectories, and essential vs. discretionary split.
  - **Milestone Goals**: Target timeline planning for child education, house down payments, weddings, vehicle upgrades, and travel.
  - **Investments & Retirement**: Interactive calculation of target corpus, safe withdrawal rates, and real-time gap analysis.
  - **SWP Monte Carlo / Longevity Simulator**: Month-by-month Systematic Withdrawal Plan cash flow projections, testing corpus survival across varying life expectancies.
  - **Utilities**: Fast CAGR and dated cash-flow XIRR calculators.

- **Private & Local Persistence**:
  - All data is saved strictly on your local machine using SQLite (`.firecalc.sqlite3`) and JSON defaults. No cloud account or remote database is required.
  - Export and import your complete financial plans as portable JSON files anytime.

- **AI Financial Assistant (Optional)**:
  - Context-aware LangGraph assistant capable of inspecting your active spending, goals, and portfolio parameters to answer strategic retirement questions.
  - Supports Google Gemini, OpenRouter, and OpenCode API endpoints.

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.11** or newer
- (Recommended) [**uv**](https://docs.astral.sh/uv/) for lightning-fast package management, or standard `pip`

---

### Option 1: Running with `uv` (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ramcharan-tech/FIRECalculator.git
   cd FIRECalculator
   ```

2. **(Optional) Configure AI Assistant:**
   If you plan to use the AI financial assistant, copy `.env.example` to `.env` and add your API key:
   ```bash
   cp .env.example .env    # On Windows PowerShell: Copy-Item .env.example .env
   ```
   *(Note: The core calculator runs 100% offline without any API keys).*

3. **Run the application:**
   ```bash
   uv run --all-extras streamlit run app.py
   ```
   *Windows users can also simply run `run.bat` or `run.ps1`.*

---

### Option 2: Running with standard `pip` and `venv`

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ramcharan-tech/FIRECalculator.git
   cd FIRECalculator
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows:
   python -m venv .venv
   .venv\Scripts\activate

   # macOS / Linux:
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *Or install directly from `pyproject.toml`:*
   ```bash
   pip install ".[assistant]"
   ```

4. **Launch the app:**
   ```bash
   streamlit run app.py
   ```

The application will automatically open in your default browser at `http://localhost:8501`.

---

## ⚙️ Environment Configuration

To enable the AI Assistant, configure any of the supported providers in `.env`:

```env
# Google Gemini
GEMINI_API_KEY="your-gemini-api-key"

# OpenRouter (Access Claude, OpenAI, DeepSeek, etc.)
OPENROUTER_API_KEY="your-openrouter-api-key"

# OpenCode / Custom OpenAI-compatible endpoint
OPENCODE_API_KEY="your-opencode-key"
OPENCODE_BASE_URL="https://opencode.ai/inference/openai/v1"
OPENCODE_MODEL="deepseek-v4.1-flash"
```

Keys are loaded securely via `python-dotenv` and are never logged or stored in application state.

---

## 📁 Repository Structure

```text
FIRECalculator/
├── app.py                   # Main Streamlit application and UI layout
├── pyproject.toml           # Project metadata and dependencies
├── requirements.txt         # Pinned requirements for standard pip install
├── uv.lock                  # Lockfile ensuring reproducible uv builds
├── run.bat                  # One-click Windows startup script
├── run.ps1                  # Windows PowerShell startup script
├── firecalc_presets.json    # Curated Indian expense & lifestyle presets
├── firecalc/                # Core calculation engine
│   ├── calculations.py      # FIRE corpus, SWP, CAGR, XIRR calculations
│   ├── tax.py               # Indian Section 112A LTCG tax logic
│   ├── india_presets.py     # Preset loaders and category inflation definitions
│   ├── assistant.py         # LangGraph AI agent and section analysis tools
│   └── storage.py           # SQLite local persistence engine
└── README.md
```

---

## ⚠️ Disclaimer

This calculator is designed strictly for educational and self-planning purposes. It does not constitute formal financial, tax, or legal advice. Financial market returns, future inflation rates, and statutory tax rules fluctuate over time. Please consult a SEBI-registered investment advisor (RIA) for personalized financial planning.

---

## 📄 License

Open-source under the [MIT License](LICENSE) (or applicable open license).
