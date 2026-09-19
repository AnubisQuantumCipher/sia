import { describe, expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import * as preparer from './prepare-index.ts';

// JACKAL status=exact parsed=1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1 exact=17;
// parsed=2048+17 exact=2065. non_claims: NOT formal-bounded: this lane carries
// no Lean-checked certificate; The epistemic class above is the STRONGEST claim
// this result supports; exact rational arithmetic (not yet checker-covered).
const sha = (value: string | Uint8Array) => createHash('sha256').update(value).digest('hex');
function policy(mode = 'nomic-prefix-v1') {
  return { schema: 'sia-embedding-input-policy-v1', mode,
    document_prefix: mode === 'bare-v1' ? '' : 'search_document: ',
    query_prefix: mode === 'bare-v1' ? '' : 'search_query: ', encoding: 'utf-8',
    document_stage: 'after-lossless-chunking', query_stage: 'original-query', overflow: 'refuse' };
}
function request(mode = 'nomic-prefix-v1'): any {
  const text = 'search_document: original é\n' + 'a'.repeat(2048) + '\n[origin:model] unchanged\n';
  const pages = [{ slug: 'events/synthetic', title: 'Original', type: 'event', origin: 'model',
    text, text_sha256: sha(text) }];
  const inputPolicy = policy(mode);
  return { v: 2, operation: 'prepare_index', source: 'sia', dataset_sha256: sha('same dataset'),
    pages_sha256: sha(preparer.canonicalJson(pages)), pages, output: { parent_fd: 8 },
    embedding: { model: 'ollama:nomic-embed-text:v1.5', dimensions: 3, endpoint: 'http://127.0.0.1:11434/v1' },
    embedding_input_policy: inputPolicy, embedding_input_policy_sha256: sha(preparer.canonicalJson(inputPolicy)) };
}
function harness() {
  const calls: any[] = []; const pages = new Map<string, any>(); const chunks = new Map<string, any[]>();
  let marker: any;
  const engine = {
    writeEmbeddingInputPolicy: async (policy: any, digest: string) => {
      marker = { policy: structuredClone(policy), digest }; calls.push('write-policy');
    },
    assertEmbeddingInputPolicy: async (policy: any, digest: string) => {
      calls.push('assert-policy');
      if (!marker || marker.digest !== digest || preparer.canonicalJson(marker.policy) !== preparer.canonicalJson(policy))
        throw new Error('policy marker mismatch');
    },
    writePage: async (page: any, rows: any[]) => {
      calls.push('write-page');
      pages.set(page.slug, { slug: page.slug, title: page.title, type: page.type, compiled_truth: page.text,
        timeline: '', frontmatter: { origin: page.origin } });
      chunks.set(page.slug, rows.map(row => ({ ...row, embedding: new Float32Array(row.embedding) })));
    },
    listSlugs: async () => Array.from(pages.keys()), readPage: async (slug: string) => pages.get(slug),
    readChunks: async (slug: string) => chunks.get(slug), close: async () => { calls.push('close'); },
  };
  const dependencies = {
    openNew: async () => { calls.push('open'); return engine; },
    embedDocument: async (text: string, embedding: unknown) => {
      calls.push({ embed: text, embedding }); return new Float32Array([1, 0, 0]);
    },
  };
  return { calls, pages, chunks, engine, dependencies, corruptMarker: () => { marker = null; } };
}

describe('v2 lossless index preparation with explicit embedding input', () => {
  test('admits both literal policy modes while leaving v1 admission intact', () => {
    for (const mode of ['bare-v1', 'nomic-prefix-v1']) {
      const q = request(mode);
      expect(preparer.parsePrepareRequest(Buffer.from(JSON.stringify(q)))).toEqual(q);
    }
    const legacy = request('bare-v1'); legacy.v = 1;
    delete legacy.embedding_input_policy; delete legacy.embedding_input_policy_sha256;
    expect(preparer.parsePrepareRequest(Buffer.from(JSON.stringify(legacy)))).toEqual(legacy);
  });

  test('embeds prefix plus each original chunk and never stores that added prefix', async () => {
    expect(Buffer.byteLength('search_document: ')).toBe(17);
    for (const mode of ['bare-v1', 'nomic-prefix-v1']) {
      const q = request(mode); const before = preparer.canonicalJson(q); const h = harness();
      const originalChunks = preparer.splitLossless(q.pages[0].text);
      const result: any = await preparer.prepareIndex(q, h.dependencies);
      expect(result.status).toBe('ok'); expect(result.v).toBe(2);
      expect(preparer.canonicalJson(q)).toBe(before);
      expect(h.calls.slice(0, 3)).toEqual(['open', 'write-policy', 'assert-policy']);
      const inputs = h.calls.filter(x => x?.embed).map(x => x.embed);
      expect(inputs).toEqual(originalChunks.map(text => q.embedding_input_policy.document_prefix + text));
      expect(inputs[0]).toBe(q.embedding_input_policy.document_prefix + originalChunks[0]);
      expect(h.pages.get(q.pages[0].slug).compiled_truth).toBe(q.pages[0].text);
      expect(h.pages.get(q.pages[0].slug).frontmatter.origin).toBe('model');
      expect(h.chunks.get(q.pages[0].slug)!.map(row => row.chunk_text)).toEqual(originalChunks);
      expect(result.embedding_input_policy).toEqual(q.embedding_input_policy);
      expect(result.bindings.embedding_input_policy_sha256).toBe(q.embedding_input_policy_sha256);
      expect(result.bindings.pages_sha256).toBe(q.pages_sha256);
      result.pages[0].chunks.forEach((row: any, index: number) => {
        expect(row).toMatchObject({ text_sha256: sha(originalChunks[index]), bytes: Buffer.byteLength(originalChunks[index]),
          embedding_input_sha256: sha(inputs[index]), embedding_input_bytes: Buffer.byteLength(inputs[index]) });
        expect(row.vector_sha256).toBe(sha(Buffer.from(new Float32Array([1, 0, 0]).buffer)));
      });
      if (mode === 'nomic-prefix-v1') expect(Buffer.byteLength(inputs[0])).toBe(2065);
      expect(h.calls.slice(-2)).toEqual(['assert-policy', 'close']);
      expect(result.non_claims).toContain('Embedding-input digests bind adapter-supplied UTF-8 text, not an independently observed HTTP body or proof of model computation.');
    }
  });

  test('rejects unsupported or inconsistent policy before any output or provider side effect', async () => {
    for (const change of [
      { embedding_input_policy_sha256: sha('foreign') },
      { embedding_input_policy: { ...policy(), document_prefix: 'search_document:' } },
      { embedding_input_policy: { ...policy(), document_stage: 'before-chunking' } },
      { embedding_input_policy: { ...policy(), query_prefix: '' } },
      { embedding_input_policy: { ...policy(), overflow: 'truncate' } },
      { embedding_input_policy: { ...policy(), source_rewrite: true } },
      { embedding: { ...request().embedding, model: 'ollama:other' } },
    ]) {
      const q = { ...request(), ...change };
      if ('embedding_input_policy' in change) q.embedding_input_policy_sha256 = sha(preparer.canonicalJson(q.embedding_input_policy));
      const h = harness();
      expect((await preparer.prepareIndex(q, h.dependencies)).status).toBe('refused');
      expect(h.calls).toEqual([]);
    }
  });

  test('a missing or mismatched persisted marker refuses before embedding', async () => {
    const h = harness(); h.engine.writeEmbeddingInputPolicy = async () => { h.calls.push('write-policy'); };
    const result: any = await preparer.prepareIndex(request(), h.dependencies);
    expect(result.status).toBe('refused'); expect(result).not.toHaveProperty('pages');
    expect(h.calls.filter(x => x?.embed)).toEqual([]); expect(h.calls.at(-1)).toBe('close');
  });

  test('marker mutation during preparation refuses complete readback publication', async () => {
    const h = harness(); const write = h.engine.writePage;
    h.engine.writePage = async (page, chunks) => { await write(page, chunks); h.corruptMarker(); };
    const result: any = await preparer.prepareIndex(request(), h.dependencies);
    expect(result.status).toBe('refused'); expect(result).not.toHaveProperty('pages');
    expect(h.calls.at(-1)).toBe('close');
  });

  test('original content, origin, complete chunk roster and vector readback remain controlling', async () => {
    for (const kind of ['content', 'origin', 'chunk', 'vector']) {
      const h = harness(); const write = h.engine.writePage;
      h.engine.writePage = async (page, rows) => {
        await write(page, rows);
        if (kind === 'content') h.pages.get(page.slug).compiled_truth = 'search_document: ' + page.text;
        if (kind === 'origin') h.pages.get(page.slug).frontmatter.origin = 'evidence';
        if (kind === 'chunk') h.chunks.get(page.slug)!.pop();
        if (kind === 'vector') h.chunks.get(page.slug)![0].embedding = new Float32Array([0, 1, 0]);
      };
      const result: any = await preparer.prepareIndex(request(), h.dependencies);
      expect(result.status).toBe('refused'); expect(result).not.toHaveProperty('pages');
      expect(h.calls.at(-1)).toBe('close');
    }
  });
});
