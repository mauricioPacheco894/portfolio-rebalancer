"""Unit tests for the portfolio rebalancing module."""

from decimal import Decimal
import pytest

from portfolio import Portfolio, RebalanceAction, Stock


class TestStock:
    """Tests for Stock initialization, price updates, and identity semantics."""

    def test_stock_creation_and_price_retrieval(self) -> None:
        stock = Stock("aapl", 150.50)
        assert stock.symbol == "AAPL"
        assert stock.current_price() == Decimal("150.5")

    def test_current_price_updates_when_argument_provided(self) -> None:
        stock = Stock("META", Decimal("300.00"))
        assert stock.current_price() == Decimal("300.00")

        updated = stock.current_price(325.75)
        assert updated == Decimal("325.75")
        assert stock.current_price() == Decimal("325.75")

    def test_equality_and_hash_depend_only_on_symbol(self) -> None:
        stock_a = Stock("aapl", "150.00")
        stock_b = Stock("AAPL", "200.00")
        stock_c = Stock("META", "150.00")

        assert stock_a == stock_b
        assert stock_a != stock_c
        assert hash(stock_a) == hash(stock_b)

        stock_set = {stock_a}
        stock_a.current_price("175.00")
        assert stock_b in stock_set

    @pytest.mark.parametrize("invalid_price", [0, -10, "0.00", "-0.01", Decimal("-5")])
    def test_stock_rejects_non_positive_prices(self, invalid_price: object) -> None:
        with pytest.raises(ValueError, match="strictly greater than 0"):
            Stock("AAPL", invalid_price)  # type: ignore[arg-type]

        stock = Stock("AAPL", "100.00")
        with pytest.raises(ValueError, match="strictly greater than 0"):
            stock.current_price(invalid_price)  # type: ignore[arg-type]

    @pytest.mark.parametrize("invalid_symbol", ["", "   "])
    def test_stock_rejects_empty_symbol(self, invalid_symbol: str) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            Stock(invalid_symbol, "100.00")


class TestPortfolioRebalance:
    """Tests for portfolio rebalancing scenarios."""

    def test_base_rebalance_40_meta_60_aapl(self) -> None:
        """Verify standard two-stock rebalance (40% META / 60% AAPL) and SELL-before-BUY order."""
        meta = Stock("META", 500.00)
        aapl = Stock("AAPL", 200.00)

        portfolio = Portfolio()
        # Current holdings:
        # META: 10 shares @ $500 = $5,000 (50%)
        # AAPL: 25 shares @ $200 = $5,000 (50%)
        # Total portfolio value = $10,000
        portfolio.set_holding(meta, 10)
        portfolio.set_holding(aapl, 25)

        # Target allocations: 40% META ($4,000), 60% AAPL ($6,000)
        portfolio.set_allocation(meta, 0.40)
        portfolio.set_allocation(aapl, 0.60)

        actions = portfolio.rebalance()

        assert actions == [
            RebalanceAction(
                symbol="META",
                action="SELL",
                shares=Decimal("2.0000"),
                amount=Decimal("1000.00"),
            ),
            RebalanceAction(
                symbol="AAPL",
                action="BUY",
                shares=Decimal("5.0000"),
                amount=Decimal("1000.00"),
            ),
        ]

    def test_rebalance_after_market_price_change(self) -> None:
        """Verify that updating Stock.current_price() dynamically changes rebalance actions."""
        meta = Stock("META", "250.00")
        aapl = Stock("AAPL", "150.00")

        portfolio = Portfolio()
        # Initially balanced at 40% META ($4,000) and 60% AAPL ($6,000) -> Total $10,000
        portfolio.set_holding(meta, 16)
        portfolio.set_holding(aapl, 40)
        portfolio.set_allocation(meta, "0.40")
        portfolio.set_allocation(aapl, "0.60")

        assert portfolio.rebalance() == []

        # Market prices change:
        # META jumps to $300 -> 16 * 300 = $4,800
        # AAPL drops to $130 -> 40 * 130 = $5,200
        # Total value remains $10,000; targets are still $4,000 META and $6,000 AAPL
        meta.current_price(300.00)
        aapl.current_price(130.00)

        actions = portfolio.rebalance()

        # META needs -$800 / $300 = -2.6667 shares ($800.01)
        # AAPL needs +$800 / $130 = +6.1538 shares ($799.99)
        assert actions == [
            RebalanceAction(
                symbol="META",
                action="SELL",
                shares=Decimal("2.6667"),
                amount=Decimal("800.01"),
            ),
            RebalanceAction(
                symbol="AAPL",
                action="BUY",
                shares=Decimal("6.1538"),
                amount=Decimal("799.99"),
            ),
        ]

    def test_full_sell_and_buy_from_zero(self) -> None:
        """Cover union of keys: selling 100% of an exited position and buying a new one from 0."""
        tsla = Stock("TSLA", "200.00")  # To be completely sold (not in allocations)
        meta = Stock("META", "400.00")  # Kept and adjusted
        nvda = Stock("NVDA", "100.00")  # New position bought from 0 shares

        portfolio = Portfolio()
        # Current value: TSLA (10 * $200 = $2,000) + META (20 * $400 = $8,000) = $10,000
        portfolio.set_holding(tsla, 10)
        portfolio.set_holding(meta, 20)
        portfolio.register_stock(nvda)

        # Target allocations: 40% META ($4,000), 60% NVDA ($6,000), 0% TSLA
        portfolio.set_allocation(meta, 0.40)
        portfolio.set_allocation(nvda, 0.60)

        actions = portfolio.rebalance()

        # Both SELL orders (META and TSLA) must precede the BUY order (NVDA)
        assert actions == [
            RebalanceAction(
                symbol="META",
                action="SELL",
                shares=Decimal("10.0000"),
                amount=Decimal("4000.00"),
            ),
            RebalanceAction(
                symbol="TSLA",
                action="SELL",
                shares=Decimal("10.0000"),
                amount=Decimal("2000.00"),
            ),
            RebalanceAction(
                symbol="NVDA",
                action="BUY",
                shares=Decimal("60.0000"),
                amount=Decimal("6000.00"),
            ),
        ]

    def test_already_balanced_portfolio_returns_empty_list(self) -> None:
        meta = Stock("META", "100.00")
        aapl = Stock("AAPL", "100.00")

        portfolio = Portfolio(
            holdings={"META": Decimal("40"), "AAPL": Decimal("60")},
            allocations={"META": Decimal("0.40"), "AAPL": Decimal("0.60")},
            _stocks={"META": meta, "AAPL": aapl},
        )

        assert portfolio.rebalance() == []

    def test_ignores_differences_smaller_than_share_precision_threshold(self) -> None:
        """Differences rounding to less than 0.0001 shares must not generate zero-share orders."""
        meta = Stock("META", "1000.00")
        aapl = Stock("AAPL", "1000.00")

        portfolio = Portfolio()
        # Total = ~100 shares = $100,000. Deviation is 0.00004 shares (< 0.00005 ROUND_HALF_UP cutoff)
        portfolio.set_holding(meta, "40.00004")
        portfolio.set_holding(aapl, "59.99996")
        portfolio.set_allocation(meta, "0.40")
        portfolio.set_allocation(aapl, "0.60")

        assert portfolio.rebalance() == []

    def test_allocation_tolerance_allows_thirds(self) -> None:
        """Three equal allocations of 0.3333 (sum = 0.9999) are accepted within ±0.0001 tolerance."""
        a = Stock("AAA", "100.00")
        b = Stock("BBB", "100.00")
        c = Stock("CCC", "100.00")

        portfolio = Portfolio()
        portfolio.set_holding(a, 30)
        portfolio.set_allocation(a, "0.3333")
        portfolio.set_allocation(b, "0.3333")
        portfolio.set_allocation(c, "0.3333")

        actions = portfolio.rebalance()
        assert [act.action for act in actions] == ["SELL", "BUY", "BUY"]


class TestPortfolioValidation:
    """Tests for error handling and invariant enforcement."""

    @pytest.mark.parametrize("bad_weights", [(0.40, 0.50), (0.60, 0.60)])
    def test_rebalance_fails_when_allocations_do_not_sum_to_one(
        self, bad_weights: tuple[float, float]
    ) -> None:
        meta = Stock("META", 500)
        aapl = Stock("AAPL", 200)

        portfolio = Portfolio()
        portfolio.set_holding(meta, 10)
        portfolio.set_allocation(meta, bad_weights[0])
        portfolio.set_allocation(aapl, bad_weights[1])

        with pytest.raises(ValueError, match="Target allocations must sum to 1.0"):
            portfolio.rebalance()

    def test_rebalance_fails_with_empty_allocations(self) -> None:
        meta = Stock("META", 500)
        portfolio = Portfolio()
        portfolio.set_holding(meta, 10)

        with pytest.raises(ValueError, match="empty target allocations"):
            portfolio.rebalance()

    def test_rebalance_fails_when_total_portfolio_value_is_zero(self) -> None:
        meta = Stock("META", 500)
        aapl = Stock("AAPL", 200)

        portfolio = Portfolio()
        portfolio.set_allocation(meta, 0.40)
        portfolio.set_allocation(aapl, 0.60)

        with pytest.raises(ValueError, match="Total portfolio value must be strictly greater than 0"):
            portfolio.rebalance()

    def test_negative_holdings_or_invalid_allocation_weights_raise_value_error(self) -> None:
        meta = Stock("META", 500)
        portfolio = Portfolio()

        with pytest.raises(ValueError, match="cannot be negative"):
            portfolio.set_holding(meta, -5)

        with pytest.raises(ValueError, match="must be between 0 and 1"):
            portfolio.set_allocation(meta, -0.10)

        with pytest.raises(ValueError, match="must be between 0 and 1"):
            portfolio.set_allocation(meta, 1.05)

    def test_unregistered_stock_raises_key_error_on_rebalance(self) -> None:
        portfolio = Portfolio()
        portfolio.set_holding("META", 10)
        portfolio.set_allocation("META", 1.0)

        with pytest.raises(KeyError, match="Stock 'META' is not registered"):
            portfolio.rebalance()
