import test from 'node:test';
import assert from 'node:assert/strict';
import {canonicalDate, documentLink, splitSse, localDay, formatBytes, errorMessage, spaceBase} from '../public/assets/utils.js';

test('assistant file links always keep the selected space prefix', () => {
  assert.equal(documentLink('/v1/documents/doc-a/versions/4/download', 'walter-123'), '/s/walter-123/v1/documents/doc-a/versions/4/download');
  assert.equal(documentLink('/v1/documents/doc-a/download', 'personal-456'), '/s/personal-456/v1/documents/doc-a/download');
  for (const path of ['https://other.test/v1/documents/doc-a/download', '/s/another/v1/documents/doc-a/download', '/v1/documents/doc-a/download?token=private', '/v1/documents/../download', '/v1/documents/%2e%2e/download', '/v1/documents/doc%2fother/download', '/v1/documents/doc%5cother/download', 'javascript:alert(1)']) assert.equal(documentLink(path, 'current'), null, path);
  assert.throws(() => spaceBase('../personal'));
});

test('SSE preserves split frames and ignores heartbeat comments', () => {
  let pending = '';
  const received = [];
  const frames = ': ping\r\n\r\ndata: {"type":"token","content":"Hola\\n"}\r\n\r\ndata: {"type":"proposal",\r\ndata: "proposal":{"id":"p-1"}}\r\n\r\ndata: {"type":"done"}\n\n';
  // One-byte chunks cover CRLF and Unicode/frame boundary behaviour.
  for (const char of frames) { const result = splitSse(pending + char); received.push(...result.events); pending = result.remainder; }
  assert.deepEqual(received, [{type: 'token', content: 'Hola\n'}, {type: 'proposal', proposal: {id: 'p-1'}}, {type: 'done'}]);
  assert.equal(pending, '');
  assert.throws(() => splitSse('data: invalid\n\n'), /respuesta del chat/);
});

test('dates use the requested timezone instead of the host timezone', () => {
  assert.equal(localDay(new Date('2026-10-08T01:00:00Z'), 'America/Mexico_City'), '2026-10-07');
  assert.equal(localDay(new Date('2026-10-08T01:00:00Z'), 'Europe/Madrid'), '2026-10-08');
});

test('canonical naive timestamps are UTC, explicit offsets and epochs are preserved', () => {
  assert.equal(canonicalDate('2026-10-09T01:37:00').toISOString(), '2026-10-09T01:37:00.000Z');
  assert.equal(canonicalDate('2026-10-08T19:37:00-06:00').toISOString(), '2026-10-09T01:37:00.000Z');
  assert.equal(canonicalDate('2026-10-09T01:37:00Z').toISOString(), '2026-10-09T01:37:00.000Z');
  assert.equal(canonicalDate(0).toISOString(), '1970-01-01T00:00:00.000Z');
});

test('unavailable usage and API errors stay explicit', () => {
  assert.equal(formatBytes(null), 'Sin medición');
  assert.equal(formatBytes(0), '0 B');
  assert.equal(formatBytes(5 * 1024 ** 3), '5 GB');
  assert.equal(errorMessage({detail: 'Espacio suspendido'}, 423), 'Espacio suspendido');
  assert.match(errorMessage({}, 401), /sesión terminó/);
  assert.equal(errorMessage({detail: [{msg: 'Campo requerido'}]}, 422), 'Campo requerido');
});
