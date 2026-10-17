"""CISC 121 Lab - Part B: returns, drawdown, valuation and debt stress  (STARTER - complete the 6 TODOs)
Run from the lab folder:  python3 starter/returns_drawdown_starter.py
Data are SYNTHETIC (prices.csv, fundamentals.csv) - tickers are fictional.
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

prices = pd.read_csv("prices.csv", index_col="date", parse_dates=True)
fund = pd.read_csv("fundamentals.csv").set_index("ticker")

# ---- B1. Returns -------------------------------------------------------------
# TODO 1: daily simple returns r_t = P_t / P_{t-1} - 1 (drop the first NaN row)
daily = None
# TODO 2: cumulative return since day 0: product of (1 + r) minus 1
cumulative = None
last_day = daily.iloc[-1]                            # the Oct 16 move

# ---- B2. Risk ----------------------------------------------------------------
# TODO 3: annualized volatility (std of daily returns * sqrt(252)) and Sharpe ratio
#         (annualized mean return / annualized vol, risk-free rate = 0)
ann_vol = None
sharpe = None

def drawdown_series(p):
    """TODO 4: percent below the running peak (always <= 0). Hint: cummax()."""
    return None

dd = prices.apply(drawdown_series)
max_dd = dd.min()                                    # worst peak-to-trough fall
trough = dd.idxmin()
peak = pd.Series({c: prices[c][:trough[c]].idxmax() for c in prices})

summary = pd.DataFrame({
    "oct16_ret_%": (last_day * 100).round(2),
    "cum_ret_%": (cumulative.iloc[-1] * 100).round(1),
    "ann_vol_%": (ann_vol * 100).round(1),
    "sharpe": sharpe.round(2),
    "max_dd_%": (max_dd * 100).round(1),
    "peak_date": peak.dt.date, "trough_date": trough.dt.date,
})
print("=== Risk / return summary (60 trading days, synthetic) ===")
print(summary.to_string())

# ---- B3. Growth vs valuation --------------------------------------------------
f = fund.copy()
# TODO 5: ev_b = market cap + debt; ev_to_sales = ev_b / revenue_b;
#         ev_sales_per_growth = ev_to_sales / revenue_growth_pct (lower = cheaper per unit of growth)
f["ev_to_sales"] = None
f["ev_sales_per_growth"] = None
print("\n=== Growth vs valuation ===")
print(f[["revenue_growth_pct", "ev_to_sales", "ev_sales_per_growth"]].round(2).to_string())

# ---- B4. Debt financing stress -----------------------------------------------
# TODO 6: debt_to_ebitda, interest_b (= debt * rate), coverage (= EBITDA / interest),
#         and two stress cases: rates +2 percentage points, and EBITDA down 30%
f["debt_to_ebitda"] = f["coverage"] = f["coverage_+2pts"] = f["coverage_ebitda_-30%"] = None
print("\n=== Debt stress (coverage < 2 is a warning sign) ===")
print(f[["debt_to_ebitda", "coverage", "coverage_+2pts", "coverage_ebitda_-30%"]].round(2).to_string())

# ---- B5. Figures --------------------------------------------------------------
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
for c in prices.columns:
    ax[0].plot(cumulative.index, cumulative[c] * 100, label=c)
    ax[1].plot(dd.index, dd[c] * 100, label=c)
ax[0].set_title("Cumulative return (%)"); ax[1].set_title("Drawdown from running peak (%)")
ax[0].legend(fontsize=7); [a.grid(alpha=.3) for a in ax]
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig("returns_drawdown.png", dpi=130)
print("\nSaved returns_drawdown.png")
