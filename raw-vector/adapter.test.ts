import { describe, expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, openSync, closeSync, rmSync, symlinkSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// The import is deliberately local: core contract tests must not open an index,
// initialize the embedding gateway, or import the installed gbrain runtime.
import {
  parseRequest, runRawVector, canonicalJson, digestSnapshot,
  MAX_REQUEST_BYTES, MAX_QUERY_BYTES, MAX_SNAPSHOT_ROWS,
} from './adapter.ts';
import * as adapter from './adapter.ts';

const sha = (value: string) => createHash('sha256').update(value).digest('hex');
const state = {
  logical_sha256: sha('fixed logical snapshot'),
  catalog_sha256: sha('fixed schema catalog'),
};
function request() {
  return {
    v: 1, operation: 'query', lane: 'raw_vector', queries: [{ id: 'held-out-a', text: 'What repaired audio?' }],
    limit: 5,
    snapshot: { fd: 8, ...state },
    embedding: { model: 'llama-server:private-fixture', dimensions: 3,
      endpoint: 'http://127.0.0.1:8081/v1' },
    binding: { executable_sha256: sha('pinned executable'), build_receipt_sha256: sha('pinned closure') },
  };
}
function harness() {
  const calls: unknown[] = [];
  let digestCalls = 0;
  const engine = {
    snapshot: async () => { calls.push('snapshot'); digestCalls += 1; return { ...state }; },
    searchVector: async (vector: Float32Array, options: unknown) => {
      calls.push({ search: Array.from(vector), options });
      return [{ slug: 'event/audio-repair', source_id: 'sia', page_id: 7, title: 'Audio repair',
        type: 'event', chunk_id: 11, chunk_index: 0, chunk_text: 'wireplumber restarted',
        chunk_source: 'compiled_truth', score: 0.75, stale: false }];
    },
    close: async () => { calls.push('close'); },
  };
  const dependencies = {
    connect: async (fd: number) => { calls.push({ connect: fd }); return engine; },
    embed: async (text: string, config: unknown, signal: AbortSignal) => {
      calls.push({ embed: text, config, signal: signal instanceof AbortSignal });
      return new Float32Array([1, 0, 0]);
    },
    now: () => 1000,
  };
  return { calls, engine, dependencies, digestCalls: () => digestCalls };
}

describe('query-only raw-vector request admission', () => {
  test('opens only the fixed ordinary index child of an owned private descriptor parent', () => {
    const directory = mkdtempSync(join(tmpdir(), 'sia-vector-parent-test-'));
    const fd = openSync(directory, 'r');
    try {
      expect(() => adapter.snapshotIndexPath(fd)).toThrow('snapshot-index-missing');
      mkdirSync(join(directory, 'index'), { mode: 0o700 });
      expect(adapter.snapshotIndexPath(fd)).toBe(`/proc/self/fd/${fd}/index`);
      chmodSync(join(directory, 'index'), 0o755);
      expect(() => adapter.snapshotIndexPath(fd)).toThrow('snapshot-index-invalid');
      chmodSync(join(directory, 'index'), 0o700);
      chmodSync(directory, 0o755);
      expect(() => adapter.snapshotIndexPath(fd)).toThrow('snapshot-parent-invalid');
      chmodSync(directory, 0o700);
    } finally { closeSync(fd); rmSync(directory, { recursive: true }); }
    const links = mkdtempSync(join(tmpdir(), 'sia-vector-symlink-test-'));
    const linkFd = openSync(links, 'r');
    try {
      mkdirSync(join(links, 'target'), { mode: 0o700 });
      symlinkSync('target', join(links, 'index'));
      expect(() => adapter.snapshotIndexPath(linkFd)).toThrow('snapshot-index-invalid');
    } finally { closeSync(linkFd); rmSync(links, { recursive: true }); }
  });

  test('admits the explicit private-snapshot query protocol', () => {
    expect(parseRequest(Buffer.from(JSON.stringify(request())))).toEqual(request());
  });

  test('rejects answer keys, hidden policy fields, and malformed descriptors before connecting', async () => {
    for (const change of [
      { answer_key: ['event/audio-repair'] },
      { queries: [{ ...request().queries[0], relevant_slugs: ['event/audio-repair'] }] },
      { snapshot: { ...request().snapshot, path: '/some/database' } },
      { snapshot: { ...request().snapshot, fd: true } },
      { limit: true },
      { embedding: { ...request().embedding, endpoint: 'https://remote.example/v1' } },
      { embedding: { ...request().embedding, dimensions: 0 } },
      { binding: { executable_sha256: 'unbound', build_receipt_sha256: sha('closure') } },
      { queries: [request().queries[0], request().queries[0]] },
    ]) {
      const h = harness();
      const result = await runRawVector({ ...request(), ...change }, h.dependencies);
      expect(result.status).toBe('refused');
      expect(h.calls).toEqual([]);
    }
  });

  test('enforces raw input and UTF-8 query byte budgets', () => {
    expect(() => parseRequest(Buffer.alloc(MAX_REQUEST_BYTES + 1, 32))).toThrow('request-byte-budget');
    const q = request();
    q.queries[0].text = 'é'.repeat(MAX_QUERY_BYTES);
    expect(() => parseRequest(Buffer.from(JSON.stringify(q)))).toThrow('query-byte-budget');
    expect(() => parseRequest(Buffer.from([0xff]))).toThrow('request-utf8');
  });

  test('never admits a query beyond the pinned gateway ceiling and counts Unicode bytes exactly', () => {
    // gateway.ts declares MAX_CHARS=8000, and truncateUtf8 actually measures
    // UTF-16 code units. A byte ceiling at that value guarantees no admitted
    // well-formed UTF-8 text can reach the gateway's truncating branch.
    const boundary = request();
    boundary.queries[0].text = 'a'.repeat(8000);
    expect(parseRequest(Buffer.from(JSON.stringify(boundary)))).toEqual(boundary);
    boundary.queries[0].text += 'a';
    expect(() => parseRequest(Buffer.from(JSON.stringify(boundary)))).toThrow('query-byte-budget');
    const unicode = request();
    unicode.queries[0].text = 'é'.repeat(8000 / Buffer.byteLength('é'));
    expect(Buffer.byteLength(unicode.queries[0].text)).toBe(8000);
    expect(parseRequest(Buffer.from(JSON.stringify(unicode)))).toEqual(unicode);
    unicode.queries[0].text += 'é';
    expect(() => parseRequest(Buffer.from(JSON.stringify(unicode)))).toThrow('query-byte-budget');
  });

  test('rejects duplicate JSON members that could hide answer keys or substitute a binding', () => {
    const body = JSON.stringify(request()).replace('"v":1', '"v":1,"v":1');
    expect(() => parseRequest(Buffer.from(body))).toThrow('duplicate-json-key');
  });
});

describe('raw-vector execution contract', () => {
  test('names the failed execution phase without returning raw exception messages', async () => {
    for (const phase of ['connect', 'snapshot-before', 'embed', 'search', 'snapshot-after', 'close']) {
      const h = harness();
      const fail = async () => { throw new Error('private path, query text and provider details'); };
      if (phase === 'connect') h.dependencies.connect = fail;
      if (phase === 'snapshot-before') h.engine.snapshot = fail;
      if (phase === 'embed') h.dependencies.embed = fail;
      if (phase === 'search') h.engine.searchVector = fail;
      if (phase === 'snapshot-after') {
        let first = true;
        h.engine.snapshot = async () => {
          if (first) { first = false; return { ...state }; }
          return fail();
        };
      }
      if (phase === 'close') h.engine.close = fail;
      const result = await runRawVector(request(), h.dependencies);
      expect(result).toMatchObject({ status: 'refused', reason: `adapter-${phase}-failed` });
      expect(JSON.stringify(result)).not.toContain('private path');
      expect(result).not.toHaveProperty('results');
    }
  });

  test('binds a closed database component and retains only SQLSTATE-form diagnostic codes', async () => {
    for (const [code, suffix] of [['42601', '-sqlstate-42601'], ['42P01', '-sqlstate-42P01'],
      ['private-diagnostic', ''], ['EPERM', ''], [42601, ''], ['42P01\nprivate', '']]) {
      const h = harness();
      h.engine.snapshot = () => adapter.withDatabaseStage('catalog-read', async () => {
        throw Object.assign(new Error('private SQL and object names'), { code });
      });
      const result = await runRawVector(request(), h.dependencies);
      expect(result).toMatchObject({ status: 'refused', reason: `adapter-snapshot-before-catalog-read-failed${suffix}` });
      expect(JSON.stringify(result)).not.toContain('private SQL');
    }
    await expect(adapter.withDatabaseStage('private input as stage', async () => 'unreachable'))
      .rejects.toThrow('database-stage-invalid');
  });

  test('publishes the exact row bytes whose digest is claimed across language serializers', async () => {
    const h = harness();
    h.engine.searchVector = async () => [{ slug: 'event/unicode', source_id: 'sia', page_id: 7,
      title: 'Memory — π', type: 'event', chunk_id: 11, chunk_index: 0,
      chunk_text: 'Retained Unicode and a small floating-point score.', chunk_source: 'compiled_truth',
      score: 1e-7, stale: false }];
    const result = await runRawVector(request(), h.dependencies);
    expect(result.status).toBe('ok');
    const encoded = result.results[0].ranked_rows_canonical_base64;
    expect(typeof encoded).toBe('string');
    const rowBytes = Buffer.from(encoded, 'base64');
    expect(rowBytes.toString('base64')).toBe(encoded);
    const rowText = new TextDecoder('utf-8', { fatal: true }).decode(rowBytes);
    expect(JSON.parse(rowText)).toEqual(result.results[0].rows);
    expect(rowText).toContain('"score":1e-7');
    expect(rowText).toContain('Memory — π');
    expect(createHash('sha256').update(rowBytes).digest('hex')).toBe(result.results[0].ranked_rows_sha256);
  });

  test('binds the snapshot before embedding and after search, retaining only normalized raw rows', async () => {
    const h = harness();
    const result = await runRawVector(request(), h.dependencies);
    expect(result.status).toBe('ok');
    expect(result.lane).toBe('raw_vector');
    expect(h.calls[0]).toEqual({ connect: 8 });
    expect(h.calls[1]).toBe('snapshot');
    expect(h.calls[2]).toMatchObject({ embed: request().queries[0].text,
      config: request().embedding, signal: true });
    expect(h.calls[3]).toEqual({ search: [1, 0, 0], options: {
      limit: 5, offset: 0, sourceId: 'sia', detail: 'high',
      exclude_slug_prefixes: ['test/', 'attachments/', '.raw/'],
      include_slug_prefixes: [], excludePrivate: false,
      embeddingColumn: { name: 'embedding', type: 'vector', dimensions: 3,
        embeddingModel: 'llama-server:private-fixture' },
    } });
    expect(h.calls.slice(4)).toEqual(['snapshot', 'close']);
    expect(result.bindings).toMatchObject({ ...state, ...request().binding });
    expect(result.results[0].ranked_rows_sha256).toBe(sha(canonicalJson(result.results[0].rows)));
    expect(result.results[0].query_sha256).toBe(sha(request().queries[0].text));
    expect(result.results[0].vector_f32le_base64).toBe(Buffer.from(new Float32Array([1, 0, 0]).buffer).toString('base64'));
    const scoreBytes = Buffer.alloc(8);
    scoreBytes.writeDoubleLE(0.75);
    expect(result.results[0].rows[0].score_f64le_base64).toBe(scoreBytes.toString('base64'));
    expect(result.non_claims).toContain('The embedding model identifier and endpoint are bound; served model weights are not attested by this adapter.');
    expect(result.non_claims).toContain('Raw-vector search retains gbrain page pooling, visibility filters, and bounded approximate candidate retrieval.');
    expect(result.results[0].rows[0]).toMatchObject({ slug: 'event/audio-repair', source_id: 'sia', score: 0.75 });
    expect(result.results[0].rows[0].chunk_text).toBe('wireplumber restarted');
    expect(result.results[0].rows[0]).toMatchObject({ title: 'Audio repair', type: 'event' });
    expect(result.results[0].latency_ms).toEqual({ embedding: 0, search: 0 });
    expect(result.latency_ms).toEqual({ total: 0 });
  });

  test('processes ordered queries sequentially under the same connection and snapshot binding', async () => {
    const h = harness();
    const q = request();
    q.queries.push({ id: 'held-out-b', text: 'What happened later?' });
    const result = await runRawVector(q, h.dependencies);
    expect(result.status).toBe('ok');
    expect(result.results.map((r: {id: string}) => r.id)).toEqual(['held-out-a', 'held-out-b']);
    expect(h.calls.filter(x => typeof x === 'object' && x !== null && 'connect' in x)).toHaveLength(1);
    expect(h.digestCalls()).toBe(2);
    expect(h.calls.slice(2, 6).map(x => typeof x === 'object' && x !== null && 'embed' in x ? 'embed' : 'search'))
      .toEqual(['embed', 'search', 'embed', 'search']);
  });

  test('capture binds a private snapshot without sending any query to the embedding provider', async () => {
    const h = harness();
    const q = { ...request(), operation: 'capture', queries: [],
      snapshot: { fd: 8, logical_sha256: null, catalog_sha256: null } };
    const result = await runRawVector(q, h.dependencies);
    expect(result.status).toBe('ok');
    expect(result.results).toEqual([]);
    expect(result.bindings).toMatchObject(state);
    expect(h.calls).toEqual([{ connect: 8 }, 'snapshot', 'snapshot', 'close']);
  });

  test('does not embed or search an unbound generation and always closes the engine', async () => {
    const h = harness();
    h.engine.snapshot = async () => ({ ...state, logical_sha256: sha('another generation') });
    const result = await runRawVector(request(), h.dependencies);
    expect(result).toMatchObject({ status: 'refused', reason: 'snapshot-identity-mismatch' });
    expect(h.calls).toEqual([{ connect: 8 }, 'close']);
  });

  test('refuses post-search mutation and never returns ranked rows with the refusal', async () => {
    const h = harness();
    let first = true;
    h.engine.snapshot = async () => {
      if (first) { first = false; return { ...state }; }
      return { ...state, catalog_sha256: sha('changed catalog') };
    };
    const result = await runRawVector(request(), h.dependencies);
    expect(result).toMatchObject({ status: 'refused', reason: 'snapshot-changed-during-query' });
    expect(result).not.toHaveProperty('rows');
    expect(result).not.toHaveProperty('results');
    expect(h.calls.at(-1)).toBe('close');
  });

  test('refuses malformed or zero query vectors before search', async () => {
    for (const vector of [new Float32Array([1]), new Float32Array([NaN, 0, 0]),
      new Float32Array([Infinity, 0, 0]), new Float32Array([0, 0, 0])]) {
      const h = harness();
      h.dependencies.embed = async () => vector;
      const result = await runRawVector(request(), h.dependencies);
      expect(result).toMatchObject({ status: 'refused', reason: 'embedding-vector-invalid' });
      expect(h.calls.some(x => typeof x === 'object' && x !== null && 'search' in x)).toBe(false);
      expect(h.calls.at(-1)).toBe('close');
    }
  });

  test('refuses foreign-source, duplicate, non-finite, out-of-order, and over-budget rows', async () => {
    const base = { slug: 'event/a', source_id: 'sia', page_id: 1, title: 'A', type: 'event',
      chunk_id: 1, chunk_index: 0, chunk_text: 'a', chunk_source: 'compiled_truth', score: 0.8, stale: false };
    for (const rows of [
      [{ ...base, source_id: 'other' }], [base, base], [{ ...base, score: NaN }],
      [{ ...base, score: 0.2 }, { ...base, slug: 'event/b', page_id: 2, score: 0.9 }],
      Array.from({ length: 6 }, (_, i) => ({ ...base, slug: `event/${i}`, page_id: i + 1 })),
    ]) {
      const h = harness();
      h.engine.searchVector = async () => rows;
      const result = await runRawVector(request(), h.dependencies);
      expect(result).toMatchObject({ status: 'refused', reason: 'ranked-rows-invalid' });
      expect(result).not.toHaveProperty('rows');
      expect(h.calls.at(-1)).toBe('close');
    }
  });

  test('fails closed on provider/search/disconnect errors without leaking raw errors', async () => {
    for (const failure of ['embed', 'search', 'close']) {
      const h = harness();
      const error = async () => { throw new Error('secret fixture endpoint credential'); };
      if (failure === 'embed') h.dependencies.embed = error;
      if (failure === 'search') h.engine.searchVector = error;
      if (failure === 'close') h.engine.close = error;
      const result = await runRawVector(request(), h.dependencies);
      expect(result.status).toBe('refused');
      expect(JSON.stringify(result)).not.toContain('secret fixture');
      expect(result).not.toHaveProperty('rows');
    }
  });
});

describe('complete bounded logical snapshot digest', () => {
  test('binds every row and catalog definition, independent of object key order', async () => {
    const tables: Record<string, unknown[]> = {
      catalog: [{ table: 'pages', definition: 'CREATE TABLE pages (...)' }],
      pages: [{ id: 1, slug: 'event/a', frontmatter: { origin: 'evidence' } }],
      content_chunks: [{ id: 2, page_id: 1, embedding: '[1,0,0]', chunk_text: 'audio' }],
      sources: [{ id: 'sia', archived: false }], timeline_entries: [], config: [],
    };
    const reader = async (table: string, offset: number, limit: number) => tables[table].slice(offset, offset + limit);
    const before = await digestSnapshot(reader);
    tables.pages[0] = { frontmatter: { origin: 'evidence' }, slug: 'event/a', id: 1 };
    expect(await digestSnapshot(reader)).toEqual(before);
    tables.content_chunks[0] = { id: 2, page_id: 1, embedding: '[0,1,0]', chunk_text: 'audio' };
    expect((await digestSnapshot(reader)).logical_sha256).not.toBe(before.logical_sha256);
    tables.catalog[0] = { table: 'pages', definition: 'CREATE VIEW pages AS SELECT ...' };
    expect((await digestSnapshot(reader)).catalog_sha256).not.toBe(before.catalog_sha256);
  });

  test('refuses excess rows instead of digesting a truncated snapshot', async () => {
    const reader = async (_table: string, offset: number, limit: number) =>
      Array.from({ length: Math.min(limit, Math.max(0, MAX_SNAPSHOT_ROWS + 1 - offset)) }, () => ({ id: 'repeated' }));
    await expect(digestSnapshot(reader)).rejects.toThrow('snapshot-row-budget');
  });
});

describe('snapshot embedding compatibility', () => {
  test('reads only bounded scalar compatibility evidence and parameterizes declared identities', async () => {
    const good = { config_model_matches: true, config_dimensions_match: true, search_column_matches: true,
      physical_column_matches: true, chunk_models_match: true, embedded_text_matches: true };
    const calls: { sql: string; parameters: unknown[] }[] = [];
    const execute = async (sql: string, parameters: unknown[]) => {
      calls.push({ sql, parameters });
      return [{ ...good }];
    };
    await expect(adapter.inspectSnapshotEmbedding(execute, request().embedding)).resolves.toBeUndefined();
    expect(calls).toHaveLength(1);
    expect(calls[0].parameters).toEqual([request().embedding.model, '3', 'vector(3)']);
    expect(calls[0].sql).not.toContain(request().embedding.model);
    expect(calls[0].sql).not.toMatch(/SELECT\s+DISTINCT\s+cc\.model/i);
    expect(calls[0].sql).not.toMatch(/SELECT\s+key\s*,\s*value/i);
    for (const field of Object.keys(good)) {
      for (const value of [false, null, 'true', 1]) {
        await expect(adapter.inspectSnapshotEmbedding(async () => [{ ...good, [field]: value }], request().embedding))
          .rejects.toThrow('snapshot-embedding-mismatch');
      }
    }
    await expect(adapter.inspectSnapshotEmbedding(async () => [], request().embedding))
      .rejects.toThrow('snapshot-embedding-mismatch');
    await expect(adapter.inspectSnapshotEmbedding(async () => [good, good], request().embedding))
      .rejects.toThrow('snapshot-embedding-mismatch');
  });

  test('queries each compatibility condition without projecting stored labels or text', async () => {
    const metadata = { config_model_matches: true, config_dimensions_match: true, search_column_matches: true,
      physical_column_matches: true, chunk_models_match: true, embedded_text_matches: true };
    let inspected = '';
    await adapter.inspectSnapshotEmbedding(async (sql: string) => {
      inspected = sql.replace(/\s+/g, ' ');
      return [metadata];
    }, request().embedding);
    expect(inspected).toContain("bool_and(value=$1),false) FROM public.config WHERE key='embedding_model'");
    expect(inspected).toContain("bool_and(value=$2),false) FROM public.config WHERE key='embedding_dimensions'");
    expect(inspected).toContain("bool_and(value='embedding'),true) FROM public.config WHERE key='search_embedding_column'");
    expect(inspected).toContain('bool_and(format_type(a.atttypid,a.atttypmod)=$3),false)');
    expect(inspected).toContain("c.relname='content_chunks' AND c.relkind='r' AND a.attname='embedding'");
    expect(inspected).toContain('cc.model IS DISTINCT FROM $1) AS chunk_models_match');
    expect(inspected).toContain('cc.embedded_text_hash IS NULL OR cc.embedded_text_hash <> md5(cc.chunk_text)');
    expect(() => adapter.validateSnapshotEmbedding(metadata)).not.toThrow();
    expect(() => adapter.validateSnapshotEmbedding({ ...metadata, models: ['unexpected raw label'] }))
      .toThrow('snapshot-embedding-mismatch');
  });
});
