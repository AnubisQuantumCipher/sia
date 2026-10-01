"""Pure source gist rendering and additive, replayable page publication.

The source-effects transaction owns native-source revalidation and later git,
index and status publication. This component owns the exact derived page bytes.
It never edits an episode and never replaces an existing differing gist page.
"""

import base64
import copy
import hashlib
import json
import os
import re
import stat

import siaeventplan as eventplan
import sialiveloop as live


NON_CLAIMS = (
    "Gist page publication records derived additions, not source authentication, biological consolidation, a held-out retrieval win, or JACKAL assurance.",
    "The source-effects owner must retain or revalidate the original native capture through publication; a page plan does not authenticate source generations.",
    "Published page bytes are not a corpus commit, index synchronization, source acknowledgment, live-loop admission, status readiness, or observed recall delivery.",
    "Exact existing target bytes permit idempotent replay; they do not establish which attempt first published the page.",
    "Original episodes are never deleted or replaced; all upstream live-loop, gist, capture and source-origin boundaries remain controlling.",
)
PLAN_KEYS = frozenset({
    "schema", "status", "transition_sha256", "gist_pages_sha256", "pages",
    "target_versions", "non_claims", "plan_sha256"})
PAGE_KEYS = frozenset({
    "proposal", "raw_utf8_base64", "raw_bytes", "raw_sha256", "target_version"})
TRANSITION_KEYS = frozenset({
    "schema", "status", "state", "state_sha256", "history_capture",
    "history_capture_sha256", "gist_pages", "non_claims", "transition_sha256"})
TARGET_KEYS = frozenset({"slug", "source_sha256", "version_sha256"})
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SUBJECT = re.compile(r"gists/live/[0-9a-f]{64}\Z")
_PLACEHOLDER = "0" * 64
_BOUNDARY = (
    "\n\nPublication boundary: this derived gist adds attributed recorded meaning; "
    "it does not replace its source episodes or establish a cognitive win.\n")


def _refuse(reason):
    error = ValueError("source gist page refused: " + reason)
    error.reason = reason
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        _refuse(label + "-shape")


def _hex(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _refuse("digest-shape")


def _raw(owner, value):
    return live._canonical(value, owner["MAX_STATE_JSON_BYTES"])


def _sha(owner, value):
    return hashlib.sha256(_raw(owner, value)).hexdigest()


def _own(owner, value, field):
    return _sha(owner, {key: item for key, item in value.items() if key != field})


def _pin(owner, value, field, expected):
    _hex(expected)
    _hex(value[field])
    if value[field] != expected or _own(owner, value, field) != expected:
        _refuse("external-" + field)


def _same(owner, first, second):
    return _raw(owner, first) == _raw(owner, second)


def _proposal(owner, value):
    _keys(value, live._PAGE_KEYS, "proposal")
    if type(value["subject"]) is not str or _SUBJECT.fullmatch(value["subject"]) is None \
            or value["origin"] != "derived" or type(value["content"]) is not str:
        _refuse("derived-gist-proposal")
    for name in ("source_sha256", "content_sha256", "version_sha256"):
        _hex(value[name])
    eventplan._text_size(value["content"], owner["MAX_EVENT_PAGE_BYTES"], quoted=False)
    if hashlib.sha256(value["content"].encode("utf-8")).hexdigest() != value["content_sha256"] \
            or live._version(value) != value["version_sha256"]:
        _refuse("proposal-content-or-origin-binding")


def _header(proposal):
    return ("---\ntype: gist\norigin: derived\ntitle: Recorded episode gist\n"
            "gist_source_sha256: " + proposal["source_sha256"] + "\n"
            "gist_proposal_sha256: " + proposal["version_sha256"] + "\n---\n")


def _render(proposal):
    return (_header(proposal) + proposal["content"] + _BOUNDARY).encode("utf-8")


def _target(version):
    return {"slug": version["subject"], "source_sha256": version["source_sha256"],
            "version_sha256": version["version_sha256"]}


def _receipt(owner, plan):
    value = {"schema": "sia-controller-source-gist-publication-v1",
             "status": "gist-pages-published", "plan_sha256": plan["plan_sha256"],
             "gist_pages_sha256": plan["gist_pages_sha256"],
             "target_versions": plan["target_versions"], "non_claims": list(NON_CLAIMS)}
    return {**value, "publication_sha256": _sha(owner, value)}


def _reservation(owner, proposals, initial):
    """Reserve the entire plan, result and observations before rendering."""
    if type(proposals) is not list or len(proposals) > owner["MAX_SOURCE_REPLAY_EVENTS"]:
        _refuse("proposal-roster-capacity")
    budget = eventplan._Budget(owner, initial)
    budget.reserve("fixed-plan-and-receipt", 8192)
    seen = set()
    for proposal in proposals:
        _proposal(owner, proposal)
        subject = proposal["subject"]
        if subject in seen:
            _refuse("duplicate-target")
        seen.add(subject)
        content_size = eventplan._text_size(
            proposal["content"], owner["MAX_EVENT_PAGE_BYTES"], quoted=False)
        raw_size = len(_header(proposal).encode("utf-8")) + content_size + len(_BOUNDARY.encode("utf-8"))
        if raw_size > owner["MAX_EVENT_PAGE_BYTES"]:
            _refuse("rendered-page-capacity")
        # proposal, target-version text, base64 and an eventual held exact
        # target observation all coexist. JSON escaping is reserved using the
        # actual content, not a guessed ratio or a caller's raw_bytes field.
        budget.reserve(("page", subject),
                       8192 + live._size(proposal, budget.limit)
                       + eventplan._text_size(proposal["content"], budget.limit)
                       + len(_header(proposal)) + len(_BOUNDARY)
                       + ((raw_size + 2) // 3 * 4) + raw_size)
    return budget


def _transition_proposals(owner, transition, expected):
    _raw(owner, transition)
    _keys(transition, TRANSITION_KEYS, "transition")
    _pin(owner, transition, "transition_sha256", expected)
    if transition["schema"] != "sia-live-loop-transition-v1" \
            or transition["status"] != "planned" \
            or transition["non_claims"] != list(live.NON_CLAIMS):
        _refuse("transition-contract")
    state = transition["state"]
    _keys(state, live._STATE_KEYS, "state")
    _hex(transition["state_sha256"])
    if _sha(owner, state) != transition["state_sha256"]:
        _refuse("transition-state-pin")
    live._policy(state["policy"])
    live._state(state, transition["state_sha256"], state["policy"], state["observed_at"])
    captured = live._capture(state, transition["state_sha256"])
    if not _same(owner, captured, transition["history_capture"]) \
            or captured["capture_sha256"] != transition["history_capture_sha256"]:
        _refuse("transition-history-join")
    idle = state["idle"]
    if type(idle) is not dict or type(idle.get("requested")) is not bool:
        _refuse("idle-contract")
    if not idle["requested"]:
        expected_idle, proposals = {"requested": False, "gist": None}, []
    elif state["policy"]["schema"] == "sia-live-loop-policy-v2":
        _keys(idle, {"requested", "binding"}, "idle")
        binding = idle["binding"]
        if type(binding) is dict \
                and binding.get("schema") == "sia-live-idle-without-native-binding-v1":
            import sialiveidle
            sialiveidle.validate_receipt(
                intake=state["intake"], expected_intake_sha256=_sha(owner, state["intake"]),
                policy=state["policy"], expected_policy_sha256=state["policy_sha256"],
                observed_at=state["observed_at"], receipt=binding)
            if transition["gist_pages"] != []:
                _refuse("gist-proposals-without-native-source")
            return []
        if type(binding) is not dict or type(binding.get("bindings")) is not dict:
            _refuse("idle-binding")
        pins = binding["bindings"]
        gist_inputs = {"episode_bindings": binding["episode_bindings"],
                       "expected_episode_bindings_sha256": pins["episode_bindings_sha256"],
                       "gist_inputs": binding["gist_inputs"],
                       "expected_gist_inputs_sha256": pins["gist_inputs_sha256"]}
        live._gist_inputs(gist_inputs, state["intake"], state["policy"], True,
                          expected_intake_sha256=_sha(owner, state["intake"]),
                          expected_policy_sha256=state["policy_sha256"],
                          observed_at=state["observed_at"])
        expected_idle, proposals = live._idle(
            gist_inputs, state["intake"], True, policy=state["policy"],
            expected_intake_sha256=_sha(owner, state["intake"]))
    else:
        _keys(idle, {"requested", "gist"}, "idle")
        artifact = idle["gist"]
        _keys(artifact, {"artifact_json", "artifact_sha256"}, "gist-artifact")
        if type(artifact["artifact_json"]) is not str:
            _refuse("gist-artifact-text")
        body = json.loads(artifact["artifact_json"])
        gist_inputs = {name: body[name] for name in ("capture", "replay", "policy")}
        gist_inputs.update({"expected_" + name + "_sha256": body[name + "_sha256"]
                            for name in ("capture", "replay", "policy")})
        live._gist_inputs(gist_inputs, state["intake"], state["policy"], True)
        expected_idle, proposals = live._idle(gist_inputs, state["intake"], True)
    if not _same(owner, expected_idle, idle) \
            or not _same(owner, proposals, transition["gist_pages"]):
        _refuse("complete-idle-proposal-replay")
    return proposals


def prepare(owner, *, transition, expected_transition_sha256):
    """Render every replay-bound proposal without filesystem effects."""
    original = _raw(owner, transition)
    _keys(transition, TRANSITION_KEYS, "transition")
    _reservation(owner, transition["gist_pages"], len(original))
    proposals = _transition_proposals(owner, transition, expected_transition_sha256)
    result = prepare_pages(
        owner, gist_pages=proposals, expected_gist_pages_sha256=_sha(owner, proposals),
        transition_sha256=expected_transition_sha256)
    if _raw(owner, transition) != original:
        _refuse("transition-changed-during-render")
    return result


def prepare_pages(owner, *, gist_pages, expected_gist_pages_sha256, transition_sha256):
    """Render an externally pinned roster; the caller owns transition replay."""
    original = _raw(owner, gist_pages)
    _hex(expected_gist_pages_sha256)
    _hex(transition_sha256)
    _reservation(owner, gist_pages, len(original))
    if _sha(owner, gist_pages) != expected_gist_pages_sha256:
        _refuse("external-gist-pages-pin")
    rows = []
    for proposal in gist_pages:
        raw = _render(proposal)
        version = owner["_corpus_page_version_from_bytes"](slug=proposal["subject"], raw=raw)
        if version["origin"] != "derived":
            _refuse("rendered-origin")
        rows.append({"proposal": proposal, "raw_utf8_base64": base64.b64encode(raw).decode("ascii"),
                     "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                     "target_version": version})
    body = {"schema": "sia-controller-source-gist-page-plan-v1", "status": "prepared-not-published",
            "transition_sha256": transition_sha256,
            "gist_pages_sha256": expected_gist_pages_sha256, "pages": rows,
            "target_versions": [_target(row["target_version"]) for row in rows],
            "non_claims": list(NON_CLAIMS)}
    result = {**body, "plan_sha256": _sha(owner, body)}
    detached = copy.deepcopy(result)
    if not _same(owner, detached, result) or _raw(owner, gist_pages) != original:
        _refuse("input-or-result-changed")
    return detached


def _admit_plan(owner, plan, expected):
    original = _raw(owner, plan)
    _keys(plan, PLAN_KEYS, "plan")
    if plan["schema"] != "sia-controller-source-gist-page-plan-v1" \
            or plan["status"] != "prepared-not-published" \
            or plan["non_claims"] != list(NON_CLAIMS) or type(plan["pages"]) is not list:
        _refuse("plan-contract")
    _pin(owner, plan, "plan_sha256", expected)
    _hex(plan["transition_sha256"])
    _hex(plan["gist_pages_sha256"])
    for row in plan["pages"]:
        _keys(row, PAGE_KEYS, "planned-page")
    proposals = [row["proposal"] for row in plan["pages"]]
    budget = _reservation(owner, proposals, len(original))
    if _sha(owner, proposals) != plan["gist_pages_sha256"]:
        _refuse("complete-proposal-roster")
    images, targets = {}, []
    for row in plan["pages"]:
        proposal = row["proposal"]
        raw = _render(proposal)
        if type(row["raw_bytes"]) is not int or row["raw_bytes"] != len(raw) \
                or row["raw_sha256"] != hashlib.sha256(raw).hexdigest() \
                or row["raw_utf8_base64"] != base64.b64encode(raw).decode("ascii"):
            _refuse("exact-rendered-page-binding")
        version = owner["_corpus_page_version_from_bytes"](slug=proposal["subject"], raw=raw)
        if not _same(owner, version, row["target_version"]) or version["origin"] != "derived":
            _refuse("target-version-binding")
        images[proposal["subject"] + ".md"] = raw
        targets.append(_target(version))
    if not _same(owner, targets, plan["target_versions"]):
        _refuse("complete-target-roster")
    receipt = _receipt(owner, plan)
    detached = copy.deepcopy(receipt)
    if not _same(owner, detached, receipt) or _raw(owner, plan) != original:
        _refuse("input-or-result-changed")
    return original, images, detached, budget


def publication_receipt(owner, *, plan, expected_plan_sha256):
    """Return the expected receipt; this operation does not observe publication."""
    _original, _images, receipt, _budget = _admit_plan(owner, plan, expected_plan_sha256)
    return receipt


def _observe(owner, images, budget, required=frozenset()):
    captured = eventplan._Capture(owner, budget)
    present = set()
    try:
        for relative, wanted in images.items():
            try:
                actual = captured.read_file(captured.path(relative), owner["MAX_EVENT_PAGE_BYTES"])
            except FileNotFoundError:
                if relative in required:
                    _refuse("published-target-disappeared")
                continue
            info = captured.files[relative]["generation"]
            if actual != wanted or stat.S_IMODE(info["mode"]) != 0o600:
                _refuse("existing-target-differs")
            present.add(relative)
        captured.current()
        return captured, present
    except BaseException:
        captured.close()
        raise


def publish(owner, *, plan, expected_plan_sha256):
    """Publish exact additive bytes with one corpus lease and fixed staging."""
    original, images, receipt, budget = _admit_plan(owner, plan, expected_plan_sha256)
    if not images:
        return receipt
    with owner["corpus_owner"]():
        captured, present = _observe(owner, images, budget)
        try:
            for relative, raw in images.items():
                captured.current()
                if _raw(owner, plan) != original:
                    _refuse("plan-changed-before-effect")
                path = captured.path(relative)
                affected = frozenset(eventplan._ancestors(relative))
                if relative not in present:
                    owner["_before_corpus_mutation"]()
                    captured.current()
                    if _raw(owner, plan) != original:
                        _refuse("plan-changed-at-mutation-barrier")
                    owner["ensure_durable_directory"](os.path.dirname(path))
                    captured.current(exempt_directories=affected)
                refreshed, observed = _observe(owner, images, budget, present)
                try:
                    captured.named_current(exempt_directories=affected)
                except BaseException:
                    refreshed.close()
                    raise
                captured.close()
                captured, present = refreshed, observed
                captured.current()
                if _raw(owner, plan) != original:
                    _refuse("plan-changed-before-page-publication")
                owner["siaqueue"].fixed_atomic_publish(
                    path, raw, mode=0o600, exclusive=True, authority_roots=(owner["CORPUS"],),
                    destination_dir_fd=captured.directories[os.path.dirname(relative)]["fd"])
                captured.current(exempt_files=frozenset({relative}), exempt_directories=affected)
                refreshed, observed = _observe(owner, images, budget, present | {relative})
                try:
                    captured.named_current(exempt_files=frozenset({relative}), exempt_directories=affected)
                except BaseException:
                    refreshed.close()
                    raise
                captured.close()
                captured, present = refreshed, observed
            if _raw(owner, plan) != original:
                _refuse("plan-changed-during-publication")
            captured.current()
            return receipt
        finally:
            captured.close()
