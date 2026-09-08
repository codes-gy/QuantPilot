from app.features.strategy.engine import MarketSnapshot, Signal, evaluate_entry


def test_ma_cross_triggers_buy_when_fast_above_slow():
    history = [10, 10, 10, 10, 10, 12, 14, 16, 18, 20]
    snapshot = MarketSnapshot(symbol="TEST", price=20, price_history=history)
    rule = {"type": "ma_cross", "fast": 3, "slow": 10}

    assert evaluate_entry(rule, snapshot) == Signal.BUY


def test_ma_cross_holds_when_not_enough_history():
    snapshot = MarketSnapshot(symbol="TEST", price=20, price_history=[20])
    rule = {"type": "ma_cross", "fast": 3, "slow": 10}

    assert evaluate_entry(rule, snapshot) == Signal.HOLD
