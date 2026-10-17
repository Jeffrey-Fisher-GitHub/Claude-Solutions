"""CISC 121 Lab - Part B: returns, drawdown, valuation and debt stress  (SOLUTION)
Run from the lab folder:  python3 solution/returns_drawdown.py
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
daily = prices.pct_change().dropna()                 # r_t = P_t / P_{t-1} - 1
cumulative = (1 + daily).cumprod() - 1               # growth of $1, minus 1
last_day = daily.iloc[-1]                            # the Oct 16 move

# ---- B2. Risk ----------------------------------------------------------------
ann_vol = daily.std() * np.sqrt(252)                 # annualized volatility
sharpe = (daily.mean() * 252) / ann_vol              # risk-free rate assumed 0

def drawdown_series(p):
    """Percent below the running peak: p / cummax(p) - 1 (always <= 0)."""
    return p / p.cummax() - 1

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
f["ev_b"] = f.market_cap_b + f.debt_b                         # enterprise value (cash ignored)
f["ev_to_sales"] = f.ev_b / f.revenue_b
f["ev_sales_per_growth"] = f.ev_to_sales / f.revenue_growth_pct   # lower = cheaper per unit growth
print("\n=== Growth vs valuation ===")
print(f[["revenue_growth_pct", "ev_to_sales", "ev_sales_per_growth"]].round(2).to_string())

# ---- B4. Debt financing stress -----------------------------------------------
f["debt_to_ebitda"] = f.debt_b / f.ebitda_b
f["interest_b"] = f.debt_b * f.interest_rate_pct / 100
f["coverage"] = f.ebitda_b / f.interest_b                     # EBITDA / interest expense
f["coverage_+2pts"] = f.ebitda_b / (f.debt_b * (f.interest_rate_pct + 2) / 100)
f["coverage_ebitda_-30%"] = f.ebitda_b * 0.7 / f.interest_b
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
