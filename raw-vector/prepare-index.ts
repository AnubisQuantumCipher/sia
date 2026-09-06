/** Construct a new private benchmark index from a frozen front-door export.
 * Build separately as src/sia-raw-vector.ts in the pinned source closure.
 * The preparer never opens an existing database or the resident index.
 */
import { createHash } from 'node:crypto';
import { fstatSync, mkdirSync, readSync, readlinkSync, writeSync } from 'node:fs';

export const MAX_CHUNK_BYTES = 2048;
export const MAX_PAGE_BYTES = 131072;
export const MAX_TOTAL_PAGE_BYTES = 4194304;
export const MAX_REQUEST_BYTES = 8388608;
export const MAX_PAGES = 256;
export const MAX_CHUNKS = 4096;
export const MAX_SETUP_DIAGNOSTIC_BYTES = 65536;
// Deliberately conservative UTF-8 bound below the pinned gateway's UTF-16 cap.
const MAX_EMBEDDING_INPUT_BYTES = 8000;
const MAX_RECEIPT_BYTES = 2097152;
const HASH = /^[a-f0-9]{64}$/;
const ORIGINS = ['evidence', 'derived', 'model', 'legacy-unlabeled'];
const POLICY = { chunking: 'utf8-contiguous-codepoint-v1', max_chunk_bytes: MAX_CHUNK_BYTES,
  source: 'sia', chunk_source: 'compiled_truth', input_type: 'document' };
const NON_CLAIMS = [
  'Origin labels are retained from the supplied frozen export; this preparer does not independently attest its source evidence.',
  'This is a new benchmark projection of exported pages, not a copy or attestation of the resident index.',
  'The provider model identifier and endpoint are bound; the parent must separately attest served model weights.',
  'Preparation timestamps are index-construction metadata, not the original event times.',
  'Lossless deterministic chunking is a declared benchmark policy, not a cognitive mechanism or a demonstrated retrieval improvement.',
  'Failure can leave a partial private index; it is never reported as an admitted completed snapshot.',
];
export const EMBEDDING_INPUT_NON_CLAIMS = [
  'Embedding input prefixes affect only provider input; original query, page and chunk text identities are retained.',
  'Embedding-input digests bind adapter-supplied UTF-8 text, not an independently observed HTTP body or proof of model computation.',
];
type EmbeddingInputPolicy = {
  schema: 'sia-embedding-input-policy-v1'; mode: 'bare-v1' | 'nomic-prefix-v1';
  document_prefix: string; query_prefix: string; encoding: 'utf-8';
  document_stage: 'after-lossless-chunking'; query_stage: 'original-query'; overflow: 'refuse';
};
type Embedding = { model: string; dimensions: number; endpoint: string };
type Page = { slug: string; title: string; type: string; origin: string; text: string; text_sha256: string };
type PrepareRequest = { v: 1 | 2; operation: 'prepare_index'; source: 'sia'; dataset_sha256: string;
  pages_sha256: string; embedding: Embedding; output: { parent_fd: number }; pages: Page[];
  embedding_input_policy?: EmbeddingInputPolicy; embedding_input_policy_sha256?: string };
type Chunk = { chunk_index: number; chunk_text: string; chunk_source: 'compiled_truth';
  embedding: Float32Array; model: string; modality: 'text' };
type Engine = {
  writeEmbeddingInputPolicy?(policy: EmbeddingInputPolicy, digest: string): Promise<void>;
  assertEmbeddingInputPolicy?(policy: EmbeddingInputPolicy, digest: string): Promise<void>;
  writePage(page: Page, chunks: Chunk[]): Promise<void>;
  readPage(slug: string): Promise<any>;
  readChunks(slug: string): Promise<any[]>;
  listSlugs(): Promise<string[]>;
  setupDiagnostics?: SetupDiagnostics;
  close(): Promise<void>;
};
type Dependencies = {
  openNew(fd: number, embedding: Embedding): Promise<Engine>;
  embedDocument(text: string, embedding: Embedding, signal: AbortSignal): Promise<Float32Array>;
};
class Refusal extends Error { constructor(readonly reason: string) { super(reason); } }
type SetupDiagnostics = {
  source: 'gbrain.initSchema/process.stderr'; classification: string; text: string | null;
  utf8_base64: string; sha256: string; bytes_seen: number; truncated: boolean; non_claims: string[];
};
class DiagnosticRefusal extends Refusal {
  constructor(reason: string, readonly diagnostics: SetupDiagnostics) { super(reason); }
}
function refuse(reason: string): never { throw new Refusal(reason); }
function sha(value: string | Uint8Array): string { return createHash('sha256').update(value).digest('hex'); }
function bytes(value: string): number { return Buffer.byteLength(value, 'utf8'); }
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
}
function keys(value: unknown, allowed: string[]): asserts value is Record<string, unknown> {
  if (!record(value) || Object.keys(value).sort().join('\0') !== [...allowed].sort().join('\0')) refuse('request-shape');
}
function integer(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
}
function validText(value: unknown, max: number, empty = false): value is string {
  return typeof value === 'string' && (empty || value.length > 0) && bytes(value) <= max
    && !value.includes('\0')
    && !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value);
}
export function canonicalJson(value: unknown, depth = 0): string {
  if (depth > 32) refuse('json-depth-budget');
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(v => canonicalJson(v, depth + 1)).join(',') + ']';
  if (record(value)) return '{' + Object.keys(value).sort().map(k =>
    JSON.stringify(k) + ':' + canonicalJson(value[k], depth + 1)).join(',') + '}';
  return refuse('json-value-invalid');
}

function validateEmbeddingInputPolicy(policy: unknown, digest: unknown, model: unknown): asserts policy is EmbeddingInputPolicy {
  keys(policy, ['schema', 'mode', 'document_prefix', 'query_prefix', 'encoding', 'document_stage', 'query_stage', 'overflow']);
  if (!['bare-v1', 'nomic-prefix-v1'].includes(policy.mode as string)) refuse('embedding-input-policy-invalid');
  const prefixed = policy.mode === 'nomic-prefix-v1';
  if (policy.schema !== 'sia-embedding-input-policy-v1' || policy.encoding !== 'utf-8'
    || policy.document_stage !== 'after-lossless-chunking' || policy.query_stage !== 'original-query'
    || policy.overflow !== 'refuse' || policy.document_prefix !== (prefixed ? 'search_document: ' : '')
    || policy.query_prefix !== (prefixed ? 'search_query: ' : '')
    || prefixed && model !== 'ollama:nomic-embed-text:v1.5') refuse('embedding-input-policy-invalid');
  if (typeof digest !== 'string' || digest.length !== 64 || !HASH.test(digest)
    || digest !== sha(canonicalJson(policy))) refuse('embedding-input-policy-mismatch');
}

function uniqueJson(source: string): unknown {
  let cursor = 0;
  const ws = () => { while (/[ \t\r\n]/.test(source[cursor] ?? '\0')) cursor += 1; };
  const string = (): string => {
    const start = cursor;
    if (source[cursor++] !== '"') return refuse('request-json');
    while (cursor < source.length) {
      const ch = source[cursor++];
      if (ch === '\\') { cursor += 1; continue; }
      if (ch === '"') {
        try { return JSON.parse(source.slice(start, cursor)); } catch { return refuse('request-json'); }
      }
    }
    return refuse('request-json');
  };
  const value = (depth: number): void => {
    if (depth > 32) refuse('json-depth-budget');
    ws();
    if (source[cursor] === '"') { string(); return; }
    if (source[cursor] === '{') {
      cursor += 1; ws();
      const seen = new Set<string>();
      if (source[cursor] === '}') { cursor += 1; return; }
      while (true) {
        ws(); const key = string();
        if (seen.has(key)) refuse('duplicate-json-key');
        seen.add(key); ws();
        if (source[cursor++] !== ':') refuse('request-json');
        value(depth + 1); ws();
        const next = source[cursor++];
        if (next === '}') return;
        if (next !== ',') refuse('request-json');
      }
    }
    if (source[cursor] === '[') {
      cursor += 1; ws();
      if (source[cursor] === ']') { cursor += 1; return; }
      while (true) {
        value(depth + 1); ws();
        const next = source[cursor++];
        if (next === ']') return;
        if (next !== ',') refuse('request-json');
      }
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(source.slice(cursor));
    if (!token) refuse('request-json');
    cursor += token[0].length;
  };
  value(0); ws();
  if (cursor !== source.length) refuse('request-json');
  try { return JSON.parse(source); } catch { return refuse('request-json'); }
}

function validate(raw: unknown): PrepareRequest {
  const v2 = record(raw) && raw.v === 2;
  keys(raw, ['v', 'operation', 'source', 'dataset_sha256', 'pages_sha256', 'embedding', 'output', 'pages',
    ...(v2 ? ['embedding_input_policy', 'embedding_input_policy_sha256'] : [])]);
  if (raw.v !== 1 && raw.v !== 2 || raw.operation !== 'prepare_index' || raw.source !== 'sia'
    || typeof raw.dataset_sha256 !== 'string' || !HASH.test(raw.dataset_sha256)
    || typeof raw.pages_sha256 !== 'string' || !HASH.test(raw.pages_sha256)) refuse('request-shape');
  keys(raw.output, ['parent_fd']);
  if (!integer(raw.output.parent_fd, 3, 1048576)) refuse('request-shape');
  keys(raw.embedding, ['model', 'dimensions', 'endpoint']);
  if (!validText(raw.embedding.model, 256) || !/^(?:ollama|llama-server):[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(raw.embedding.model)
    || !integer(raw.embedding.dimensions, 1, 16000) || typeof raw.embedding.endpoint !== 'string') refuse('request-shape');
  try {
    const endpoint = new URL(raw.embedding.endpoint);
    if (endpoint.protocol !== 'http:' || !['127.0.0.1', '[::1]'].includes(endpoint.hostname)
      || !endpoint.port || endpoint.pathname !== '/v1' || endpoint.search || endpoint.hash
      || endpoint.username || endpoint.password || endpoint.href !== raw.embedding.endpoint) refuse('request-shape');
  } catch { refuse('request-shape'); }
  if (v2) validateEmbeddingInputPolicy(raw.embedding_input_policy, raw.embedding_input_policy_sha256, raw.embedding.model);
  if (!Array.isArray(raw.pages) || raw.pages.length === 0 || raw.pages.length > MAX_PAGES) refuse('page-count-budget');
  const slugs = new Set<string>();
  let total = 0;
  let chunks = 0;
  for (const page of raw.pages) {
    keys(page, ['slug', 'title', 'type', 'origin', 'text', 'text_sha256']);
    if (!validText(page.slug, 1024) || !/^[a-z0-9][a-z0-9._-]*(?:\/[a-z0-9][a-z0-9._-]*)*$/.test(page.slug)
      || slugs.has(page.slug) || ['test/', 'attachments/', '.raw/'].some(p => (page.slug as string).startsWith(p))
      || !validText(page.title, 4096) || !validText(page.type, 128) || !/^[a-z][a-z0-9_-]*$/.test(page.type)
      || !ORIGINS.includes(page.origin as string)) refuse('request-shape');
    if (!validText(page.text, MAX_PAGE_BYTES)) refuse('page-text-invalid');
    if (typeof page.text_sha256 !== 'string' || !HASH.test(page.text_sha256) || sha(page.text) !== page.text_sha256)
      refuse('page-text-identity-mismatch');
    total += bytes(page.text);
    if (total > MAX_TOTAL_PAGE_BYTES) refuse('page-total-byte-budget');
    const pageChunks = splitLossless(page.text);
    if (v2 && pageChunks.some(chunk => bytes((raw.embedding_input_policy as EmbeddingInputPolicy).document_prefix)
      + bytes(chunk) > MAX_EMBEDDING_INPUT_BYTES)) refuse('embedding-input-byte-budget');
    chunks += pageChunks.length;
    if (chunks > MAX_CHUNKS) refuse('chunk-count-budget');
    slugs.add(page.slug);
  }
  if (sha(canonicalJson(raw.pages)) !== raw.pages_sha256) refuse('pages-identity-mismatch');
  const encoded = canonicalJson(raw);
  if (bytes(encoded) > MAX_REQUEST_BYTES) refuse('request-byte-budget');
  return JSON.parse(encoded);
}

export function parsePrepareRequest(input: Uint8Array): PrepareRequest {
  if (input.byteLength > MAX_REQUEST_BYTES) refuse('request-byte-budget');
  let source: string;
  try { source = new TextDecoder('utf-8', { fatal: true }).decode(input); }
  catch { return refuse('request-utf8'); }
  return validate(uniqueJson(source));
}

export function splitLossless(input: string): string[] {
  if (!validText(input, MAX_PAGE_BYTES)) refuse('page-text-invalid');
  const parts: string[] = [];
  let part = '';
  let size = 0;
  for (const point of input) {
    const width = bytes(point);
    if (size + width > MAX_CHUNK_BYTES) { parts.push(part); part = ''; size = 0; }
    part += point;
    size += width;
  }
  if (part) parts.push(part);
  return parts;
}

export function createPrivateIndexDirectory(fd: number): string {
  if (!integer(fd, 3, 1048576)) refuse('output-descriptor-invalid');
  const stat = fstatSync(fd);
  if (!stat.isDirectory() || stat.uid !== process.getuid!() || (stat.mode & 0o077) !== 0)
    refuse('output-descriptor-invalid');
  const parent = `/proc/self/fd/${fd}`;
  const target = readlinkSync(parent);
  const resident = '/home/sicarii/.local/share/sia/.gbrain';
  if (target === resident || target.startsWith(resident + '/')) refuse('resident-index-forbidden');
  const index = `${parent}/index`;
  try { mkdirSync(index, { mode: 0o700 }); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'EEXIST') refuse('output-index-exists');
    throw error;
  }
  return index;
}

export async function captureSetupDiagnostics<T>(
  initialize: () => Promise<T>, dimensions: number,
  stream: { write: (...args: any[]) => boolean } = process.stderr,
): Promise<{ value: T; diagnostics: SetupDiagnostics }> {
  const original = stream.write;
  const retained: Buffer[] = [];
  let retainedBytes = 0;
  let seen = 0;
  let failed = false;
  let value: T | undefined;
  let writerFailure = false;
  stream.write = (chunk: unknown, encodingOrCallback?: BufferEncoding | (() => void), callback?: () => void): boolean => {
    let encoded: Buffer;
    try {
      encoded = typeof chunk === 'string'
        ? Buffer.from(chunk, typeof encodingOrCallback === 'string' ? encodingOrCallback : 'utf8')
        : Buffer.from(chunk as Uint8Array);
    } catch { writerFailure = true; throw new Refusal('setup-diagnostics-write-invalid'); }
    seen += encoded.byteLength;
    const remaining = MAX_SETUP_DIAGNOSTIC_BYTES - retainedBytes;
    if (remaining > 0) {
      const prefix = encoded.subarray(0, Math.min(remaining, encoded.byteLength));
      // Copy only the retained prefix, so a small view cannot pin a large
      // discarded backing buffer past the byte budget.
      retained.push(Buffer.from(prefix));
      retainedBytes += prefix.byteLength;
    }
    const done = typeof encodingOrCallback === 'function' ? encodingOrCallback : callback;
    if (done) queueMicrotask(done);
    return true;
  };
  try { value = await initialize(); }
  catch { failed = true; }
  finally { stream.write = original; }

  const captured = Buffer.concat(retained);
  let decoded: string | null = null;
  try { decoded = new TextDecoder('utf-8', { fatal: true }).decode(captured); } catch {}
  const truncated = seen > MAX_SETUP_DIAGNOSTIC_BYTES;
  let classification = 'known-setup-diagnostics';
  if (truncated) classification = 'setup-diagnostics-byte-budget';
  else if (writerFailure) classification = 'setup-diagnostics-write-invalid';
  else if (failed) classification = 'schema-initialization-failed';
  else if (decoded === null) classification = 'setup-diagnostics-utf8-invalid';
  else {
    // These are the pinned source's fresh-schema progress messages, not a
    // success oracle. Any other output retains its bytes and forces refusal.
    const lines = decoded === '' ? [] : decoded.endsWith('\n') ? decoded.slice(0, -1).split('\n') : [decoded];
    if (lines.some(line => line !== '  Setting up brain schema (v144)...'
      && line !== `  v142: takes.embedding resized to vector(${dimensions}); existing take vectors cleared`
      && !/^  [0-9]+ migration\(s\) applied$/.test(line)) || (decoded !== '' && !decoded.endsWith('\n')))
      classification = 'unrecognized-setup-diagnostics';
  }
  const diagnostics: SetupDiagnostics = {
    source: 'gbrain.initSchema/process.stderr', classification, text: decoded,
    utf8_base64: captured.toString('base64'), sha256: sha(captured), bytes_seen: seen, truncated,
    non_claims: [
      'Captured setup diagnostics are informational output, not proof of schema or data correctness.',
      'When truncated is true, text/base64 and sha256 describe only the retained prefix, not the complete diagnostic stream.',
    ],
  };
  if (classification !== 'known-setup-diagnostics') {
    const reason = classification === 'unrecognized-setup-diagnostics' ? 'setup-diagnostics-unrecognized' : classification;
    throw new DiagnosticRefusal(reason, diagnostics);
  }
  return { value: value as T, diagnostics };
}

function vectorBytes(vector: unknown, dimensions: number): Buffer {
  if (!(vector instanceof Float32Array) || vector.length !== dimensions || !vector.every(Number.isFinite)
    || !vector.some(x => x !== 0)) refuse('embedding-vector-invalid');
  const encoded = Buffer.alloc(vector.byteLength);
  vector.forEach((value, index) => encoded.writeFloatLE(value, index * 4));
  return encoded;
}

export async function prepareIndex(raw: unknown, dependencies: Dependencies): Promise<any> {
  let engine: Engine | undefined;
  let result: any;
  const v = record(raw) && raw.v === 2 ? 2 : 1;
  const nonClaims = [...NON_CLAIMS, ...(v === 2 ? EMBEDDING_INPUT_NON_CLAIMS : [])];
  try {
    const request = validate(raw);
    engine = await dependencies.openNew(request.output.parent_fd, { ...request.embedding });
    if (request.v === 2) {
      if (typeof engine.writeEmbeddingInputPolicy !== 'function' || typeof engine.assertEmbeddingInputPolicy !== 'function')
        refuse('embedding-input-policy-unavailable');
      await engine.writeEmbeddingInputPolicy({ ...request.embedding_input_policy! }, request.embedding_input_policy_sha256!);
      await engine.assertEmbeddingInputPolicy({ ...request.embedding_input_policy! }, request.embedding_input_policy_sha256!);
    }
    const pages: any[] = [];
    for (const page of request.pages) {
      const chunks: Chunk[] = [];
      const receipts: any[] = [];
      for (const chunkText of splitLossless(page.text)) {
        const embeddingInput = (request.embedding_input_policy?.document_prefix ?? '') + chunkText;
        const embedding = await dependencies.embedDocument(embeddingInput, { ...request.embedding }, AbortSignal.timeout(30000));
        const vector = vectorBytes(embedding, request.embedding.dimensions);
        const chunk_index = chunks.length;
        chunks.push({ chunk_index, chunk_text: chunkText, chunk_source: 'compiled_truth',
          embedding, model: request.embedding.model, modality: 'text' });
        receipts.push({ chunk_index, text_sha256: sha(chunkText), vector_sha256: sha(vector), bytes: bytes(chunkText),
          ...(request.v === 2 ? { embedding_input_sha256: sha(embeddingInput), embedding_input_bytes: bytes(embeddingInput) } : {}) });
      }
      await engine.writePage({ ...page }, chunks);
      pages.push({ slug: page.slug, origin: page.origin, text_sha256: page.text_sha256, chunks: receipts });
    }
    // Validate final persisted state after every write, including previously
    // written pages. No successful receipt can omit the readback boundary.
    if (canonicalJson((await engine.listSlugs()).sort()) !== canonicalJson(request.pages.map(p => p.slug).sort()))
      refuse('index-readback-mismatch');
    for (const [index, page] of request.pages.entries()) {
      const stored = await engine.readPage(page.slug);
      const chunks = await engine.readChunks(page.slug);
      const expected = splitLossless(page.text);
      if (!stored || stored.slug !== page.slug || stored.title !== page.title || stored.type !== page.type
        || stored.compiled_truth !== page.text || stored.timeline !== '' || stored.frontmatter?.origin !== page.origin
        || !Array.isArray(chunks) || chunks.length !== expected.length) refuse('index-readback-mismatch');
      for (const [chunkIndex, chunk] of chunks.entries()) {
        if (chunk.chunk_index !== chunkIndex || chunk.chunk_text !== expected[chunkIndex]
          || chunk.model !== request.embedding.model || chunk.chunk_source !== 'compiled_truth') refuse('index-readback-mismatch');
        let digest: string;
        try { digest = sha(vectorBytes(chunk.embedding, request.embedding.dimensions)); }
        catch { refuse('index-readback-mismatch'); }
        if (digest !== pages[index].chunks[chunkIndex].vector_sha256) refuse('index-readback-mismatch');
      }
    }
    if (request.v === 2)
      await engine.assertEmbeddingInputPolicy!({ ...request.embedding_input_policy! }, request.embedding_input_policy_sha256!);
    result = { v: request.v, status: 'ok', operation: 'prepare_index', index_leaf: 'index',
      ...(request.v === 2 ? { embedding_input_policy: request.embedding_input_policy } : {}),
      bindings: { dataset_sha256: request.dataset_sha256, pages_sha256: request.pages_sha256,
        request_sha256: sha(canonicalJson(request)), policy_sha256: sha(canonicalJson(POLICY)),
        embedding_sha256: sha(canonicalJson(request.embedding)),
        ...(request.v === 2 ? { embedding_input_policy_sha256: request.embedding_input_policy_sha256 } : {}) },
      policy: { ...POLICY }, embedding: { ...request.embedding }, pages,
      ...(engine.setupDiagnostics ? { setup_diagnostics: engine.setupDiagnostics } : {}), non_claims: nonClaims };
    if (bytes(canonicalJson(result)) > MAX_RECEIPT_BYTES) refuse('receipt-byte-budget');
  } catch (error) {
    result = { v, status: 'refused', operation: 'prepare_index',
      reason: error instanceof Refusal ? error.reason : 'prepare-execution-failed',
      ...(error instanceof DiagnosticRefusal ? { setup_diagnostics: error.diagnostics }
        : engine?.setupDiagnostics ? { setup_diagnostics: engine.setupDiagnostics } : {}), non_claims: nonClaims };
  } finally {
    if (engine) {
      try { await engine.close(); }
      catch { result = { v, status: 'refused', operation: 'prepare_index', reason: 'engine-close-failed',
        ...(result?.setup_diagnostics ? { setup_diagnostics: result.setup_diagnostics } : {}), non_claims: nonClaims }; }
    }
  }
  return result;
}

async function productionDependencies(request: PrepareRequest): Promise<Dependencies> {
  const { PGLiteEngine } = await import('./core/pglite-engine.ts');
  const { configureGateway, embedOne } = await import('./core/ai/gateway.ts');
  const configure = (embedding: Embedding) => configureGateway({ embedding_model: embedding.model,
    embedding_dimensions: embedding.dimensions, base_urls: { [embedding.model.split(':', 1)[0]]: embedding.endpoint }, env: {} });
  return {
    embedDocument: async (text, embedding, signal) => embedOne(text, { embeddingModel: embedding.model,
      dimensions: embedding.dimensions, inputType: 'document', abortSignal: signal }),
    openNew: async (fd, embedding) => {
      const index = createPrivateIndexDirectory(fd);
      configure(embedding);
      const engine = new PGLiteEngine();
      let setupDiagnostics: SetupDiagnostics | undefined;
      try {
        await engine.connect({ engine: 'pglite', database_path: index });
        const setup = await captureSetupDiagnostics(() => engine.initSchema(), embedding.dimensions);
        setupDiagnostics = setup.diagnostics;
        await engine.setConfig('search_embedding_column', 'embedding');
        const config = await engine.getAllConfig();
        if (config.embedding_model !== embedding.model || config.embedding_dimensions !== String(embedding.dimensions))
          refuse('schema-embedding-mismatch');
        await engine.executeRaw(`INSERT INTO public.sources(id,name,config) VALUES($1,$2,$3::jsonb)`,
          ['sia', 'SIA frozen benchmark export', canonicalJson({ dataset_sha256: request.dataset_sha256 })]);
      } catch (error) {
        try { await engine.disconnect(); } catch {}
        if (setupDiagnostics && !(error instanceof DiagnosticRefusal))
          throw new DiagnosticRefusal(error instanceof Refusal ? error.reason : 'prepare-execution-failed', setupDiagnostics);
        throw error;
      }
      return {
        setupDiagnostics,
        writeEmbeddingInputPolicy: async (policy, digest) => {
          validateEmbeddingInputPolicy(policy, digest, embedding.model);
          await engine.setConfig('sia_embedding_input_policy', canonicalJson(policy));
          await engine.setConfig('sia_embedding_input_policy_sha256', digest);
        },
        assertEmbeddingInputPolicy: async (policy, digest) => {
          validateEmbeddingInputPolicy(policy, digest, embedding.model);
          // Only scalar booleans cross the bridge, never unbounded stored labels.
          const rows = await engine.executeRaw(`SELECT
            (SELECT count(*)=1 AND COALESCE(bool_and(value=$1),false) FROM public.config
              WHERE key='sia_embedding_input_policy') AS policy_matches,
            (SELECT count(*)=1 AND COALESCE(bool_and(value=$2),false) FROM public.config
              WHERE key='sia_embedding_input_policy_sha256') AS digest_matches`, [canonicalJson(policy), digest]);
          if (!Array.isArray(rows) || rows.length !== 1 || !record(rows[0])
            || Object.keys(rows[0]).sort().join('\0') !== ['digest_matches', 'policy_matches'].join('\0')
            || rows[0].policy_matches !== true || rows[0].digest_matches !== true) refuse('embedding-input-policy-mismatch');
        },
        writePage: async (page, chunks) => {
          await engine.putPage(page.slug, { title: page.title, type: page.type, compiled_truth: page.text, timeline: '',
            frontmatter: { origin: page.origin, dataset_sha256: request.dataset_sha256, source_text_sha256: page.text_sha256 },
            source_kind: 'sia-frozen-frontdoor-export', source_uri: page.slug }, { sourceId: 'sia' });
          await engine.upsertChunks(page.slug, chunks, { sourceId: 'sia', embeddingColumn: {
            name: 'embedding', type: 'vector', dimensions: embedding.dimensions, embeddingModel: embedding.model } });
        },
        listSlugs: async () => Array.from(await engine.getAllSlugs({ sourceId: 'sia' })),
        readPage: (slug) => engine.getPage(slug, { sourceId: 'sia' }),
        readChunks: (slug) => engine.getChunks(slug, { sourceId: 'sia', includeEmbedding: true }),
        close: () => engine.disconnect(),
      };
    },
  };
}

function readRequest(fd: number): PrepareRequest {
  if (!integer(fd, 3, 1048576)) refuse('request-descriptor-invalid');
  const before = fstatSync(fd, { bigint: true });
  if (!before.isFile() || before.uid !== BigInt(process.getuid!()) || before.nlink > 1n
    || (before.mode & 0o077n) !== 0n || before.size > BigInt(MAX_REQUEST_BYTES)) refuse('request-descriptor-invalid');
  const chunks: Buffer[] = [];
  let size = 0;
  while (true) {
    const buffer = Buffer.alloc(65536);
    const count = readSync(fd, buffer, 0, buffer.length, size);
    if (count === 0) break;
    size += count;
    if (size > MAX_REQUEST_BYTES) refuse('request-byte-budget');
    chunks.push(buffer.subarray(0, count));
  }
  const after = fstatSync(fd, { bigint: true });
  for (const key of ['dev', 'ino', 'size', 'mtimeNs', 'ctimeNs'] as const)
    if (before[key] !== after[key]) refuse('request-descriptor-changed');
  return parsePrepareRequest(Buffer.concat(chunks));
}

async function main(): Promise<void> {
  let result: any;
  let request: PrepareRequest | undefined;
  try {
    const argv = process.argv.slice(2);
    if (argv.length !== 2 || argv[0] !== '--request-fd' || !/^[1-9][0-9]*$/.test(argv[1])) refuse('entrypoint-arguments');
    request = readRequest(Number(argv[1]));
    const keep = new Set(['HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL']);
    for (const key of Object.keys(process.env)) if (!keep.has(key)) delete process.env[key];
    process.env.TZ = 'UTC';
    process.env.GBRAIN_PGLITE_WAL_REPAIR = 'off';
    console.log = (...args) => console.error(...args);
    console.info = (...args) => console.error(...args);
    result = await prepareIndex(request, await productionDependencies(request));
  } catch (error) {
    result = { v: request?.v ?? 1, status: 'refused', operation: 'prepare_index',
      reason: error instanceof Refusal ? error.reason : 'prepare-execution-failed',
      non_claims: [...NON_CLAIMS, ...(request?.v === 2 ? EMBEDDING_INPUT_NON_CLAIMS : [])] };
  }
  writeSync(1, canonicalJson(result) + '\n');
  process.exit(result.status === 'ok' ? 0 : 2);
}
if (import.meta.main) await main();
