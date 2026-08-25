"""Archive-security tests (spec §§11, 15.3) using synthetic ZIP fixtures."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from quantara.archive import (
    UNSAFE_ZIP_ERROR,
    CorruptArchive,
    MemberSpec,
    inspect_zip,
    read_member_bytes,
)

PATTERN = r"^BTCUSDT-1m-2024-01\.csv$"
CSV_NAME = "BTCUSDT-1m-2024-01.csv"
CSV_BYTES = (
    b"open_time,open,high,low,close,volume,close_time,"
    b"quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    b"1704067200000,42571.90,42600.00,42500.10,42590.50,12.5,"
    b"1704067259999,500000.25,3210,6.25,250000.125,0\n"
)


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, blob in members.items():
            zf.writestr(name, blob)
    return path


@pytest.fixture()
def good_archive(tmp_path: Path) -> Path:
    return write_zip(tmp_path / "good.zip", {CSV_NAME: CSV_BYTES})


def test_inspect_accepts_exactly_one_matching_member(good_archive: Path) -> None:
    spec = inspect_zip(good_archive, PATTERN)
    assert isinstance(spec, MemberSpec)
    assert spec.name == CSV_NAME
    assert spec.uncompressed_size == len(CSV_BYTES)


def test_missing_csv_member_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "missing.zip", {"other.txt": b"x"})
    with pytest.raises(CorruptArchive):
        inspect_zip(archive, PATTERN)


def test_wrong_csv_name_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "wrong.zip", {"WRONG.csv": CSV_BYTES})
    with pytest.raises(CorruptArchive):
        inspect_zip(archive, PATTERN)


def test_duplicate_member_names_are_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "dup.zip", {CSV_NAME: CSV_BYTES, "nested/" + CSV_NAME: CSV_BYTES}
    )
    # The nested variant is an unexpected extra member under the anchored
    # pattern; either way the archive must be rejected.
    with pytest.raises((CorruptArchive, UNSAFE_ZIP_ERROR)):
        inspect_zip(archive, PATTERN)


def test_identical_duplicate_member_names_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "dup2.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(CSV_NAME, CSV_BYTES)
        zf.writestr(CSV_NAME, CSV_BYTES)  # same name twice
    with pytest.raises(CorruptArchive):
        inspect_zip(target, PATTERN)


def test_unexpected_extra_members_are_rejected(tmp_path: Path) -> None:
    archive = write_zip(
        tmp_path / "extra.zip", {CSV_NAME: CSV_BYTES, "readme.txt": b"sneaky"}
    )
    with pytest.raises(UNSAFE_ZIP_ERROR):
        inspect_zip(archive, PATTERN)


@pytest.mark.parametrize(
    "evil_name",
    [
        "/abs/BTCUSDT-1m-2024-01.csv",
        "C:/BTCUSDT-1m-2024-01.csv",
        "C:\\\\BTCUSDT-1m-2024-01.csv",
        "../BTCUSDT-1m-2024-01.csv",
        "a/../../BTCUSDT-1m-2024-01.csv",
        "\\\\server\\\\share.csv",
    ],
)
def test_unsafe_member_names_are_rejected(tmp_path: Path, evil_name: str) -> None:
    archive = write_zip(tmp_path / "evil.zip", {evil_name: CSV_BYTES})
    with pytest.raises((UNSAFE_ZIP_ERROR, CorruptArchive)):
        inspect_zip(archive, PATTERN)


def test_corrupt_central_directory_is_rejected(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "corrupt.zip", {CSV_NAME: CSV_BYTES})
    blob = bytearray(archive.read_bytes())
    blob[-40:-10] = b"\x00" * 30  # smash central directory records
    target = tmp_path / "smashed.zip"
    target.write_bytes(bytes(blob))
    with pytest.raises(CorruptArchive):
        inspect_zip(target, PATTERN)


def test_random_bytes_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "noise.zip"
    target.write_bytes(b"this is definitely not a zip archive" * 10)
    with pytest.raises(CorruptArchive):
        inspect_zip(target, PATTERN)


def test_oversized_declared_member_is_rejected(
    tmp_path: Path, good_archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import quantara.archive as archive_module

    monkeypatch.setattr(archive_module, "MAX_MEMBER_BYTES", 8)
    with pytest.raises(UNSAFE_ZIP_ERROR):
        inspect_zip(good_archive, PATTERN)


def test_excessive_compression_ratio_is_rejected(tmp_path: Path) -> None:
    bomb = write_zip(tmp_path / "ratio.zip", {CSV_NAME: b"\x00" * (2 << 20)})
    with pytest.raises(UNSAFE_ZIP_ERROR):
        inspect_zip(bomb, PATTERN)


def test_streaming_returns_exact_bytes(good_archive: Path) -> None:
    spec = inspect_zip(good_archive, PATTERN)
    assert read_member_bytes(good_archive, spec) == CSV_BYTES


def test_crc_corruption_surfaces_mid_stream(tmp_path: Path) -> None:
    archive = write_zip(tmp_path / "crc.zip", {CSV_NAME: CSV_BYTES * 64})
    blob = bytearray(archive.read_bytes())
    # Locate the member's compressed data via its local file header and flip
    # one byte inside the deflate stream itself.
    with zipfile.ZipFile(archive) as zf:
        info = zf.infolist()[0]
        header_offset = info.header_offset
        name_len = int.from_bytes(blob[header_offset + 26 : header_offset + 28], "little")
        extra_len = int.from_bytes(blob[header_offset + 28 : header_offset + 30], "little")
        data_start = header_offset + 30 + name_len + extra_len
    blob[data_start + info.compress_size // 2] ^= 0xFF
    target = tmp_path / "crc-flipped.zip"
    target.write_bytes(bytes(blob))
    spec = inspect_zip(target, PATTERN)
    with pytest.raises(CorruptArchive):
        read_member_bytes(target, spec)
