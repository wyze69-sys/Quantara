"""Verified artifact acquisition.

Streams the official ZIP and checksum documents into unique staging paths
under data/staging/<attempt_id>/ with running SHA-256 and size caps; parses the
checksum document strictly; verifies local vs official hashes; reuses matching
retained artifacts byte-for-byte; quarantines same-name/different-hash
conflicts; retries only eligible transient failures with bounded backoff; and
follows redirects hop-by-hop against the descriptor's allow-listed hosts.
"""
