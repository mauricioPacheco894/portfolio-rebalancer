# Portfolio Rebalancer

A lightweight, dependency-free Python module that calculates the exact buy and sell trades required to align a stock portfolio's current holdings with its target percentage allocations.

## Project Structure

- `portfolio.py` — Domain model (`Stock`, `RebalanceAction`, `Portfolio`), validation, rebalancing logic, and a runnable CLI example.
- `test_portfolio.py` — Unit test suite covering standard rebalancing, price updates, full liquidations, new positions from zero, rounding thresholds, and invariant validations.
- `README.md` — Architecture notes, financial assumptions, and usage instructions.

## Design Decisions

1. **Exact Decimal Arithmetic (`decimal.Decimal`):**
   Floating-point numbers (`float`) introduce IEEE 754 representation errors that are unsuitable for financial calculations. All internal prices, share quantities, weights, and monetary amounts use `Decimal` (similar to `BigDecimal` in Java). For caller ergonomics, numeric inputs (`Decimal`, `str`, `int`, or `float`) are normalized via string conversion (`Decimal(str(value))`) before any calculation takes place.
2. **Domain Modeling with `@dataclass`:**
   - `RebalanceAction` is modeled as an immutable value object (`@dataclass(frozen=True)`), analogous to a Java `record`, containing `symbol`, `action` (`"SELL"` or `"BUY"`), `shares`, and `amount`.
   - `Stock` encapsulates a normalized uppercase ticker symbol and a mutable market price while defining `__eq__` and `__hash__` strictly by `symbol`.
   - `Portfolio` stores current share quantities in `holdings: dict[str, Decimal]`, target weights in `allocations: dict[str, Decimal]`, and registered stock instances in `_stocks: dict[str, Stock]`.
3. **`Stock.current_price(last_available_price=None)` Contract:**
   Follows the problem specification by acting as both a getter and an optional updater: when called with no arguments, it returns the current price; when passed a new `last_available_price` (strictly `> 0`), it updates and returns the new price.
4. **Set Union Iteration (`holdings.keys() | allocations.keys()`):**
   `Portfolio.rebalance()` iterates over the union of keys from both dictionaries in a single pass. This naturally handles three scenarios without special-case branching:
   - Partial adjustments for stocks present in both `holdings` and `allocations`.
   - **100% liquidation (`SELL`)** when a currently held stock is omitted from `allocations` (implicit target weight of `0`).
   - **Buying from scratch (`BUY`)** when a target stock in `allocations` is not yet held in `holdings` (implicit current shares of `0`).
5. **Liquidity-First Order Execution (`SELL` before `BUY`):**
   The returned list of `RebalanceAction` items is sorted so that all `SELL` orders appear before `BUY` orders (and alphabetically by ticker within each group), reflecting real-world execution where capital must be freed from sales before funding purchases.

## Financial Assumptions & Validation Rules

- **Base-1 Target Weights:** Target allocations are expressed as ratios in `[0, 1]` (e.g., `0.40` for 40% and `0.60` for 60%).
- **Allocation Sum Tolerance:** Target allocations must sum to `1.0` within a tolerance of `±0.0001` to accommodate repeating fractions such as thirds (`0.3333` × 3 = `0.9999`).
- **Fractional Shares & Rounding:**
  - Share quantities are rounded to **4 decimal places (`0.0001`)** using `ROUND_HALF_UP`.
  - Monetary trade amounts are computed from the rounded share count (`shares * price`) and rounded to **2 decimal places (`0.01`)** using `ROUND_HALF_UP`.
  - Trade deltas smaller than `0.0001` shares are ignored to prevent zero-share orders.
- **Portfolio Valuation:** Total portfolio value must be strictly greater than `0` to execute a rebalance, and all stock prices must be strictly greater than `0`.

## Running the Demo & Tests

### Quick Demo (No Dependencies Required)

Run `portfolio.py` directly with Python 3.10+ to execute the 40% `META` / 60% `AAPL` example:

```bash
python3 portfolio.py
```

Example output:

```text
Initial Portfolio (Total Value: $10000.00):
  - META: 10 shares @ $500.00 = $5000.00 (Current: 50.0% -> Target: 40.0%)
  - AAPL: 25 shares @ $200.00 = $5000.00 (Current: 50.0% -> Target: 60.0%)

Rebalance Actions (SELL first to free liquidity, then BUY):
  [SELL] META: 2.0000 shares ($1000.00)
  [BUY] AAPL: 5.0000 shares ($1000.00)
```

### Running the Unit Test Suite

Using a virtual environment with `pytest` installed:

```bash
.venv/bin/pytest -v
```

*(Or `pytest -v` if your virtual environment is already activated).*

## AI / LLM Usage

An AI coding assistant was used as a pair-programming tool during the development of this module. Coming primarily from a Java / Spring Boot background (where `BigDecimal` and `record` are standard for financial domain modeling), I defined the domain architecture, data structures, financial invariants, edge cases, and business rules, and collaborated with the assistant to translate those patterns into clean, idiomatic Python using `dataclasses`, `Decimal`, and `pytest`.

The full transcript of the design and implementation conversation is available in [AI_CONVERSATION.md](./AI_CONVERSATION.md).
