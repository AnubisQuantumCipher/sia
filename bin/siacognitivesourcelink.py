"""Pure, additive selection of completely witnessed signed source-link joins.

This is not selection-v2, a baseline input, an inference engine, or a metric.
It reads no paths and invokes no keeper or retrieval worker. The caller pins
the capture and policy; native capture admission establishes internal bindings,
not independent authentication of those caller-supplied expectations.
"""

import copy
import hashlib
import json
import re

import siacognitivehistory as history
import siavectoradmit as adapter
import siavectorprepare as preparer


SCHEMA = "sia-cognitive-source-link-selection-v1"
POLICY_SCHEMA = "sia-cognitive-source-link-policy-v1"
MAX_CAPTURE_BYTES = history.MAX_CAPTURE_BYTES
MAX_POLICY_BYTES = preparer.MAX_RECEIPT_BYTES
MAX_SELECTION_BYTES = history.MAX_CAPTURE_BYTES
MAX_EVENTS = history.sialib.MAX_SOURCE_REPLAY_EVENTS
NON_CLAIMS = (
    "Source-link join is an engineering retrieval task, not demonstrated associative cognition or a causal relationship.",
    "Native signed subjects and deterministic SIA-generated links are different provenance layers; shared links do not establish entity equivalence.",
    "Only the declared SEKHMET arg1 projection is supported; unsupported sources and rows do not establish absent relationships.",
    "The complete captured signed population is not the entire machine history or corpus.",
    "Dependency components prevent shared declared subjects, bridges, occurrences, and source pages across query splits for this capture; authentication anchors remain shared.",
    "This is not a temporal holdout, and later captures may merge dependency components and change assignments.",
    "The seed event ID is a disclosed public cue bound to this capture, not an independently content-authenticating identifier.",
    "Unavailable witnesses are declared; a retained subset is never substituted for a complete counterpart target set.",
    "Page origins remain controlling; generated links and signed-row matches do not promote model or legacy-unlabeled pages to evidence.",
    "This schema is not a drop-in selection-v2, baseline, or measurement input; an independently tested adapter is required.",
    "No retrieval worker, metric, tuned parameters, statistical power, cognitive improvement, or real-source availability is established.",
    "Capture and policy hashes bind represented bytes; external authentication remains the caller's obligation.",
)
_RELATION_RULES = {
    "projection": "sekhmet-native-arg1-unit-link-v1",
    "native_subject": "exact-chain-arg1-v1",
    "link_provenance": "deterministic-signed-row-projection-v1",
    "collision": "refuse-distinct-native-subjects-sharing-bridge-v1",
    "unsupported": "declare-source-and-row-roster-v1",
}
_QUERY_RULES = {
    "template": "seed-event-id-counterpart-action-v1",
    "targets": "all-complete-exact-subject-counterpart-occurrences-v1",
    "actions": "different-from-seed-native-action-v1",
    "witnesses": "exact-native-line-and-generated-link-v1",
    "origin": "evidence-only-support-v1",
    "page_relation": "every-seed-target-page-distinct-v1",
    "shortcuts": "exclude-whole-query-v1",
}
_OUTPUT_KEYS = {
    "schema", "capture_sha256", "policy_sha256", "pages", "pages_sha256",
    "event_population", "source_coverage", "relations", "dependency_groups",
    "queries", "answer_key", "exclusions", "source_non_claims", "non_claims",
    "selection_sha256",
}
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ESCAPED = re.compile(r'[\x00-\x1f"\\]')
_MISSING = object()


class SourceLinkRefusal(ValueError):
    """The complete source-link construction or its replay was not admitted."""


def _fail(reason):
    raise SourceLinkRefusal("source-link selection refused: " + reason)


def _keys(value, names, label):
    if type(value) is not dict or len(value) != len(names) or set(value) != set(names):
        _fail(label + " fields are invalid")


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _measure(value, maximum):
    """Bound the whole graph and its exact canonical JSON bytes without encoding.

    Strings use UTF-8 and JSON's scalar escapes; unsupported floats, exotic
    containers, cycles and excessive nesting refuse before copy/hash/serialize.
    Shared references are charged at every represented occurrence.
    """
    used = 0
    active = set()

    def take(size):
        nonlocal used
        if size > maximum - used:
            _fail("JSON representation exceeds its byte ceiling")
        used += size

    def visit(item, depth):
        if depth > 64:
            _fail("JSON nesting exceeds its ceiling")
        kind = type(item)
        if kind is str:
            if len(item) > maximum - used:
                _fail("JSON text exceeds its byte ceiling")
            take(len(item.encode("utf-8", "strict")) + 2)
            for match in _ESCAPED.finditer(item):
                take(1 if match.group() in ('"', "\\", "\b", "\f", "\n", "\r", "\t") else 5)
        elif kind is int:
            if not -adapter.MAX_SAFE_INTEGER <= item <= adapter.MAX_SAFE_INTEGER:
                _fail("JSON integer exceeds its exact range")
            take(len(str(item)))
        elif kind is bool:
            take(4 if item else 5)
        elif item is None:
            take(4)
        elif kind in (dict, list):
            if id(item) in active or len(item) > maximum - used:
                _fail("JSON container is cyclic or excessive")
            take(2)
            active.add(id(item))
            try:
                first = True
                if kind is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            _fail("JSON object key is not text")
                        if not first:
                            take(1)
                        first = False
                        visit(key, depth + 1)
                        take(1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        if not first:
                            take(1)
                        first = False
                        visit(child, depth + 1)
            finally:
                active.remove(id(item))
        else:
            _fail("value is not bounded canonical JSON")

    visit(value, 0)
    return used


def _canonical(value, maximum=MAX_SELECTION_BYTES):
    expected = _measure(value, maximum)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) != expected:
        _fail("JSON encoding disagrees with its admitted size")
    return raw


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(domain, *parts):
    return _sha(_canonical([domain, *parts]))


class _OutputBudget:
    """Reserve each complete list element before attaching/copying/hashing it."""

    def __init__(self, output, maximum):
        self.maximum = maximum
        self.used = _measure(output, maximum)

    def reserve(self, rows, value):
        separator = 1 if rows else 0
        size = _measure(value, self.maximum - self.used - separator)
        self.used += size + separator

    def append(self, rows, value):
        self.reserve(rows, value)
        rows.append(value)


class _WorkBudget:
    """Bound auxiliary native/dependency representations before retaining them."""

    def __init__(self, maximum):
        self.maximum = maximum
        self.used = 0

    def reserve(self, value):
        self.used += _measure(value, self.maximum - self.used)


def _policy(value):
    _keys(value, {"schema", "seed", "population", "relations", "split",
                  "queries", "pages", "protocol", "resources", "require_queries"}, "policy")
    if value["schema"] != POLICY_SCHEMA \
            or value["population"] != "complete-captured-signed-rows-v1" \
            or type(value["seed"]) is not str or not value["seed"] \
            or len(value["seed"].encode("utf-8")) > 1024 \
            or type(value["require_queries"]) is not bool:
        _fail("policy identity, seed, population, or requirement is invalid")
    for key, rules in (("relations", _RELATION_RULES), ("queries", _QUERY_RULES)):
        _keys(value[key], rules, key)
        if any(type(value[key][name]) is not str or value[key][name] != rule
               for name, rule in rules.items()):
            _fail(key + " changes a frozen rule")
    split = value["split"]
    _keys(split, {"kind", "dependencies", "calibration_modulus", "calibration_residue"}, "split")
    if split["kind"] != "dependency-components-before-eligibility-v1" \
            or split["dependencies"] != "bridge-chain-arg1-native-source-page-v1" \
            or not _integer(split["calibration_modulus"], 2, adapter.MAX_QUERIES) \
            or not _integer(split["calibration_residue"], 0, split["calibration_modulus"] - 1):
        _fail("dependency split policy is invalid")
    pages = value["pages"]
    _keys(pages, {"order", "title", "max_pages", "max_page_bytes",
                  "max_total_page_bytes", "max_chunks"}, "pages")
    if pages["order"] != "seeded-slug-sha256-v1" or pages["title"] != "slug-v1":
        _fail("page ordering or title rule is invalid")
    for name, hard in (("max_pages", preparer.MAX_PAGES),
                       ("max_page_bytes", preparer.MAX_PAGE_BYTES),
                       ("max_total_page_bytes", preparer.MAX_TOTAL_PAGE_BYTES),
                       ("max_chunks", preparer.MAX_CHUNKS)):
        if not _integer(pages[name], 1, hard):
            _fail("page ceiling is invalid: " + name)
    protocol = value["protocol"]
    _keys(protocol, {"chunking", "max_chunk_bytes", "page_pooling", "max_query_bytes"}, "protocol")
    if protocol["chunking"] != preparer.POLICY["chunking"] \
            or protocol["page_pooling"] != "single-chunk-per-slug" \
            or not _integer(protocol["max_chunk_bytes"], preparer.MAX_CHUNK_BYTES, preparer.MAX_CHUNK_BYTES) \
            or not _integer(protocol["max_query_bytes"], adapter.MAX_QUERY_BYTES, adapter.MAX_QUERY_BYTES):
        _fail("chunk/query protocol differs from the frozen source contract")
    resources = value["resources"]
    _keys(resources, {"max_capture_bytes", "max_policy_bytes", "max_selection_bytes",
                      "max_events", "max_relations", "max_dependency_groups", "max_queries",
                      "overflow"}, "resources")
    for name, hard in (("max_capture_bytes", MAX_CAPTURE_BYTES),
                       ("max_policy_bytes", MAX_POLICY_BYTES),
                       ("max_selection_bytes", MAX_SELECTION_BYTES),
                       ("max_events", MAX_EVENTS), ("max_relations", MAX_EVENTS),
                       ("max_dependency_groups", MAX_EVENTS), ("max_queries", adapter.MAX_QUERIES)):
        if not _integer(resources[name], 1, hard):
            _fail("resource ceiling is invalid: " + name)
    if resources["overflow"] != "refuse-complete-request-v1":
        _fail("resource overflow rule is invalid")


def _base(capture, capture_pin, policy_pin):
    return {
        "schema": SCHEMA, "capture_sha256": capture_pin, "policy_sha256": policy_pin,
        "pages": [], "pages_sha256": "0" * 64,
        "event_population": capture["events"], "source_coverage": [], "relations": [],
        "dependency_groups": [], "queries": [], "answer_key": [], "exclusions": [],
        "source_non_claims": {"capture": capture["non_claims"], "source": capture["source_non_claims"]},
        "non_claims": list(NON_CLAIMS), "selection_sha256": "0" * 64,
    }


def _inputs(capture, expected_capture_sha256, policy, expected_policy_sha256,
            selection=_MISSING):
    # Complete structure/byte admission for every supplied artifact precedes
    # any canonical encoding, hashing, history admission, or detached copy.
    _measure(policy, MAX_POLICY_BYTES)
    _policy(policy)
    resources = policy["resources"]
    _measure(policy, resources["max_policy_bytes"])
    _measure(capture, resources["max_capture_bytes"])
    if selection is not _MISSING:
        _measure(selection, resources["max_selection_bytes"])
        _keys(selection, _OUTPUT_KEYS, "selection")
    if not _digest(expected_capture_sha256) or not _digest(expected_policy_sha256):
        _fail("external capture and policy pins are required")
    if type(capture) is not dict or capture.get("capture_sha256") != expected_capture_sha256:
        _fail("external capture pin mismatch")
    if type(capture.get("events")) is not list or len(capture["events"]) > resources["max_events"]:
        _fail("complete native event population exceeds its ceiling")
    pages = capture.get("pages")
    if type(pages) is not list or len(pages) > policy["pages"]["max_pages"]:
        _fail("complete page population exceeds its ceiling")
    total = 0
    for page in pages:
        if type(page) is not dict or type(page.get("text")) is not str:
            _fail("source page is malformed")
        size = len(page["text"].encode("utf-8"))
        if size > policy["pages"]["max_page_bytes"]:
            _fail("complete source page exceeds its ceiling")
        total += size
        if total > policy["pages"]["max_total_page_bytes"]:
            _fail("complete source page bytes exceed their ceiling")
    # Mandatory retained provenance alone must fit before history copies it.
    _measure(_base(capture, expected_capture_sha256, expected_policy_sha256),
             resources["max_selection_bytes"])
    if _sha(_canonical(policy, resources["max_policy_bytes"])) != expected_policy_sha256:
        _fail("external policy pin mismatch")
    admitted = history.admit_capture(capture)
    return admitted, copy.deepcopy(policy)


def _page_records(capture, policy, output, budget):
    # Count and raw byte limits were admitted before copying the capture.
    ordered = sorted(capture["pages"], key=lambda page: (
        _identity("sia-cognitive-page-order-v1", policy["seed"], page["slug"]), page["slug"]))
    originals, chunks = {}, {}
    chunk_count = 0
    for page in ordered:
        row = {"slug": page["slug"], "title": page["slug"], "type": page["type"],
               "origin": page["origin"], "text": page["text"], "text_sha256": page["sha256"]}
        budget.append(output["pages"], row)
        originals[page["slug"]] = page
        pieces = []
        for piece in preparer._chunk_bytes(page["text"]):
            if chunk_count >= policy["pages"]["max_chunks"]:
                _fail("complete page chunk population exceeds its ceiling")
            pieces.append(piece)
            chunk_count += 1
        chunks[page["slug"]] = pieces
    output["pages_sha256"] = _sha(_canonical(output["pages"], budget.maximum))
    return originals, chunks


def _native_population(capture, policy, output, budget, work):
    entries = []
    coverage = {chain["chain"]: {"chain": chain["chain"], "status": None,
                                 "reason": None, "supported_sequences": [],
                                 "unsupported_sequences": []}
                for chain in capture["chains"]}
    bridge_subjects = {}
    for event in sorted(capture["events"], key=lambda item: (item["chain"], int(item["seq"]))):
        row, chain = event["row"], event["chain"]
        if row[2].startswith("GENESIS:") or row[2] == "genesis":
            continue
        reason = None
        if chain != "sekhmet":
            reason = "unsupported-native-link-projection"
        elif not row[3] or row[3] in ("sekhmet", "-"):
            reason = "unsupported-native-subject-field"
        else:
            # A native row remains in the population even if its captured
            # projection/witness is absent. Reprojection here supplies only
            # deterministic dependency facts, never a replacement witness.
            work.reserve(row)
            expected = history.sialib.signed_ledger_event_projection(chain, row)
            links = [] if expected is None else sorted(
                link for link in expected.links if not link.startswith("organs/"))
            if len(links) != 1 or not links[0].startswith("units/"):
                reason = "unsupported-native-subject-link"
        if reason is not None:
            coverage[chain]["unsupported_sequences"].append(event["seq"])
            budget.append(output["exclusions"], {
                "kind": "source-row", "chain": chain, "seq": event["seq"], "reason": reason})
            continue
        if len(entries) >= policy["resources"]["max_relations"]:
            _fail("complete relation population exceeds its ceiling")
        subject, bridge = (chain, row[3]), links[0]
        previous = bridge_subjects.setdefault(bridge, subject)
        if previous != subject:
            _fail("generated bridge collision between distinct native subjects")
        projected = history._projection(expected)
        identity = {"chain": chain, "seq": event["seq"], "entry_hash": event["entry_hash"],
                    "event_id": projected["event_id"]}
        line, _payload, _base_line = history.sialib._event_line(
            expected, projected["event_id"], projected["semantic_id"])
        work.reserve({"occurrence": identity, "projection": projected, "line": line})
        entries.append({"source": event, "occurrence": identity,
                        "action": row[2], "subject": subject, "bridge": bridge,
                        "line": line, "native_pages": set(), "relation": None,
                        "options": set(), "reason": None})
        coverage[chain]["supported_sequences"].append(event["seq"])
    for chain in sorted(coverage):
        row = coverage[chain]
        if chain != "sekhmet":
            row.update(status="unsupported", reason="unsupported-native-link-projection")
        elif row["supported_sequences"]:
            row["status"] = "partial" if row["unsupported_sequences"] else "supported"
            if row["unsupported_sequences"]:
                row["reason"] = "unsupported-native-subject-rows"
        else:
            row.update(status="unsupported", reason="no-supported-native-subject-rows")
        budget.append(output["source_coverage"], row)
    return entries


def _lines(text):
    """Yield LF-delimited source lines without allocating a complete line list."""
    start = 0
    while start < len(text):
        end = text.find("\n", start)
        if end < 0:
            yield text[start:]
            return
        yield text[start:end]
        start = end + 1


def _dependencies(entries, pages, policy, output, budget, work):
    parents = {}

    def node(key):
        if key not in parents:
            work.reserve(list(key))
            parents[key] = key
        return key

    def find(key):
        root = key
        while parents[root] != root:
            root = parents[root]
        while parents[key] != key:
            parent = parents[key]
            parents[key] = root
            key = parent
        return root

    def join(left, right):
        left, right = find(node(left)), find(node(right))
        if left != right:
            # Stable root choice prevents iteration order changing components.
            if right < left:
                left, right = right, left
            parents[right] = left

    native_lines = {}
    for index, entry in enumerate(entries):
        if entry["line"] in native_lines:
            _fail("native occurrence line is ambiguous")
        native_lines[entry["line"]] = index
        join(("subject", *entry["subject"]), ("bridge", entry["bridge"]))
    # Scan each captured page once. Non-evidence/inspected-only pages still
    # connect groups; source retention eligibility has not been applied yet.
    for slug in sorted(pages):
        for line in _lines(pages[slug]["text"]):
            index = native_lines.get(line)
            if index is None:
                continue
            entry = entries[index]
            if slug not in entry["native_pages"]:
                work.reserve([entry["occurrence"], slug])
                entry["native_pages"].add(slug)
                join(("subject", *entry["subject"]), ("page", slug))
    components = {}
    for entry in entries:
        root = find(("subject", *entry["subject"]))
        if root not in components:
            if len(components) >= policy["resources"]["max_dependency_groups"]:
                _fail("dependency component population exceeds its ceiling")
            components[root] = {"bridges": set(), "subjects": set(),
                                "source_pages": set(), "entries": []}
        component = components[root]
        component["bridges"].add(entry["bridge"])
        component["subjects"].add(entry["subject"])
        component["source_pages"].update(entry["native_pages"])
        component["entries"].append(entry)
    membership = {}
    groups = []
    for component in components.values():
        subjects = [{"chain": chain, "field": "arg1", "value": value}
                    for chain, value in component["subjects"]]
        identities = [entry["occurrence"] for entry in component["entries"]]
        dependencies = {
            "bridges": sorted(component["bridges"]),
            "subjects": sorted(subjects, key=_canonical),
            "source_pages": sorted(component["source_pages"]),
            "occurrences": sorted(identities, key=_canonical),
        }
        # Reserve the complete dependency roster before hashing it. Digest
        # placeholders have the same represented length as the final fields.
        group = {"id": "0" * 64, "split": "calibration", "dependencies": dependencies}
        budget.reserve(groups, group)
        identifier = _identity("sia-cognitive-source-link-group-v1", dependencies)
        residue = int(_identity("sia-cognitive-source-link-split-v1",
                                policy["seed"], identifier), 16) \
            % policy["split"]["calibration_modulus"]
        partition = ("calibration" if residue == policy["split"]["calibration_residue"]
                     else "heldout")
        group.update(id=identifier, split=partition)
        groups.append(group)
        for entry in component["entries"]:
            membership[entry["subject"]] = group
    # The budget above conservatively reserved the longer partition spelling;
    # settle it against the actual full representation before later additions.
    output["dependency_groups"].extend(sorted(groups, key=lambda group: group["id"]))
    budget.used = _measure(output, budget.maximum)
    return membership


def _witness(entry, pages, chunks):
    event, retention = entry["source"], entry["source"]["retention"]
    if event["projection"] is None or retention["status"] != "retained" \
            or retention["projected_event_retained"] is not True \
            or retention["retrieval_excerpt"] != entry["line"]:
        return None, set(), "required-native-witness-unavailable"
    slug = retention["source_slug"]
    if slug not in pages or slug not in entry["native_pages"]:
        return None, set(), "required-native-witness-unavailable"
    page = pages[slug]
    if page["origin"] != "evidence":
        return None, set(), "required-source-origin-not-evidence"
    encoded = entry["line"].encode("utf-8")
    token = "[[" + entry["bridge"] + "]]"
    token_bytes = token.encode("utf-8")
    start = encoded.find(token_bytes)
    if start < 0:
        return None, set(), "required-native-witness-unavailable"
    options = {index for index, chunk in enumerate(chunks[slug]) if encoded in chunk}
    if not options:
        return None, set(), "required-excerpt-crosses-chunk"
    index = min(options)
    witness = {
        "source_slug": slug, "origin": page["origin"], "page_sha256": page["sha256"],
        "page_lineage_sha256": page["lineage_sha256"], "excerpt": entry["line"],
        "excerpt_sha256": "0" * 64, "chunk_index": index,
        "chunk_sha256": "0" * 64, "link_token": token,
        "link_utf8_start": start, "link_utf8_end": start + len(token_bytes),
    }
    return witness, options, None


def _relations(entries, pages, chunks, output, budget):
    for entry in entries:
        # Source text and all possible chunk bytes are already bounded. Reserve
        # the complete actual witness shape before filling its digest slots.
        prototype = {
            "occurrence": entry["occurrence"], "action": entry["action"],
            "native_subject": {"field": "arg1", "value": entry["subject"][1]},
            "generated_link": {"slug": entry["bridge"],
                               "provenance": _RELATION_RULES["link_provenance"]},
            "witness": None,
        }
        witness, options, reason = _witness(entry, pages, chunks)
        prototype["witness"] = witness
        budget.reserve(output["relations"], prototype)
        if witness is not None:
            witness["excerpt_sha256"] = _sha(witness["excerpt"].encode("utf-8"))
            witness["chunk_sha256"] = _sha(chunks[witness["source_slug"]][witness["chunk_index"]])
        output["relations"].append(prototype)
        entry.update(relation=prototype, options=options, reason=reason)


def _public_text(seed_event_id, action):
    # Only the disclosed seed event ID and action enter this formatter.
    # No private bridge, subject, target, group, or witness argument exists.
    return (
        "In the captured signed sekhmet chain, which occurrences of exact action "
        + json.dumps(action, ensure_ascii=False)
        + " share the explicitly projected non-organ link of seed event "
        + json.dumps(seed_event_id, ensure_ascii=False)
        + "? Return every counterpart occurrence with the seed and counterpart "
          "source witnesses; this asks for shared source links, not causation."
    )


def _query_populations(entries, policy):
    populations = {}
    for entry in entries:
        populations.setdefault(entry["subject"], {}).setdefault(entry["action"], []).append(entry)
    # Bound ALL proposed queries before any witness-based exclusion. This cap
    # cannot be evaded by arranging many unavailable targets or by clipping.
    proposals = 0
    for actions in populations.values():
        alternatives = len(actions) - 1
        for population in actions.values():
            proposals += len(population) * alternatives
            if proposals > policy["resources"]["max_queries"]:
                _fail("complete query proposal population exceeds its ceiling")
    return populations


def _support_plan(seed, targets):
    if seed["reason"] is not None:
        return None, seed["reason"]
    for target in targets:
        if target["reason"] is not None:
            return None, target["reason"]
    seed_slug = seed["relation"]["witness"]["source_slug"]
    if any(target["relation"]["witness"]["source_slug"] == seed_slug for target in targets):
        return None, "seed-target-source-page-shortcut"
    per_page = {}
    for entry in (seed, *targets):
        slug = entry["relation"]["witness"]["source_slug"]
        if slug in per_page:
            per_page[slug].intersection_update(entry["options"])
            if not per_page[slug]:
                return None, "page-pooling-witness-conflict"
        else:
            if len(per_page) >= adapter.MAX_RESULTS:
                return None, "required-pages-exceed-adapter-results"
            per_page[slug] = set(entry["options"])
    return {slug: min(options) for slug, options in per_page.items()}, None


def _queries(entries, populations, membership, policy, chunks, output, budget):
    queries, answers = [], []
    for seed in entries:
        group = membership[seed["subject"]]
        for action, targets in sorted(populations[seed["subject"]].items()):
            if action == seed["action"]:
                continue
            # Complete targets are borrowed from the native population, never
            # reconstructed from eligible relations or a shortened witness set.
            identities = [target["occurrence"] for target in targets]
            plan, reason = _support_plan(seed, targets)
            if reason is not None:
                exclusion = {
                    "kind": "query", "id": "0" * 64, "group_id": group["id"],
                    "seed": seed["occurrence"], "counterpart_action": action,
                    "targets": identities, "reason": reason}
                budget.reserve(output["exclusions"], exclusion)
                exclusion["id"] = _identity(
                    "sia-cognitive-source-link-query-v1", seed["occurrence"], action)
                output["exclusions"].append(exclusion)
                continue
            _measure(action, policy["protocol"]["max_query_bytes"])
            text = _public_text(seed["occurrence"]["event_id"], action)
            if len(text.encode("utf-8")) > policy["protocol"]["max_query_bytes"]:
                _fail("complete public query exceeds its byte ceiling")
            query = {"id": "0" * 64, "text": text, "group_id": group["id"], "split": group["split"]}
            answer = {
                "id": "0" * 64, "class": "source-link-join", "group_id": group["id"],
                "seed": seed["occurrence"], "counterpart_action": action,
                "native_subject": {"chain": seed["subject"][0], "field": "arg1", "value": seed["subject"][1]},
                "bridge": seed["bridge"], "targets": identities, "support": [],
            }
            budget.reserve(queries, query)
            budget.reserve(answers, answer)
            for role, population in (("seed", (seed,)), ("target", targets)):
                for entry in population:
                    original = entry["relation"]["witness"]
                    index = plan[original["source_slug"]]
                    # The shallow prospective mapping contains only already
                    # bounded immutable scalars. Its full repeated excerpt is
                    # reserved before digesting or attaching this support row.
                    witness = {**original, "chunk_index": index, "chunk_sha256": "0" * 64}
                    support = {"role": role, "occurrence": entry["occurrence"], "witness": witness}
                    budget.reserve(answer["support"], support)
                    witness["chunk_sha256"] = _sha(chunks[witness["source_slug"]][index])
                    answer["support"].append(support)
            identifier = _identity("sia-cognitive-source-link-query-v1", seed["occurrence"], action)
            query["id"] = answer["id"] = identifier
            queries.append(query)
            answers.append(answer)
    output["queries"].extend(sorted(queries, key=lambda query: query["id"]))
    output["answer_key"].extend(sorted(answers, key=lambda answer: answer["id"]))
    if policy["require_queries"] and not output["queries"]:
        _fail("required source-link queries are unavailable")
    budget.used = _measure(output, budget.maximum)


def _construct(capture, policy, capture_pin, policy_pin):
    output = _base(capture, capture_pin, policy_pin)
    budget = _OutputBudget(output, policy["resources"]["max_selection_bytes"])
    work = _WorkBudget(policy["resources"]["max_capture_bytes"])
    pages, chunks = _page_records(capture, policy, output, budget)
    entries = _native_population(capture, policy, output, budget, work)
    populations = _query_populations(entries, policy)
    membership = _dependencies(entries, pages, policy, output, budget, work)
    _relations(entries, pages, chunks, output, budget)
    _queries(entries, populations, membership, policy, chunks, output, budget)
    output["selection_sha256"] = _sha(_canonical(
        {key: value for key, value in output.items() if key != "selection_sha256"}, budget.maximum))
    _measure(output, budget.maximum)
    return output


def select_source_links(*, capture, expected_capture_sha256, policy, expected_policy_sha256):
    """Construct a detached, caller-pinned source-link selection without I/O."""
    try:
        admitted, selected_policy = _inputs(
            capture, expected_capture_sha256, policy, expected_policy_sha256)
        return _construct(admitted, selected_policy, expected_capture_sha256, expected_policy_sha256)
    except SourceLinkRefusal:
        raise
    except (history.HistoryRefusal, KeyError, TypeError, ValueError, UnicodeError,
            RecursionError, AttributeError, OverflowError) as exc:
        raise SourceLinkRefusal("source-link selection input is malformed") from exc


def admit_selection(selection, *, capture, expected_capture_sha256, policy, expected_policy_sha256):
    """Recompute the full construction from independently pinned source inputs."""
    try:
        admitted, selected_policy = _inputs(
            capture, expected_capture_sha256, policy, expected_policy_sha256, selection)
        expected = _construct(admitted, selected_policy, expected_capture_sha256, expected_policy_sha256)
        maximum = selected_policy["resources"]["max_selection_bytes"]
        # Canonical byte equality preserves strict scalar types (not bool/int
        # equality) and rejects rehashed but arbitrarily changed private keys.
        if _canonical(selection, maximum) != _canonical(expected, maximum):
            _fail("selection differs from complete source and policy replay")
        return expected
    except SourceLinkRefusal:
        raise
    except (history.HistoryRefusal, KeyError, TypeError, ValueError, UnicodeError,
            RecursionError, AttributeError, OverflowError) as exc:
        raise SourceLinkRefusal("source-link selection replay is malformed") from exc


def public_queries(selection, *, split, capture, expected_capture_sha256,
                   policy, expected_policy_sha256):
    """Return only the selected split's declared public id/text worker inputs."""
    if type(split) is not str or split not in ("calibration", "heldout"):
        _fail("an explicit calibration or heldout split is required")
    admitted = admit_selection(
        selection, capture=capture, expected_capture_sha256=expected_capture_sha256,
        policy=policy, expected_policy_sha256=expected_policy_sha256)
    return [{"id": query["id"], "text": query["text"]}
            for query in admitted["queries"] if query["split"] == split]
