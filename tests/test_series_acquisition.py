"""D02 acquisition contracts; synthetic transport cases and explicit live gates.

Full-member checks are value-blind. The local source selects by timestamp only;
live checks compare hashes and bounded inventory, never market values.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import quantara.series_acquisition as acquisition
from quantara.acquisition import (
    ChecksumMismatch,
    DownloadFailed,
    InvalidChecksumDocument,
    NonAllowlistedHost,
)
from quantara.archive import CorruptArchive, UnsafeZipMember
from quantara.series_acquisition import SeriesAcquirer, source_inventory
from quantara.series_descriptor import SERIES_REGISTRY, SeriesDescriptor, SeriesDescriptorError

ROOT = Path(__file__).resolve().parents[1]
BTC = SeriesDescriptor('btc_settled_funding')
KRAKEN = SeriesDescriptor('kraken_xbtusd_spot_ohlcv_1h')
PERIOD = '2024-01'
PAYLOAD = b'1704067200000,8,0.0001\n1704096000000,8,-0.0002\n'


@pytest.fixture(autouse=True)
def isolated_archive_environment(monkeypatch, request):
    if 'live' not in request.node.name:
        monkeypatch.delenv('QUANTARA_KRAKEN_ARCHIVE', raising=False)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def zipped(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)
    return stream.getvalue()


def binance_source(descriptor=BTC, period=PERIOD, blob=None):
    archive = descriptor.archive_for(period)
    blob = blob if blob is not None else zipped({archive.member: PAYLOAD})
    checksum = f'{sha(blob)}  {archive.member[:-4]}.zip\n'.encode()
    return blob, checksum


def worker(tmp_path, handler, descriptor=BTC, period=PERIOD, **kwargs):
    return SeriesAcquirer(
        descriptor, period, tmp_path, transport=httpx.MockTransport(handler),
        sleeper=lambda _: None, **kwargs,
    )


def good_handler(blob, checksum):
    def handle(request):
        return httpx.Response(
            200, content=checksum if request.url.path.endswith('.CHECKSUM') else blob,
        )
    return handle


def attempts(tmp_path):
    return [json.loads(p.read_text()) for p in sorted(tmp_path.glob('staging/*/attempt.json'))]


def test_inventory_is_exactly_the_closed_descriptor_inventory():
    for series_id in SERIES_REGISTRY:
        descriptor = SeriesDescriptor(series_id)
        inventory = source_inventory(descriptor)
        assert tuple(item.period for item in inventory) == descriptor.object_periods
        assert all(item.series_id == series_id for item in inventory)
    with pytest.raises(SeriesDescriptorError):
        SeriesAcquirer(BTC, '2025-01', Path('unused'))


@pytest.mark.parametrize(
    'series_id', tuple(key for key in SERIES_REGISTRY if key != KRAKEN.series_id),
)
def test_every_binance_family_uses_its_own_mandatory_checksum(tmp_path, series_id):
    descriptor = SeriesDescriptor(series_id)
    period = descriptor.object_periods[0]
    archive = descriptor.archive_for(period)
    blob, checksum = binance_source(descriptor, period)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return good_handler(blob, checksum)(request)

    result = worker(tmp_path, handler, descriptor, period).acquire()
    assert calls == [archive.checksum_url, archive.archive_url]
    assert result.raw_path.read_bytes() == blob
    assert result.raw_sha256 == sha(blob)
    assert result.member_sha256 == sha(PAYLOAD)
    assert result.checksum_path.read_bytes() == checksum
    assert result.integrity_basis == 'binance_adjacent_checksum'
    assert result.raw_format == 'zip'
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence['status'] == 'VERIFIED'
    assert evidence['series_id'] == series_id
    assert evidence['market_rows_parsed'] == 0


@pytest.mark.parametrize('failure', ['missing', 'wrong_name', 'malformed', 'mismatch'])
def test_missing_or_invalid_checksum_never_falls_back(tmp_path, failure):
    blob, checksum = binance_source()
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path.endswith('.CHECKSUM'):
            if failure == 'missing':
                return httpx.Response(404)
            if failure == 'wrong_name':
                return httpx.Response(200, content=checksum.replace(b'BTCUSDT', b'ETHUSDT'))
            if failure == 'malformed':
                return httpx.Response(200, content=b'invalid')
            return httpx.Response(200, content=checksum)
        return httpx.Response(200, content=b'wrong')

    with pytest.raises((DownloadFailed, InvalidChecksumDocument, ChecksumMismatch)):
        worker(tmp_path, handler).acquire()
    assert len(calls) == (2 if failure == 'mismatch' else 1)
    assert not list(tmp_path.glob('objects/raw/sha256/*'))
    assert attempts(tmp_path)[0]['status'] == 'BLOCKED'


def test_rights_are_checked_before_network_or_raw_retention(tmp_path):
    legal = tmp_path / 'repo/configs/legal'
    legal.mkdir(parents=True)
    source = ROOT / 'configs/legal/binance-usdm-provider-rights.v3.yaml'
    text = source.read_text().replace('OWNER_APPROVED_PENDING_COUNSEL', 'PROHIBITED')
    (legal / source.name).write_text(text)

    def forbidden(_):
        pytest.fail('network before rights gate')

    with pytest.raises(SeriesDescriptorError, match='rights'):
        worker(tmp_path / 'data', forbidden, repo_root=tmp_path / 'repo').acquire()
    assert attempts(tmp_path / 'data')[0]['status'] == 'BLOCKED'


@pytest.mark.parametrize('status', [429, 502, 503, 504, 'timeout', 'reset'])
def test_transient_retry_is_bounded_and_recorded(tmp_path, status):
    calls = []

    def handler(request):
        calls.append(1)
        if status == 'timeout':
            raise httpx.ReadTimeout('synthetic', request=request)
        if status == 'reset':
            raise httpx.ReadError('connection reset', request=request)
        return httpx.Response(status)

    with pytest.raises(DownloadFailed):
        worker(tmp_path, handler).acquire()
    assert len(calls) == 3
    evidence = attempts(tmp_path)[0]
    assert len(evidence['requests']) == 3
    assert len(evidence['retry_evidence']) >= 2


@pytest.mark.parametrize('status', [400, 403, 404, 500])
def test_deterministic_status_is_not_retried(tmp_path, status):
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(status)

    with pytest.raises(DownloadFailed):
        worker(tmp_path, handler).acquire()
    assert len(calls) == 1


@pytest.mark.parametrize('location', [
    'https://evil.example/archive', 'http://data.binance.vision/archive',
    'https://data.binance.vision.evil.example/archive',
    'https://user:pass@data.binance.vision/archive', 'https://data.binance.vision:444/archive',
])
def test_redirect_authority_is_checked_before_every_request(tmp_path, location):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(302, headers={'location': '/allowed-hop'})
        return httpx.Response(302, headers={'location': location})

    with pytest.raises(NonAllowlistedHost):
        worker(tmp_path, handler).acquire()
    assert len(calls) == 2
    assert len(attempts(tmp_path)[0]['requests']) == 2


def test_relative_allowed_redirect_and_loop_bound(tmp_path):
    blob, checksum = binance_source()
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(302, headers={'location': '/checksum'})
        return httpx.Response(200, content=blob if request.url.path.endswith('.zip') else checksum)

    assert worker(tmp_path / 'ok', handler).acquire().raw_sha256 == sha(blob)

    def loop(_):
        return httpx.Response(302, headers={'location': '/loop'})

    with pytest.raises(DownloadFailed):
        worker(tmp_path / 'loop', loop).acquire()
    assert len(attempts(tmp_path / 'loop')[0]['requests']) <= 6


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks, fail=False):
        self.chunks = chunks
        self.fail = fail
        self.reads = 0

    def __iter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.fail:
            raise httpx.ReadTimeout('interrupted stream')


@pytest.mark.parametrize('headers', [
    {'content-length': '999999'}, {'content-length': '-1'},
    {'content-length': 'invalid'}, {'content-encoding': 'gzip'},
])
def test_invalid_length_or_encoding_rejected_before_body_read(tmp_path, headers):
    stream = Stream([b'unread'])
    with pytest.raises(DownloadFailed):
        worker(tmp_path, lambda _: httpx.Response(200, headers=headers, stream=stream)).acquire()
    assert stream.reads == 0


def test_stream_cap_without_content_length_and_truncated_body(tmp_path):
    blob, checksum = binance_source()

    def oversized(request):
        if request.url.path.endswith('.CHECKSUM'):
            return httpx.Response(200, content=checksum)
        return httpx.Response(200, stream=Stream([blob, blob]))

    with pytest.raises(DownloadFailed):
        worker(tmp_path / 'cap', oversized, max_zip_bytes=len(blob)).acquire()

    def truncated(_):
        return httpx.Response(200, headers={'content-length': '100'}, stream=Stream([b'abc']))

    with pytest.raises(DownloadFailed):
        worker(tmp_path / 'short', truncated).acquire()


def test_retry_after_partial_stream_restarts_into_a_unique_file(tmp_path):
    blob, checksum = binance_source()
    calls = []

    def handler(request):
        if request.url.path.endswith('.CHECKSUM'):
            return httpx.Response(200, content=checksum)
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, stream=Stream([blob[:20]], fail=True))
        return httpx.Response(200, content=blob)

    result = worker(tmp_path, handler).acquire()
    assert result.raw_path.read_bytes() == blob
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence['requests'][1]['received_bytes'] == 20
    assert evidence['requests'][1]['sha256'] == sha(blob[:20])


@pytest.mark.parametrize('case', ['extra', 'traversal', 'wrong', 'crc', 'bomb'])
def test_binance_archive_safety_before_publication(tmp_path, case):
    member = BTC.archive_for(PERIOD).member
    members = {member: PAYLOAD}
    if case == 'extra':
        members['extra.csv'] = PAYLOAD
    if case == 'traversal':
        members['../outside.csv'] = PAYLOAD
    if case == 'wrong':
        members = {'wrong.csv': PAYLOAD}
    if case == 'bomb':
        members[member] = b'0' * 100000
    blob = zipped(members)
    if case == 'crc':
        modified = bytearray(blob)
        offset = modified.index(b'PK\x01\x02')
        modified[offset + 16] ^= 1
        blob = bytes(modified)
    blob, checksum = binance_source(blob=blob)
    with pytest.raises((CorruptArchive, UnsafeZipMember)):
        worker(tmp_path, good_handler(blob, checksum)).acquire()
    assert not list(tmp_path.glob('objects/raw/sha256/*'))


def test_reuse_rehashes_objects_and_never_overwrites_corruption(tmp_path):
    blob, checksum = binance_source()
    handler = good_handler(blob, checksum)
    first = worker(tmp_path, handler).acquire()
    second = worker(tmp_path, handler).acquire()
    assert second.reused_raw
    assert first.attempt_id != second.attempt_id
    assert first.raw_path == second.raw_path
    first.raw_path.write_bytes(b'corrupt')
    with pytest.raises(ChecksumMismatch):
        worker(tmp_path, handler).acquire()
    assert first.raw_path.read_bytes() == b'corrupt'


def test_concurrent_attempts_have_unique_staging_and_no_clobber(tmp_path):
    blob, checksum = binance_source()
    handler = good_handler(blob, checksum)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(tmp_path, handler).acquire(), range(2)))
    assert len({r.attempt_id for r in results}) == 2
    assert len({r.raw_path for r in results}) == 1
    assert results[0].raw_path.read_bytes() == blob
    assert len(attempts(tmp_path)) == 2


@pytest.fixture()
def kraken_source(monkeypatch):
    # Offset/CRC/ZIP64 behavior uses synthetic bytes only. No production API can
    # override the frozen anchor; monkeypatch is scoped to offline tests.
    member = KRAKEN.archive_for('2020-2024').member
    blob = zipped({'unselected.csv': b'opaque', member: PAYLOAD})
    with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
        info = bundle.getinfo(member)
        directory_start = bundle.start_dir
    offset = info.header_offset
    name_length, extra_length = struct.unpack_from('<HH', blob, offset + 26)
    start = offset + 30 + name_length + extra_length
    anchor = replace(
        acquisition._KRAKEN, remote_size=len(blob), member_count=2,
        directory_start=directory_start, directory_end=len(blob) - 23,
        header_offset=offset, data_start=start, compressed_size=info.compress_size,
        member_size=info.file_size, crc32=info.CRC, member_sha256=sha(PAYLOAD),
    )
    monkeypatch.setattr(acquisition, '_KRAKEN', anchor)
    calls = []

    def handler(request):
        assert request.url.host == 'drive.usercontent.google.com'
        assert request.headers['accept-encoding'] == 'identity'
        start, end = map(int, request.headers['range'].removeprefix('bytes=').split('-'))
        calls.append((start, end))
        return httpx.Response(206, headers={
            'content-range': f'bytes {start}-{end}/{len(blob)}',
        }, content=blob[start:end + 1])

    return blob, anchor, calls, handler


def test_kraken_retrieves_only_frozen_ranges_and_records_non_signature(tmp_path, kraken_source):
    blob, anchor, calls, handler = kraken_source
    result = worker(tmp_path, handler, KRAKEN, '2020-2024').acquire()
    assert result.raw_format == 'zip_raw_deflate_member'
    assert result.raw_path.read_bytes() == blob[
        anchor.data_start:anchor.data_start + anchor.compressed_size
    ]
    assert calls == [
        (anchor.directory_start, anchor.directory_end),
        (anchor.header_offset, anchor.header_offset + 29),
        (anchor.header_offset + 30, anchor.data_start - 1),
        (anchor.data_start, anchor.data_start + anchor.compressed_size - 1),
    ]
    assert result.member_sha256 == sha(PAYLOAD)
    assert result.checksum_path is None
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence['operator_signature'] is False
    assert 'not an operator signature' in evidence['integrity_note']
    assert evidence['anchors']['remote_size'] == len(blob)
    assert evidence['market_rows_parsed'] == 0
    assert evidence['member_sha256'] == sha(PAYLOAD)


CONFIRMATION = b'''<!DOCTYPE html><html><form
    action="https://drive.usercontent.google.com/download" method="get">
    <input type="hidden" name="id" value="1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP">
    <input type="hidden" name="export" value="download">
    <input type="hidden" name="confirm" value="t">
    <input type="hidden" name="uuid" value="12345678-1234-1234-1234-123456789abc">
    </form></html>'''


def test_kraken_a9_confirmation_keeps_same_object_and_byte_range(tmp_path, kraken_source):
    blob, anchor, calls, range_handler = kraken_source
    confirmations = []

    def handler(request):
        assert request.url.params['id'] == '1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP'
        if 'confirm' not in request.url.params:
            confirmations.append(request.headers['range'])
            return httpx.Response(200, headers={'content-type': 'text/html'}, content=CONFIRMATION)
        assert request.url.params['confirm'] == 't'
        assert request.url.params['uuid'] == '12345678-1234-1234-1234-123456789abc'
        assert request.headers['range'] == confirmations[-1]
        return range_handler(request)

    result = worker(tmp_path, handler, KRAKEN, '2020-2024').acquire()
    assert result.member_sha256 == sha(PAYLOAD)
    assert len(confirmations) == 4
    evidence = json.loads(result.evidence_path.read_text())
    assert len(evidence['requests']) == 8


@pytest.mark.parametrize('html', [
    CONFIRMATION.replace(b'1ptNqWYidLkhb2VAKuLCxmp2OXEfGO-AP', b'other-file'),
    CONFIRMATION.replace(b'https://drive.usercontent.google.com', b'https://evil.example'),
    CONFIRMATION.replace(b'name="uuid"', b'name="other"'),
    CONFIRMATION.replace(b'12345678-1234-1234-1234-123456789abc', b'bad&injection=true'),
    CONFIRMATION.replace(b'</form>', b'<input name="id" value="other"></form>'),
    b'not a confirmation',
])
def test_kraken_confirmation_rejects_unbound_or_ambiguous_html(tmp_path, kraken_source, html):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, headers={'content-type': 'text/html'}, content=html)

    with pytest.raises(DownloadFailed):
        worker(tmp_path, handler, KRAKEN, '2020-2024').acquire()
    assert len(calls) == 1


def test_kraken_confirmation_cannot_loop_or_trigger_full_archive_read(tmp_path, kraken_source):
    calls = []
    stream = Stream([b'unread'])

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(200, headers={'content-type': 'text/html'}, content=CONFIRMATION)
        return httpx.Response(200, headers={'content-type': 'text/html'}, stream=stream)

    with pytest.raises(DownloadFailed):
        worker(tmp_path, handler, KRAKEN, '2020-2024').acquire()
    assert len(calls) == 2
    assert stream.reads == 0


@pytest.mark.parametrize('failure', ['status', 'size', 'range', 'length', 'encoding'])
def test_kraken_range_response_contract_fails_before_body(tmp_path, kraken_source, failure):
    blob, anchor, calls, handler = kraken_source
    stream = Stream([b'unread'])

    def bad(request):
        start, end = anchor.directory_start, anchor.directory_end
        headers = {'content-range': f'bytes {start}-{end}/{len(blob)}'}
        status = 206
        if failure == 'status':
            status = 200
        if failure == 'size':
            headers['content-range'] = f'bytes {start}-{end}/{len(blob) + 1}'
        if failure == 'range':
            headers['content-range'] = f'bytes 0-{end}/{len(blob)}'
        if failure == 'length':
            headers['content-length'] = '1'
        if failure == 'encoding':
            headers['content-encoding'] = 'gzip'
        return httpx.Response(status, headers=headers, stream=stream)

    with pytest.raises(DownloadFailed):
        worker(tmp_path, bad, KRAKEN, '2020-2024').acquire()
    assert stream.reads == 0
    assert not list(tmp_path.glob('objects/raw/sha256/*'))


@pytest.mark.parametrize('field', [
    'crc32', 'member_sha256', 'member_size', 'compressed_size', 'header_offset', 'member_count',
])
def test_kraken_anchor_drift_blocks_without_publishing(tmp_path, kraken_source, monkeypatch, field):
    blob, anchor, calls, handler = kraken_source
    value = '0' * 64 if field == 'member_sha256' else getattr(anchor, field) + 1
    monkeypatch.setattr(acquisition, '_KRAKEN', replace(anchor, **{field: value}))
    with pytest.raises((ChecksumMismatch, CorruptArchive, DownloadFailed)):
        worker(tmp_path, handler, KRAKEN, '2020-2024').acquire()
    assert not list(tmp_path.glob('objects/raw/sha256/*'))
    assert attempts(tmp_path)[0]['status'] == 'BLOCKED'


class ValueBlindProbe:
    """Streaming JSON projection: excluded values are never accumulated/decoded."""

    def __init__(self, source, selected):
        self.source, self.selected = source, selected
        self.byte = source.read(1)

    def advance(self):
        self.byte = self.source.read(1)

    def whitespace(self):
        while self.byte and self.byte in b' \t\r\n':
            self.advance()

    def string(self, keep):
        token = bytearray(b'"') if keep else None
        self.advance()
        escaped = False
        while self.byte:
            byte = self.byte
            if keep:
                token.extend(byte)
            self.advance()
            if byte == b'"' and not escaped:
                return json.loads(token) if keep else None
            escaped = byte == b'\\' and not escaped
        raise AssertionError('unterminated probe string')

    def value(self, keep=False, root=True):
        self.whitespace()
        if self.byte == b'{':
            result = {} if keep or root else None
            self.advance()
            self.whitespace()
            while self.byte != b'}':
                key = self.string(keep or root)
                self.whitespace()
                assert self.byte == b':'
                self.advance()
                retain = key in self.selected if root else keep
                value = self.value(retain, False)
                if retain:
                    result[key] = value
                self.whitespace()
                if self.byte == b',':
                    self.advance()
                    self.whitespace()
                else:
                    assert self.byte == b'}'
            self.advance()
            return result
        if self.byte == b'[':
            result = [] if keep else None
            self.advance()
            self.whitespace()
            while self.byte != b']':
                value = self.value(keep, False)
                if keep:
                    result.append(value)
                self.whitespace()
                if self.byte == b',':
                    self.advance()
                    self.whitespace()
                else:
                    assert self.byte == b']'
            self.advance()
            return result
        if self.byte == b'"':
            return self.string(keep)
        token = bytearray() if keep else None
        while self.byte and self.byte not in b',]} \t\r\n':
            if keep:
                token.extend(self.byte)
            self.advance()
        return json.loads(token) if keep else None


def test_value_blind_probe_skips_unknown_values_even_before_anchors(monkeypatch):
    original = json.loads

    def guarded(value, *args, **kwargs):
        assert b'NEVER_DECODE' not in bytes(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(json, 'loads', guarded)
    source = io.BytesIO(b'{"last_row":["NEVER_DECODE"],"remote_size_bytes":9}')
    assert ValueBlindProbe(source, {'remote_size_bytes'}).value() == {'remote_size_bytes': 9}


def test_frozen_kraken_metadata_matches_a9_without_loading_rows():
    expected = {
        'remote_size_bytes': acquisition._KRAKEN.remote_size,
        'zip_member_count': acquisition._KRAKEN.member_count,
        'chosen_member': acquisition._KRAKEN.member,
        'member_compress_size': acquisition._KRAKEN.compressed_size,
        'member_file_size': acquisition._KRAKEN.member_size,
        'member_crc32': f'{acquisition._KRAKEN.crc32:08x}',
        'member_sha256': acquisition._KRAKEN.member_sha256,
    }
    with (ROOT / acquisition._KRAKEN.audit_path).open('rb', buffering=0) as source:
        found = ValueBlindProbe(source, {*expected, 'range_requests'}).value()
    ranges = found.pop('range_requests')
    assert found == expected
    anchor = acquisition._KRAKEN
    assert ranges[3] == {
        'start': anchor.directory_start, 'end': anchor.directory_end,
        'bytes': anchor.directory_end - anchor.directory_start + 1,
    }
    assert ranges[4]['start'] == anchor.header_offset
    assert ranges[6]['end'] == anchor.data_start - 1
    assert ranges[7] == {
        'start': anchor.data_start, 'end': anchor.data_start + anchor.compressed_size - 1,
        'bytes': anchor.compressed_size,
    }


def test_zip64_metadata_handles_large_offsets_and_missing_fields():
    anchor = acquisition._KRAKEN
    extra = struct.pack('<HHQ', 1, 8, anchor.header_offset)
    assert acquisition._zip64(extra, anchor.member_size, anchor.compressed_size, 0xffffffff) == (
        anchor.member_size, anchor.compressed_size, anchor.header_offset,
    )
    for bad in (b'', extra[:-1], extra + extra):
        with pytest.raises(CorruptArchive):
            acquisition._zip64(bad, anchor.member_size, anchor.compressed_size, 0xffffffff)


@pytest.mark.parametrize('case', ['corrupt', 'truncated', 'trailing', 'oversize'])
def test_opaque_member_hash_sink_refuses_corruption(tmp_path, kraken_source, case):
    blob, anchor, calls, handler = kraken_source
    compressed = blob[anchor.data_start:anchor.data_start + anchor.compressed_size]
    if case == 'corrupt':
        compressed = b'bad deflate'
    elif case == 'truncated':
        compressed = compressed[:-1]
    elif case == 'trailing':
        compressed += b'extra'
    else:
        anchor = replace(anchor, member_size=1)
    path = tmp_path / 'compressed'
    path.write_bytes(compressed)
    with pytest.raises((CorruptArchive, ChecksumMismatch)):
        acquisition._hash_deflate(path, anchor)


def test_checksum_store_corruption_is_preserved_and_blocks(tmp_path):
    blob, checksum = binance_source()
    result = worker(tmp_path, good_handler(blob, checksum)).acquire()
    result.checksum_path.write_bytes(b'corrupt checksum object')
    with pytest.raises(ChecksumMismatch):
        worker(tmp_path, good_handler(blob, checksum)).acquire()
    assert result.checksum_path.read_bytes() == b'corrupt checksum object'


def test_single_attempt_cannot_rewrite_terminal_evidence(tmp_path):
    blob, checksum = binance_source()
    instance = worker(tmp_path, good_handler(blob, checksum))
    result = instance.acquire()
    previous = result.evidence_path.read_bytes()
    with pytest.raises(DownloadFailed):
        instance.acquire()
    assert result.evidence_path.read_bytes() == previous


@pytest.mark.integration
def test_live_binance_frozen_acquisition_hashes_only(tmp_path):
    result = SeriesAcquirer(BTC, '2020-01', tmp_path).acquire()
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence['status'] == 'VERIFIED'
    assert evidence['market_rows_parsed'] == 0
    assert result.raw_size > 0
    print(json.dumps(evidence, indent=2, sort_keys=True))


# Synthetic values only. Out-of-window payloads are intentionally not valid CSV
# or UTF-8, so a whole-row parser or decoder would fail the local source tests.
LOCAL_SELECTED = (
    b'1577836800,1.00,2.00,0.50,1.50,0.00000001,2\r\n'
    b'1577844000,1.00,2.00,0.50,1.50,0.00000001,2\n'
    b'1609459200,1.00,2.00,0.50,1.50,0.00000001,2\n'
    b'1735686000,1.00,2.00,0.50,1.50,0.00000001,2\n'
)
LOCAL_PAYLOAD = (
    b'1388534400,EXCLUDED_EARLY\n' + LOCAL_SELECTED
    + b'1735689600,EXCLUDED_FUTURE\xff,"\n'
    + b'1767222000,EXCLUDED_FINAL\xff'
)


def no_network(_):
    pytest.fail('an explicit local source must not perform network requests')


@pytest.fixture()
def local_archive(tmp_path, monkeypatch):
    def build(payload=LOCAL_PAYLOAD):
        blob = zipped({'unselected.csv': b'EXCLUDED_OTHER', acquisition._KRAKEN.member: payload})
        with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
            info = bundle.getinfo(acquisition._KRAKEN.member)
            directory_start = bundle.start_dir
        offset = info.header_offset
        name_length, extra_length = struct.unpack_from('<HH', blob, offset + 26)
        anchor = replace(
            acquisition._KRAKEN, remote_size=len(blob), member_count=2,
            directory_start=directory_start, directory_end=len(blob) - 23,
            header_offset=offset, data_start=offset + 30 + name_length + extra_length,
            compressed_size=info.compress_size, member_size=info.file_size,
            crc32=info.CRC, member_sha256=sha(payload),
        )
        path = tmp_path / 'synthetic.zip'
        path.write_bytes(blob)
        monkeypatch.setattr(acquisition, '_KRAKEN', anchor)
        monkeypatch.setenv('QUANTARA_KRAKEN_ARCHIVE', str(path))
        return path, blob, anchor
    return build


@pytest.mark.parametrize('chunk_size', [1, 7, 65536])
def test_local_archive_slices_without_retaining_excluded_values(
    tmp_path, monkeypatch, local_archive, chunk_size,
):
    path, blob, anchor = local_archive()
    monkeypatch.setattr(acquisition, '_CHUNK', chunk_size)
    root = tmp_path / 'data'
    result = worker(root, no_network, KRAKEN, '2020-2024').acquire()
    assert result.raw_format == 'csv_2020_2024'
    assert result.raw_path.read_bytes() == LOCAL_SELECTED
    assert result.raw_sha256 == sha(LOCAL_SELECTED)
    assert result.raw_size == len(LOCAL_SELECTED)
    assert result.member_sha256 == anchor.member_sha256
    assert result.member_size == len(LOCAL_PAYLOAD)
    assert result.member_crc32 == f'{anchor.crc32:08x}'
    assert path.read_bytes() == blob
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence['acquisition_source'] == 'local_archive'
    assert evidence['local_archive_path'] == str(path.resolve())
    assert evidence['requests'] == []
    assert evidence['operator_signature'] is False
    assert evidence['market_rows_parsed'] == 0
    assert evidence['inventory'] == {
        'window_start_ts': 1577836800, 'window_end_exclusive_ts': 1735689600,
        'total_member_rows': 7, 'rows': 4, 'unique_timestamps': 4,
        'duplicate_timestamps': 0, 'expected_hours': 43848, 'missing_hours': 43844,
        'per_year_rows': {'2020': 2, '2021': 1, '2022': 0, '2023': 0, '2024': 1},
    }
    for retained in root.rglob('*'):
        if retained.is_file():
            assert b'EXCLUDED_' not in retained.read_bytes()


@pytest.mark.parametrize('field', [
    'remote_size', 'member_count', 'member_size', 'crc32', 'member_sha256',
    'compressed_size', 'header_offset', 'data_start', 'member',
])
def test_local_archive_anchor_drift_blocks_without_retention(
    tmp_path, monkeypatch, local_archive, field,
):
    path, blob, anchor = local_archive()
    if field == 'member_sha256':
        value = '0' * 64
    elif field == 'member':
        value = 'other.csv'
    else:
        value = getattr(anchor, field) + 1
    monkeypatch.setattr(acquisition, '_KRAKEN', replace(anchor, **{field: value}))
    root = tmp_path / 'data'
    with pytest.raises((ChecksumMismatch, CorruptArchive, DownloadFailed)):
        worker(root, no_network, KRAKEN, '2020-2024').acquire()
    assert not list(root.glob('objects/raw/sha256/*'))
    assert attempts(root)[0]['status'] == 'BLOCKED'
    assert path.read_bytes() == blob


def test_local_archive_reuses_verified_slice_and_preserves_corruption(tmp_path, local_archive):
    local_archive()
    root = tmp_path / 'data'
    first = worker(root, no_network, KRAKEN, '2020-2024').acquire()
    second = worker(root, no_network, KRAKEN, '2020-2024').acquire()
    assert second.reused_raw
    assert second.raw_path == first.raw_path
    assert second.attempt_id != first.attempt_id
    first.raw_path.write_bytes(b'corrupt')
    with pytest.raises(ChecksumMismatch):
        worker(root, no_network, KRAKEN, '2020-2024').acquire()
    assert first.raw_path.read_bytes() == b'corrupt'


def test_local_archive_counts_duplicates_without_filling_or_deduplicating(tmp_path, local_archive):
    line = b'1577836800,1,2,0.5,1.5,0,0\n'
    local_archive(line * 2)
    result = worker(tmp_path / 'data', no_network, KRAKEN, '2020-2024').acquire()
    inventory = json.loads(result.evidence_path.read_text())['inventory']
    assert result.raw_path.read_bytes() == line * 2
    assert inventory['rows'] == 2
    assert inventory['unique_timestamps'] == 1
    assert inventory['duplicate_timestamps'] == 1
    assert inventory['missing_hours'] == 43847


@pytest.mark.parametrize('payload', [
    b'timestamp,open,high,low,close,volume,trades\n',
    b'1577836801,1,2,0.5,1.5,0,0\n',
    b'1577836800\n',
    b'9999999999999999999999999999999999999999999999999999,opaque\n',
])
def test_local_archive_rejects_bad_timestamp_metadata(tmp_path, local_archive, payload):
    local_archive(payload)
    root = tmp_path / 'data'
    with pytest.raises(CorruptArchive):
        worker(root, no_network, KRAKEN, '2020-2024').acquire()
    assert attempts(root)[0]['status'] == 'BLOCKED'
    assert not list(root.glob('objects/raw/sha256/*'))


@pytest.mark.parametrize('location', ['', 'missing.zip', '.'])
def test_local_archive_invalid_explicit_path_never_falls_back(tmp_path, monkeypatch, location):
    monkeypatch.setenv('QUANTARA_KRAKEN_ARCHIVE', location)
    with pytest.raises(DownloadFailed):
        worker(tmp_path / 'data', no_network, KRAKEN, '2020-2024').acquire()


def test_local_archive_rights_precede_opening_file(tmp_path, monkeypatch):
    legal = tmp_path / 'repo/configs/legal'
    legal.mkdir(parents=True)
    source = ROOT / 'configs/legal/kraken-spot-provider-rights.v1.yaml'
    text = source.read_text().replace('OWNER_APPROVED_PENDING_COUNSEL', 'PROHIBITED')
    (legal / source.name).write_text(text)
    monkeypatch.setenv('QUANTARA_KRAKEN_ARCHIVE', str(tmp_path / 'must-not-open.zip'))
    with pytest.raises(SeriesDescriptorError, match='rights'):
        worker(
            tmp_path / 'data', no_network, KRAKEN, '2020-2024', repo_root=tmp_path / 'repo',
        ).acquire()


# No integration marker: default CI collects this gate and explicitly skips it
# when the opt-in environment variable is absent. Invoke serially with -k live.
@pytest.mark.skipif(
    'QUANTARA_KRAKEN_ARCHIVE' not in os.environ, reason='QUANTARA_KRAKEN_ARCHIVE is unset',
)
def test_live_local_kraken_archive_a9_inventory(tmp_path):
    if os.environ.get('PYTEST_XDIST_WORKER'):
        pytest.fail('local archive live gate must run serially')
    result = SeriesAcquirer(KRAKEN, '2020-2024', tmp_path).acquire()
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence['status'] == 'VERIFIED'
    assert evidence['acquisition_source'] == 'local_archive'
    assert evidence['requests'] == []
    assert result.member_size == 5640237
    assert result.member_crc32 == 'c351083a'
    assert result.member_sha256 == (
        'b45e7ce94911d4c1d13bf5c2e270c9219b81631292f7c40bab27e81f7f3f8297'
    )
    assert evidence['anchors']['remote_size'] == 7885068519
    assert evidence['anchors']['member_count'] == 24056
    assert evidence['market_rows_parsed'] == 0
    assert evidence['operator_signature'] is False
    assert evidence['inventory'] == {
        'window_start_ts': 1577836800, 'window_end_exclusive_ts': 1735689600,
        'total_member_rows': 96381, 'rows': 43828, 'unique_timestamps': 43828,
        'duplicate_timestamps': 0, 'expected_hours': 43848, 'missing_hours': 20,
        'per_year_rows': {'2020': 8783, '2021': 8754, '2022': 8760, '2023': 8759, '2024': 8772},
    }
    # Read only the verified bounded slice, and examine timestamp prefixes only.
    count = 0
    with result.raw_path.open('rb') as source:
        for line in source:
            assert 1577836800 <= int(line.partition(b',')[0]) < 1735689600
            count += 1
    assert count == 43828
    assert acquisition._digest_file(result.raw_path, result.raw_size) == (
        result.raw_sha256, result.raw_size,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
