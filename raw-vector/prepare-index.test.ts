import { describe, expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, openSync, closeSync, rmSync, statSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { canonicalJson, splitLossless, parsePrepareRequest, prepareIndex, createPrivateIndexDirectory,
  MAX_CHUNK_BYTES, MAX_PAGE_BYTES } from './prepare-index.ts';
import * as preparer from './prepare-index.ts';

const sha = (value: string) => createHash('sha256').update(value).digest('hex');
function request() {
  const pages = [{ slug: 'event/audio', title: 'Audio', type: 'event', origin: 'evidence',
    text: '---\norigin: evidence\n---\nAudio was repaired.\n',
    text_sha256: sha('---\norigin: evidence\n---\nAudio was repaired.\n') }];
  return { v: 1, operation: 'prepare_index', source: 'sia', dataset_sha256: sha('frozen dataset'),
    pages_sha256: sha(canonicalJson(pages)), embedding: { model: 'llama-server:private-fixture', dimensions: 3,
      endpoint: 'http://127.0.0.1:8081/v1' }, output: { parent_fd: 8 }, pages };
}
function harness() {
  const calls: unknown[] = [];
  const pages = new Map<string, any>();
  const chunks = new Map<string, any[]>();
  const engine = {
    writePage: async (page: any, rows: any[]) => {
      calls.push({ write: page.slug });
      pages.set(page.slug, { slug: page.slug, title: page.title, type: page.type, compiled_truth: page.text,
        timeline: '', frontmatter: { origin: page.origin } });
      chunks.set(page.slug, rows.map(row => ({ ...row, embedding: new Float32Array(row.embedding) })));
    },
    readPage: async (slug: string) => pages.get(slug),
    readChunks: async (slug: string) => chunks.get(slug),
    listSlugs: async () => Array.from(pages.keys()),
    close: async () => { calls.push('close'); },
  };
  const dependencies = {
    openNew: async (fd: number, embedding: unknown) => { calls.push({ open: fd, embedding }); return engine; },
    embedDocument: async (text: string, embedding: unknown, signal: AbortSignal) => {
      calls.push({ embed: text, embedding, signal: signal instanceof AbortSignal });
      return new Float32Array([1, 0, 0]);
    },
  };
  return { calls, pages, chunks, engine, dependencies };
}

describe('lossless benchmark index preparation', () => {
  test('deterministically splits all UTF-8 text without dropping whitespace or cutting codepoints', () => {
    const input = ' \n😀é漢字\t'.repeat(MAX_CHUNK_BYTES) + '\nlast byte\n';
    const rows = splitLossless(input);
    expect(rows.join('')).toBe(input);
    expect(rows).toEqual(splitLossless(input));
    expect(rows.length).toBeGreaterThan(1);
    for (const row of rows) {
      expect(Buffer.byteLength(row)).toBeLessThanOrEqual(MAX_CHUNK_BYTES);
      expect(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(row))).toBe(row);
    }
    expect(() => splitLossless('before\u0000after')).toThrow('page-text-invalid');
    expect(() => splitLossless('\ud800')).toThrow('page-text-invalid');
  });

  test('rejects corrupt text identities, duplicate slugs, answer keys and content beyond the declared budget before creating output', async () => {
    for (const patch of [
      { pages_sha256: sha('wrong') },
      { answer_keys: ['event/audio'] },
      { pages: [{ ...request().pages[0], text_sha256: sha('wrong') }] },
      { pages: [request().pages[0], request().pages[0]] },
      { pages: [{ ...request().pages[0], origin: 'verified' }] },
      { pages: [{ ...request().pages[0], slug: 'event/Audio' }] },
      { pages: [{ ...request().pages[0], text: 'x'.repeat(MAX_PAGE_BYTES + 1) }] },
      { output: { parent_fd: true } },
      { embedding: { ...request().embedding, endpoint: 'https://outside.example/v1' } },
    ]) {
      const h = harness();
      const result = await prepareIndex({ ...request(), ...patch }, h.dependencies);
      expect(result.status).toBe('refused');
      expect(h.calls).toEqual([]);
    }
  });

  test('rejects duplicate JSON fields and invalid UTF-8 in the descriptor input', () => {
    const body = JSON.stringify(request()).replace('"v":1', '"v":1,"v":1');
    expect(() => parsePrepareRequest(Buffer.from(body))).toThrow('duplicate-json-key');
    expect(() => parsePrepareRequest(Buffer.from([0xff]))).toThrow('request-utf8');
  });

  test('creates only a new private leaf and refuses an existing index before touching its contents', () => {
    const directory = mkdtempSync(join(tmpdir(), 'sia-prepare-test-'));
    const fd = openSync(directory, 'r');
    try {
      const path = createPrivateIndexDirectory(fd);
      expect(path).toBe(`/proc/self/fd/${fd}/index`);
      expect(statSync(path).mode & 0o777).toBe(0o700);
      mkdirSync(join(directory, 'index', 'retained-marker'));
      expect(() => createPrivateIndexDirectory(fd)).toThrow('output-index-exists');
      expect(readdirSync(join(directory, 'index'))).toEqual(['retained-marker']);
    } finally { closeSync(fd); rmSync(directory, { recursive: true }); }
  });

  test('uses sequential document encoding, stores exact page origin/text and checks readback before success', async () => {
    const q = request();
    q.pages[0].text = 'start\n' + 'ü'.repeat(MAX_CHUNK_BYTES) + '\nend\n';
    q.pages[0].text_sha256 = sha(q.pages[0].text);
    q.pages_sha256 = sha(canonicalJson(q.pages));
    const h = harness();
    const result = await prepareIndex(q, h.dependencies);
    expect(result.status).toBe('ok');
    expect(h.calls[0]).toEqual({ open: 8, embedding: q.embedding });
    const encoded = h.calls.filter(x => typeof x === 'object' && x !== null && 'embed' in x) as any[];
    expect(encoded.map(x => x.embed).join('')).toBe(q.pages[0].text);
    expect(encoded.every(x => x.signal && canonicalJson(x.embedding) === canonicalJson(q.embedding))).toBe(true);
    expect(h.calls.slice(1, -2)).toEqual(encoded);
    expect(h.calls.slice(-2)).toEqual([{ write: 'event/audio' }, 'close']);
    expect(h.pages.get('event/audio').compiled_truth).toBe(q.pages[0].text);
    expect(h.pages.get('event/audio').frontmatter.origin).toBe('evidence');
    expect(result.pages[0]).toMatchObject({ slug: 'event/audio', origin: 'evidence', text_sha256: q.pages[0].text_sha256 });
    expect(result.bindings).toMatchObject({ dataset_sha256: q.dataset_sha256, pages_sha256: q.pages_sha256 });
    expect(result.non_claims).toContain('Origin labels are retained from the supplied frozen export; this preparer does not independently attest its source evidence.');
  });

  test('rejects content, origin, chunk omission and embedding mutations found during readback', async () => {
    for (const mutation of ['content', 'origin', 'chunk', 'vector', 'extra-page']) {
      const h = harness();
      const originalWrite = h.engine.writePage;
      h.engine.writePage = async (page, rows) => {
        await originalWrite(page, rows);
        if (mutation === 'content') h.pages.get(page.slug).compiled_truth += 'invented';
        if (mutation === 'origin') h.pages.get(page.slug).frontmatter.origin = 'model';
        if (mutation === 'chunk') h.chunks.set(page.slug, []);
        if (mutation === 'vector') h.chunks.get(page.slug)![0].embedding = new Float32Array([0, 1, 0]);
        if (mutation === 'extra-page') h.pages.set('event/unexpected', {});
      };
      const result = await prepareIndex(request(), h.dependencies);
      expect(result).toMatchObject({ status: 'refused', reason: 'index-readback-mismatch' });
      expect(result).not.toHaveProperty('pages');
      expect(h.calls.at(-1)).toBe('close');
    }
  });

  test('refuses invalid vectors before writes and closes after provider failures', async () => {
    for (const vector of [new Float32Array([1]), new Float32Array([NaN, 0, 0]), new Float32Array([0, 0, 0])]) {
      const h = harness();
      h.dependencies.embedDocument = async () => vector;
      const result = await prepareIndex(request(), h.dependencies);
      expect(result).toMatchObject({ status: 'refused', reason: 'embedding-vector-invalid' });
      expect(h.pages.size).toBe(0);
      expect(h.calls.at(-1)).toBe('close');
    }
    const h = harness();
    h.dependencies.embedDocument = async () => { throw new Error('private provider failure'); };
    const result = await prepareIndex(request(), h.dependencies);
    expect(result.status).toBe('refused');
    expect(JSON.stringify(result)).not.toContain('private provider failure');
    expect(h.calls.at(-1)).toBe('close');
  });
});

describe('bounded initSchema diagnostic receipt', () => {
  test('retains known setup diagnostics verbatim with a digest and restores the original writer', async () => {
    const outside: string[] = [];
    const writer = (chunk: string | Uint8Array) => { outside.push(Buffer.from(chunk).toString('utf8')); return true; };
    const stream = { write: writer };
    const known = '  Setting up brain schema (v144)...\n'
      + '  v142: takes.embedding resized to vector(768); existing take vectors cleared\n'
      + '  139 migration(s) applied\n';
    const result = await preparer.captureSetupDiagnostics(async () => {
      stream.write(Buffer.from(known));
      return 'schema-return-value';
    }, 768, stream);
    expect(result.value).toBe('schema-return-value');
    expect(result.diagnostics).toMatchObject({ source: 'gbrain.initSchema/process.stderr',
      classification: 'known-setup-diagnostics', text: known, sha256: sha(known), truncated: false });
    expect(Buffer.from(result.diagnostics.utf8_base64, 'base64').toString('utf8')).toBe(known);
    expect(result.diagnostics.non_claims).toContain('Captured setup diagnostics are informational output, not proof of schema or data correctness.');
    expect(outside).toEqual([]);
    expect(stream.write).toBe(writer);
    stream.write('later diagnostic');
    expect(outside).toEqual(['later diagnostic']);
  });

  test('unknown/error output refuses with its original bytes and cannot become known setup progress', async () => {
    for (const diagnostic of ['ERROR: partial schema\n', '  v142: takes.embedding resized to vector(4); existing take vectors cleared\n',
      'unexpected output\n', '  139 migration(s) applied\nERROR: failed later\n']) {
      const writer = () => true;
      const stream = { write: writer };
      let caught: any;
      try { await preparer.captureSetupDiagnostics(async () => { stream.write(diagnostic); }, 768, stream); }
      catch (error) { caught = error; }
      expect(caught?.reason).toBe('setup-diagnostics-unrecognized');
      expect(caught?.diagnostics).toMatchObject({ classification: 'unrecognized-setup-diagnostics', text: diagnostic,
        sha256: sha(diagnostic), truncated: false });
      expect(stream.write).toBe(writer);
    }
  });

  test('restores stderr after initSchema throws, preserving diagnostics without returning success', async () => {
    const writer = () => true;
    const stream = { write: writer };
    const logged = '  Setting up brain schema (v144)...\n';
    let caught: any;
    try { await preparer.captureSetupDiagnostics(async () => {
      stream.write(logged);
      throw new Error('schema execution failed');
    }, 768, stream); } catch (error) { caught = error; }
    expect(caught?.reason).toBe('schema-initialization-failed');
    expect(caught?.diagnostics).toMatchObject({ classification: 'schema-initialization-failed', text: logged,
      sha256: sha(logged), truncated: false });
    expect(stream.write).toBe(writer);
  });

  test('excess diagnostics refuse with an explicitly bounded prefix and restore the writer', async () => {
    const writer = () => true;
    const stream = { write: writer };
    const output = 'x'.repeat(preparer.MAX_SETUP_DIAGNOSTIC_BYTES + 1);
    let caught: any;
    try { await preparer.captureSetupDiagnostics(async () => { stream.write(output); }, 768, stream); }
    catch (error) { caught = error; }
    expect(caught?.reason).toBe('setup-diagnostics-byte-budget');
    const retained = Buffer.from(caught.diagnostics.utf8_base64, 'base64');
    expect(retained.length).toBe(preparer.MAX_SETUP_DIAGNOSTIC_BYTES);
    expect(caught.diagnostics).toMatchObject({ classification: 'setup-diagnostics-byte-budget', truncated: true,
      bytes_seen: Buffer.byteLength(output), sha256: createHash('sha256').update(retained).digest('hex') });
    expect(stream.write).toBe(writer);
  });

  test('carries setup diagnostics into successful and refused preparation receipts', async () => {
    const stream = { write: (_chunk: string) => true };
    const captured = await preparer.captureSetupDiagnostics(async () => {
      stream.write('  Setting up brain schema (v144)...\n');
    }, 768, stream);
    const successful = harness();
    (successful.engine as any).setupDiagnostics = captured.diagnostics;
    expect((await prepareIndex(request(), successful.dependencies)).setup_diagnostics).toEqual(captured.diagnostics);
    const failed = harness();
    failed.dependencies.openNew = async () => {
      await preparer.captureSetupDiagnostics(async () => { stream.write('ERROR: migration failed\n'); }, 768, stream);
      throw new Error('unreachable');
    };
    const result = await prepareIndex(request(), failed.dependencies);
    expect(result.status).toBe('refused');
    expect(result.setup_diagnostics.text).toBe('ERROR: migration failed\n');
    expect(result.setup_diagnostics.classification).toBe('unrecognized-setup-diagnostics');
  });
});
