"""Exact kline parsing and numeric policy.

Validates the exact ordered 12-name UTF-8 header contract; parses unsigned
base-10 epoch-millisecond timestamps directly to integers; parses numeric
fields through decimal.Decimal only (binary floats are never constructed);
enforces the representability budget for decimal128(38,18) without rounding;
and keeps the source ignore field verbatim.
"""
