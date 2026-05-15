from __future__ import annotations

import pytest

from open_composer.expressions import ExpressionSafetyError, assert_expression_safe


@pytest.mark.parametrize(
    "safe_expr",
    [
        "close > ema(close, 3)",
        "macd(close, 2, 4) > macd_signal(close, 2, 4, 2)",
        "zscore(close, 3) > 0",
        "crossover(close, sma(close, 5))",
        "(close - ema(close, 5)) / ema(close, 5) > 0.01",
        "zscore(close, 20) > -1.0",
        "atr(14) > 0",
        "bollinger_upper(close, 20, 2.0) > close",
    ],
)
def test_safe_expressions_pass_ast_safety(safe_expr: str) -> None:
    assert_expression_safe(safe_expr)


@pytest.mark.parametrize(
    ("evil_expr", "reason"),
    [
        ("__import__('os').system('rm -rf /')", "forbidden function call"),
        ("eval('1+1')", "forbidden function call"),
        ("open('/etc/passwd').read()", "forbidden function call"),
        ("getattr(close, '__class__')", "forbidden function call"),
        ("subprocess.call(['ls'])", "forbidden name"),
        ("close.__dict__", "forbidden AST node"),
        ("[i for i in range(10)]", "forbidden AST node"),
        ("lambda x: x", "forbidden AST node"),
        ("close[0]", "forbidden AST node"),
    ],
)
def test_unsafe_expressions_rejected(evil_expr: str, reason: str) -> None:
    with pytest.raises(ExpressionSafetyError, match=reason):
        assert_expression_safe(evil_expr)
