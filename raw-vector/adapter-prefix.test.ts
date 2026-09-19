import { describe, expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import * as adapter from './adapter.ts';

// Synthetic contract only; never import the gateway or open a real index.
// JACKAL status=exact parsed=8000-(1+1+1+1+1+1+1+1+1+1+1+1+1+1) exact=7986;
// parsed=(8000-(1+1+1+1+1+1+1+1+1+1+1+1+1+1))/2 exact=3993.
// non_claims: NOT formal-bounded: this lane carries no Lean-checked certificate;
// The epistemic class above is the STRONGEST claim this result supports;
// exact rational arithmetic (not yet checker-covered). These are not code proofs.
const sha = (value: string | Uint8Array) => createHash('sha256').update(value).digest('hex');
const canonical = adapter.canonicalJson;
const providerOrSearchCall = (value: unknown) => value !== null && typeof value === 'object'
  && (Object.hasOwn(value, 'embed') || Object.hasOwn(value, 'search'));
const BOUNDARIES = [
  'Embedding input prefixes affect only provider input; original query, page and chunk text identities are retained.',
  'Embedding-input digests bind adapter-supplied UTF-8 text, not an independently observed HTTP body or proof of model computation.',
];
function policy(mode = 'nomic-prefix-v1') {
  return { schema: 'sia-embedding-input-policy-v1', mode,
    document_prefix: mode === 'bare-v1' ? '' : 'search_document: ',
    query_prefix: mode === 'bare-v1' ? '' : 'search_query: ', encoding: 'utf-8',
    document_stage: 'after-lossless-chunking', query_stage: 'original-query', overflow: 'refuse' };
}
const state = { logical_sha256: sha('synthetic index'), catalog_sha256: sha('synthetic catalog') };
function request(mode = 'nomic-prefix-v1'): any {
  const inputPolicy = policy(mode);
  return { v: 2, operation: 'query', lane: 'raw_vector',
    queries: [{ id: 'synthetic-a', text: 'search_query: original é\n' }], limit: 5,
    snapshot: { fd: 8, ...state }, embedding: { model: 'ollama:nomic-embed-text:v1.5',
      dimensions: 3, endpoint: 'http://127.0.0.1:11434/v1' },
    binding: { executable_sha256: sha('same executable'), build_receipt_sha256: sha('same build') },
    embedding_input_policy: inputPolicy, embedding_input_policy_sha256: sha(canonical(inputPolicy)) };
}
function harness() {
  const calls: any[] = [];
  const row = { slug: 'events/synthetic', source_id: 'sia', page_id: 7, title: 'Original title',
    type: 'event', chunk_id: 11, chunk_index: 0, chunk_text: 'search_document: original stored é\n',
    chunk_source: 'compiled_truth', score: 0.75, stale: false };
  const engine = {
    snapshot: async () => { calls.push('snapshot'); return { ...state }; },
    searchVector: async (vector: Float32Array, options: unknown) => {
      calls.push({ search: Array.from(vector), options }); return [row];
    }, close: async () => { calls.push('close'); },
  };
  const dependencies = {
    connect: async (fd: number) => { calls.push({ connect: fd }); return engine; },
    embed: async (text: string, embedding: unknown) => {
      calls.push({ embed: text, embedding }); return new Float32Array([1, 0, 0]);
    }, now: () => 1000,
  };
  return { calls, engine, dependencies, row };
}

describe('explicit v2 embedding-input policy', () => {
  test('classifies provider/search events by their own fields', () => {
    const embedding = { embed: 'original input' };
    const search = { search: [] };
    expect(['snapshot', 'close', embedding, search].filter(providerOrSearchCall)).toEqual([embedding, search]);
  });

  test('admits both declared modes without deriving policy from model name', () => {
    for (const mode of ['bare-v1', 'nomic-prefix-v1']) {
      const q = request(mode);
      expect(adapter.parseRequest(Buffer.from(JSON.stringify(q)))).toEqual(q);
    }
  });

  test('rejects missing, self-inconsistent, arbitrary or type-confused policy before connecting', async () => {
    for (const mutate of [
      (q: any) => { delete q.embedding_input_policy; },
      (q: any) => { delete q.embedding_input_policy_sha256; },
      (q: any) => { q.embedding_input_policy_sha256 = sha('other'); },
      (q: any) => { q.embedding_input_policy.mode = 'automatic'; },
      (q: any) => { q.embedding_input_policy.query_prefix = 'search_query:'; },
      (q: any) => { q.embedding_input_policy.document_prefix = ''; },
      (q: any) => { q.embedding_input_policy.extra = 'hidden'; },
      (q: any) => { q.embedding_input_policy.overflow = 'truncate'; },
      (q: any) => { q.embedding_input_policy = []; },
      (q: any) => { q.embedding.model = 'ollama:other'; },
      (q: any) => { q.v = true; },
    ]) {
      const q = request(); mutate(q);
      if (q.embedding_input_policy && typeof q.embedding_input_policy === 'object'
        && !Array.isArray(q.embedding_input_policy)
        && q.embedding_input_policy_sha256 === request().embedding_input_policy_sha256)
        q.embedding_input_policy_sha256 = sha(canonical(q.embedding_input_policy));
      const h = harness();
      expect((await adapter.runRawVector(q, h.dependencies)).status).toBe('refused');
      expect(h.calls).toEqual([]);
    }
  });

  test('bounds the complete UTF-8 provider input before connecting without narrowing v1', async () => {
    expect(Buffer.byteLength('search_query: ')).toBe(14);
    for (const original of ['a'.repeat(7986), 'é'.repeat(3993)]) {
      const q = request(); q.queries[0].text = original;
      expect(Buffer.byteLength(q.embedding_input_policy.query_prefix + original)).toBe(8000);
      expect(adapter.parseRequest(Buffer.from(JSON.stringify(q)))).toEqual(q);
      q.queries[0].text += 'é';
      const h = harness();
      expect((await adapter.runRawVector(q, h.dependencies)).status).toBe('refused');
      expect(h.calls).toEqual([]);
    }
    const bare = request('bare-v1'); bare.queries[0].text = 'a'.repeat(8000);
    expect(adapter.parseRequest(Buffer.from(JSON.stringify(bare)))).toEqual(bare);
    const legacy = { ...bare, v: 1 };
    delete legacy.embedding_input_policy; delete legacy.embedding_input_policy_sha256;
    expect(adapter.parseRequest(Buffer.from(JSON.stringify(legacy)))).toEqual(legacy);
  });

  test('adds exactly one transform even when original text already starts with a prefix', async () => {
    for (const mode of ['bare-v1', 'nomic-prefix-v1']) {
      const q = request(mode); const before = canonical(q); const h = harness();
      const result: any = await adapter.runRawVector(q, h.dependencies);
      expect(result.status).toBe('ok'); expect(result.v).toBe(2);
      expect(canonical(q)).toBe(before);
      const input = q.embedding_input_policy.query_prefix + q.queries[0].text;
      expect(h.calls.filter(x => x?.embed).map(x => x.embed)).toEqual([input]);
      expect(result.embedding_input_policy).toEqual(q.embedding_input_policy);
      expect(result.bindings.embedding_input_policy_sha256).toBe(q.embedding_input_policy_sha256);
      expect(result.results[0]).toMatchObject({ query_sha256: sha(q.queries[0].text),
        embedding_input_sha256: sha(input), embedding_input_bytes: Buffer.byteLength(input) });
      expect(result.results[0].rows[0].chunk_text).toBe(h.row.chunk_text);
      expect(result.results[0].vector_f32le_base64).toBe(Buffer.from(new Float32Array([1, 0, 0]).buffer).toString('base64'));
      expect(result.results[0].ranked_rows_sha256).toBe(sha(Buffer.from(result.results[0].ranked_rows_canonical_base64, 'base64')));
      expect(h.calls.find(x => x?.options)?.options).toEqual({ limit: 5, offset: 0, sourceId: 'sia', detail: 'high',
        exclude_slug_prefixes: ['test/', 'attachments/', '.raw/'], include_slug_prefixes: [], excludePrivate: false,
        embeddingColumn: { name: 'embedding', type: 'vector', dimensions: 3, embeddingModel: q.embedding.model } });
      for (const boundary of BOUNDARIES) expect(result.non_claims).toContain(boundary);
    }
  });

  test('captures the policy-bound index with no embedding calls and no answers', async () => {
    const q = request(); q.operation = 'capture'; q.queries = [];
    q.snapshot = { fd: 8, logical_sha256: null, catalog_sha256: null };
    const h = harness(); const result: any = await adapter.runRawVector(q, h.dependencies);
    expect(result.status).toBe('ok'); expect(result.results).toEqual([]);
    expect(result.bindings.embedding_input_policy_sha256).toBe(q.embedding_input_policy_sha256);
    expect(h.calls.filter(providerOrSearchCall)).toEqual([]);
  });

  test('checks complete fixed scalar policy SQL predicates before embedding', async () => {
    const q = request();
    const base = { config_model_matches: true, config_dimensions_match: true, search_column_matches: true,
      physical_column_matches: true, chunk_models_match: true, embedded_text_matches: true,
      embedding_input_policy_matches: true, embedding_input_policy_sha256_matches: true };
    for (const invalid of [null, 'embedding_input_policy_matches', 'embedding_input_policy_sha256_matches']) {
      let checked = false; const h = harness();
      h.engine.snapshot = async () => {
        await (adapter.inspectSnapshotEmbedding as any)(async (sql: string, parameters: unknown[]) => {
          checked = true;
          expect(sql).toContain("key='sia_embedding_input_policy'");
          expect(sql).toContain("key='sia_embedding_input_policy_sha256'");
          expect(sql).toContain('count(*)=1');
          expect(sql).toContain('cc.embedded_text_hash IS NULL');
          expect(sql).toContain('cc.embedded_text_hash <> md5(cc.chunk_text)');
          expect(parameters).toContain(canonical(q.embedding_input_policy));
          expect(parameters).toContain(q.embedding_input_policy_sha256);
          return [{ ...base, ...(invalid ? { [invalid]: false } : {}) }];
        }, q.embedding, q.embedding_input_policy, q.embedding_input_policy_sha256);
        return { ...state };
      };
      const result: any = await adapter.runRawVector(q, h.dependencies);
      expect(checked).toBe(true);
      expect(result.status).toBe(invalid ? 'refused' : 'ok');
      if (invalid) expect(h.calls.filter(providerOrSearchCall)).toEqual([]);
    }
  });

  test('still refuses post-search snapshot mutation without partial ranked rows', async () => {
    const q = request(); const h = harness(); let first = true;
    h.engine.snapshot = async () => {
      if (first) { first = false; return { ...state }; }
      return { ...state, logical_sha256: sha('changed policy or index') };
    };
    const result: any = await adapter.runRawVector(q, h.dependencies);
    expect(result.status).toBe('refused'); expect(result).not.toHaveProperty('results');
    expect(h.calls.at(-1)).toBe('close');
  });
});
