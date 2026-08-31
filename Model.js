// SIA Model — pure logic for the Omarchy Brain panel.
// Pixels only: everything shown is read from the brainstem's snapshots
// (~/.local/state/sia/*.json); the brain itself lives in gbrain + the
// signed corpus. Nothing here is evidence.
//
// Layout philosophy (after the Hermes Star Map): time is radial — the
// cortex sits at the center, the organs on a fixed inner ring, and every
// memory at a radius set by its age: older toward the center, newest at
// the rim. Faint day rings mark the time bands. The force simulation
// only handles angular spacing; timestamps own the radius.
.pragma library

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
  return "entity"
}

// ---------------------------------------------------------------- colors

function nodeColor(n, pal) {
  return pal[kindKey(n)] || pal.entity
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

var L = { pos: {}, seeded: false, phase: 0,
          minT: 0, maxT: 1, adj: {}, edgesByNode: {}, rings: [] }

function resetLayout() {
  L.pos = {}; L.seeded = false; L.adj = {}; L.edgesByNode = {}; L.rings = []
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

  // organ index for stable ring placement
  var organs = graph.nodes.filter(function(x) { return x.t === "organ" })
  var organIndex = {}
  for (i = 0; i < organs.length; i++) organIndex[organs[i].id] = i

  var live = {}
  for (i = 0; i < graph.nodes.length; i++) {
    n = graph.nodes[i]
    live[n.id] = true
    if (L.pos[n.id]) continue
    var x, y
    if (n.id === "sia/cortex") { x = cx; y = cy }
    else if (n.t === "organ") {
      var k = organIndex[n.id] || 0
      var ang = (2 * Math.PI * k) / Math.max(1, organs.length) - Math.PI / 2
      x = cx + Math.cos(ang) * R_ORGAN * half
      y = cy + Math.sin(ang) * R_ORGAN * half
    } else {
      // spawn at the node's own time-radius, near a neighbor's angle
      var nb = L.edgesByNode[n.id]
      var a2 = Math.random() * 2 * Math.PI
      if (nb && nb.length && L.pos[nb[0].other]) {
        var p0 = L.pos[nb[0].other]
        a2 = Math.atan2(p0.y - cy, p0.x - cx) + (Math.random() - 0.5) * 0.9
      }
      var r0 = targetRadius(n, half)
      x = cx + Math.cos(a2) * r0
      y = cy + Math.sin(a2) * r0
    }
    L.pos[n.id] = { x: x, y: y, vx: 0, vy: 0 }
  }
  for (var id in L.pos) if (!live[id]) delete L.pos[id]
  L.seeded = true
}

function step(graph, w, h) {
  if (!graph || !graph.nodes || !L.seeded) return
  var nodes = graph.nodes, edges = graph.edges
  var cx = w / 2, cy = h / 2, half = Math.min(w, h) / 2
  var i, j, a, b, dx, dy, d2, d, f
  var K_REP = 700, K_SPRING = 0.012, REST = 40, K_RAD = 0.09, DAMP = 0.80
  for (i = 0; i < nodes.length; i++) {
    a = L.pos[nodes[i].id]; if (!a) continue
    for (j = i + 1; j < nodes.length; j++) {
      b = L.pos[nodes[j].id]; if (!b) continue
      dx = a.x - b.x; dy = a.y - b.y
      d2 = dx * dx + dy * dy
      if (d2 > 26000) continue
      if (d2 < 1) { d2 = 1; dx = Math.random() - 0.5; dy = Math.random() - 0.5 }
      f = K_REP / d2
      d = Math.sqrt(d2)
      a.vx += (dx / d) * f; a.vy += (dy / d) * f
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
    }
  }
  for (i = 0; i < edges.length; i++) {
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
    if (n.id === "sia/cortex") {
      a.vx += (cx - a.x) * 0.3; a.vy += (cy - a.y) * 0.3
    } else {
      // time owns the radius: spring toward the node's temporal ring
      dx = a.x - cx; dy = a.y - cy
      var r = Math.sqrt(dx * dx + dy * dy) || 1
      var want = targetRadius(n, half)
      var k = n.t === "organ" ? K_RAD * 3.5 : K_RAD
      a.vx += (dx / r) * (want - r) * k
      a.vy += (dy / r) * (want - r) * k
    }
    a.vx *= DAMP; a.vy *= DAMP
    var vm = Math.sqrt(a.vx * a.vx + a.vy * a.vy)
    if (vm > 6) { a.vx *= 6 / vm; a.vy *= 6 / vm }
    a.x += a.vx; a.y += a.vy
    var m = 8
    if (a.x < m) a.x = m; if (a.x > w - m) a.x = w - m
    if (a.y < m) a.y = m; if (a.y > h - m) a.y = h - m
  }
  L.phase += 0.03
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
