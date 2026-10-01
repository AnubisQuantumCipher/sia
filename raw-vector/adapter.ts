/**
 * Query-only raw-vector adapter. The build stages this file at
 * src/sia-raw-vector.ts inside the admitted pinned gbrain source closure.
 *
 * Only main() imports gbrain. The core seam has no filesystem/network effects.
 * The parent owns executable admission, private snapshot creation, process
 * containment and serving-model attestation. This process binds what it reads
 * and returns; it cannot attest the embedding service's loaded weights.
 */
import { createHash } from 'node:crypto';
import { fstatSync, lstatSync, readSync, readlinkSync, writeSync } from 'node:fs';

export const MAX_REQUEST_BYTES = 262144;
// The pinned gateway truncates at 8000 UTF-16 code units. This conservative
// UTF-8 byte bound keeps every admitted query below that truncating branch.
export const MAX_QUERY_BYTES = 8000;
export const MAX_QUERIES = 64;
export const MAX_RESULTS = 100;
export const MAX_SNAPSHOT_ROWS = 50000;
export const MAX_SNAPSHOT_BYTES = 67108864;
export const MAX_RESULT_BYTES = 4194304;
export const MAX_CHUNK_BYTES = 65536;
const SNAPSHOT_BATCH_ROWS = 128;
const EMBEDDING_TIMEOUT_MS = 30000;
const HASH = /^[a-f0-9]{64}$/;
const TABLES = ['catalog', 'pages', 'content_chunks', 'sources', 'timeline_entries', 'config'] as const;
const EXCLUDES = ['test/', 'attachments/', '.raw/'];
const NON_CLAIMS = [
  'The embedding model identifier and endpoint are bound; served model weights are not attested by this adapter.',
  'Raw-vector search retains gbrain page pooling, visibility filters, and bounded approximate candidate retrieval.',
  'The parent admits the executable and build receipt; their supplied identities are not self-attestation.',
  'A private benchmark snapshot does not attest the resident index or the completeness of machine history.',
  'Pre/post logical identity checks rely on the private snapshot and exclusive engine owner; they are not a hostile same-user sandbox.',
  'Scores and vectors are observed floating-point engine output, not JACKAL-certified arithmetic or a cognitive win.',
  'Returned chunks retain their text; this adapter does not infer an origin label that the raw API did not return.',
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

type SnapshotIdentity = { logical_sha256: string; catalog_sha256: string };
type Embedding = { model: string; dimensions: number; endpoint: string };
type Request = {
  v: 1 | 2; operation: 'capture' | 'query'; lane: 'raw_vector';
  queries: { id: string; text: string }[]; limit: number;
  snapshot: { fd: number; logical_sha256: string | null; catalog_sha256: string | null };
  embedding: Embedding;
  binding: { executable_sha256: string; build_receipt_sha256: string };
  embedding_input_policy?: EmbeddingInputPolicy; embedding_input_policy_sha256?: string;
};
type Engine = {
  snapshot(): Promise<SnapshotIdentity>;
  searchVector(vector: Float32Array, options: Record<string, unknown>): Promise<unknown[]>;
  close(): Promise<void>;
};
export type Dependencies = {
  connect(fd: number): Promise<Engine>;
  embed(text: string, config: Embedding, signal: AbortSignal): Promise<Float32Array>;
  now(): number;
};

class Refusal extends Error {
  constructor(readonly reason: string) { super(reason); }
}
class DatabaseFailure extends Error {
  constructor(readonly component: string, readonly sqlstate: string | null) { super('database-operation-failed'); }
}
function sqlstate(error: unknown): string | null {
  try {
    const code = (error as { code?: unknown })?.code;
    // PostgreSQL SQLSTATE-form codes only. In particular, filesystem errno
    // names and arbitrary exception strings must not enter the protocol.
    return typeof code === 'string' && /^(?:[0-9][0-9A-Z]|F0|HV|P0|XX)[0-9A-Z]{3}$/.test(code) ? code : null;
  } catch { return null; }
}
export async function withDatabaseStage<T>(component: string, operation: () => Promise<T>): Promise<T> {
  const allowed = ['embedding-compatibility', ...TABLES.flatMap(table => [`${table}-budget`, `${table}-read`])];
  if (!allowed.includes(component)) refuse('database-stage-invalid');
  try { return await operation(); }
  catch (error) {
    if (error instanceof Refusal || error instanceof DatabaseFailure) throw error;
    throw new DatabaseFailure(component, sqlstate(error));
  }
}
function failureReason(stage: string, error: unknown): string {
  if (error instanceof Refusal) return error.reason;
  const component = error instanceof DatabaseFailure ? `-${error.component}` : '';
  const code = error instanceof DatabaseFailure ? error.sqlstate : sqlstate(error);
  return `adapter-${stage}${component}-failed${code ? '-sqlstate-' + code : ''}`;
}
function refuse(reason: string): never { throw new Refusal(reason); }
function sha(value: string | Uint8Array): string {
  return createHash('sha256').update(value).digest('hex');
}
function bytes(value: string): number { return Buffer.byteLength(value, 'utf8'); }
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
}
function keys(value: unknown, allowed: string[]): asserts value is Record<string, unknown> {
  if (!record(value) || Object.keys(value).sort().join('\0') !== [...allowed].sort().join('\0'))
    refuse('request-shape');
}
function integer(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
}
function text(value: unknown, max: number): value is string {
  return typeof value === 'string' && value.length > 0 && bytes(value) <= max
    && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value)
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

// JSON.parse normally accepts duplicate members. Scan the token structure first
// so two different readers cannot disagree about the admitted request.
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

function validateRequest(raw: unknown): Request {
  const v2 = record(raw) && raw.v === 2;
  keys(raw, ['v', 'operation', 'lane', 'queries', 'limit', 'snapshot', 'embedding', 'binding',
    ...(v2 ? ['embedding_input_policy', 'embedding_input_policy_sha256'] : [])]);
  if (raw.v !== 1 && raw.v !== 2 || raw.lane !== 'raw_vector' || !['capture', 'query'].includes(raw.operation as string))
    refuse('request-shape');
  if (v2) validateEmbeddingInputPolicy(raw.embedding_input_policy, raw.embedding_input_policy_sha256,
    record(raw.embedding) ? raw.embedding.model : undefined);
  if (!integer(raw.limit, 1, MAX_RESULTS) || !Array.isArray(raw.queries) || raw.queries.length > MAX_QUERIES)
    refuse('request-shape');
  if (raw.operation === 'capture' ? raw.queries.length !== 0 : raw.queries.length === 0) refuse('request-shape');
  const ids = new Set<string>();
  for (const query of raw.queries) {
    keys(query, ['id', 'text']);
    if (!text(query.id, 128) || !/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(query.id) || ids.has(query.id))
      refuse('request-shape');
    if (typeof query.text === 'string' && bytes(query.text) > MAX_QUERY_BYTES) refuse('query-byte-budget');
    if (!text(query.text, MAX_QUERY_BYTES) || !query.text.trim()) refuse('request-shape');
    if (v2 && bytes((raw.embedding_input_policy as EmbeddingInputPolicy).query_prefix) + bytes(query.text) > MAX_QUERY_BYTES)
      refuse('embedding-input-byte-budget');
    ids.add(query.id);
  }
  keys(raw.snapshot, ['fd', 'logical_sha256', 'catalog_sha256']);
  if (!integer(raw.snapshot.fd, 3, 1048576)) refuse('request-shape');
  for (const field of ['logical_sha256', 'catalog_sha256']) {
    if (raw.operation === 'capture') {
      if (raw.snapshot[field] !== null) refuse('request-shape');
    } else if (typeof raw.snapshot[field] !== 'string' || !HASH.test(raw.snapshot[field] as string)) refuse('request-shape');
  }
  keys(raw.embedding, ['model', 'dimensions', 'endpoint']);
  if (!text(raw.embedding.model, 256) || !/^(?:llama-server|ollama):[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(raw.embedding.model)
    || !integer(raw.embedding.dimensions, 1, 16000) || typeof raw.embedding.endpoint !== 'string') refuse('request-shape');
  try {
    const endpoint = new URL(raw.embedding.endpoint);
    if (endpoint.protocol !== 'http:' || !['127.0.0.1', '[::1]'].includes(endpoint.hostname)
      || !endpoint.port || endpoint.pathname !== '/v1' || endpoint.search || endpoint.hash
      || endpoint.username || endpoint.password || endpoint.href !== raw.embedding.endpoint) refuse('request-shape');
  } catch { refuse('request-shape'); }
  keys(raw.binding, ['executable_sha256', 'build_receipt_sha256']);
  if (Object.values(raw.binding).some(x => typeof x !== 'string' || !HASH.test(x))) refuse('request-shape');
  const encoded = canonicalJson(raw);
  if (bytes(encoded) > MAX_REQUEST_BYTES) refuse('request-byte-budget');
  // Detach all mutable request values from callers before any await.
  return JSON.parse(encoded) as Request;
}

export function parseRequest(input: Uint8Array): Request {
  if (input.byteLength > MAX_REQUEST_BYTES) refuse('request-byte-budget');
  let source: string;
  try { source = new TextDecoder('utf-8', { fatal: true }).decode(input); }
  catch { return refuse('request-utf8'); }
  return validateRequest(uniqueJson(source));
}

export function readRequestFd(fd: number): Request {
  if (!integer(fd, 3, 1048576)) refuse('request-descriptor-invalid');
  const before = fstatSync(fd, { bigint: true });
  if (!before.isFile() || before.uid !== BigInt(process.getuid!()) || before.nlink > 1n
    || (before.mode & 0o077n) !== 0n || before.size > BigInt(MAX_REQUEST_BYTES)) refuse('request-descriptor-invalid');
  const chunks: Buffer[] = [];
  let size = 0;
  while (true) {
    const buffer = Buffer.alloc(8192);
    const count = readSync(fd, buffer, 0, buffer.length, size);
    if (count === 0) break;
    size += count;
    if (size > MAX_REQUEST_BYTES) refuse('request-byte-budget');
    chunks.push(buffer.subarray(0, count));
  }
  const after = fstatSync(fd, { bigint: true });
  for (const key of ['dev', 'ino', 'size', 'mtimeNs', 'ctimeNs'] as const)
    if (before[key] !== after[key]) refuse('request-descriptor-changed');
  return parseRequest(Buffer.concat(chunks));
}

export function snapshotIndexPath(fd: number): string {
  if (!integer(fd, 3, 1048576)) refuse('snapshot-parent-invalid');
  const parent = fstatSync(fd);
  if (!parent.isDirectory() || parent.uid !== process.getuid!() || (parent.mode & 0o7777) !== 0o700)
    refuse('snapshot-parent-invalid');
  const path = `/proc/self/fd/${fd}`;
  const target = readlinkSync(path);
  const resident = '/home/sicarii/.local/share/sia/.gbrain';
  if (target === resident || target.startsWith(resident + '/')) refuse('resident-index-forbidden');
  const index = `${path}/index`;
  let child;
  try { child = lstatSync(index); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') refuse('snapshot-index-missing');
    throw error;
  }
  if (!child.isDirectory() || child.uid !== process.getuid!() || (child.mode & 0o7777) !== 0o700)
    refuse('snapshot-index-invalid');
  return index;
}

export async function digestSnapshot(
  read: (table: string, offset: number, limit: number) => Promise<unknown[]>,
): Promise<SnapshotIdentity> {
  const logical = createHash('sha256');
  const catalog = createHash('sha256');
  let count = 0;
  let size = 0;
  for (const table of TABLES) {
    for (let offset = 0; ; offset += SNAPSHOT_BATCH_ROWS) {
      const batch = await read(table, offset, SNAPSHOT_BATCH_ROWS);
      if (!Array.isArray(batch) || batch.length > SNAPSHOT_BATCH_ROWS) refuse('snapshot-reader-invalid');
      for (const row of batch) {
        count += 1;
        if (count > MAX_SNAPSHOT_ROWS) refuse('snapshot-row-budget');
        const encoded = canonicalJson([table, row]) + '\n';
        size += bytes(encoded);
        if (size > MAX_SNAPSHOT_BYTES) refuse('snapshot-byte-budget');
        logical.update(encoded);
        if (table === 'catalog') catalog.update(encoded);
      }
      if (batch.length < SNAPSHOT_BATCH_ROWS) break;
    }
  }
  return { logical_sha256: logical.digest('hex'), catalog_sha256: catalog.digest('hex') };
}

function searchOptions(request: Request): Record<string, unknown> {
  return { limit: request.limit, offset: 0, sourceId: 'sia', detail: 'high',
    exclude_slug_prefixes: [...EXCLUDES], include_slug_prefixes: [], excludePrivate: false,
    embeddingColumn: { name: 'embedding', type: 'vector', dimensions: request.embedding.dimensions,
      embeddingModel: request.embedding.model } };
}
function normalizedRows(raw: unknown, limit: number): Record<string, unknown>[] {
  if (!Array.isArray(raw) || raw.length > limit) refuse('ranked-rows-invalid');
  const seen = new Set<string>();
  let previous: { score: number; page_id: number; chunk_id: number } | undefined;
  return raw.map(row => {
    if (!record(row) || !text(row.slug, 1024) || row.source_id !== 'sia'
      || !integer(row.page_id, 1, Number.MAX_SAFE_INTEGER) || !integer(row.chunk_id, 1, Number.MAX_SAFE_INTEGER)
      || !integer(row.chunk_index, 0, Number.MAX_SAFE_INTEGER) || typeof row.score !== 'number'
      || !Number.isFinite(row.score) || typeof row.stale !== 'boolean'
      || !['compiled_truth', 'timeline'].includes(row.chunk_source as string)
      || !text(row.title, 4096) || !text(row.type, 128) || typeof row.chunk_text !== 'string'
      || bytes(row.chunk_text) > MAX_CHUNK_BYTES || seen.has(row.slug)
      || EXCLUDES.some(prefix => (row.slug as string).startsWith(prefix))) refuse('ranked-rows-invalid');
    if (previous && (row.score > previous.score || (row.score === previous.score
      && (row.page_id < previous.page_id || (row.page_id === previous.page_id && row.chunk_id < previous.chunk_id)))))
      refuse('ranked-rows-invalid');
    seen.add(row.slug);
    previous = { score: row.score, page_id: row.page_id, chunk_id: row.chunk_id };
    const score = Buffer.alloc(8); score.writeDoubleLE(row.score);
    return { slug: row.slug, source_id: row.source_id, page_id: row.page_id, title: row.title, type: row.type,
      chunk_id: row.chunk_id, chunk_index: row.chunk_index, chunk_source: row.chunk_source,
      chunk_text: row.chunk_text, score: row.score, score_f64le_base64: score.toString('base64'), stale: row.stale };
  });
}
function identity(value: SnapshotIdentity): SnapshotIdentity {
  if (!record(value) || !HASH.test(value.logical_sha256) || !HASH.test(value.catalog_sha256)) refuse('snapshot-identity-invalid');
  return { logical_sha256: value.logical_sha256, catalog_sha256: value.catalog_sha256 };
}
function elapsed(start: number, end: number): number {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) refuse('clock-invalid');
  return end - start;
}

export function validateSnapshotEmbedding(metadata: unknown, withInputPolicy = false): void {
  const fields = ['config_model_matches', 'config_dimensions_match', 'search_column_matches',
    'physical_column_matches', 'chunk_models_match', 'embedded_text_matches',
    ...(withInputPolicy ? ['embedding_input_policy_matches', 'embedding_input_policy_sha256_matches'] : [])];
  if (!record(metadata) || Object.keys(metadata).sort().join('\0') !== fields.sort().join('\0')
    || fields.some(field => metadata[field] !== true)) refuse('snapshot-embedding-mismatch');
}

export async function inspectSnapshotEmbedding(
  execute: (sql: string, parameters: unknown[]) => Promise<unknown[]>, expected: Embedding,
  inputPolicy?: EmbeddingInputPolicy, inputPolicySha256?: string,
): Promise<void> {
  const withInputPolicy = inputPolicy !== undefined || inputPolicySha256 !== undefined;
  if (withInputPolicy) validateEmbeddingInputPolicy(inputPolicy, inputPolicySha256, expected.model);
  // No persisted model label, config value or chunk text crosses the result
  // boundary here. A malformed private snapshot can only return fixed booleans.
  const rows = await execute(`SELECT
    (SELECT count(*)=1 AND COALESCE(bool_and(value=$1),false) FROM public.config
      WHERE key='embedding_model') AS config_model_matches,
    (SELECT count(*)=1 AND COALESCE(bool_and(value=$2),false) FROM public.config
      WHERE key='embedding_dimensions') AS config_dimensions_match,
    (SELECT count(*)<=1 AND COALESCE(bool_and(value='embedding'),true) FROM public.config
      WHERE key='search_embedding_column') AS search_column_matches,
    (SELECT count(*)=1 AND COALESCE(bool_and(format_type(a.atttypid,a.atttypmod)=$3),false)
      FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname='content_chunks' AND c.relkind='r'
      AND a.attname='embedding' AND NOT a.attisdropped) AS physical_column_matches,
    NOT EXISTS (SELECT 1 FROM public.content_chunks cc JOIN public.pages p ON p.id=cc.page_id
      WHERE p.source_id='sia' AND cc.modality='text' AND cc.embedding IS NOT NULL
      AND cc.model IS DISTINCT FROM $1) AS chunk_models_match,
    NOT EXISTS (SELECT 1 FROM public.content_chunks cc JOIN public.pages p ON p.id=cc.page_id
      WHERE p.source_id='sia' AND cc.modality='text' AND cc.embedding IS NOT NULL
      AND (cc.embedded_text_hash IS NULL OR cc.embedded_text_hash <> md5(cc.chunk_text))) AS embedded_text_matches${withInputPolicy ? `,
    (SELECT count(*)=1 AND COALESCE(bool_and(value=$4),false) FROM public.config
      WHERE key='sia_embedding_input_policy') AS embedding_input_policy_matches,
    (SELECT count(*)=1 AND COALESCE(bool_and(value=$5),false) FROM public.config
      WHERE key='sia_embedding_input_policy_sha256') AS embedding_input_policy_sha256_matches` : ''}`,
  [expected.model, String(expected.dimensions), `vector(${expected.dimensions})`,
    ...(withInputPolicy ? [canonicalJson(inputPolicy), inputPolicySha256] : [])]);
  if (!Array.isArray(rows) || rows.length !== 1) refuse('snapshot-embedding-mismatch');
  validateSnapshotEmbedding(rows[0], withInputPolicy);
}

export async function runRawVector(raw: unknown, dependencies: Dependencies): Promise<any> {
  let engine: Engine | undefined;
  let result: any;
  let stage = 'admission';
  const v = record(raw) && raw.v === 2 ? 2 : 1;
  const nonClaims = [...NON_CLAIMS, ...(v === 2 ? EMBEDDING_INPUT_NON_CLAIMS : [])];
  const refusalHeader = { v, status: 'refused', lane: 'raw_vector',
    ...(v === 2 && record(raw) && ['capture', 'query'].includes(raw.operation as string) ? { operation: raw.operation } : {}) };
  try {
    const request = validateRequest(raw);
    const started = dependencies.now();
    stage = 'connect';
    engine = await dependencies.connect(request.snapshot.fd);
    stage = 'snapshot-before';
    const before = identity(await engine.snapshot());
    if (request.operation === 'query' && (before.logical_sha256 !== request.snapshot.logical_sha256
      || before.catalog_sha256 !== request.snapshot.catalog_sha256)) refuse('snapshot-identity-mismatch');
    const results: Record<string, unknown>[] = [];
    let resultBytes = 0;
    for (const query of request.queries) {
      stage = 'embed';
      const embedStarted = dependencies.now();
      const embeddingInput = (request.embedding_input_policy?.query_prefix ?? '') + query.text;
      const vector = await dependencies.embed(embeddingInput, { ...request.embedding }, AbortSignal.timeout(EMBEDDING_TIMEOUT_MS));
      if (!(vector instanceof Float32Array) || vector.length !== request.embedding.dimensions
        || !vector.every(Number.isFinite) || !vector.some(x => x !== 0)) refuse('embedding-vector-invalid');
      const vectorBytes = Buffer.alloc(vector.byteLength);
      vector.forEach((value, index) => vectorBytes.writeFloatLE(value, index * 4));
      stage = 'search';
      const searchStarted = dependencies.now();
      const rows = normalizedRows(await engine.searchVector(vector, searchOptions(request)), request.limit);
      const rowBytes = Buffer.from(canonicalJson(rows), 'utf8');
      const queryResult = { id: query.id, query_sha256: sha(query.text),
        ...(request.v === 2 ? { embedding_input_sha256: sha(embeddingInput), embedding_input_bytes: bytes(embeddingInput) } : {}),
        vector_f32le_base64: vectorBytes.toString('base64'), vector_sha256: sha(vectorBytes),
        rows, ranked_rows_canonical_base64: rowBytes.toString('base64'), ranked_rows_sha256: sha(rowBytes),
        latency_ms: { embedding: elapsed(embedStarted, searchStarted), search: elapsed(searchStarted, dependencies.now()) } };
      resultBytes += bytes(canonicalJson(queryResult));
      if (resultBytes > MAX_RESULT_BYTES) refuse('result-byte-budget');
      results.push(queryResult);
    }
    stage = 'snapshot-after';
    const after = identity(await engine.snapshot());
    if (canonicalJson(before) !== canonicalJson(after)) refuse('snapshot-changed-during-query');
    stage = 'receipt';
    const config = { engine: 'pglite', embedding: request.embedding, search: searchOptions(request),
      env: { GBRAIN_SEARCH_EXCLUDE: '', GBRAIN_SOURCE_BOOST: '', GBRAIN_PGLITE_WAL_REPAIR: 'off', TZ: 'UTC' },
      ...(request.v === 2 ? { embedding_input_policy: request.embedding_input_policy,
        embedding_input_policy_sha256: request.embedding_input_policy_sha256 } : {}) };
    result = { v: request.v, status: 'ok', operation: request.operation, lane: 'raw_vector',
      ...(request.v === 2 ? { embedding_input_policy: request.embedding_input_policy } : {}),
      bindings: { ...before, ...request.binding, config_sha256: sha(canonicalJson(config)),
        request_sha256: sha(canonicalJson(request)),
        ...(request.v === 2 ? { embedding_input_policy_sha256: request.embedding_input_policy_sha256 } : {}) },
      results, latency_ms: { total: elapsed(started, dependencies.now()) }, non_claims: nonClaims };
  } catch (error) {
    result = { ...refusalHeader, reason: failureReason(stage, error), non_claims: nonClaims };
  } finally {
    if (engine) {
      try { await engine.close(); }
      catch (error) { result = { ...refusalHeader, reason: failureReason('close', error), non_claims: nonClaims }; }
    }
  }
  return result;
}

// Catalog rows include definitions affecting the SQL's interpretation and index
// selection. Every data column in each search-relevant table is also digested.
// PostgreSQL JSON text preserves its numeric spelling before JS sees it.
const CATALOG_SQL = `
  SELECT kind, identity, definition FROM (
    SELECT 'relation' AS kind, n.nspname || '.' || c.relname AS identity,
      jsonb_build_array(c.relkind, c.relpersistence, c.reloptions, c.relrowsecurity, c.relforcerowsecurity)::text AS definition
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public'
    UNION ALL
    SELECT 'column', c.relname || '.' || a.attname,
      jsonb_build_array(a.attnum, format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,
        pg_get_expr(d.adbin,d.adrelid))::text
      FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
      WHERE n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped
    UNION ALL
    SELECT 'index', c.relname, pg_get_indexdef(c.oid) FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='i'
    UNION ALL
    SELECT 'constraint', c.conrelid::regclass::text || '.' || c.conname, pg_get_constraintdef(c.oid)
      FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public'
    UNION ALL
    SELECT 'function', p.oid::regprocedure::text, pg_get_functiondef(p.oid)
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind IN ('f','p','w')
    UNION ALL
    SELECT 'extension', extname, extversion FROM pg_extension
    UNION ALL
    SELECT 'setting', name, setting FROM pg_settings WHERE name IN
      ('server_version','server_encoding','TimeZone','lc_collate','lc_ctype','default_text_search_config')
  ) catalog ORDER BY kind COLLATE "C", identity COLLATE "C", definition COLLATE "C"`;

async function productionDependencies(request: Request): Promise<Dependencies> {
  // Literal imports resolve inside the private pinned build closure, never from
  // the resident installation or an ambient package resolver at execution time.
  const { PGLiteEngine } = await import('./core/pglite-engine.ts');
  const { configureGateway, embedQuery } = await import('./core/ai/gateway.ts');
  return {
    now: () => performance.now(),
    embed: async (text, config, signal) => {
      const provider = config.model.split(':', 1)[0];
      configureGateway({ embedding_model: config.model, embedding_dimensions: config.dimensions,
        base_urls: { [provider]: config.endpoint }, env: {} });
      return embedQuery(text, { embeddingModel: config.model, dimensions: config.dimensions, abortSignal: signal });
    },
    connect: async (fd) => {
      // PGlite's NodeFS rejects a bare proc-fd symlink as its data directory.
      // A fixed ordinary child keeps descriptor authority without reopening a
      // resolved path. The parent retains and rechecks both directory identities.
      const path = snapshotIndexPath(fd);
      const engine = new PGLiteEngine();
      try { await engine.connect({ engine: 'pglite', database_path: path }); }
      catch (error) { try { await engine.disconnect(); } catch {} throw error; }
      const read = async (table: string, offset: number, limit: number): Promise<unknown[]> => {
        if (!TABLES.includes(table as typeof TABLES[number])) refuse('snapshot-reader-invalid');
        const query = table === 'catalog' ? CATALOG_SQL
          : `SELECT to_jsonb(t)::text AS payload FROM public.${table} t ORDER BY ${table === 'config' ? 'key' : 'id'}`;
        // Read only lengths first; a single stored giant chunk must refuse before
        // the PGlite/JS bridge materializes its complete payload in the caller.
        const lengths = await withDatabaseStage(`${table}-budget`, () => engine.executeRaw(
          `SELECT octet_length(to_jsonb(bounded)::text) AS bytes
          FROM (${query} LIMIT $1 OFFSET $2) bounded`, [limit, offset]));
        let byteCount = 0;
        for (const item of lengths) {
          const n = Number(item.bytes);
          if (!Number.isSafeInteger(n) || n < 0) refuse('snapshot-reader-invalid');
          byteCount += n;
          if (byteCount > MAX_SNAPSHOT_BYTES) refuse('snapshot-byte-budget');
        }
        const rows = await withDatabaseStage(`${table}-read`, () => engine.executeRaw(`${query} LIMIT $1 OFFSET $2`, [limit, offset]));
        return table === 'catalog' ? rows : rows.map((row: { payload: string }) => row.payload);
      };
      const snapshot = async (): Promise<SnapshotIdentity> => {
        await withDatabaseStage('embedding-compatibility', () =>
          inspectSnapshotEmbedding((sql, parameters) => engine.executeRaw(sql, parameters), request.embedding,
            request.embedding_input_policy, request.embedding_input_policy_sha256));
        return digestSnapshot(read);
      };
      return { snapshot,
        searchVector: (vector, options) => engine.searchVector(vector, options),
        close: () => engine.disconnect() };
    },
  };
}

async function main(): Promise<void> {
  let result: any;
  let request: Request | undefined;
  let stage = 'entrypoint';
  try {
    const argv = process.argv.slice(2);
    if (argv.length !== 2 || argv[0] !== '--request-fd' || !/^[1-9][0-9]*$/.test(argv[1])) refuse('entrypoint-arguments');
    request = readRequestFd(Number(argv[1]));
    // The parent has already chosen a private launch context. Remove policy and
    // credential variables before imported code can consult ambient settings.
    const keep = new Set(['HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL']);
    for (const key of Object.keys(process.env)) if (!keep.has(key)) delete process.env[key];
    process.env.TZ = 'UTC';
    process.env.GBRAIN_SEARCH_EXCLUDE = '';
    process.env.GBRAIN_SOURCE_BOOST = '';
    process.env.GBRAIN_PGLITE_WAL_REPAIR = 'off';
    console.log = (...args) => console.error(...args);
    console.info = (...args) => console.error(...args);
    stage = 'runtime-import';
    result = await runRawVector(request, await productionDependencies(request));
  } catch (error) {
    result = { v: request?.v ?? 1, status: 'refused', lane: 'raw_vector',
      ...(request?.v === 2 ? { operation: request.operation } : {}),
      reason: failureReason(stage, error), non_claims: [...NON_CLAIMS, ...(request?.v === 2 ? EMBEDDING_INPUT_NON_CLAIMS : [])] };
  }
  writeSync(1, canonicalJson(result) + '\n');
  // PGlite writes ambient process.exitCode asynchronously; use our own verdict.
  process.exit(result.status === 'ok' ? 0 : 2);
}

if (import.meta.main) await main();
