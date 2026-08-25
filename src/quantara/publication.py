"""Publication protocol.

Content-addressed immutable object store under data/objects/{raw,checksum,
normalized}/sha256/, staged commit directories atomically renamed into place,
current.json pointer replaced only after independent graph verification, and
idempotent VERIFIED_NO_OP detection. Readers never discover partial graphs.
"""
