"""Portfolio rebalancing module using exact Decimal arithmetic."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

ActionType = Literal["BUY", "SELL"]
NumericInput = Decimal | int | float | str

SHARES_PRECISION = Decimal("0.0001")
CURRENCY_PRECISION = Decimal("0.01")
ALLOCATION_TARGET_SUM = Decimal("1.0")
ALLOCATION_TOLERANCE = Decimal("0.0001")


def _to_decimal(value: NumericInput, field_name: str = "value") -> Decimal:
    """Convert a supported numeric input into a Decimal safely using string conversion for floats."""
    if isinstance(value, bool):
        raise TypeError(f"Unsupported type for {field_name}: bool")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Invalid non-finite numeric value for {field_name}: {value!r}")
        return value
    if isinstance(value, (int, float, str)):
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid numeric value for {field_name}: {value!r}") from exc
        if not parsed.is_finite():
            raise ValueError(f"Invalid non-finite numeric value for {field_name}: {value!r}")
        return parsed
    raise TypeError(f"Unsupported type for {field_name}: {type(value).__name__}")


def _normalize_symbol(symbol: str) -> str:
    """Validate and normalize a stock ticker symbol to uppercase."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Stock symbol must be a non-empty string.")
    return symbol.strip().upper()


@dataclass(frozen=True)
class RebalanceAction:
    """Immutable record representing a single buy or sell order required to rebalance."""

    symbol: str
    action: ActionType
    shares: Decimal
    amount: Decimal


@dataclass(eq=False)
class Stock:
    """Represents a tradable stock with a mutable current market price.

    Identity and hashing are strictly based on the normalized ticker symbol.
    """

    symbol: str
    price: InitVar[NumericInput]
    _price: Decimal = field(init=False, repr=False)

    def __post_init__(self, price: NumericInput) -> None:
        self.symbol = _normalize_symbol(self.symbol)
        self.current_price(price)

    def current_price(self, last_available_price: NumericInput | None = None) -> Decimal:
        """Return the current price, updating it first if last_available_price is provided."""
        if last_available_price is not None:
            parsed_price = _to_decimal(last_available_price, field_name="last_available_price")
            if parsed_price <= Decimal("0"):
                raise ValueError(
                    f"Stock price for {self.symbol} must be strictly greater than 0."
                )
            self._price = parsed_price
        return self._price

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Stock):
            return NotImplemented
        return self.symbol == other.symbol

    def __hash__(self) -> int:
        return hash(self.symbol)

    def __repr__(self) -> str:
        return f"Stock(symbol={self.symbol!r}, price={self._price!r})"


@dataclass
class Portfolio:
    """Manages current stock holdings and target allocations to compute rebalancing trades."""

    holdings: dict[str, Decimal] = field(default_factory=dict)
    allocations: dict[str, Decimal] = field(default_factory=dict)
    _stocks: dict[str, Stock] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.holdings = {
            _normalize_symbol(symbol): _to_decimal(shares, field_name=f"holdings[{symbol}]")
            for symbol, shares in self.holdings.items()
        }
        for symbol, shares in self.holdings.items():
            if shares < Decimal("0"):
                raise ValueError(f"Holdings for {symbol} cannot be negative.")

        self.allocations = {
            _normalize_symbol(symbol): _to_decimal(weight, field_name=f"allocations[{symbol}]")
            for symbol, weight in self.allocations.items()
        }
        for symbol, weight in self.allocations.items():
            if weight < Decimal("0") or weight > ALLOCATION_TARGET_SUM:
                raise ValueError(
                    f"Allocation for {symbol} must be between 0 and 1 (got {weight})."
                )

        self._stocks = {
            _normalize_symbol(symbol): stock for symbol, stock in self._stocks.items()
        }

    def register_stock(self, stock: Stock) -> None:
        """Register or update a Stock instance in the portfolio's internal catalog."""
        if not isinstance(stock, Stock):
            raise TypeError("Expected a Stock instance.")
        self._stocks[stock.symbol] = stock

    def set_holding(self, stock_or_symbol: Stock | str, shares: NumericInput) -> None:
        """Set the current share count for a stock (registering the Stock if provided)."""
        symbol = self._resolve_stock_symbol(stock_or_symbol)
        parsed_shares = _to_decimal(shares, field_name="shares")
        if parsed_shares < Decimal("0"):
            raise ValueError(f"Holdings for {symbol} cannot be negative.")

        if parsed_shares == Decimal("0"):
            self.holdings.pop(symbol, None)
        else:
            self.holdings[symbol] = parsed_shares

    def set_allocation(self, stock_or_symbol: Stock | str, target_weight: NumericInput) -> None:
        """Set the target allocation weight (base 1) for a stock."""
        symbol = self._resolve_stock_symbol(stock_or_symbol)
        parsed_weight = _to_decimal(target_weight, field_name="target_weight")
        if parsed_weight < Decimal("0") or parsed_weight > ALLOCATION_TARGET_SUM:
            raise ValueError(
                f"Target allocation for {symbol} must be between 0 and 1 (got {parsed_weight})."
            )

        if parsed_weight == Decimal("0"):
            self.allocations.pop(symbol, None)
        else:
            self.allocations[symbol] = parsed_weight

    def total_value(self) -> Decimal:
        """Calculate the total current market value of the portfolio without rounding."""
        total = Decimal("0")
        for symbol, shares in self.holdings.items():
            if shares == Decimal("0"):
                continue
            stock = self._get_registered_stock(symbol)
            total += shares * stock.current_price()
        return total

    def rebalance(self) -> list[RebalanceAction]:
        """Compute the list of SELL and BUY actions required to reach target allocations.

        Returns:
            A list of RebalanceAction objects ordered with all SELL actions first,
            followed by all BUY actions (sorted alphabetically by symbol within each group).
        """
        self._validate_allocations()

        total_val = self.total_value()
        if total_val <= Decimal("0"):
            raise ValueError("Total portfolio value must be strictly greater than 0 to rebalance.")

        all_symbols = sorted(self.holdings.keys() | self.allocations.keys())
        actions: list[RebalanceAction] = []

        for symbol in all_symbols:
            current_shares = self.holdings.get(symbol, Decimal("0"))
            target_weight = self.allocations.get(symbol, Decimal("0"))

            if current_shares == Decimal("0") and target_weight == Decimal("0"):
                continue

            stock = self._get_registered_stock(symbol)
            price = stock.current_price()

            current_value = current_shares * price
            target_value = total_val * target_weight
            value_delta = target_value - current_value

            raw_shares_delta = value_delta / price
            shares_to_trade = abs(raw_shares_delta).quantize(
                SHARES_PRECISION, rounding=ROUND_HALF_UP
            )

            if shares_to_trade < SHARES_PRECISION:
                continue

            action_type: ActionType = "BUY" if raw_shares_delta > Decimal("0") else "SELL"
            trade_amount = (shares_to_trade * price).quantize(
                CURRENCY_PRECISION, rounding=ROUND_HALF_UP
            )

            actions.append(
                RebalanceAction(
                    symbol=symbol,
                    action=action_type,
                    shares=shares_to_trade,
                    amount=trade_amount,
                )
            )

        actions.sort(key=lambda item: (0 if item.action == "SELL" else 1, item.symbol))
        return actions

    def _resolve_stock_symbol(self, stock_or_symbol: Stock | str) -> str:
        """Register the Stock if an instance is given, and return its normalized symbol."""
        if isinstance(stock_or_symbol, Stock):
            self.register_stock(stock_or_symbol)
            return stock_or_symbol.symbol
        return _normalize_symbol(stock_or_symbol)

    def _get_registered_stock(self, symbol: str) -> Stock:
        """Retrieve a registered Stock by symbol or raise KeyError if missing."""
        if symbol not in self._stocks:
            raise KeyError(f"Stock '{symbol}' is not registered in the portfolio.")
        return self._stocks[symbol]

    def _validate_allocations(self) -> None:
        """Validate that target allocations are present, non-negative, and sum to 1.0."""
        if not self.allocations:
            raise ValueError("Cannot rebalance a portfolio with empty target allocations.")

        for symbol, weight in self.allocations.items():
            if weight < Decimal("0") or weight > ALLOCATION_TARGET_SUM:
                raise ValueError(
                    f"Target allocation for {symbol} must be between 0 and 1 (got {weight})."
                )

        allocation_sum = sum(self.allocations.values(), Decimal("0"))
        if abs(allocation_sum - ALLOCATION_TARGET_SUM) > ALLOCATION_TOLERANCE:
            raise ValueError(
                f"Target allocations must sum to {ALLOCATION_TARGET_SUM} "
                f"(±{ALLOCATION_TOLERANCE}), got {allocation_sum}."
            )
