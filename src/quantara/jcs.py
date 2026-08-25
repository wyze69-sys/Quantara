"""RFC 8785 JSON Canonicalization Scheme serialization subset.

Canonicalizes strings, integers, booleans, nulls, arrays, and objects with
shortest string escaping and key ordering by UTF-16 code units. Binary floats
are rejected unconditionally. The production serializer never validates its
own output; correctness is pinned by independently generated RFC test vectors.
"""
