"""RFC 8785 JSON Canonicalization Scheme serialization subset.

Canonicalizes strings, integers, booleans, nulls, arrays, and objects with
shortest string escaping (RFC 8785 §3.2.2.2) and property sorting by UTF-16
code units (§3.2.3). Binary floats are rejected unconditionally: hashing
payloads admit only strings, integers, booleans, nulls, arrays, and objects.
The production serializer never validates its own output; correctness is
pinned by independently generated RFC-derived test vectors.
"""

from __future__ import annotations

from typing import Any

__all__ = ["JcsFloatRejected", "canonicalize"]

_STRING_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class JcsFloatRejected(TypeError):
    """Raised when a float appears anywhere in a canonicalization payload."""


def _serialize_string(value: str, out: list[str]) -> None:
    pieces: list[str] = ['"']
    for char in value:
        escape = _STRING_ESCAPES.get(char)
        if escape is not None:
            pieces.append(escape)
        elif char < "\u0020":
            pieces.append(f"\\u{ord(char):04x}")
        else:
            pieces.append(char)
    pieces.append('"')
    out.append("".join(pieces))


def _serialize(value: Any, out: list[str]) -> None:
    if value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif value is None:
        out.append("null")
    elif isinstance(value, int):
        out.append(str(value))
    elif isinstance(value, str):
        _serialize_string(value, out)
    elif isinstance(value, list):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _serialize(item, out)
        out.append("]")
    elif isinstance(value, dict):
        # RFC 8785 §3.2.3: sort properties by UTF-16 code units.
        ordered_keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        out.append("{")
        for index, key in enumerate(ordered_keys):
            if index:
                out.append(",")
            _serialize_string(key, out)
            out.append(":")
            _serialize(value[key], out)
        out.append("}")
    elif isinstance(value, float):
        raise JcsFloatRejected(
            "binary floats are forbidden in canonicalization payloads"
        )
    else:
        raise TypeError(f"type not serializable under JCS subset: {type(value)!r}")


def canonicalize(value: Any) -> str:
    """Serialize *value* as an RFC 8785 JCS string; floats are hard-rejected."""
    out: list[str] = []
    _serialize(value, out)
    return "".join(out)
