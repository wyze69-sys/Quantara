"""Hardened ZIP inspection and streaming member access.

Inspects the central directory before any data is read; requires exactly one
member matching the descriptor's member pattern; rejects absolute paths,
drive prefixes, UNC paths, parent traversal segments, unexpected extra
members, corrupt central directories, oversized members, and excessive
compression ratios; streams the single approved CSV member via ZipFile.open
without extracting to disk so CRC failures surface mid-stream as hard
failures (spec §§11, 15.3).
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from quantara.errors import CORRUPT_ARCHIVE, UNSAFE_ZIP_MEMBER, QuantaraError

__all__ = [
    "MAX_COMPRESSION_RATIO",
    "MAX_MEMBER_BYTES",
    "MemberSpec",
    "UNSAFE_ZIP_ERROR",
    "CorruptArchive",
    "UnsafeZipMember",
    "inspect_zip",
    "read_member_bytes",
    "stream_member",
]

# Policy bounds with rationale: the real archive is tens of MB compressed and
# ~3–4 MB uncompressed, so 256 MiB / 100× are generous safety ceilings.
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
_CHUNK = 1 << 20


class UnsafeZipMember(QuantaraError):
    error_id = UNSAFE_ZIP_MEMBER


class CorruptArchive(QuantaraError):
    error_id = CORRUPT_ARCHIVE


# Alias so callers can catch either spelling of the unsafe-member condition.
UNSAFE_ZIP_ERROR = UnsafeZipMember

_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")
_TRAVERSAL_MARKER = ".."


def _name_is_safe(name: str) -> bool:
    if not name:
        return False
    if name.startswith(("/", "\\")):
        return False
    if _DRIVE_PATTERN.match(name):
        return False
    if name.startswith("\\\\"):
        return False
    segments = re.split(r"[\\/]", name)
    if any(segment == _TRAVERSAL_MARKER for segment in segments):
        return False
    return True


@dataclass(frozen=True)
class MemberSpec:
    name: str
    uncompressed_size: int
    compressed_size: int


def inspect_zip(archive_path: Path | str, member_pattern: str) -> MemberSpec:
    """Central-directory-only inspection; nothing is decompressed here."""
    path = Path(archive_path)
    try:
        with zipfile.ZipFile(path) as bundle:
            infos = bundle.infolist()
    except zipfile.BadZipFile as exc:
        raise CorruptArchive(f"{path.name}: not a readable ZIP ({exc})") from exc

    if not infos:
        raise CorruptArchive(f"{path.name}: archive has no members")

    for info in infos:
        if not _name_is_safe(info.filename):
            raise UnsafeZipMember(f"unsafe member name rejected: {info.filename!r}")

    pattern = re.compile(member_pattern)
    matching = [info for info in infos if pattern.fullmatch(info.filename)]
    if len(matching) != 1:
        raise CorruptArchive(
            f"{path.name}: expected exactly one member matching {member_pattern}, "
            f"found {len(matching)}"
        )
    unexpected = [info.filename for info in infos if not pattern.fullmatch(info.filename)]
    if unexpected:
        raise UnsafeZipMember(f"unexpected extra members rejected: {unexpected}")

    member = matching[0]
    if member.file_size > MAX_MEMBER_BYTES:
        raise UnsafeZipMember(
            f"declared uncompressed size {member.file_size} exceeds cap "
            f"{MAX_MEMBER_BYTES}"
        )
    if member.compress_size > 0:
        ratio = member.file_size / member.compress_size
        if ratio > MAX_COMPRESSION_RATIO:
            raise UnsafeZipMember(
                f"compression ratio {ratio:.1f}x exceeds cap {MAX_COMPRESSION_RATIO}x"
            )
    return MemberSpec(
        name=member.filename,
        uncompressed_size=member.file_size,
        compressed_size=member.compress_size,
    )


def stream_member(archive_path: Path | str, spec: MemberSpec) -> Iterator[bytes]:
    """Stream the approved member without filesystem extraction.

    CRC failures surface as CorruptArchive while streaming, never after a
    silent partial read.
    """
    try:
        with zipfile.ZipFile(Path(archive_path)) as bundle:
            with bundle.open(spec.name) as handle:
                total = 0
                while chunk := handle.read(_CHUNK):
                    total += len(chunk)
                    yield chunk
                if total != spec.uncompressed_size:
                    raise CorruptArchive(
                        f"streamed size {total} differs from declared "
                        f"{spec.uncompressed_size}"
                    )
    except zipfile.BadZipFile as exc:
        raise CorruptArchive(f"CRC or structure failure while streaming: {exc}") from exc


def read_member_bytes(archive_path: Path | str, spec: MemberSpec) -> bytes:
    return b"".join(stream_member(archive_path, spec))
