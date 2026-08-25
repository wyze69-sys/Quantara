"""Hardened ZIP inspection and streaming member access.

Inspects the central directory before any data is read; requires exactly one
member matching the descriptor's member pattern; rejects absolute paths,
drive prefixes, parent traversal segments, unexpected extra members, corrupt
central directories, oversized members, and excessive compression ratios;
streams the single approved CSV member via ZipFile.open without extracting to
disk so CRC failures surface mid-stream as hard failures.
"""
