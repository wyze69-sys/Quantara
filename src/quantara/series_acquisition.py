"""D02: closed, rights-gated acquisition of the frozen source-object inventory.

Binance requires its adjacent operator checksum. Remote Kraken acquisition
retains the opaque raw DEFLATE member. Explicit local acquisition reads the ZIP
in place, verifies the same A9 anchors, and retains only the 2020-2024 CSV slice.
Only timestamp prefixes are interpreted; market values are never decoded.

Acquirer supplies the established retry/backoff policy and evidence containers;
its buffering transport and replace-based publication are deliberately overridden
for streaming caps, range validation and atomic no-clobber object creation.
Legacy acquisition, descriptors, archives and published identities are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
import uuid
import zipfile
import zlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx

from quantara.acquisition import (
    DEFAULT_MAX_ZIP_BYTES,
    MAX_ATTEMPTS,
    MAX_REDIRECT_HOPS,
    RETRYABLE_STATUS,
    Acquirer,
    ChecksumMismatch,
    DownloadFailed,
    InvalidChecksumDocument,
    NonAllowlistedHost,
    RetryEvidence,
    parse_checksum_document,
)
from quantara.archive import (
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    CorruptArchive,
    inspect_zip,
    stream_member,
)
from quantara.series_descriptor import SeriesArchive, SeriesDescriptor, SeriesDescriptorError

_ROOT = Path(__file__).resolve().parents[2]
_CHUNK = 64 * 1024
_CHECKSUM_CAP = 8192
_DIRECTORY_CAP = 4 * 1024 * 1024
_CONFIRMATION_CAP = 64 * 1024


@dataclass(frozen=True)
class _KrakenAnchor:
    member: str = 'master_q4/XBTUSD_60.csv'
    remote_size: int = 7885068519
    member_count: int = 24056
    directory_start: int = 7882536772
    directory_end: int = 7885068420
    header_offset: int = 4750749207
    data_start: int = 4750749292
    compressed_size: int = 2237806
    member_size: int = 5640237
    crc32: int = 0xc351083a
    member_sha256: str = 'b45e7ce94911d4c1d13bf5c2e270c9219b81631292f7c40bab27e81f7f3f8297'
    audit_path: str = 'temp/audit_a9_kraken/a9_kraken_range_probe_v1.json'
    audit_sha256_lf: str = '808c1a17c0b710187c36254c31992d2b645cc2533b7fec4b4c0d05b7d42f7c14'


# Frozen A9 acquisition metadata only, independently bound by Protocol v1's
# normalized-text audit reference. Never load the full probe JSON at runtime;
# its archive-wide first_row/last_row fields are outside this acquisition API.
_KRAKEN = _KrakenAnchor()


@dataclass(frozen=True)
class SeriesAcquisitionEvidence:
    series_id: str
    period: str
    attempt_id: str
    raw_path: Path
    raw_sha256: str
    raw_size: int
    raw_format: str
    member: str
    member_sha256: str
    member_size: int
    member_crc32: str
    checksum_path: Path | None
    checksum_sha256: str | None
    official_digest: str | None
    reused_raw: bool
    integrity_basis: str
    evidence_path: Path


def source_inventory(descriptor: SeriesDescriptor) -> tuple[SeriesArchive, ...]:
    """Frozen expected objects, not a claim of remote existence or row coverage."""
    descriptor = _closed(descriptor)
    return tuple(descriptor.archive_for(period) for period in descriptor.object_periods)


def _closed(descriptor: SeriesDescriptor) -> SeriesDescriptor:
    if type(descriptor) is not SeriesDescriptor:
        raise SeriesDescriptorError('acquisition requires a closed SeriesDescriptor')
    return SeriesDescriptor(descriptor.series_id)


def _digest_file(path: Path, cap: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ChecksumMismatch('raw/checksum object is not a regular retained file')
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as handle:
        while block := handle.read(_CHUNK):
            size += len(block)
            if size > cap:
                raise DownloadFailed('retained or staged object exceeds size cap')
            digest.update(block)
    return digest.hexdigest(), size


def _zip64(extra: bytes, size: int, compressed: int, offset: int) -> tuple[int, int, int]:
    """Resolve ZIP64 sentinel fields in their specified order, metadata only."""
    cursor, extended = 0, None
    while cursor < len(extra):
        if cursor + 4 > len(extra):
            raise CorruptArchive('truncated ZIP extra field')
        kind, length = struct.unpack_from('<HH', extra, cursor)
        cursor += 4
        if cursor + length > len(extra):
            raise CorruptArchive('truncated ZIP extra payload')
        if kind == 1:
            if extended is not None:
                raise CorruptArchive('duplicate ZIP64 extra field')
            extended = extra[cursor:cursor + length]
        cursor += length
    values, cursor = [size, compressed, offset], 0
    for index, value in enumerate(values):
        if value == 0xffffffff:
            if extended is None or cursor + 8 > len(extended):
                raise CorruptArchive('missing ZIP64 sentinel value')
            values[index] = struct.unpack_from('<Q', extended, cursor)[0]
            cursor += 8
    return tuple(values)


def _verify_directory(blob: bytes, anchor: _KrakenAnchor) -> int:
    cursor, count, matches, member_flags = 0, 0, 0, 0
    while cursor < len(blob):
        if cursor + 46 > len(blob):
            raise CorruptArchive('truncated central directory')
        fields = struct.unpack_from('<4s6H3I5H2I', blob, cursor)
        if fields[0] != b'PK\x01\x02':
            raise CorruptArchive('invalid central directory signature')
        flags, method, crc, compressed, size = (
            fields[3], fields[4], fields[7], fields[8], fields[9]
        )
        name_len, extra_len, comment_len, disk = fields[10:14]
        end = cursor + 46 + name_len + extra_len + comment_len
        if end > len(blob):
            raise CorruptArchive('central directory entry exceeds pinned range')
        name = blob[cursor + 46:cursor + 46 + name_len]
        if name == anchor.member.encode('ascii'):
            matches += 1
            extra = blob[cursor + 46 + name_len:cursor + 46 + name_len + extra_len]
            size, compressed, offset = _zip64(extra, size, compressed, fields[16])
            if (size, compressed, offset, crc) != (
                anchor.member_size, anchor.compressed_size, anchor.header_offset, anchor.crc32,
            ):
                raise CorruptArchive('Kraken central-directory anchor drift')
            if disk != 0 or method != zipfile.ZIP_DEFLATED or flags & ~0x080e:
                raise CorruptArchive('unsupported Kraken member encoding or encryption')
            member_flags = flags
        count += 1
        cursor = end
    if matches != 1 or count != anchor.member_count:
        raise CorruptArchive('Kraken directory member count or identity drift')
    return member_flags


def _verify_deflate(chunks, anchor: _KrakenAnchor, sink=None) -> tuple[str, int, int]:
    """Shared bounded full-member verification; optional timestamp-only selector."""
    if (anchor.member_size > MAX_MEMBER_BYTES or anchor.compressed_size <= 0
            or anchor.member_size > anchor.compressed_size * MAX_COMPRESSION_RATIO):
        raise CorruptArchive('Kraken member exceeds archive safety bounds')
    decoder, digest, size, crc = zlib.decompressobj(-15), hashlib.sha256(), 0, 0
    try:
        for compressed in chunks:
            while compressed:
                block = decoder.decompress(compressed, _CHUNK)
                compressed = decoder.unconsumed_tail
                size += len(block)
                if size > anchor.member_size:
                    raise CorruptArchive('Kraken inflated size exceeds pinned size')
                digest.update(block)
                crc = zlib.crc32(block, crc)
                if sink is not None:
                    sink.feed(block)
                del block
                if decoder.unused_data:
                    raise CorruptArchive('trailing bytes after Kraken DEFLATE stream')
        if not decoder.eof or size != anchor.member_size:
            raise CorruptArchive('truncated Kraken DEFLATE stream or size drift')
    except zlib.error as exc:
        raise CorruptArchive('invalid Kraken DEFLATE stream') from exc
    if crc != anchor.crc32:
        raise ChecksumMismatch('Kraken computed CRC differs from A9 central-directory CRC')
    if digest.hexdigest() != anchor.member_sha256:
        raise ChecksumMismatch('Kraken computed member SHA-256 differs from A9')
    return digest.hexdigest(), size, crc


def _hash_deflate(path: Path, anchor: _KrakenAnchor) -> tuple[str, int, int]:
    """Opaque hash-only sink; never decode, split, persist or return inflated bytes."""
    with path.open('rb') as handle:
        return _verify_deflate(iter(lambda: handle.read(_CHUNK), b''), anchor)


class _KrakenWindow:
    """Stream timestamp prefixes; discard excluded payloads without row buffering.

    Writes selected source bytes exactly, including decimals and line endings.
    Counts describe source inventory only, not canonical quality approval.
    """

    def __init__(self, output):
        self.output = output
        self.prefix = bytearray()
        self.in_payload = False
        self.keep = False
        self.total = 0
        self.rows = 0
        self.timestamps = set()
        self.years = {str(year): 0 for year in range(2020, 2025)}

    def feed(self, block: bytes) -> None:
        cursor = 0
        while cursor < len(block):
            if not self.in_payload:
                byte = block[cursor]
                cursor += 1
                if byte != ord(','):
                    if not ord('0') <= byte <= ord('9') or len(self.prefix) >= 10:
                        raise CorruptArchive('invalid Kraken timestamp prefix')
                    self.prefix.append(byte)
                    continue
                if not self.prefix:
                    raise CorruptArchive('missing Kraken timestamp prefix')
                timestamp = int(self.prefix)
                self.keep = 1577836800 <= timestamp < 1735689600
                self.total += 1
                if self.keep:
                    if timestamp % 3600:
                        raise CorruptArchive('Kraken timestamp is off the hourly grid')
                    self.rows += 1
                    self.timestamps.add(timestamp)
                    self.years[str(datetime.fromtimestamp(timestamp, UTC).year)] += 1
                    self.output.write(self.prefix)
                    self.output.write(b',')
                self.prefix.clear()
                self.in_payload = True
            else:
                newline = block.find(b'\n', cursor)
                end = len(block) if newline < 0 else newline + 1
                if self.keep:
                    self.output.write(memoryview(block)[cursor:end])
                cursor = end
                if newline >= 0:
                    self.in_payload = False
                    self.keep = False

    def inventory(self) -> dict:
        if self.prefix:
            raise CorruptArchive('truncated Kraken timestamp prefix')
        return {
            'window_start_ts': 1577836800, 'window_end_exclusive_ts': 1735689600,
            'total_member_rows': self.total, 'rows': self.rows,
            'unique_timestamps': len(self.timestamps),
            'duplicate_timestamps': self.rows - len(self.timestamps),
            'expected_hours': 43848, 'missing_hours': 43848 - len(self.timestamps),
            'per_year_rows': self.years,
        }


class _ConfirmationForm(HTMLParser):
    """Parse only the A9-documented public download form; never execute HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.fields = {}
        self.in_form = False

    def handle_starttag(self, tag, attrs):
        if tag not in ('form', 'input'):
            return
        attributes = dict(attrs)
        if len(attributes) != len(attrs):
            raise DownloadFailed('ambiguous download confirmation attributes')
        if tag == 'form':
            self.forms.append(attributes)
            self.in_form = True
        elif self.in_form:
            name = attributes.get('name')
            if name in ('id', 'export', 'confirm', 'uuid'):
                if name in self.fields:
                    raise DownloadFailed('duplicate download confirmation field')
                self.fields[name] = attributes.get('value')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.in_form = False


def _confirmed_url(path: Path, archive: SeriesArchive) -> str:
    """Same object/host confirmation from A9 probe, not another data source."""
    parser = _ConfirmationForm()
    try:
        parser.feed(path.read_text(encoding='utf-8'))
        parser.close()
    except UnicodeError as exc:
        raise DownloadFailed('invalid download confirmation encoding') from exc
    base = httpx.URL(archive.archive_url)
    if (len(parser.forms) != 1
            or parser.forms[0].get('action') != 'https://drive.usercontent.google.com/download'
            or parser.forms[0].get('method', '').lower() != 'get'
            or parser.fields.get('id') != base.params['id']
            or parser.fields.get('export') != 'download'
            or parser.fields.get('confirm') != 't'):
        raise DownloadFailed('download confirmation does not bind the frozen object')
    nonce = parser.fields.get('uuid')
    if not isinstance(nonce, str) or not re.fullmatch(
        r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', nonce,
    ):
        raise DownloadFailed('invalid public download confirmation nonce')
    return str(base.copy_merge_params({'confirm': 't', 'uuid': nonce}))


class SeriesAcquirer(Acquirer):
    """One attempt, one closed object; rights and integrity failures are fail-closed.

    transport/sleeper support deterministic offline tests. repo_root locates
    trusted rights configuration, never comes from an untrusted descriptor.
    No caller-supplied URL, anchor, host, attempt path or source fallback exists.
    """

    def __init__(
        self, descriptor: SeriesDescriptor, period: str, data_root: Path,
        *, transport: httpx.BaseTransport | None = None, sleeper=None,
        max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES, repo_root: Path = _ROOT,
    ) -> None:
        descriptor = _closed(descriptor)
        self.archive = descriptor.archive_for(period)
        if type(max_zip_bytes) is not int or not 0 < max_zip_bytes <= DEFAULT_MAX_ZIP_BYTES:
            raise ValueError('max_zip_bytes must be a positive bounded integer')
        super().__init__(
            descriptor, data_root, uuid.uuid4().hex, transport, sleeper, max_zip_bytes,
        )
        self.repo_root = Path(repo_root)
        self.requests: list[dict] = []
        self._used = False
        self._staging = self.data_root / 'staging' / self.attempt_id

    def acquire(self) -> SeriesAcquisitionEvidence:
        if self._used:
            raise DownloadFailed('a SeriesAcquirer instance represents exactly one attempt')
        self._used = True
        self._staging.mkdir(parents=True, exist_ok=False)
        evidence_path = self._staging / 'attempt.json'
        kraken = self.archive.checksum_url is None
        record = {
            'schema': 'quantara.series-acquisition-attempt/v1',
            'attempt_id': self.attempt_id, 'series_id': self.archive.series_id,
            'period': self.archive.period, 'source_url': self.archive.archive_url,
            'started_at': datetime.now(UTC).isoformat(), 'status': 'BLOCKED',
            'market_rows_parsed': 0, 'operator_signature': False,
            'integrity_note': (
                'Computed member SHA-256 bound to frozen A9; not an operator signature.'
                if kraken else 'Adjacent operator checksum, not a digital signature.'
            ),
        }
        if kraken:
            record['anchors'] = asdict(_KRAKEN)
        local = os.environ.get('QUANTARA_KRAKEN_ARCHIVE') if kraken else None
        record['acquisition_source'] = 'local_archive' if local is not None else 'remote'
        try:
            rights = self.descriptor.load_rights(self.repo_root)
            record['rights_record'] = rights.record_id
            operations = ('acquire_internal', 'retain_raw_internal')
            record['rights_states'] = {name: rights.operations[name].state for name in operations}
            if not all(rights.permits(name) for name in operations):
                raise SeriesDescriptorError('rights prohibit acquisition or raw retention')
            if kraken and local is not None:
                result = self._kraken_local(evidence_path, local, record)
            else:
                result = self._kraken(evidence_path) if kraken else self._binance(evidence_path)
            record.update({
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(result).items()
            })
            record['status'] = 'VERIFIED'
            return result
        except BaseException as exc:
            # Never include remote bodies or value-bearing exception messages.
            record['error_type'] = type(exc).__name__
            raise
        finally:
            record.update(
                finished_at=datetime.now(UTC).isoformat(), requests=self.requests,
                retry_evidence=[asdict(item) for item in self.retry_evidence],
                redirect_hops=self.redirect_hops, http_statuses=self.http_statuses,
            )
            with evidence_path.open('x', encoding='utf-8', newline='\n') as handle:
                json.dump(record, handle, indent=2, sort_keys=True)
                handle.write('\n')

    def _store(self, path: Path, kind: str, digest: str, cap: int) -> tuple[Path, bool]:
        actual, _ = _digest_file(path, cap)
        if actual != digest:
            raise ChecksumMismatch('staged object changed before retention')
        directory = self.data_root / 'objects' / kind / 'sha256'
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / digest
        try:
            # Atomic create-if-absent, including concurrent workers. Never replace
            # a retained object. Staging and objects are on the same data volume.
            os.link(path, target)
            reused = False
        except FileExistsError:
            actual, _ = _digest_file(target, cap)
            if actual != digest:
                raise ChecksumMismatch('retained object corruption; bytes preserved') from None
            reused = True
        return target, reused

    def _binance(self, evidence_path: Path) -> SeriesAcquisitionEvidence:
        checksum = self._fetch(self.archive.checksum_url, _CHECKSUM_CAP)
        try:
            document = checksum.read_text(encoding='utf-8')
        except UnicodeError as exc:
            raise InvalidChecksumDocument('checksum is not UTF-8') from exc
        official = parse_checksum_document(document, self.archive.member[:-4] + '.zip')
        retained = self.data_root / 'objects/raw/sha256' / official
        reused = retained.exists() or retained.is_symlink()
        raw = retained if reused else self._fetch(self.archive.archive_url, self.max_zip_bytes)
        raw_sha, raw_size = _digest_file(raw, self.max_zip_bytes)
        if raw_sha != official:
            raise ChecksumMismatch('Binance ZIP differs from mandatory operator checksum')
        spec = inspect_zip(raw, self.archive.member_pattern)
        digest, crc = hashlib.sha256(), 0
        try:
            for block in stream_member(raw, spec):
                digest.update(block)
                crc = zlib.crc32(block, crc)
        except (zlib.error, RuntimeError, NotImplementedError) as exc:
            raise CorruptArchive('unsupported or corrupt Binance ZIP member') from exc
        checksum_sha, _ = _digest_file(checksum, _CHECKSUM_CAP)
        checksum_path, _ = self._store(checksum, 'checksum', checksum_sha, _CHECKSUM_CAP)
        if not reused:
            raw, reused = self._store(raw, 'raw', raw_sha, self.max_zip_bytes)
        return SeriesAcquisitionEvidence(
            self.archive.series_id, self.archive.period, self.attempt_id,
            raw, raw_sha, raw_size, 'zip', spec.name, digest.hexdigest(),
            spec.uncompressed_size, f'{crc:08x}', checksum_path, checksum_sha,
            official, reused, 'binance_adjacent_checksum', evidence_path,
        )

    def _kraken_metadata(self, read_range) -> None:
        """Identical pinned central-directory and local-header checks for both sources."""
        anchor = _KRAKEN
        if self.archive.member != anchor.member:
            raise CorruptArchive('Kraken descriptor/member anchor mismatch')
        directory = read_range(
            _DIRECTORY_CAP, (anchor.directory_start, anchor.directory_end),
        )
        flags = _verify_directory(directory, anchor)
        header = read_range(30, (anchor.header_offset, anchor.header_offset + 29))
        fields = struct.unpack('<4s5H3I2H', header)
        if fields[0] != b'PK\x03\x04' or fields[2] != flags or fields[3] != 8:
            raise CorruptArchive('Kraken local header differs from central directory')
        name_len, extra_len = fields[-2:]
        if anchor.header_offset + 30 + name_len + extra_len != anchor.data_start:
            raise CorruptArchive('Kraken local-header range drift')
        metadata = read_range(
            name_len + extra_len, (anchor.header_offset + 30, anchor.data_start - 1),
        )
        if metadata[:name_len] != anchor.member.encode('ascii'):
            raise CorruptArchive('Kraken local-header member identity drift')
        size, compressed, _ = _zip64(metadata[name_len:], fields[8], fields[7], 0)
        if flags & 8:
            valid = (fields[6] in (0, anchor.crc32) and size in (0, anchor.member_size)
                     and compressed in (0, anchor.compressed_size))
        else:
            valid = (fields[6], size, compressed) == (
                anchor.crc32, anchor.member_size, anchor.compressed_size,
            )
        if not valid:
            raise CorruptArchive('Kraken local-header integrity anchor drift')

    def _kraken(self, evidence_path: Path) -> SeriesAcquisitionEvidence:
        anchor, url = _KRAKEN, self.archive.archive_url
        self._kraken_metadata(lambda cap, extent: self._fetch(url, cap, extent).read_bytes())
        raw = self._fetch(
            url, min(self.max_zip_bytes, anchor.compressed_size),
            (anchor.data_start, anchor.data_start + anchor.compressed_size - 1),
        )
        member_sha, member_size, crc = _hash_deflate(raw, anchor)
        raw_sha, raw_size = _digest_file(raw, self.max_zip_bytes)
        raw, reused = self._store(raw, 'raw', raw_sha, self.max_zip_bytes)
        return SeriesAcquisitionEvidence(
            self.archive.series_id, self.archive.period, self.attempt_id,
            raw, raw_sha, raw_size, 'zip_raw_deflate_member', anchor.member,
            member_sha, member_size, f'{crc:08x}', None, None, None, reused,
            'kraken_frozen_a9_member_hash', evidence_path,
        )

    def _kraken_local(self, evidence_path, local, record) -> SeriesAcquisitionEvidence:
        anchor = _KRAKEN
        path = Path(local)
        if not local.strip() or path.is_symlink() or not path.is_file():
            raise DownloadFailed('explicit local Kraken archive must be a regular file')
        record['local_archive_path'] = str(path.resolve())
        selected = self._staging / 'kraken-2020-2024.csv'
        with path.open('rb') as archive:
            before = os.fstat(archive.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != anchor.remote_size:
                raise CorruptArchive('local Kraken archive size differs from A9')

            def chunks(cap, extent):
                start, end = extent
                size = end - start + 1
                if not 0 <= start <= end < anchor.remote_size or size > cap:
                    raise DownloadFailed('invalid or oversized frozen local byte range')
                archive.seek(start)
                remaining = size
                while remaining:
                    block = archive.read(min(_CHUNK, remaining))
                    if not block:
                        raise CorruptArchive('truncated local Kraken byte range')
                    remaining -= len(block)
                    yield block

            self._kraken_metadata(lambda cap, extent: b''.join(chunks(cap, extent)))
            with selected.open('xb') as output:
                window = _KrakenWindow(output)
                member_sha, member_size, crc = _verify_deflate(
                    chunks(min(self.max_zip_bytes, anchor.compressed_size), (
                        anchor.data_start, anchor.data_start + anchor.compressed_size - 1,
                    )), anchor, window,
                )
                inventory = window.inventory()
                output.flush()
                os.fsync(output.fileno())
            after = os.fstat(archive.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise CorruptArchive('local Kraken archive changed during acquisition')
        raw_sha, raw_size = _digest_file(selected, MAX_MEMBER_BYTES)
        raw, reused = self._store(selected, 'raw', raw_sha, MAX_MEMBER_BYTES)
        record['inventory'] = inventory
        return SeriesAcquisitionEvidence(
            self.archive.series_id, self.archive.period, self.attempt_id,
            raw, raw_sha, raw_size, 'csv_2020_2024', anchor.member,
            member_sha, member_size, f'{crc:08x}', None, None, None, reused,
            'kraken_frozen_a9_member_hash', evidence_path,
        )

    def _allowed(self, url: str) -> None:
        try:
            parsed = httpx.URL(url)
        except httpx.InvalidURL as exc:
            raise NonAllowlistedHost('invalid source URL') from exc
        if (parsed.scheme != 'https' or parsed.host not in self.descriptor.allowed_hosts
                or parsed.userinfo or parsed.port not in (None, 443) or parsed.fragment):
            raise NonAllowlistedHost('source/redirect authority is not allowlisted')

    def _fetch(self, url: str, cap: int, byte_range: tuple[int, int] | None = None) -> Path:
        if byte_range is not None:
            start, end = byte_range
            if not 0 <= start <= end < _KRAKEN.remote_size or end - start + 1 > cap:
                raise DownloadFailed('invalid or oversized frozen byte range')
        for attempt in range(MAX_ATTEMPTS):
            current = url
            try:
                with httpx.Client(
                    transport=self.transport, follow_redirects=False, timeout=30.0,
                ) as client:
                    for hop in range(MAX_REDIRECT_HOPS + 1):
                        self._allowed(current)
                        headers = {'Accept-Encoding': 'identity'}
                        if byte_range is not None:
                            headers['Range'] = f'bytes={byte_range[0]}-{byte_range[1]}'
                        item = {
                            'url': current, 'range': headers.get('Range'),
                            'try': attempt + 1, 'hop': hop, 'received_bytes': 0,
                        }
                        self.requests.append(item)
                        with client.stream('GET', current, headers=headers) as response:
                            item['status'] = response.status_code
                            self.http_statuses.append(response.status_code)
                            if response.status_code in RETRYABLE_STATUS:
                                break
                            if response.is_redirect:
                                location = response.headers.get('location')
                                if not location or hop == MAX_REDIRECT_HOPS:
                                    raise DownloadFailed('missing location or redirect limit')
                                current = str(response.url.join(location))
                                self._allowed(current)
                                self.redirect_hops.append(current)
                                continue
                            expected_status = 206 if byte_range is not None else 200
                            content_type = response.headers.get('content-type', '').split(';')[0]
                            if (byte_range is not None and response.status_code == 200
                                    and current == url == self.archive.archive_url
                                    and content_type.lower() == 'text/html'):
                                # A9 performs this confirmation for each range. Bound
                                # its HTML separately; a full ZIP/CSV body is refused.
                                item['kind'] = 'google_download_confirmation'
                                length = self._response_length(response, _CONFIRMATION_CAP, None)
                                page = self._save_body(response, _CONFIRMATION_CAP, length, item)
                                current = _confirmed_url(page, self.archive)
                                self._allowed(current)
                                continue
                            if response.status_code != expected_status:
                                raise DownloadFailed('unexpected HTTP status; no fallback')
                            length = self._response_length(response, cap, byte_range)
                            path = self._save_body(response, cap, length, item)
                            if (
                                byte_range is not None
                                and item['received_bytes'] != byte_range[1] - byte_range[0] + 1
                            ):
                                raise DownloadFailed('body length differs from frozen byte range')
                            return path
            except httpx.TransportError as exc:
                retryable = isinstance(exc, (
                    httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout,
                )) or 'reset' in str(exc).lower()
                self.requests[-1]['transport_error'] = type(exc).__name__
                if not retryable:
                    raise DownloadFailed('nonretryable transport failure') from exc
                self.retry_evidence.append(RetryEvidence('transport', type(exc).__name__))
            if attempt < MAX_ATTEMPTS - 1:
                self._backoff(attempt)
        raise DownloadFailed(f'exhausted {MAX_ATTEMPTS} attempts; no source fallback')

    def _save_body(self, response, cap, length, item):
        path = self._staging / f'download-{uuid.uuid4().hex}'
        item['staged_path'] = str(path)
        digest, size = hashlib.sha256(), 0
        try:
            with path.open('xb') as handle:
                # iter_bytes handles pre-buffered offline transports; HTTP
                # content encodings are refused before entering this method.
                for block in response.iter_bytes():
                    size += len(block)
                    digest.update(block)
                    if size > cap:
                        raise DownloadFailed('stream exceeded content cap')
                    handle.write(block)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            item.update(received_bytes=size, sha256=digest.hexdigest())
        if length is not None and size != length:
            raise DownloadFailed('body length differs from declared length')
        return path

    @staticmethod
    def _response_length(response, cap, byte_range):
        if response.headers.get('content-encoding', 'identity').lower() != 'identity':
            raise DownloadFailed('encoded HTTP body is forbidden')
        declared = response.headers.get('content-length')
        length = None
        if declared is not None:
            if not re.fullmatch(r'[0-9]+', declared):
                raise DownloadFailed('invalid Content-Length')
            length = int(declared)
            if length > cap:
                raise DownloadFailed('Content-Length exceeds cap')
        if byte_range is not None:
            start, end = byte_range
            expected = f'bytes {start}-{end}/{_KRAKEN.remote_size}'
            if response.headers.get('content-range') != expected:
                raise DownloadFailed('Content-Range or remote-size anchor drift')
            if length is not None and length != end - start + 1:
                raise DownloadFailed('Content-Length differs from frozen range')
        return length
