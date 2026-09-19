// SIA Model — pure logic for the Omarchy Brain panel.
// “Brain” is a product metaphor for auditable local machine memory; it is not a
// biological brain and does not establish cognition or neuroscience.
// Pixels only: everything shown is read from the brainstem service snapshots
// (~/.local/state/sia/*.json); authoritative state lives in gbrain + the
// signed corpus. Nothing here is evidence.
//
// Layout philosophy (after the Hermes Star Map): time is radial — the
// root-memory node sits at the center, source nodes hold stable semantic sectors
// on the inner ring, and records appear in those sectors at a radius set by
// age. Faint day rings mark the time bands. The force simulation gives the
// branches room to separate without allowing the whole graph to collapse into
// one edge of the canvas.
.pragma library

function releaseVersion() { return "1.8.0" }

// The checkout and the resident runtime advance as one release generation.
// Only an exact release match may expose the cockpit.  Comparison stays on
// decimal strings so a malformed or unusually large component fails closed
// instead of being rounded through JavaScript's Number representation.
function releaseVersionParts(value) {
  if (typeof value !== "string") return null
  var match = value.match(
    /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/)
  return match ? [match[1], match[2], match[3]] : null
}

function compareReleaseVersions(left, right) {
  var a = releaseVersionParts(left)
  var b = releaseVersionParts(right)
  if (!a || !b) return null
  for (var i = 0; i < a.length; i++) {
    if (a[i].length < b[i].length) return -1
    if (a[i].length > b[i].length) return 1
    if (a[i] < b[i]) return -1
    if (a[i] > b[i]) return 1
  }
  return 0
}

function nonNegativeInteger(value) {
  return typeof value === "number" && isFinite(value)
    && Math.floor(value) === value && value >= 0
    && value <= 9007199254740991
}

function validUtcSecondTimestamp(value) {
  if (typeof value !== "string"
      || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value)
      || value.slice(0, 4) === "0000")
    return false
  var parsed = Date.parse(value)
  return isFinite(parsed)
    && new Date(parsed).toISOString().replace(".000Z", "Z") === value
}

function timestampObservedBy(value, nowMs) {
  var now = Number(nowMs)
  return validUtcSecondTimestamp(value) && isFinite(now)
    && Date.parse(value) <= now
}

// This is the exact set emitted by sialib's status publisher. Surfaces map the
// compatibility state ``thinking`` to the behavior label ``processing`` but
// must not admit presentation labels as producer state.
var STATUS_STATES = ["failed", "degraded", "thinking", "ok"]

function validCalendarDate(value) {
  if (typeof value !== "string"
      || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || Number(value.slice(0, 4)) < 1) return false
  var parsed = Date.parse(value + "T00:00:00Z")
  return isFinite(parsed)
    && new Date(parsed).toISOString().slice(0, 10) === value
}

function integerNumber(value) {
  return typeof value === "number" && isFinite(value)
    && Math.floor(value) === value
    && Math.abs(value) <= 9007199254740991
}

function recordHasExactly(value, fields) {
  if (!isPlainRecord(value)) return false
  var actual = Object.keys(value).sort()
  var expected = fields.slice().sort()
  return actual.length === expected.length
    && actual.join("\n") === expected.join("\n")
}

function strictStringLength(value) {
  if (typeof value !== "string") return -1
  var length = 0
  for (var i = 0; i < value.length; i++) {
    var unit = value.charCodeAt(i)
    if (unit >= 0xD800 && unit <= 0xDBFF) {
      if (i + 1 >= value.length) return -1
      var low = value.charCodeAt(i + 1)
      if (low < 0xDC00 || low > 0xDFFF) return -1
      i += 1
    } else if (unit >= 0xDC00 && unit <= 0xDFFF) return -1
    length += 1
  }
  return length
}

function boundedNonEmptyString(value, limit) {
  var length = strictStringLength(value)
  return length > 0 && length <= limit && value.trim() !== ""
}

function boundedString(value, limit) {
  var length = strictStringLength(value)
  return length >= 0 && length <= limit
}

function codePointIsControlOrFormat(code) {
  // Exact Cc/Cf ranges in the producer runtime's Unicode data. Unpaired
  // surrogate units are already refused by strictStringLength.
  return code <= 0x1f || (code >= 0x7f && code <= 0x9f)
    || code === 0xad || (code >= 0x600 && code <= 0x605)
    || code === 0x61c || code === 0x6dd || code === 0x70f
    || (code >= 0x890 && code <= 0x891) || code === 0x8e2
    || code === 0x180e || (code >= 0x200b && code <= 0x200f)
    || (code >= 0x202a && code <= 0x202e)
    || (code >= 0x2060 && code <= 0x2064)
    || (code >= 0x2066 && code <= 0x206f)
    || code === 0xfeff || (code >= 0xfff9 && code <= 0xfffb)
    || code === 0x110bd || code === 0x110cd
    || (code >= 0x13430 && code <= 0x1343f)
    || (code >= 0x1bca0 && code <= 0x1bca3)
    || (code >= 0x1d173 && code <= 0x1d17a)
    || code === 0xe0001 || (code >= 0xe0020 && code <= 0xe007f)
}

function canonicalCorpusSlug(value) {
  if (!boundedNonEmptyString(value, 2000)) return false
  var parts = value.split("/")
  for (var i = 0; i < parts.length; i++)
    if (!/^[a-z0-9_][a-z0-9._-]*$/.test(parts[i])
        || parts[i].length > (i === parts.length - 1 ? 252 : 255))
      return false
  return true
}

function inertStatusString(value, limit, nonempty) {
  if (!boundedString(value, limit)
      || (nonempty === true && value.trim() === "")
      || value.replace(/\s+/g, " ").trim() !== value
      || /[<>\[\]|`*]/.test(value)) return false
  for (var i = 0; i < value.length; i++) {
    var code = value.codePointAt(i)
    if (codePointIsControlOrFormat(code)) return false
    if (code > 0xffff) i += 1
  }
  return true
}

function redactionFreeStatusString(value, limit, nonempty) {
  if (!inertStatusString(value, limit, nonempty)) return false
  var patterns = [
    /-----BEGIN[ A-Z]*-----[\s\S]*?(?:-----END[ A-Z]*-----|$)/,
    /\beyJ[A-Za-z0-9_-]{14,}\.?[A-Za-z0-9._-]*/,
    /\bgh[pousr]_[A-Za-z0-9]{20,}/,
    /\bsk-[A-Za-z0-9_-]{16,}/,
    /\bxox[baprs]-[A-Za-z0-9-]{10,}/,
    /\bAKIA[0-9A-Z]{16}\b/,
    /Bearer\s+[A-Za-z0-9._~+\/-]{15,}=*/i,
    /\b(?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*\S+/i,
    /~?\/[^\s]*\.ssh\/[^\s]*/,
    /\b[A-Za-z0-9+/]{40,}={1,2}(?=\s|$)/
  ]
  for (var i = 0; i < patterns.length; i++)
    if (patterns[i].test(value)) return false
  return true
}

function publicationId(value, allowEmpty) {
  return typeof value === "string"
    && ((allowEmpty === true && value === "")
        || /^[0-9a-f]{32}$/.test(value))
}

function canonicalOrganName(value) {
  if (typeof value !== "string") return false
  var canonical = value.toLowerCase().trim()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[.-]+|[.-]+$/g, "")
  return value === (canonical === "" ? "unknown" : canonical)
}

function statusIntegerJsonPath(path) {
  if (!Array.isArray(path)) return false
  if (path.length === 1)
    return ["v", "pulse_seq", "events_pulse", "events_today", "pages",
            "graph_nodes", "graph_edges"].indexOf(path[0]) !== -1
  if (path.length === 2) {
    if (["mind", "agent_queue", "redactions"].indexOf(path[0]) !== -1)
      return true
    if (path[0] === "takes"
        && ["open", "due", "resolved", "unresolvable",
            "invalid_resolved", "invalid_records"].indexOf(path[1]) !== -1)
      return true
    if (path[0] === "ledger" && path[1] === "seq") return true
    if (path[0] === "ledger_transition"
        && ["recovered", "pending_errors"].indexOf(path[1]) !== -1)
      return true
  }
  return path.length === 3
    && ((path[0] === "organs" && path[2] === "today")
        || (path[0] === "history" && path[2] === 1)
        || (path[0] === "intents" && path[2] === "days_left"))
}

function graphIntegerJsonPath(path) {
  if (path.length === 1)
    return ["v", "pages_total"].indexOf(path[0]) !== -1
  if (path.length === 2 && path[0] === "snapshot")
    return ["truncated", "omitted_nodes", "omitted_edges", "aged_out",
            "window_days"].indexOf(path[1]) !== -1
  return path.length === 3
    && ((path[0] === "nodes"
         && ["deg", "din", "dout"].indexOf(path[2]) !== -1)
        || (path[0] === "snapshot" && path[1] === "counts_by_kind"))
}

// JSON.parse is last-key-wins for duplicate object members and erases the
// lexical distinction between JSON integers and integer-valued floats.
// Runtime readers preserve both distinctions, so the UI walks the grammar
// before asking the native parser for values. Each producer profile applies
// its integer-only schema at known paths while leaving legal status benchmark
// metrics floating-point.
function strictJsonParse(text, numberProfile) {
  if (typeof text !== "string") throw new Error("JSON text is not a string")
  if (numberProfile !== undefined && numberProfile !== "status"
      && numberProfile !== "continuity"
      && numberProfile !== "continuity-acceptance"
      && numberProfile !== "graph"
      && numberProfile !== "install-completion"
      && numberProfile !== "setup-marker"
      && numberProfile !== "thought-stream")
    throw new Error("unknown JSON number profile")
  var at = 0

  function fail() { throw new Error("ambiguous or malformed JSON") }
  function whitespace() {
    while (at < text.length && /[\x20\t\r\n]/.test(text.charAt(at))) at++
  }
  function stringToken() {
    if (text.charAt(at) !== '"') fail()
    var start = at++
    while (at < text.length) {
      var character = text.charAt(at)
      var unit = text.charCodeAt(at)
      if (character === '"') {
        at++
        return JSON.parse(text.slice(start, at))
      }
      if (unit < 0x20) fail()
      if (character === "\\") {
        at++
        if (at >= text.length) fail()
        character = text.charAt(at)
        if (character === "u") {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(at + 1, at + 5))) fail()
          at += 5
          continue
        }
        if ('"\\/bfnrt'.indexOf(character) === -1) fail()
      }
      at++
    }
    fail()
  }
  function value(path) {
    whitespace()
    var character = text.charAt(at)
    if (character === "{") {
      at++
      whitespace()
      var seen = {}
      if (text.charAt(at) === "}") { at++; return }
      while (true) {
        whitespace()
        var decodedKey = stringToken()
        var key = "$" + decodedKey
        if (Object.prototype.hasOwnProperty.call(seen, key)) fail()
        seen[key] = true
        whitespace()
        if (text.charAt(at++) !== ":") fail()
        value(path.concat([decodedKey]))
        whitespace()
        character = text.charAt(at++)
        if (character === "}") return
        if (character !== ",") fail()
      }
    }
    if (character === "[") {
      at++
      whitespace()
      if (text.charAt(at) === "]") { at++; return }
      var arrayIndex = 0
      while (true) {
        value(path.concat([arrayIndex]))
        arrayIndex++
        whitespace()
        character = text.charAt(at++)
        if (character === "]") return
        if (character !== ",") fail()
      }
    }
    if (character === '"') { stringToken(); return }
    var tail = text.slice(at)
    var number = tail.match(
      /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/)
    if (number) {
      if (!isFinite(Number(number[0]))) fail()
      var integerRequired = false
      if (numberProfile === "status")
        integerRequired = statusIntegerJsonPath(path)
      else if (numberProfile === "continuity")
        integerRequired = path.length === 1 && path[0] === "schema_version"
      else if (numberProfile === "continuity-acceptance")
        integerRequired = path.length === 1 && path[0] === "schema_version"
      else if (numberProfile === "graph")
        integerRequired = graphIntegerJsonPath(path)
      else if (numberProfile === "install-completion")
        integerRequired = path.length === 1 && path[0] === "v"
      else if (numberProfile === "setup-marker")
        integerRequired = path.length === 1
          && ["pid", "ts", "v"].indexOf(path[0]) !== -1
      else if (numberProfile === "thought-stream")
        integerRequired = path.length === 1 && path[0] === "v"
      if (integerRequired
          && !/^-?(?:0|[1-9][0-9]*)$/.test(number[0])) fail()
      at += number[0].length
      return
    }
    for (var i = 0; i < 3; i++) {
      var literal = ["true", "false", "null"][i]
      if (tail.slice(0, literal.length) === literal) {
        at += literal.length
        return
      }
    }
    fail()
  }

  value([])
  whitespace()
  if (at !== text.length) fail()
  return JSON.parse(text)
}

function strictStatusJsonParse(text) {
  return strictJsonParse(text, "status")
}

function strictContinuityJsonParse(text) {
  return strictJsonParse(text, "continuity")
}

function strictContinuityAcceptanceJsonParse(text) {
  return strictJsonParse(text, "continuity-acceptance")
}

function strictGraphJsonParse(text) {
  return strictJsonParse(text, "graph")
}

function strictInstallCompletionJsonParse(text) {
  return strictJsonParse(text, "install-completion")
}

function strictSetupMarkerJsonParse(text) {
  return strictJsonParse(text, "setup-marker")
}

function strictThoughtStreamJsonParse(text) {
  return strictJsonParse(text, "thought-stream")
}

function residentOrganShape(organs, eventsToday) {
  if (!isPlainRecord(organs)) return false
  var names = Object.keys(organs), total = 0
  // status=exact, parsed=7+9+1024, exact=1040. The producer can expose its
  // seven base sources, nine optional sources, and a bounded custom roster.
  if (names.length > 1040) return false
  for (var i = 0; i < names.length; i++) {
    if (!boundedNonEmptyString(names[i], 200)
        || !canonicalOrganName(names[i])) return false
    var row = organs[names[i]]
    if (!recordHasExactly(row, ["today", "last_ts"])
        || !nonNegativeInteger(row.today)
        || typeof row.last_ts !== "string"
        || (row.last_ts !== "" && !validUtcSecondTimestamp(row.last_ts)))
      return false
    total += row.today
  }
  return total === eventsToday
}

function residentHistoryShape(history) {
  if (!Array.isArray(history) || history.length > 120) return false
  for (var i = 0; i < history.length; i++) {
    var row = history[i]
    if (!Array.isArray(row) || row.length !== 2
        || !validUtcSecondTimestamp(row[0])
        || !nonNegativeInteger(row[1])) return false
  }
  return true
}

// History cells are individually JSON-safe integers, but their aggregate need
// not fit JavaScript's exact Number lane.  Add canonical decimal strings so a
// large valid history is never rounded before the cockpit labels it a total.
function addDecimalCounts(left, right) {
  if (typeof left !== "string" || typeof right !== "string"
      || !/^(0|[1-9][0-9]*)$/.test(left)
      || !/^(0|[1-9][0-9]*)$/.test(right)) return null
  var i = left.length - 1, j = right.length - 1
  var carry = 0, out = ""
  while (i >= 0 || j >= 0 || carry !== 0) {
    var digit = carry
    if (i >= 0) digit += left.charCodeAt(i--) - 48
    if (j >= 0) digit += right.charCodeAt(j--) - 48
    out = String(digit % 10) + out
    carry = Math.floor(digit / 10)
  }
  return out
}

function historyEventTotal(history, maxRows) {
  if (!residentHistoryShape(history) || !nonNegativeInteger(maxRows))
    return null
  var start = Math.max(0, history.length - maxRows)
  var total = "0"
  for (var i = start; i < history.length; i++) {
    total = addDecimalCounts(total, String(history[i][1]))
    if (total === null) return null
  }
  return total
}

function residentWorkspaceShape(workspace) {
  if (!Array.isArray(workspace) || workspace.length > 7) return false
  var seen = ({})
  for (var i = 0; i < workspace.length; i++) {
    if (!canonicalCorpusSlug(workspace[i])
        || seen["$" + workspace[i]] === true) return false
    seen["$" + workspace[i]] = true
  }
  return true
}

function residentIntentShape(intents) {
  if (!Array.isArray(intents) || intents.length > 5) return false
  for (var i = 0; i < intents.length; i++) {
    var row = intents[i]
    if (!recordHasExactly(row, ["id", "text", "due", "days_left"])
        || typeof row.id !== "string" || !/^[0-9a-f]{10}$/.test(row.id)
        || !redactionFreeStatusString(row.text, 70, true)
        || !validCalendarDate(row.due)
        || !integerNumber(row.days_left)) return false
  }
  return true
}

function residentBenchTrendShape(rows) {
  if (!Array.isArray(rows) || rows.length > 30) return false
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i]
    if (!recordHasExactly(
          row, ["date", "slug_match_at_5", "kind"])
        || !validCalendarDate(row.date)
        || typeof row.slug_match_at_5 !== "number"
        || !isFinite(row.slug_match_at_5)
        || row.slug_match_at_5 < 0 || row.slug_match_at_5 > 1
        || row.kind !== "heuristic-slug-retrieval-drift-tripwire")
      return false
  }
  return true
}

function residentRenderedCollectionsShape(status, required) {
  return ((!required && status.organs === undefined)
          || residentOrganShape(status.organs, status.events_today))
    && ((!required && status.history === undefined)
        || residentHistoryShape(status.history))
    && ((!required && status.workspace === undefined)
        || residentWorkspaceShape(status.workspace))
    && ((!required && status.intents === undefined)
        || residentIntentShape(status.intents))
    && ((!required && status.bench_trend === undefined)
        || residentBenchTrendShape(status.bench_trend))
}

// These are the only historical two-field generated-entry kinds whose producer was
// model-backed.  sialib uses the same closed policy while normalizing an old
// row to {kind,text,origin:"model"}; keep the cockpit admission exact.
function legacyModelThoughtKind(value) {
  return ["grade", "ponder", "note", "take"].indexOf(value) !== -1
}

function residentThoughtSummaryShape(value) {
  if (!recordHasExactly(value, ["ts", "kind", "text", "origin"])
      || ["evidence", "derived", "model", "legacy-unlabeled"]
           .indexOf(value.origin) === -1) return false
  if (value.ts === "")
    return value.kind === "" && value.text === ""
      && value.origin === "legacy-unlabeled"
  return validUtcSecondTimestamp(value.ts)
    && redactionFreeStatusString(value.kind, 2000, true)
    && canonicalOrganName(value.kind)
    && redactionFreeStatusString(value.text, 2000, true)
}

function residentDreamSummaryShape(value) {
  if (recordHasExactly(value, [])) return true
  if (recordHasExactly(value, ["last", "status", "summary"]))
    return validUtcSecondTimestamp(value.last)
      && ["ok", "clean", "partial"].indexOf(value.status) !== -1
      && redactionFreeStatusString(value.summary, 400, false)
  if (!recordHasExactly(
        value, ["last", "attempt", "status", "summary"])) return false
  return (value.last === "" || validUtcSecondTimestamp(value.last))
    && validUtcSecondTimestamp(value.attempt)
    && redactionFreeStatusString(value.status, 80, true)
    && redactionFreeStatusString(value.summary, 160, false)
}

function residentTakesSummaryShape(value) {
  if (recordHasExactly(value, [])) return true
  var fields = [
    "open", "due", "resolved", "brier", "calibration_status",
    "monitoring_display_eligible", "unresolvable", "invalid_resolved",
    "invalid_records"
  ]
  if (!recordHasExactly(value, fields)) return false
  var counts = ["open", "due", "resolved", "unresolvable",
                "invalid_resolved", "invalid_records"]
  for (var i = 0; i < counts.length; i++)
    if (!nonNegativeInteger(value[counts[i]])) return false
  if (value.due > value.open
      || (value.brier !== null
          && (typeof value.brier !== "number" || !isFinite(value.brier)
              || value.brier < 0 || value.brier > 1))) return false
  var states = ["no-resolved-outcomes", "single-case",
                "descriptive-series", "outcome-imbalanced",
                "monitoring-population"]
  if (states.indexOf(value.calibration_status) === -1
      || typeof value.monitoring_display_eligible !== "boolean") return false
  return ((value.calibration_status === "no-resolved-outcomes")
          === (value.resolved === 0))
    && ((value.brier === null) === (value.resolved === 0))
    && ((value.calibration_status === "single-case")
        === (value.resolved === 1))
    && (value.monitoring_display_eligible
        === (value.calibration_status === "monitoring-population"))
    && (value.resolved < 30
        ? value.calibration_status === (value.resolved === 0
            ? "no-resolved-outcomes" : value.resolved === 1
              ? "single-case" : "descriptive-series")
        : ["outcome-imbalanced", "monitoring-population"]
            .indexOf(value.calibration_status) !== -1)
}

function residentLedgerSummaryShape(value) {
  if (!recordHasExactly(value, ["seq", "head"])
      || !nonNegativeInteger(value.seq)
      || typeof value.head !== "string") return false
  return value.seq === 0 ? value.head === ""
    : /^[0-9a-f]{12}$/.test(value.head)
}

function residentStatusErrorsShape(value) {
  if (!isPlainRecord(value)) return false
  var names = Object.keys(value)
  if (names.length > 1024) return false
  for (var i = 0; i < names.length; i++) {
    if (!redactionFreeStatusString(names[i], 200, true)) return false
    var detail = value[names[i]]
    if (typeof detail === "string") {
      if (!redactionFreeStatusString(detail, 160, false)) return false
      continue
    }
    if (!Array.isArray(detail) || detail.length > 1024) return false
    for (var j = 0; j < detail.length; j++) {
      var row = detail[j]
      var fileRow = recordHasExactly(row, ["file", "error"])
      var configRow = recordHasExactly(row, ["config", "error"])
      if ((!fileRow && !configRow)
          || !redactionFreeStatusString(
               fileRow ? row.file : row.config, 4096, true)
          || !redactionFreeStatusString(row.error, 160, false)) return false
    }
  }
  return true
}

function residentStatusRedactionsShape(value) {
  if (!isPlainRecord(value)) return false
  var names = Object.keys(value)
  if (names.length > 1024) return false
  for (var i = 0; i < names.length; i++)
    if (!boundedNonEmptyString(names[i], 200)
        || !canonicalOrganName(names[i])
        || !nonNegativeInteger(value[names[i]])) return false
  return true
}

function residentCurrentStatusShape(status, graphPublicationRequired) {
  var requireGraphPublication = graphPublicationRequired !== false
  var required = [
    "v", "version", "ts", "state", "pulse_seq", "day",
    "publication_id", "events_pulse",
    "events_today", "organs", "errors", "pages", "graph_nodes",
    "graph_edges", "integrity", "ledger", "ledger_transition", "thought",
    "dream", "history", "workspace", "mind", "takes", "intents",
    "bench_trend", "bench_trend_boundary", "projection_debt",
    "agent_queue", "redactions", "sync_note"
  ]
  if (requireGraphPublication) required.push("graph_publication_id")
  if (!recordHasExactly(status, required)
      || releaseVersionParts(status.version) === null
      || !validCalendarDate(status.day)
      || !nonNegativeInteger(status.pulse_seq)
      || !nonNegativeInteger(status.events_pulse)
      || !nonNegativeInteger(status.pages)
      || !nonNegativeInteger(status.graph_nodes)
      || !nonNegativeInteger(status.graph_edges)
      || status.graph_nodes > 260 || status.graph_edges > 4096
      || status.graph_nodes > status.pages
      || (status.graph_nodes === 0 && status.graph_edges !== 0)
      || (requireGraphPublication
          && !publicationId(status.graph_publication_id, true))
      || (requireGraphPublication && status.graph_publication_id === ""
          && (status.pages !== 0 || status.graph_nodes !== 0
              || status.graph_edges !== 0))
      || !residentThoughtSummaryShape(status.thought)
      || !residentDreamSummaryShape(status.dream)
      || !residentTakesSummaryShape(status.takes)
      || !residentStatusErrorsShape(status.errors)
      || !redactionFreeStatusString(status.sync_note, 400, false)
      || !residentRenderedCollectionsShape(status, true)) return false

  var mindFields = ["nodes", "edges", "decay_active", "decay_demoted",
                    "rehearsal_eligible", "rehearsal_due", "pinned"]
  if (status.v === 2) mindFields.push("familiarity_status")
  var relayFields = ["materialized", "refused", "acknowledged"]
  if (!recordHasExactly(status.mind, mindFields)
      || !recordHasExactly(status.agent_queue, relayFields)
      || !recordHasExactly(status.projection_debt, ["graph", "consolidation"])
      || !redactionFreeStatusString(
           status.projection_debt.graph, 400, false)
      || !redactionFreeStatusString(
           status.projection_debt.consolidation, 400, false)
      || !residentLedgerSummaryShape(status.ledger)
      || !recordHasExactly(
        status.ledger_transition, ["state", "recovered", "pending_errors"])
      || ["not-required", "signed", "pending"].indexOf(
        status.ledger_transition.state) === -1
      || !nonNegativeInteger(status.ledger_transition.recovered)
      || !nonNegativeInteger(status.ledger_transition.pending_errors)
      || status.ledger_transition.recovered > 1024
      || status.ledger_transition.pending_errors !== 0
      || (status.ledger_transition.state === "pending"
          && Object.keys(status.errors).length === 0)
      || !recordHasExactly(
        status.bench_trend_boundary, ["legacy_truncated"])
      || typeof status.bench_trend_boundary.legacy_truncated !== "boolean"
      || !residentStatusRedactionsShape(status.redactions)) return false
  return true
}

function residentIntegrityShape(status) {
  // Pre-release status had no integrity block; keep that distinctive upgrade
  // route. Every release-stamped publisher binds its state to chain verdicts.
  if (status.version === undefined) return true
  if (!boundedString(status.sync_note, 400)
      || !recordHasExactly(
        status.integrity, ["chains", "verdict", "checked_at"])
      || !isPlainRecord(status.integrity.chains)
      || !validUtcSecondTimestamp(status.integrity.checked_at)) return false
  var names = Object.keys(status.integrity.chains)
  // Arithmetic evidence: status=exact, parsed=8+4, exact=12. Eight configured rows plus
  // the four built-in keepers are the producer's maximum roster.
  if (!names.length || names.length > 12) return false
  if (!Object.prototype.hasOwnProperty.call(
        status.integrity.chains, "sia")) return false
  var sawFail = false, sawNonPass = false
  for (var i = 0; i < names.length; i++) {
    var chain = status.integrity.chains[names[i]]
    if (!boundedNonEmptyString(names[i], 200)
        || !canonicalOrganName(names[i])
        || ["pass", "fail", "absent"].indexOf(chain) === -1) return false
    if (chain === "fail") sawFail = true
    if (chain !== "pass") sawNonPass = true
  }
  var verdict = sawFail ? "fail" : (sawNonPass ? "degraded" : "pass")
  if (status.integrity.verdict !== verdict) return false
  // A brainstem/pulse failure may retain a prior pass/degraded integrity
  // snapshot, but a current chain failure can only publish failed state.
  if (verdict === "fail" && status.state !== "failed") return false
  if ((status.state === "ok" || status.state === "thinking")
      && verdict !== "pass") return false
  if (status.integrity.chains.sia === "pass"
      && (!residentLedgerSummaryShape(status.ledger)
          || status.ledger.seq === 0)) return false
  return true
}

// Status snapshots published before release stamping still have a narrow,
// distinctive schema.  Recognize that real legacy shape for upgrade routing;
// a generic versionless object remains a repair condition.
function residentStatusShape(status) {
  if (!isPlainRecord(status)
      || (status.v !== 1 && status.v !== 2)
      || !validUtcSecondTimestamp(status.ts)
      || STATUS_STATES.indexOf(status.state) === -1
      || !nonNegativeInteger(status.events_today)
      || !isPlainRecord(status.errors)
      || typeof status.publication_id !== "string"
      || !isPlainRecord(status.projection_debt)
      || typeof status.projection_debt.graph !== "string"
      || typeof status.projection_debt.consolidation !== "string"
      || !isPlainRecord(status.mind)
      || !isPlainRecord(status.agent_queue)) return false
  if (status.v === 2) {
    if (["complete", "incomplete", "bootstrap-pending"].indexOf(
          status.mind.familiarity_status) === -1) return false
  } else if (Object.prototype.hasOwnProperty.call(
               status.mind, "familiarity_status")) return false
  // Versionless status is a deliberately narrow legacy route. Every stamped
  // producer uses UUID-hex publication identities; the graph identity alone
  // permits the empty sentinel published before the first successful export.
  if (status.version !== undefined
      && !publicationId(status.publication_id, false)) return false
  if (status.v === 2) {
    // Detector availability belongs to the current, fully bound schema.
    // It must not travel through a versionless or older-release route.
    if (status.version !== releaseVersion()
        || !residentCurrentStatusShape(status, true)) return false
  } else if (status.version === undefined) {
    if (!residentRenderedCollectionsShape(status, false)) return false
  } else {
    var compared = compareReleaseVersions(status.version, releaseVersion())
    if (compared === null || compared > 0) return false
    if (compared === 0) {
      // Frozen v1.7.8 status predates the graph-publication field. Its exact
      // legacy roster remains an intentional recovery/upgrade route, while a
      // present graph identity must obey the current producer's UUID envelope.
      if (!residentCurrentStatusShape(
            status, status.graph_publication_id !== undefined)) return false
    } else if (status.version === "1.7.7"
               || status.version === "1.7.8") {
      // Frozen v1.7.7/v1.7.8 producers lacked the graph publication binding.
      if (!residentCurrentStatusShape(
            status, status.version === "1.7.8"
              && status.graph_publication_id !== undefined)) return false
    } else if (!residentRenderedCollectionsShape(status, false)) return false
  }
  if ((status.state === "ok" || status.state === "thinking")
      && (Object.keys(status.errors).length !== 0
          || (status.version !== undefined && status.sync_note !== "")))
    return false
  var mindFields = ["nodes", "edges", "decay_active", "decay_demoted",
                    "rehearsal_eligible", "rehearsal_due", "pinned"]
  var relayFields = ["materialized", "refused", "acknowledged"]
  for (var i = 0; i < mindFields.length; i++)
    if (!nonNegativeInteger(status.mind[mindFields[i]])) return false
  for (var j = 0; j < relayFields.length; j++)
    if (!nonNegativeInteger(status.agent_queue[relayFields[j]])) return false
  if (status.mind.decay_active > status.mind.edges
      || status.mind.decay_demoted
         !== status.mind.edges - status.mind.decay_active
      || status.mind.rehearsal_due > status.mind.rehearsal_eligible
      || status.mind.rehearsal_eligible > status.mind.nodes
      || status.mind.pinned > status.mind.nodes
      || status.agent_queue.materialized > 1024
      || status.agent_queue.acknowledged
         > status.agent_queue.materialized
      || status.agent_queue.refused > 1025) return false
  return residentIntegrityShape(status)
}

function familiarityStatusText(mind) {
  if (!isPlainRecord(mind)
      || !Object.prototype.hasOwnProperty.call(mind, "familiarity_status"))
    return "unavailable · legacy status; detector availability unreported"
  if (mind.familiarity_status === "complete")
    return "complete · first/new-shape detection available"
  if (mind.familiarity_status === "incomplete")
    return "incomplete · first/new-shape claims withheld"
  if (mind.familiarity_status === "bootstrap-pending")
    return "bootstrap pending · baseline not admitted; first/new-shape claims withheld"
  return "unavailable · detector status invalid"
}

function snapshotGenerationsMatch(status, graph) {
  return isPlainRecord(status) && isPlainRecord(graph)
    && typeof status.graph_publication_id === "string"
    && status.graph_publication_id !== ""
    && typeof graph.publication_id === "string"
    && graph.publication_id !== ""
    && status.graph_publication_id === graph.publication_id
}

function legacyResidentStatus(status) {
  return status && status.version === undefined
    && residentStatusShape(status)
}

function runtimeLifecycle(status, pluginVersion) {
  if (!status || typeof status !== "object") return "setup"
  if (status.version === undefined)
    return legacyResidentStatus(status) ? "update" : "repair"
  var compared = compareReleaseVersions(status.version, pluginVersion)
  if (compared === null) return "repair"
  if (compared < 0) return "update"
  if (compared > 0) return "ahead"
  return "ready"
}

// Rendering requires the exact current producer schema, but downgrade
// prevention has a deliberately smaller authority: a syntactically valid
// newer release number is enough to block an older cockpit from treating an
// unfamiliar future state as repairable by downgrade. Rejected equal/older
// records carry no lifecycle authority. Once ahead has been observed, a
// malformed replacement cannot erase it; a later admitted status can.
function runtimeLifecycleEvidence(status, statusValid, prior, pluginVersion) {
  if (statusValid && residentStatusShape(status)) return status
  var compared = isPlainRecord(status)
    ? compareReleaseVersions(status.version, pluginVersion) : null
  if (compared !== null && compared > 0)
    return ({version: status.version})
  return runtimeLifecycle(prior, pluginVersion) === "ahead" ? prior : null
}

function aheadVersion(evidence, pluginVersion) {
  var compared = isPlainRecord(evidence)
    ? compareReleaseVersions(evidence.version, pluginVersion) : null
  return compared !== null && compared > 0 ? evidence.version : ""
}

function installCompletionReady(completion, pluginVersion) {
  return validInstallCompletion(completion)
    && completion.state === "ready"
    && completion.version === pluginVersion
}

function installCompletionInstalling(completion, pluginVersion) {
  return validInstallCompletion(completion)
    && completion.state === "installing"
    && completion.version === pluginVersion
}

function validInstallCompletion(completion) {
  return recordHasExactly(completion, ["v", "version", "state"])
    && completion.v === 1
    && (completion.state === "installing" || completion.state === "ready")
    && releaseVersionParts(completion.version) !== null
}

// File resolution is handled by the QML surfaces.  Once both reads have
// resolved, this combines the resident status and the separate, release-bound
// completion record.  Existing completion state plus a missing status is a
// repair condition, never a claim that no current memory state exists.
function guidedLifecycle(status, completion, pluginVersion) {
  var runtime = runtimeLifecycle(status, pluginVersion)
  if (runtime === "ahead") return "ahead"
  var completionCompared = validInstallCompletion(completion)
    ? compareReleaseVersions(completion.version, pluginVersion) : null
  if (completionCompared !== null && completionCompared > 0) return "ahead"
  if (installCompletionInstalling(completion, pluginVersion))
    return "installing"
  if (runtime === "repair") return "repair"
  if (runtime === "setup") return completion ? "repair" : "setup"
  if (runtime === "update") return "update"
  return installCompletionReady(completion, pluginVersion)
    ? "ready" : "repair"
}

// `installing` is a record, not a lease.  Nothing in the first-light file
// expires it, and the install.lock the run stage holds lives under
// XDG_RUNTIME_DIR, so it is per-boot and invisible to this surface.  A
// crashed or killed installer therefore left the cockpit painting
// "INSTALLATION IN PROGRESS" forever, which is a claim about the present
// that no one is checking.
//
// The record itself carries no clock: siarelease._completion_release pins
// its schema to exactly {v, version, state}, and that pin is a fail-closed
// downgrade guard, so a timestamp cannot simply be added to it here.  The
// only honest clock available to a pixels-only surface is how long THIS
// cockpit has continuously observed this exact record.  That is what the
// caller passes in, and it is why the wording this unlocks says the
// installer has not reported progress rather than that it started long ago.
//
// The bound is a judgement, not a measurement: a first light downloads
// pinned restic, Bun, gbrain and Ollama artifacts, builds gbrain, and pulls
// a local embedding model.  Ninety minutes is well past any of that on the
// hardware SIA targets while still being a bound.  Keep it far away from
// staleAfterMaxSec(); that clock times the brainstem pulse, not an install.
function installingUnobservedAfterSec() { return 5400 }

// Returns whether the installing record has gone unobserved past the bound.
// Unknown inputs answer false: this predicate may only ever add a caveat to
// the gate, so when the clock itself is unreadable the honest move is to say
// nothing new rather than to accuse a running installer.  It never reports
// readiness or failure, and no caller may promote a lifecycle from it.
function installingProgressUnobserved(observedAtMs, nowMs) {
  var observed = Number(observedAtMs)
  var now = Number(nowMs)
  if (!isFinite(observed) || observed <= 0) return false
  if (!isFinite(now) || now < observed) return false
  return (now - observed) >= installingUnobservedAfterSec() * 1000
}

// A click asks the desktop to open a terminal; nothing in the desktop
// contract guarantees one appears, and xdg-terminal-exec drops --hold on a
// terminal that declares no TerminalArgHold=.  The run stage therefore
// publishes an owner-private marker the moment it starts, and that start is
// read back from it here.  It is evidence the installer shell began running
// with a terminal attached, never evidence that a window was mapped: nothing
// here queries the compositor.  The id is a per-click freshness token on an
// owner-private file, not a secret or an authorization: it exists so a
// marker left by an earlier attempt cannot answer this click, which a
// whole-second timestamp alone cannot rule out.
function drawAttemptId() {
  var hex = "0123456789abcdef"
  var out = ""
  for (var i = 0; i < 32; i++)
    out += hex.charAt(Math.floor(Math.random() * 16))
  return out
}

function setupTerminalPresented(marker, requestedAtSec, requestedAttempt,
                                observedAtSec) {
  if (!recordHasExactly(marker, ["attempt", "pid", "ts", "tty", "v"])
      || marker.v !== 1 || !nonNegativeInteger(marker.pid)
      || marker.pid === 0) return false
  if (typeof requestedAttempt !== "string"
      || !/^[0-9a-f]{32}$/.test(requestedAttempt)) return false
  if (marker.attempt !== requestedAttempt) return false
  // The run stage records whether it actually got a terminal, and holds the
  // window only when it did.  A marker that says otherwise is evidence
  // against presentation, never for it.
  if (marker.tty !== true) return false
  var stamp = marker.ts
  var requested = Number(requestedAtSec)
  var observed = Number(observedAtSec)
  if (!nonNegativeInteger(stamp) || stamp === 0
      || !nonNegativeInteger(requested) || requested === 0
      || !nonNegativeInteger(observed) || observed < requested) return false
  return stamp >= requested && stamp <= observed
}

// Keep this policy paired with manifest.json's staleAfterSec schema. Both UI
// entry points call the same validator so hand-edited shell configuration
// cannot bypass the declared integer range.
function staleAfterMinSec() { return 120 }
function staleAfterMaxSec() { return 900 }
function staleAfterDefaultSec() { return 240 }

function validStaleAfterSec(value, fallback) {
  var parsed = Number(value)
  if (isFinite(parsed) && Math.floor(parsed) === parsed
      && parsed >= staleAfterMinSec() && parsed <= staleAfterMaxSec())
    return parsed
  var safeFallback = Number(fallback)
  if (isFinite(safeFallback) && Math.floor(safeFallback) === safeFallback
      && safeFallback >= staleAfterMinSec()
      && safeFallback <= staleAfterMaxSec())
    return safeFallback
  return staleAfterDefaultSec()
}

// A timestamp is fresh only while it lies inside the observed clock's past
// horizon. A future stamp is not evidence of a fresh publication: accepting
// it would let one bad clock preserve a reassuring state indefinitely.
function timestampStale(value, nowMs, staleAfterSec) {
  if (!validUtcSecondTimestamp(value)) return true
  var stamped = Date.parse(value)
  var now = Number(nowMs)
  var horizon = Number(staleAfterSec)
  if (!(stamped > 0) || !isFinite(now) || !isFinite(horizon)
      || horizon <= 0) return true
  var age = now - stamped
  return age < 0 || age > horizon * 1000
}

// Retained live-loop display only. The CLI owns source admission; these
// shape/time/generation checks neither authenticate hashes nor certify scores.
function liveDigest(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value)
}

function liveBoundaryStrings(value) {
  return Array.isArray(value) && value.length > 0 && value.length <= 256
    && value.every(function(item) {
      return inertStatusString(item, 4096, true)
    })
}

function liveActivationShape(value, observedAt) {
  if (!isPlainRecord(value) || value.component !== "usage-salience"
      || value.status !== "computed-unverified" || value.observed_at !== observedAt
      || !Array.isArray(value.activations) || value.activations.length > 256
      || !Array.isArray(value.order) || value.order.length !== value.activations.length)
    return false
  var seen = Object.create(null)
  for (var item of value.activations) {
    if (!isPlainRecord(item) || !canonicalCorpusSlug(item.subject)
        || seen[item.subject] || item.component !== "usage-salience"
        || item.observed_at !== observedAt) return false
    seen[item.subject] = true
    if (item.status === "computed-unverified") {
      if (typeof item.score !== "number" || !isFinite(item.score)
          || item.reason !== null) return false
    } else if (item.status !== "unavailable" || item.score !== null
               || item.reason !== "no-use-history") return false
  }
  var ordered = Object.create(null)
  return value.order.every(function(subject) {
    if (typeof subject !== "string" || !seen[subject] || ordered[subject]) return false
    ordered[subject] = true
    return true
  })
}

function liveAdmissionShape(value) {
  return Array.isArray(value) && value.every(function(item) {
    return isPlainRecord(item) && ["perception", "delivery"].indexOf(item.kind) >= 0
      && typeof item.eligible === "boolean" && liveDigest(item.version_sha256)
      && inertStatusString(item.record_id, 1024, true)
      && ["encoding-strength-admitted", "encoding-strength-below-threshold",
          "explicit-delivery-admitted"].indexOf(item.reason) >= 0
  })
}

function liveWorkspaceView(view, status, nowMs, staleAfterSec) {
  if (!recordHasExactly(view, ["schema", "status", "origin", "as_of", "publication",
        "workspace", "encoding", "admission", "activation", "coretrieval", "idle",
        "non_claims", "upstream_non_claims", "view_sha256"])
      || view.schema !== "sia-controller-live-view-v1" || view.status !== "available"
      || view.origin !== "derived" || !nonNegativeInteger(view.as_of)
      || !nonNegativeInteger(view.as_of * 1000) || !liveDigest(view.view_sha256)
      || !liveBoundaryStrings(view.non_claims) || !isPlainRecord(view.upstream_non_claims)
      || !residentStatusShape(status) || typeof nowMs !== "number" || !isFinite(nowMs)
      || typeof staleAfterSec !== "number"
      || validStaleAfterSec(staleAfterSec, staleAfterDefaultSec()) !== staleAfterSec)
    return null
  var publication = view.publication
  if (!recordHasExactly(publication, ["publication_id", "pulse_seq", "epoch_id",
        "state_sha256", "transition_sha256", "generation_sha256", "status_timestamp",
        "source_batch_sha256", "source_effects_receipt_sha256", "policy_sha256"])
      || typeof publication.publication_id !== "string"
      || !/^[0-9a-f]{32}$/.test(publication.publication_id)
      || publication.publication_id !== status.publication_id
      || publication.pulse_seq !== status.pulse_seq
      || publication.status_timestamp !== status.ts
      || !inertStatusString(publication.epoch_id, 1024, true)
      || timestampStale(status.ts, nowMs, staleAfterSec)
      || nowMs < view.as_of * 1000 || nowMs - view.as_of * 1000 > staleAfterSec * 1000
      || ["state_sha256", "transition_sha256", "generation_sha256", "source_batch_sha256",
          "source_effects_receipt_sha256", "policy_sha256"].some(function(field) {
            return !liveDigest(publication[field])
          })) return null
  var ws = view.workspace
  if (!isPlainRecord(ws) || ws.component !== "maintained-workspace"
      || ws.status !== "computed-unverified" || ws.observed_at !== view.as_of
      || ["idle", "holding"].indexOf(ws.phase) < 0
      || ["idle", "ignited", "sustained", "released", "replaced"].indexOf(ws.transition) < 0
      || [null, "hold-expired", "explicit-release"].indexOf(ws.release_reason) < 0
      || !nonNegativeInteger(ws.capacity) || ws.capacity === 0 || ws.capacity > 256
      || typeof ws.ignition_threshold !== "number" || !isFinite(ws.ignition_threshold)
      || !Array.isArray(ws.slots) || ws.slots.length > ws.capacity
      || !Array.isArray(ws.selected_sources) || ws.selected_sources.length !== ws.slots.length
      || !Array.isArray(ws.candidates) || ws.candidates.length > 256
      || !liveActivationShape(view.activation, view.as_of) || !liveAdmissionShape(view.admission))
    return null
  var slots = Object.create(null)
  for (var i = 0; i < ws.slots.length; i++) {
    var subject = ws.slots[i]
    var selected = ws.selected_sources[i]
    if (!canonicalCorpusSlug(subject) || slots[subject]
        || !recordHasExactly(selected, ["subject", "origin", "source_sha256"])
        || selected.subject !== subject || !liveDigest(selected.source_sha256)
        || ["evidence", "derived", "model", "legacy-unlabeled"].indexOf(selected.origin) < 0)
      return null
    slots[subject] = true
  }
  var candidates = Object.create(null)
  for (var candidate of ws.candidates) {
    if (!recordHasExactly(candidate, ["subject", "eligible", "selected"])
        || !canonicalCorpusSlug(candidate.subject) || candidates[candidate.subject]
        || typeof candidate.eligible !== "boolean" || typeof candidate.selected !== "boolean"
        || candidate.selected !== !!slots[candidate.subject]) return null
    candidates[candidate.subject] = true
  }
  if (ws.phase === "holding") {
    var selection = ws.selection
    if (!ws.slots.length || !nonNegativeInteger(ws.ignited_at)
        || !nonNegativeInteger(ws.expires_at) || ws.expires_at <= ws.ignited_at
        || !nonNegativeInteger(ws.expires_at * 1000) || ws.ignited_at > view.as_of
        || !isPlainRecord(selection) || selection.observed_at !== ws.ignited_at
        || !liveActivationShape(selection.activation, selection.observed_at)
        || !liveAdmissionShape(selection.admission)) return null
  } else if (ws.slots.length || ws.selection !== null
             || ws.ignited_at !== null || ws.expires_at !== null) return null
  var idle = view.idle
  if (!isPlainRecord(idle) || typeof idle.requested !== "boolean"
      || ["not-requested", "proposals-only", "gist-pages-published"].indexOf(idle.gist_publication_status) < 0
      || idle.availability !== null && !inertStatusString(idle.availability, 256, true)) return null
  var result = {as_of: view.as_of, expired: ws.expires_at !== null && nowMs >= ws.expires_at * 1000,
    publication: publication, workspace: ws, activation: view.activation,
    admission: view.admission, idle: idle, non_claims: view.non_claims}
  try {
    var raw = JSON.stringify(result)
    if (raw.length > 16777216) return null
    return JSON.parse(raw)
  } catch (e) { return null }
}

function liveWorkspaceSummary(display) {
  if (!display) return "Live workspace unavailable — no matching retained source view"
  var ws = display.workspace
  return "Live workspace · retained as of " + display.as_of + " · " + ws.status
    + " · " + ws.slots.length + " of " + ws.capacity + " · " + ws.phase + " / " + ws.transition
    + (ws.release_reason === null ? "" : " · " + ws.release_reason)
    + (ws.expires_at === null ? "" : " · " + (display.expired ? "expired " : "expires ") + ws.expires_at)
    + " · gist " + display.idle.gist_publication_status
    + (display.idle.availability === null ? "" : " · " + display.idle.availability)
}

// ------------------------------------------------------------- continuity

// The backup worker publishes independently from the brainstem so recovery
// progress remains visible while SIA itself is quiesced.  Keep this validator
// shared by the bar and cockpit: neither surface may turn malformed or
// mid-replace bytes into a reassuring recovery state.
var CONTINUITY_STATES = [
  "unconfigured", "queued", "capturing", "uploading", "checking",
  "preparing", "prepared", "restoring", "verified", "recovery-only",
  "failed", "blocked"
]
var CONTINUITY_OPERATION_PHASES = [
  "accepted", "running", "verified", "failed", "blocked"
]
var CONTINUITY_OPERATION_KINDS = [
  "backup-setup", "backup-connect", "backup-upload", "backup-check",
  "restore-prepare", "restore-apply", "restore-recover"
]
var CONTINUITY_READINESS = ["ready", "recovery-only", "unknown"]
var CONTINUITY_PREPARED_READINESS = ["ready", "recovery-only"]
var CONTINUITY_STATUS_FIELDS = [
  "schema_version", "state", "detail", "repository_display", "latest",
  "prepared", "operation", "updated_at"
]
var CONTINUITY_LATEST_FIELDS = [
  "snapshot_id", "created_at", "verified", "readiness", "profile",
  "identity_matches"
]
var CONTINUITY_PREPARED_FIELDS = [
  "prepared_id", "snapshot_id", "created_at", "readiness", "profile",
  "ledger_head", "identity_matches"
]
var CONTINUITY_OPERATION_FIELDS = [
  "request_id", "kind", "prepared_id", "phase", "ready",
  "sia_ledger_verified"
]
var CONTINUITY_SCHEDULE_FIELDS = [
  "schema_version", "configured", "automatic", "observed_at", "upload",
  "verification"
]
var CONTINUITY_SCHEDULE_TIMER_FIELDS = [
  "cadence", "enabled", "active", "persistent", "wake_system",
  "last_trigger_at", "next_trigger_at"
]

function isPlainRecord(value) {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function validContinuityText(value, nonempty) {
  return typeof value === "string" && value.length <= 2000
    && /^[\x20-\x7e]*$/.test(value)
    && (nonempty !== true || value !== "")
}

function validContinuityIdentifier(value, allowEmpty) {
  return typeof value === "string"
    && ((allowEmpty === true && value === "")
        || /^[0-9a-f]{1,64}$/.test(value))
}

function validContinuityCorrelationId(value) {
  return typeof value === "string" && /^[0-9a-f]{32}$/.test(value)
}

function validContinuitySnapshotTimestamp(value) {
  // Arithmetic evidence: status=exact, parsed=19+1+9+6, exact=35.
  if (typeof value !== "string" || value.length > 35) return false
  var match = value.match(
    /^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?(Z|[+-][0-9]{2}:[0-9]{2})$/)
  if (!match || !validUtcSecondTimestamp(match[1] + "Z")) return false
  if (match[2] && match[2].slice(-1) === "0") return false
  if (match[3] !== "Z") {
    var offsetHour = Number(match[3].slice(1, 3))
    var offsetMinute = Number(match[3].slice(4, 6))
    if (offsetHour > 23 || offsetMinute > 59
        || (offsetHour === 0 && offsetMinute === 0)) return false
  }
  return isFinite(Date.parse(value))
}

function validContinuityLatest(value) {
  if (value === null) return true
  if (value === undefined) return false
  return recordHasExactly(value, CONTINUITY_LATEST_FIELDS)
    && validContinuityIdentifier(value.snapshot_id, false)
    && validContinuitySnapshotTimestamp(value.created_at)
    && typeof value.verified === "boolean"
    && CONTINUITY_READINESS.indexOf(value.readiness) !== -1
    && value.profile === "signed portable capsule"
    && typeof value.identity_matches === "boolean"
    && (value.readiness !== "unknown" || !value.verified)
}

function continuityLatestReady(value, receiptAuthenticated) {
  return validContinuityLatest(value)
    && value !== null && value !== undefined
    && receiptAuthenticated === true
    && value.verified === true
    && value.readiness === "ready"
    && value.identity_matches === true
}

function validContinuityPrepared(value) {
  if (value === null) return true
  if (value === undefined) return false
  return recordHasExactly(value, CONTINUITY_PREPARED_FIELDS)
    && validContinuityCorrelationId(value.prepared_id)
    && validContinuityIdentifier(value.snapshot_id, false)
    && validUtcSecondTimestamp(value.created_at)
    && CONTINUITY_PREPARED_READINESS.indexOf(value.readiness) !== -1
    && value.profile === "signed portable capsule"
    && /^[0-9a-f]{64}$/.test(value.ledger_head)
    && typeof value.identity_matches === "boolean"
}

function validContinuityOperation(value) {
  if (value === null) return true
  if (value === undefined) return false
  if (!recordHasExactly(value, CONTINUITY_OPERATION_FIELDS)
      || !validContinuityCorrelationId(value.request_id)
      || CONTINUITY_OPERATION_KINDS.indexOf(value.kind) === -1
      || !(value.prepared_id === ""
           || validContinuityCorrelationId(value.prepared_id))
      || CONTINUITY_OPERATION_PHASES.indexOf(value.phase) === -1
      || typeof value.ready !== "boolean"
      || typeof value.sia_ledger_verified !== "boolean") return false
  if (value.kind === "restore-apply") {
    if (value.prepared_id === "") return false
  } else if (value.kind === "restore-prepare") {
    if ((value.prepared_id !== "") !== (value.phase === "verified"))
      return false
  } else if (value.prepared_id !== "") return false
  var restore = value.kind === "restore-apply"
    || value.kind === "restore-recover"
  if (!restore && (value.ready || value.sia_ledger_verified)) return false
  if ((value.phase === "accepted" || value.phase === "failed")
      && (value.ready || value.sia_ledger_verified)) return false
  if (restore && value.phase === "running"
      && value.ready !== value.sia_ledger_verified) return false
  if (restore && value.phase === "verified"
      && (!value.ready || !value.sia_ledger_verified)) return false
  return true
}

function validContinuityStateOperation(value) {
  var operation = value.operation
  if (operation === null)
    return value.state === "unconfigured" || value.state === "verified"
      || value.state === "recovery-only"
  var kind = operation.kind
  var phase = operation.phase
  if (value.state === "queued") {
    return (phase === "accepted" && [
      "backup-setup", "backup-connect", "backup-upload", "backup-check",
      "restore-prepare"
    ].indexOf(kind) !== -1)
      || (phase === "running"
          && (kind === "backup-setup" || kind === "backup-connect"))
  }
  if (value.state === "capturing" || value.state === "uploading")
    return kind === "backup-upload" && phase === "running"
  if (value.state === "checking")
    return kind === "backup-check" && phase === "running"
  if (value.state === "preparing")
    return kind === "restore-prepare" && phase === "running"
  if (value.state === "prepared")
    return isPlainRecord(value.prepared)
      && kind === "restore-prepare" && phase === "verified"
      && operation.prepared_id === value.prepared.prepared_id
  if (value.state === "restoring")
    return (kind === "restore-apply"
            && (phase === "accepted" || phase === "running"))
      || (kind === "restore-recover" && phase === "running")
  if (value.state === "verified" || value.state === "recovery-only")
    return phase === "verified" && kind !== "restore-prepare"
  if (value.state === "failed") return phase === "failed"
  if (value.state === "blocked") return phase === "blocked"
  return false
}

function validContinuityScheduleTimestamp(value, nullable) {
  if (nullable && value === null) return true
  return validUtcSecondTimestamp(value)
}

function validContinuityScheduleTimer(value, cadence) {
  return recordHasExactly(value, CONTINUITY_SCHEDULE_TIMER_FIELDS)
    && value.cadence === cadence
    && typeof value.enabled === "boolean"
    && typeof value.active === "boolean"
    && typeof value.persistent === "boolean"
    && typeof value.wake_system === "boolean"
    && validContinuityScheduleTimestamp(value.last_trigger_at, true)
    && validContinuityScheduleTimestamp(value.next_trigger_at, true)
}

function validContinuitySchedule(value) {
  if (!recordHasExactly(value, CONTINUITY_SCHEDULE_FIELDS)
      || value.schema_version !== 1
      || typeof value.configured !== "boolean"
      || typeof value.automatic !== "boolean"
      || !validContinuityScheduleTimestamp(value.observed_at, false)
      || !validContinuityScheduleTimer(value.upload, "hourly")
      || !validContinuityScheduleTimer(value.verification, "weekly"))
    return false
  var active = value.configured
    && value.upload.enabled && value.upload.active
    && value.verification.enabled && value.verification.active
  return value.automatic === active
}

function validContinuityStatus(value, receiptAuthenticated) {
  return receiptAuthenticated === true
    && recordHasExactly(value, CONTINUITY_STATUS_FIELDS)
    && value.schema_version === 2
    && typeof value.state === "string"
    && CONTINUITY_STATES.indexOf(value.state) !== -1
    && validContinuityText(value.detail, true)
    && validContinuityText(value.repository_display, false)
    && (value.repository_display === ""
        || value.repository_display === "External recovery repository")
    && validUtcSecondTimestamp(value.updated_at)
    && validContinuityLatest(value.latest)
    && validContinuityPrepared(value.prepared)
    && validContinuityOperation(value.operation)
    && validContinuityStateOperation(value)
    && ((value.state === "unconfigured")
        === (value.repository_display === ""))
    && (value.state !== "unconfigured"
        || (value.latest === null && value.prepared === null))
    && (value.state !== "verified"
        || continuityLatestReady(value.latest, receiptAuthenticated))
}

function continuityStateLabel(state) {
  if (state === "unconfigured") return "NOT SET UP"
  if (state === "queued") return "COPY QUEUED"
  if (state === "capturing" || state === "uploading") return "COPYING"
  if (state === "checking") return "VERIFYING COPY"
  if (state === "preparing") return "PREPARING RESTORE"
  if (state === "prepared") return "RESTORE PREPARED"
  if (state === "restoring") return "RESTORING"
  if (state === "verified") return "RECOVERY READY"
  if (state === "recovery-only") return "NEEDS ATTENTION"
  if (state === "failed") return "FAILED"
  if (state === "blocked") return "NEEDS ATTENTION"
  return "STATUS UNAVAILABLE"
}

function continuityTone(state) {
  if (state === "verified") return "good"
  if (state === "failed" || state === "blocked") return "danger"
  if (continuityBusy(state)) return "busy"
  return "attention"
}

function continuityBusy(state) {
  return ["queued", "capturing", "uploading", "checking", "preparing",
          "restoring"].indexOf(state) !== -1
}

function continuityCanBackUp(status, receiptAuthenticated) {
  if (!validContinuityStatus(status, receiptAuthenticated)) return false
  return ["verified", "recovery-only", "failed", "blocked"]
    .indexOf(status.state) !== -1
}

function continuityCanCheck(status, receiptAuthenticated) {
  return continuityCanBackUp(status, receiptAuthenticated)
}

function continuityCanPrepare(status, receiptAuthenticated) {
  if (!validContinuityStatus(status, receiptAuthenticated)
      || continuityBusy(status.state))
    return false
  var latest = status.latest
  return isPlainRecord(latest) && latest.verified === true
    && latest.snapshot_id !== ""
}

function continuityCanApply(status, receiptAuthenticated) {
  if (!validContinuityStatus(status, receiptAuthenticated)
      || status.state !== "prepared")
    return false
  var prepared = status.prepared
  return isPlainRecord(prepared) && prepared.prepared_id !== ""
    && prepared.snapshot_id !== "" && prepared.ledger_head !== ""
}

// The bar had no clock for continuity at all, only for the brainstem pulse.
// A continuity worker that is uninstalled, masked, or wedged stops writing
// while its last file survives, so the widget went on painting yesterday's
// "verified" as though someone were still checking.  siabackup._publish_status
// stamps updated_at on every publication and sia-backup.timer fires hourly,
// so a real clock does exist here; six silent publications is far past timer
// jitter, a suspend, or one long copy.  Withdrawing a claim is the only thing
// this bound may do: staleness never promotes a state and never invents one.
function continuityStaleAfterSec() { return 21600 }

// Unreadable input answers stale.  This predicate exists to stop a reassuring
// mark from outliving the subsystem, so its unknown case must fall towards
// "not reporting", the opposite of the installing-horizon predicate above,
// which may only add a caveat.
function continuityStale(status, nowMs, staleAfterSec) {
  if (!isPlainRecord(status)) return true
  return timestampStale(status.updated_at, nowMs, staleAfterSec)
}

function continuityBarMark(status, receiptAuthenticated) {
  if (!validContinuityStatus(status, receiptAuthenticated)) return "?"
  if (status.state === "failed" || status.state === "blocked") return "!"
  if (continuityBusy(status.state)) return "↥"
  if (status.state === "unconfigured" || status.state === "recovery-only")
    return "◇"
  if (status.state === "prepared") return "◆"
  return ""
}

// ---------------------------------------------------------------- glyphs

function brainGlyph()   { return String.fromCodePoint(0xF09D1) }  // nf-md-brain
function dreamGlyph()   { return String.fromCodePoint(0xF0904) }
function chainGlyph()   { return String.fromCodePoint(0xF0208) }

function thoughtMark(kind) {
  if (kind === "integrity") return "⛓"
  if (kind === "healing")   return "✚"
  if (kind === "refusal")   return "∅"
  if (kind === "collapse")  return "≻"
  if (kind === "dream")     return "☾"
  if (kind === "anomaly")   return "σ"
  if (kind === "attention") return "◉"
  if (kind === "crash")     return "✖"
  if (kind === "ponder")    return "✦"
  if (kind === "novelty")   return "✧"
  if (kind === "surprise")  return "Δ"
  if (kind === "association") return "∞"
  if (kind === "take")      return "⊢"
  if (kind === "grade")     return "⚖"
  if (kind === "calibration") return "◎"
  if (kind === "note")      return "✉"
  if (kind === "coincidence") return "⋈"
  if (kind === "intent")    return "➤"
  if (kind === "bench")     return "≟"
  return "·"
}

// ---------------------------------------------------------------- format

function timeAgo(isoTs, nowMs) {
  if (!timestampObservedBy(isoTs, nowMs)) return ""
  var t = Date.parse(isoTs)
  var now = Number(nowMs)
  var s = Math.floor((now - t) / 1000)
  if (s < 90) return s + "s ago"
  if (s < 5400) return Math.round(s / 60) + "m ago"
  if (s < 129600) return Math.round(s / 3600) + "h ago"
  return Math.round(s / 86400) + "d ago"
}

function organLabel(slug) {
  return slug.indexOf("organs/") === 0 ? slug.substring(7) : slug
}

function shortLabel(n) {
  if (n.id === "sia/cortex") return "SIA"
  if (n.t === "organ") return organLabel(n.id)
  var p = n.id.split("/")
  return p[p.length - 1]
}

// Filter-chip compatibility key for a node kind; cortex/organ are persisted
// schema names, not biological classifications.
function kindKey(n) {
  if (n.id === "sia/cortex") return "cortex"
  if (n.t === "organ") return "organ"
  if (n.t === "event-day") return "day"
  if (n.t === "thought") return "thought"
  if (n.t === "skill") return "skill"
  // The graph also carries package, project, note, take, intent, and other
  // corpus records. Calling all of those entities made the legend claim a
  // taxonomy the snapshot does not actually provide.
  return "record"
}

// ---------------------------------------------------------------- colors

function nodeColor(n, pal) {
  return pal[kindKey(n)] || pal.record
}

// Edge types are evidence about how a corpus link was projected, not a claim
// that every NER relationship is present in this display. The canvas only
// surfaces these colors for the selected neighborhood, keeping the full map
// calm while making the inspected relation legible.
function edgeColor(kind, pal) {
  if (kind === "crashed") return pal.urgent
  if (kind === "upgraded") return pal.organ
  if (kind === "mentions") return pal.record
  return pal.thought
}

function originLabel(origin) {
  if (origin === "evidence" || origin === "derived" || origin === "model")
    return origin
  return "legacy-unlabeled"
}

function originColor(origin, pal) {
  if (origin === "evidence") return pal.organ
  if (origin === "derived") return pal.thought
  if (origin === "model") return pal.record
  return pal.urgent
}

function nodeRadius(n) {
  if (n.id === "sia/cortex") return 11
  if (n.t === "organ")   return 6 + Math.min(4, n.deg * 0.25)
  if (n.t === "thought") return 3.5
  return 2.6 + Math.min(4, n.deg * 0.35)
}

function freshness(n, nowMs) {
  if (!n || typeof n !== "object"
      || !timestampObservedBy(n.ts, nowMs)) return 0
  var t = Date.parse(n.ts)
  var now = Number(nowMs)
  var age = (now - t) / 1000
  return Math.max(0, 1 - age / 1800)   // fades over 30 min
}

// ---------------------------------------------------------------- layout

// Graph slugs are arbitrary producer-owned strings. Prefix every dictionary
// key so names such as `constructor` cannot resolve through Object.prototype.
function graphMapKey(value) { return "$" + String(value) }

var L = { pos: {}, seeded: false, replaySeed: false, phase: 0,
          minT: 0, maxT: 1, adj: {}, edgesByNode: {}, rings: [],
          targetAngle: {}, sectorWidth: {}, width: 0, height: 0 }

function resetLayout() {
  L.pos = {}; L.seeded = false; L.replaySeed = false; L.phase = 0
  L.adj = {}; L.edgesByNode = {}; L.rings = []; L.targetAngle = {}
  L.sectorWidth = {}
  L.width = 0; L.height = 0
}

function replayLayout(graph, w, h) {
  resetLayout()
  L.replaySeed = true
  syncGraph(graph, w, h)
}

function stableUnit(text) {
  var value = String(text || ""), hash = 2166136261
  for (var i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash += (hash << 1) + (hash << 4) + (hash << 7)
      + (hash << 8) + (hash << 24)
  }
  hash += hash << 13
  hash ^= hash >>> 7
  hash += hash << 3
  hash ^= hash >>> 17
  hash += hash << 5
  return (hash >>> 0) / 4294967295
}

function angleDelta(target, current) {
  var delta = target - current
  while (delta > Math.PI) delta -= 2 * Math.PI
  while (delta < -Math.PI) delta += 2 * Math.PI
  return delta
}

// radius bands as fractions of min(w,h)/2
var R_ORGAN = 0.34, R_IN = 0.52, R_OUT = 0.92

function targetRadius(n, half) {
  if (n.id === "sia/cortex") return 0
  if (n.t === "organ") return R_ORGAN * half
  return (R_IN + (R_OUT - R_IN) * (n.tsNorm || 0)) * half
}

function syncGraph(graph, w, h) {
  if (!graph || !graph.nodes) return
  var cx = w / 2, cy = h / 2, half = Math.min(w, h) / 2
  var i, n

  // Preserve a settled layout across ordinary resizes by moving it with the
  // canvas. Without this, a display/workspace change leaves yesterday's
  // pixel coordinates pulling against today's center.
  if (L.seeded && L.width > 0 && L.height > 0
      && (L.width !== w || L.height !== h)) {
    var oldCx = L.width / 2, oldCy = L.height / 2
    var oldHalf = Math.min(L.width, L.height) / 2
    var scale = oldHalf > 0 ? half / oldHalf : 1
    for (var oldId in L.pos) {
      L.pos[oldId].x = cx + (L.pos[oldId].x - oldCx) * scale
      L.pos[oldId].y = cy + (L.pos[oldId].y - oldCy) * scale
      L.pos[oldId].vx *= scale
      L.pos[oldId].vy *= scale
    }
  }
  L.width = w; L.height = h

  // Time normalization over dated non-source nodes. ``organ`` remains the
  // compatibility graph type consumed below.
  var minT = Infinity, maxT = -Infinity
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    if (n.t === "organ" || n.id === "sia/cortex") continue
    var t = Date.parse(n.ts)
    if (t > 0) { if (t < minT) minT = t; if (t > maxT) maxT = t }
  }
  if (!isFinite(minT)) { minT = Date.now() - 86400000; maxT = Date.now() }
  if (maxT - minT < 60000) minT = maxT - 60000
  L.minT = minT; L.maxT = maxT
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    if (n.t === "organ" || n.id === "sia/cortex") { n.tsNorm = 0; continue }
    var tt = Date.parse(n.ts)
    n.tsNorm = tt > 0 ? (tt - minT) / (maxT - minT) : 0
  }

  // day rings: one per UTC day boundary in range (thin to <= 8)
  L.rings = []
  var DAY = 86400000
  var firstDay = Math.ceil(minT / DAY) * DAY
  var days = []
  for (var d = firstDay; d <= maxT; d += DAY) days.push(d)
  var step = Math.max(1, Math.ceil(days.length / 8))
  for (i = 0; i < days.length; i += step) {
    var frac = (days[i] - minT) / (maxT - minT)
    L.rings.push({
      r: (R_IN + (R_OUT - R_IN) * frac) * half,
      label: new Date(days[i]).toISOString().substring(5, 10)
    })
  }

  // adjacency + per-node edge lists (for hover neighborhoods + inspector)
  L.adj = {}; L.edgesByNode = {}
  for (i = 0; i < graph.edges.length; i++) {
    var e = graph.edges[i]
    var sourceKey = graphMapKey(e.s), destinationKey = graphMapKey(e.d)
    if (!L.adj[sourceKey]) L.adj[sourceKey] = {}
    if (!L.adj[destinationKey]) L.adj[destinationKey] = {}
    L.adj[sourceKey][destinationKey] = true
    L.adj[destinationKey][sourceKey] = true
    if (!L.edgesByNode[sourceKey]) L.edgesByNode[sourceKey] = []
    if (!L.edgesByNode[destinationKey]) L.edgesByNode[destinationKey] = []
    L.edgesByNode[sourceKey].push({ other: e.d, type: e.t, why: e.why || "", out: true })
    L.edgesByNode[destinationKey].push({ other: e.s, type: e.t, why: e.why || "", out: false })
  }

  // Source sectors are deterministic and independent of snapshot order. The
  // fixed anchors prevent a high-degree branch from dragging the whole graph
  // into one side of the canvas while local forces still organize each branch.
  var organs = graph.nodes.filter(function(x) {
    return x.t === "organ" && x.id !== "sia/cortex"
  })
    .slice().sort(function(a, b) {
      return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0)
    })
  var nodeById = {}
  for (i = 0; i < graph.nodes.length; i++)
    nodeById[graphMapKey(graph.nodes[i].id)] = graph.nodes[i]

  L.targetAngle = {}; L.sectorWidth = {}
  var branchNodes = {}, unownedNodes = []
  for (i = 0; i < organs.length; i++)
    branchNodes[graphMapKey(organs[i].id)] = []
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    if (n.id === "sia/cortex" || n.t === "organ") continue
    var organNeighbors = []
    var linked = L.edgesByNode[graphMapKey(n.id)] || []
    for (var ni = 0; ni < linked.length; ni++) {
      var linkedNode = nodeById[graphMapKey(linked[ni].other)]
      if (linkedNode && linkedNode.t === "organ"
          && linkedNode.id !== "sia/cortex")
        organNeighbors.push(linkedNode.id)
    }
    organNeighbors.sort()
    if (organNeighbors.length) {
      branchNodes[graphMapKey(organNeighbors[0])].push(n)
    } else unownedNodes.push(n)
  }

  var organWeight = {}, totalWeight = 0
  for (i = 0; i < organs.length; i++) {
    var organKey = graphMapKey(organs[i].id)
    organWeight[organKey] = branchNodes[organKey].length + 1
    totalWeight += organWeight[organKey]
  }
  var sector = 2 * Math.PI / Math.max(1, organs.length)
  var sectorCursor = -Math.PI / 2
  for (i = 0; i < organs.length; i++) {
    organKey = graphMapKey(organs[i].id)
    var ownedWidth = totalWeight > 0
      ? 2 * Math.PI * organWeight[organKey] / totalWeight : sector
    L.sectorWidth[organKey] = ownedWidth
    L.targetAngle[organKey] = sectorCursor + ownedWidth / 2
    sectorCursor += ownedWidth
  }

  function stableNodeOrder(a, b) {
    var ah = stableUnit("order:" + a.id)
    var bh = stableUnit("order:" + b.id)
    if (ah !== bh) return ah - bh
    return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0)
  }

  for (i = 0; i < organs.length; i++) {
    organKey = graphMapKey(organs[i].id)
    var branch = branchNodes[organKey]
    branch.sort(stableNodeOrder)
    if (!branch.length) continue
    var branchWidth = L.sectorWidth[organKey] * 0.88
    var branchStart = L.targetAngle[organKey] - branchWidth / 2
    var branchSlot = branchWidth / branch.length
    for (var bi = 0; bi < branch.length; bi++) {
      var branchJitter = (stableUnit("jitter:" + branch[bi].id) - 0.5)
        * branchSlot * 0.30
      L.targetAngle[graphMapKey(branch[bi].id)] = branchStart
        + branchSlot * (bi + 0.5) + branchJitter
    }
  }

  unownedNodes.sort(stableNodeOrder)
  var unownedSlot = 2 * Math.PI / Math.max(1, unownedNodes.length)
  for (i = 0; i < unownedNodes.length; i++) {
    var freeJitter = (stableUnit("free:" + unownedNodes[i].id) - 0.5)
      * unownedSlot * 0.30
    L.targetAngle[graphMapKey(unownedNodes[i].id)] = -Math.PI / 2
      + unownedSlot * (i + 0.5) + freeJitter
  }

  var live = {}
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    var nodeKey = graphMapKey(n.id)
    live[nodeKey] = true
    if (L.pos[nodeKey]) continue
    var x, y
    if (n.id === "sia/cortex") { x = cx; y = cy }
    else if (n.t === "organ") {
      var ang = L.targetAngle[nodeKey]
      x = cx + Math.cos(ang) * R_ORGAN * half
      y = cy + Math.sin(ang) * R_ORGAN * half
    } else {
      // Ordinary refreshes start at the stable time/sector coordinate. A
      // deliberate replay starts beside the owning source, then moves each
      // record outward as its timestamp becomes visible.
      var a2 = L.targetAngle[nodeKey]
      var r0 = L.replaySeed
        ? (R_ORGAN * half
           + (stableUnit("radius:" + n.id) - 0.5) * 18)
        : targetRadius(n, half)
      x = cx + Math.cos(a2) * r0
      y = cy + Math.sin(a2) * r0
    }
    L.pos[nodeKey] = { x: x, y: y, vx: 0, vy: 0 }
  }
  for (var id in L.pos) if (!live[id]) delete L.pos[id]
  L.replaySeed = false
  L.seeded = true
}

function step(graph, w, h, revealT) {
  if (!graph || !graph.nodes || !L.seeded) return
  var nodes = graph.nodes, edges = graph.edges
  var cx = w / 2, cy = h / 2, half = Math.min(w, h) / 2
  var i, j, a, b, dx, dy, d2, d, f
  var K_REP = 760, K_SPRING = 0.009, REST = 44
  var K_RAD = 0.085, K_ANGLE = 0.032, K_ORGAN = 0.16, DAMP = 0.82
  var active = {}
  for (i = 0; i < nodes.length; i++)
    active[graphMapKey(nodes[i].id)] = nodes[i].id === "sia/cortex"
      || nodes[i].t === "organ" || revealT === undefined
      || (nodes[i].tsNorm || 0) <= revealT
  for (i = 0; i < nodes.length; i++) {
    if (!active[graphMapKey(nodes[i].id)]) continue
    a = L.pos[graphMapKey(nodes[i].id)]; if (!a) continue
    for (j = i + 1; j < nodes.length; j++) {
      if (!active[graphMapKey(nodes[j].id)]) continue
      b = L.pos[graphMapKey(nodes[j].id)]; if (!b) continue
      dx = a.x - b.x; dy = a.y - b.y
      d2 = dx * dx + dy * dy
      if (d2 > 26000) continue
      if (d2 < 1) {
        d2 = 1
        var nudge = stableUnit(nodes[i].id + "|" + nodes[j].id)
          * 2 * Math.PI
        dx = Math.cos(nudge); dy = Math.sin(nudge)
      }
      f = K_REP / d2
      d = Math.sqrt(d2)
      a.vx += (dx / d) * f; a.vy += (dy / d) * f
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
    }
  }
  for (i = 0; i < edges.length; i++) {
    if (!active[graphMapKey(edges[i].s)]
        || !active[graphMapKey(edges[i].d)]) continue
    a = L.pos[graphMapKey(edges[i].s)]
    b = L.pos[graphMapKey(edges[i].d)]
    if (!a || !b) continue
    dx = b.x - a.x; dy = b.y - a.y
    d = Math.sqrt(dx * dx + dy * dy) || 1
    f = K_SPRING * (d - REST)
    a.vx += (dx / d) * f; a.vy += (dy / d) * f
    b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
  }
  for (i = 0; i < nodes.length; i++) {
    var n = nodes[i]
    var activeKey = graphMapKey(n.id)
    a = L.pos[activeKey]; if (!a) continue
    if (!active[activeKey]) { a.vx = 0; a.vy = 0; continue }
    if (n.id === "sia/cortex") {
      a.x = cx; a.y = cy; a.vx = 0; a.vy = 0
      continue
    } else if (n.t === "organ") {
      var organAngle = L.targetAngle[activeKey]
      var organX = cx + Math.cos(organAngle) * R_ORGAN * half
      var organY = cy + Math.sin(organAngle) * R_ORGAN * half
      a.vx += (organX - a.x) * K_ORGAN
      a.vy += (organY - a.y) * K_ORGAN
    } else {
      // Time owns radius; semantic ownership softly owns angle. The latter is
      // a tether, not a fixed point, so repulsion and links can still arrange
      // a branch inside the source's sector.
      dx = a.x - cx; dy = a.y - cy
      var r = Math.sqrt(dx * dx + dy * dy) || 1
      var want = targetRadius(n, half)
      a.vx += (dx / r) * (want - r) * K_RAD
      a.vy += (dy / r) * (want - r) * K_RAD
      var turn = angleDelta(L.targetAngle[activeKey], Math.atan2(dy, dx))
        * r * K_ANGLE
      a.vx += (-dy / r) * turn
      a.vy += (dx / r) * turn
    }
    a.vx *= DAMP; a.vy *= DAMP
    var vm = Math.sqrt(a.vx * a.vx + a.vy * a.vy)
    if (vm > 6) { a.vx *= 6 / vm; a.vy *= 6 / vm }
    a.x += a.vx; a.y += a.vy
    var m = Math.max(12, nodeRadius(n) + 6)
    if (a.x < m) a.x = m; if (a.x > w - m) a.x = w - m
    if (a.y < m) a.y = m; if (a.y > h - m) a.y = h - m
  }
  L.phase += 0.03
}

// Candidate label centers, ordered from the node's outward radial side to
// progressively quieter fallbacks. The painter performs collision tests
// against nodes, earlier labels, and the graph card's UI margins.
function labelCandidates(x, y, cx, cy, nodeR, labelW, labelH) {
  var dx = x - cx, dy = y - cy
  var distance = Math.sqrt(dx * dx + dy * dy)
  var ux = distance > 0 ? dx / distance : 0
  var uy = distance > 0 ? dy / distance : -1
  var tx = -uy, ty = ux
  var radial = nodeR + labelH * 0.5 + 7
  var diagonal = labelW * 0.30 + nodeR + 5
  var side = labelW * 0.5 + nodeR + 7
  return [
    { x: x + ux * radial, y: y + uy * radial },
    { x: x + ux * radial + tx * diagonal,
      y: y + uy * radial + ty * diagonal },
    { x: x + ux * radial - tx * diagonal,
      y: y + uy * radial - ty * diagonal },
    { x: x + tx * side, y: y + ty * side },
    { x: x - tx * side, y: y - ty * side },
    { x: x - ux * radial, y: y - uy * radial },
    { x: x, y: y - nodeR - labelH * 0.5 - 6 },
    { x: x, y: y + nodeR + labelH * 0.5 + 6 }
  ]
}

function posOf(id)   { return L.pos[graphMapKey(id)] }
function phase()     { return L.phase }
function rings()     { return L.rings }
function neighbors(id) { return L.adj[graphMapKey(id)] || {} }
function hasNeighbor(neighborsMap, id) {
  return !!neighborsMap && neighborsMap[graphMapKey(id)] === true
}
function nodeEdges(id) { return L.edgesByNode[graphMapKey(id)] || [] }

function slugLabel(slug) {
  if (slug === "sia/cortex") return "SIA"
  if (slug.indexOf("organs/") === 0) return slug.substring(7)
  var p = slug.split("/")
  if (p[0] === "events" && p.length > 2)
    return p[1] + " · " + p[2]          // source · date, not a bare date
  if (p[0] === "epochs" && p.length > 2)
    return p[1] + " · " + p[2]
  return p[p.length - 1]
}
