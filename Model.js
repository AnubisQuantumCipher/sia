// SIA Model — pure logic for the Omarchy Brain panel.
// Pixels only: everything shown is read from the brainstem's snapshots
// (~/.local/state/sia/*.json); the brain itself lives in gbrain + the
// signed corpus. Nothing here is evidence.
//
// Layout philosophy (after the Hermes Star Map): time is radial — the
// cortex sits at the center, organs hold stable semantic sectors on the
// inner ring, and memories bloom through those sectors at a radius set by
// age. Faint day rings mark the time bands. The force simulation gives the
// branches room to breathe without allowing the whole mind to collapse into
// one edge of the canvas.
.pragma library

function releaseVersion() { return "1.7.6" }

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
}

// Status snapshots published before release stamping still have a narrow,
// distinctive schema.  Recognize that real legacy shape for upgrade routing;
// a generic versionless object remains a repair condition.
function residentStatusShape(status) {
  if (!status || typeof status !== "object" || Array.isArray(status)
      || status.v !== 1 || typeof status.ts !== "string"
      || typeof status.state !== "string"
      || typeof status.publication_id !== "string"
      || !status.projection_debt
      || typeof status.projection_debt !== "object"
      || Array.isArray(status.projection_debt)
      || typeof status.projection_debt.graph !== "string"
      || typeof status.projection_debt.consolidation !== "string"
      || !status.mind || typeof status.mind !== "object"
      || Array.isArray(status.mind)
      || !status.agent_queue || typeof status.agent_queue !== "object"
      || Array.isArray(status.agent_queue)) return false
  var mindFields = ["nodes", "edges", "decay_active", "decay_demoted",
                    "rehearsal_eligible", "rehearsal_due", "pinned"]
  var relayFields = ["materialized", "refused", "acknowledged"]
  for (var i = 0; i < mindFields.length; i++)
    if (!nonNegativeInteger(status.mind[mindFields[i]])) return false
  for (var j = 0; j < relayFields.length; j++)
    if (!nonNegativeInteger(status.agent_queue[relayFields[j]])) return false
  return true
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

function installCompletionReady(completion, pluginVersion) {
  return !!completion && typeof completion === "object"
    && completion.v === 1 && completion.state === "ready"
    && completion.version === pluginVersion
}

function installCompletionInstalling(completion, pluginVersion) {
  return !!completion && typeof completion === "object"
    && completion.v === 1 && completion.state === "installing"
    && completion.version === pluginVersion
}

function validInstallCompletion(completion) {
  return !!completion && typeof completion === "object"
    && completion.v === 1
    && (completion.state === "installing" || completion.state === "ready")
    && releaseVersionParts(completion.version) !== null
}

// File resolution is handled by the QML surfaces.  Once both reads have
// resolved, this combines the resident status and the separate, release-bound
// completion record.  Existing completion state plus a missing status is a
// repair condition, never a claim that no brain exists.
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

function setupTerminalPresented(marker, requestedAtSec, requestedAttempt) {
  if (!marker || typeof marker !== "object" || marker.v !== 1) return false
  if (typeof requestedAttempt !== "string"
      || !/^[0-9a-f]{32}$/.test(requestedAttempt)) return false
  if (marker.attempt !== requestedAttempt) return false
  // The run stage records whether it actually got a terminal, and holds the
  // window only when it did.  A marker that says otherwise is evidence
  // against presentation, never for it.
  if (marker.tty !== true) return false
  if (typeof marker.ts !== "number") return false
  var stamp = marker.ts
  var requested = Number(requestedAtSec)
  if (!isFinite(stamp) || Math.floor(stamp) !== stamp) return false
  if (!isFinite(requested) || requested <= 0) return false
  return stamp >= Math.floor(requested)
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

function isPlainRecord(value) {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function optionalString(value) {
  return value === undefined || value === null || typeof value === "string"
}

function validContinuityLatest(value) {
  if (value === undefined || value === null) return true
  return isPlainRecord(value)
    && typeof value.snapshot_id === "string"
    && typeof value.created_at === "string"
    && typeof value.verified === "boolean"
    && typeof value.readiness === "string"
    && typeof value.profile === "string"
    && typeof value.identity_matches === "boolean"
}

function continuityLatestReady(value) {
  return isPlainRecord(value)
    && value.snapshot_id !== ""
    && value.created_at !== ""
    && value.profile !== ""
    && value.verified === true
    && value.readiness === "ready"
    && value.identity_matches === true
}

function validContinuityPrepared(value) {
  if (value === undefined || value === null) return true
  return isPlainRecord(value)
    && typeof value.prepared_id === "string"
    && typeof value.snapshot_id === "string"
    && typeof value.created_at === "string"
    && typeof value.readiness === "string"
    && typeof value.profile === "string"
    && typeof value.ledger_head === "string"
    && typeof value.identity_matches === "boolean"
}

function validContinuityOperation(value) {
  if (value === undefined || value === null) return true
  return isPlainRecord(value)
    && typeof value.request_id === "string" && value.request_id !== ""
    && typeof value.kind === "string" && value.kind !== ""
    && typeof value.prepared_id === "string"
    && typeof value.phase === "string"
    && CONTINUITY_OPERATION_PHASES.indexOf(value.phase) !== -1
    && typeof value.ready === "boolean"
    && typeof value.sia_ledger_verified === "boolean"
    && (value.kind !== "restore-apply" || value.prepared_id !== "")
}

function validContinuityScheduleTimestamp(value, nullable) {
  if (nullable && value === null) return true
  if (typeof value !== "string"
      || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value))
    return false
  var parsed = Date.parse(value)
  return parsed > 0
    && new Date(parsed).toISOString().replace(".000Z", "Z") === value
}

function validContinuityScheduleTimer(value, cadence) {
  return isPlainRecord(value)
    && value.cadence === cadence
    && typeof value.enabled === "boolean"
    && typeof value.active === "boolean"
    && typeof value.persistent === "boolean"
    && typeof value.wake_system === "boolean"
    && validContinuityScheduleTimestamp(value.last_trigger_at, true)
    && validContinuityScheduleTimestamp(value.next_trigger_at, true)
}

function validContinuitySchedule(value) {
  if (!isPlainRecord(value)
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

function validContinuityStatus(value) {
  return isPlainRecord(value)
    && value.schema_version === 2
    && typeof value.state === "string"
    && CONTINUITY_STATES.indexOf(value.state) !== -1
    && optionalString(value.detail)
    && optionalString(value.repository_display)
    && validContinuityLatest(value.latest)
    && validContinuityPrepared(value.prepared)
    && validContinuityOperation(value.operation)
    && (value.state !== "verified" || continuityLatestReady(value.latest))
    && (value.state !== "prepared"
        || (isPlainRecord(value.prepared)
            && value.prepared.prepared_id !== ""
            && value.prepared.snapshot_id !== ""
            && value.prepared.ledger_head !== ""))
    && (value.state !== "restoring"
        || (isPlainRecord(value.operation)
            && (value.operation.kind === "restore-apply"
                || value.operation.kind === "restore-recover")
            && (value.operation.phase === "accepted"
                || value.operation.phase === "running")))
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

function continuityCanBackUp(status) {
  if (!validContinuityStatus(status)) return false
  return ["verified", "recovery-only", "failed", "blocked"]
    .indexOf(status.state) !== -1
}

function continuityCanCheck(status) {
  return continuityCanBackUp(status)
}

function continuityCanPrepare(status) {
  if (!validContinuityStatus(status) || continuityBusy(status.state))
    return false
  var latest = status.latest
  return isPlainRecord(latest) && latest.verified === true
    && latest.snapshot_id !== ""
}

function continuityCanApply(status) {
  if (!validContinuityStatus(status) || status.state !== "prepared")
    return false
  var prepared = status.prepared
  return isPlainRecord(prepared) && prepared.prepared_id !== ""
    && prepared.snapshot_id !== "" && prepared.ledger_head !== ""
}

function continuityBarMark(status) {
  if (!validContinuityStatus(status)) return "?"
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
  var t = Date.parse(isoTs)
  if (!(t > 0)) return ""
  var s = Math.max(0, Math.floor((nowMs - t) / 1000))
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

// filter-chip key for a node kind
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
  var t = Date.parse(n.ts)
  if (!(t > 0)) return 0
  var age = (nowMs - t) / 1000
  if (age < 0) age = 0
  return Math.max(0, 1 - age / 1800)   // fades over 30 min
}

// ---------------------------------------------------------------- layout

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

  // time normalization over dated non-organ nodes
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
    if (!L.adj[e.s]) L.adj[e.s] = {}
    if (!L.adj[e.d]) L.adj[e.d] = {}
    L.adj[e.s][e.d] = true
    L.adj[e.d][e.s] = true
    if (!L.edgesByNode[e.s]) L.edgesByNode[e.s] = []
    if (!L.edgesByNode[e.d]) L.edgesByNode[e.d] = []
    L.edgesByNode[e.s].push({ other: e.d, type: e.t, why: e.why || "", out: true })
    L.edgesByNode[e.d].push({ other: e.s, type: e.t, why: e.why || "", out: false })
  }

  // Organ sectors are deterministic and independent of snapshot order. The
  // fixed anchors prevent a high-degree branch from dragging the whole mind
  // into one hemisphere while the local forces still organize each branch.
  var organs = graph.nodes.filter(function(x) {
    return x.t === "organ" && x.id !== "sia/cortex"
  })
    .slice().sort(function(a, b) {
      return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0)
    })
  var nodeById = {}
  for (i = 0; i < graph.nodes.length; i++)
    nodeById[graph.nodes[i].id] = graph.nodes[i]

  L.targetAngle = {}; L.sectorWidth = {}
  var branchNodes = {}, unownedNodes = []
  for (i = 0; i < organs.length; i++) branchNodes[organs[i].id] = []
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    if (n.id === "sia/cortex" || n.t === "organ") continue
    var organNeighbors = []
    var linked = L.edgesByNode[n.id] || []
    for (var ni = 0; ni < linked.length; ni++) {
      var linkedNode = nodeById[linked[ni].other]
      if (linkedNode && linkedNode.t === "organ"
          && linkedNode.id !== "sia/cortex")
        organNeighbors.push(linkedNode.id)
    }
    organNeighbors.sort()
    if (organNeighbors.length) {
      branchNodes[organNeighbors[0]].push(n)
    } else unownedNodes.push(n)
  }

  var organWeight = {}, totalWeight = 0
  for (i = 0; i < organs.length; i++) {
    organWeight[organs[i].id] = branchNodes[organs[i].id].length + 1
    totalWeight += organWeight[organs[i].id]
  }
  var sector = 2 * Math.PI / Math.max(1, organs.length)
  var sectorCursor = -Math.PI / 2
  for (i = 0; i < organs.length; i++) {
    var ownedWidth = totalWeight > 0
      ? 2 * Math.PI * organWeight[organs[i].id] / totalWeight : sector
    L.sectorWidth[organs[i].id] = ownedWidth
    L.targetAngle[organs[i].id] = sectorCursor + ownedWidth / 2
    sectorCursor += ownedWidth
  }

  function stableNodeOrder(a, b) {
    var ah = stableUnit("order:" + a.id)
    var bh = stableUnit("order:" + b.id)
    if (ah !== bh) return ah - bh
    return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0)
  }

  for (i = 0; i < organs.length; i++) {
    var branch = branchNodes[organs[i].id]
    branch.sort(stableNodeOrder)
    if (!branch.length) continue
    var branchWidth = L.sectorWidth[organs[i].id] * 0.88
    var branchStart = L.targetAngle[organs[i].id] - branchWidth / 2
    var branchSlot = branchWidth / branch.length
    for (var bi = 0; bi < branch.length; bi++) {
      var branchJitter = (stableUnit("jitter:" + branch[bi].id) - 0.5)
        * branchSlot * 0.30
      L.targetAngle[branch[bi].id] = branchStart
        + branchSlot * (bi + 0.5) + branchJitter
    }
  }

  unownedNodes.sort(stableNodeOrder)
  var unownedSlot = 2 * Math.PI / Math.max(1, unownedNodes.length)
  for (i = 0; i < unownedNodes.length; i++) {
    var freeJitter = (stableUnit("free:" + unownedNodes[i].id) - 0.5)
      * unownedSlot * 0.30
    L.targetAngle[unownedNodes[i].id] = -Math.PI / 2
      + unownedSlot * (i + 0.5) + freeJitter
  }

  var live = {}
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    live[n.id] = true
    if (L.pos[n.id]) continue
    var x, y
    if (n.id === "sia/cortex") { x = cx; y = cy }
    else if (n.t === "organ") {
      var ang = L.targetAngle[n.id]
      x = cx + Math.cos(ang) * R_ORGAN * half
      y = cy + Math.sin(ang) * R_ORGAN * half
    } else {
      // Ordinary refreshes start at the stable time/sector coordinate. A
      // deliberate replay starts beside the owning organ, then blooms each
      // memory outward as its timestamp becomes visible.
      var a2 = L.targetAngle[n.id]
      var r0 = L.replaySeed
        ? (R_ORGAN * half
           + (stableUnit("radius:" + n.id) - 0.5) * 18)
        : targetRadius(n, half)
      x = cx + Math.cos(a2) * r0
      y = cy + Math.sin(a2) * r0
    }
    L.pos[n.id] = { x: x, y: y, vx: 0, vy: 0 }
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
    active[nodes[i].id] = nodes[i].id === "sia/cortex"
      || nodes[i].t === "organ" || revealT === undefined
      || (nodes[i].tsNorm || 0) <= revealT
  for (i = 0; i < nodes.length; i++) {
    if (!active[nodes[i].id]) continue
    a = L.pos[nodes[i].id]; if (!a) continue
    for (j = i + 1; j < nodes.length; j++) {
      if (!active[nodes[j].id]) continue
      b = L.pos[nodes[j].id]; if (!b) continue
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
    if (!active[edges[i].s] || !active[edges[i].d]) continue
    a = L.pos[edges[i].s]; b = L.pos[edges[i].d]
    if (!a || !b) continue
    dx = b.x - a.x; dy = b.y - a.y
    d = Math.sqrt(dx * dx + dy * dy) || 1
    f = K_SPRING * (d - REST)
    a.vx += (dx / d) * f; a.vy += (dy / d) * f
    b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
  }
  for (i = 0; i < nodes.length; i++) {
    var n = nodes[i]
    a = L.pos[n.id]; if (!a) continue
    if (!active[n.id]) { a.vx = 0; a.vy = 0; continue }
    if (n.id === "sia/cortex") {
      a.x = cx; a.y = cy; a.vx = 0; a.vy = 0
      continue
    } else if (n.t === "organ") {
      var organAngle = L.targetAngle[n.id]
      var organX = cx + Math.cos(organAngle) * R_ORGAN * half
      var organY = cy + Math.sin(organAngle) * R_ORGAN * half
      a.vx += (organX - a.x) * K_ORGAN
      a.vy += (organY - a.y) * K_ORGAN
    } else {
      // Time owns radius; semantic ownership softly owns angle. The latter is
      // a tether, not a fixed point, so repulsion and links can still produce
      // a living, self-organizing branch inside the organ's sector.
      dx = a.x - cx; dy = a.y - cy
      var r = Math.sqrt(dx * dx + dy * dy) || 1
      var want = targetRadius(n, half)
      a.vx += (dx / r) * (want - r) * K_RAD
      a.vy += (dy / r) * (want - r) * K_RAD
      var turn = angleDelta(L.targetAngle[n.id], Math.atan2(dy, dx))
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

function posOf(id)   { return L.pos[id] }
function phase()     { return L.phase }
function rings()     { return L.rings }
function neighbors(id) { return L.adj[id] || {} }
function nodeEdges(id) { return L.edgesByNode[id] || [] }

function slugLabel(slug) {
  if (slug === "sia/cortex") return "SIA"
  if (slug.indexOf("organs/") === 0) return slug.substring(7)
  var p = slug.split("/")
  if (p[0] === "events" && p.length > 2)
    return p[1] + " · " + p[2]          // organ · date, not a bare date
  if (p[0] === "epochs" && p.length > 2)
    return p[1] + " · " + p[2]
  return p[p.length - 1]
}
