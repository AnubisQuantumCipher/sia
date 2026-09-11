"""Storage-free delivery binding retained by a controller source successor.

This component checks represented bytes supplied by an outer descriptor-owning
capture. It does not acquire that capture, its parent, a journal or a clock.
The source validator separately replays the complete collector projection;
the WAL reader must compare the declared parent source schema to the actual
retained predecessor, and the live adapter must compare the entire actual
parent generation. A self-consistent hypothetical v3 is not that authority.

Outer source/view pins use source-native ASCII JSON. Birth and adoption keep
their original native-integer UTF-8 component hashes. Only genuine live
documents enter the live serializer; filesystem identities never do.
"""

import copy
import os
import re
import stat
from types import SimpleNamespace

import siacontrollerdeliveryepoch as epoch_api
import siacontrollerdeliveryinput as binding_api
import siadelivery as journal_api
import siaeventintake as intake_api
import sialiveloop as live
import siasourcebatch as source


NON_CLAIMS = (
    "This pure wrapper checks represented-byte consistency, not the actual parent source schema, acknowledged predecessor or independently observed parent generation.",
    "Supplied held views and native identities are retained unchanged; this wrapper observes no storage or filesystem generation and provides no hostile same-user protection.",
    "Binding is not readiness, source acknowledgment, pulse consumption, writer authorization, emitted output or human receipt.",
    "The full source-to-intake projection is the separate source validator's responsibility; this wrapper cannot authenticate absent collector returns or reconstruct complete machine history.",
    "A declared v3 continuation preserves the externally pinned original adoption, but does not prove that an acknowledged v3 parent retained it; actual WAL and candidate parent joins remain mandatory.",
    "A capture-held notification fence remains pending, not cleared, hidden, completed or converted to readiness by this representation.",
    "No JACKAL assurance, biological cognition, cognitive authorization or held-out retrieval win is established.",
    "All original epoch, adoption, held-view, source, intake, live-loop, journal and delivery-binding nonclaims remain controlling.",
)
_SCHEMA = "sia-controller-source-delivery-input-v1"
_KEYS = {
    "schema", "status", "parent_source_schema", "epoch_view",
    "expected_epoch_view_sha256", "expected_adoption_sha256",
    "journal", "expected_journal_sha256", "binding",
    "expected_binding_sha256", "non_claims", "input_sha256",
}
_VIEW_KEYS = {
    "schema", "status", "epoch_adoption", "parent_committed",
    "parent_generation", "expected_parent_generation_sha256",
    "records_directory", "records_identity", "non_claims",
}
_FENCE_KEYS = {
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
}
_ADOPTED_KEYS = {
    "schema", "status", "birth", "expected_birth_sha256", "adoption",
    "expected_adoption_sha256", "non_claims",
}
_GENERATION_KEYS = {
    "schema", "publication_id", "pulse_seq", "epoch_id", "state_sha256",
    "transition_sha256", "candidate_sha256", "status_sha256", "parent_committed",
    "transition", "non_claims", "generation_sha256",
}
_RECEIPT_KEYS = {
    "schema", "publication_id", "pulse_seq", "epoch_id", "state_sha256",
    "transition_sha256", "candidate_sha256", "generation_sha256", "status_sha256",
    "parent_generation_sha256",
}
_TRANSITION_KEYS = {
    "schema", "status", "state", "state_sha256", "history_capture",
    "history_capture_sha256", "gist_pages", "non_claims", "transition_sha256",
}
_PROJECTION_KEYS = {
    "schema", "status", "bindings", "associations", "intake", "intake_sha256",
    "source_non_claims", "non_claims", "projection_sha256",
}
_BINDING_KEYS = {
    "schema", "status", "epoch_id", "observed_at", "journal_sha256",
    "previous_state_sha256", "intake_sha256", "policy_sha256", "deliveries",
    "deliveries_sha256", "journal_non_claims", "non_claims", "binding_sha256",
}
_LEGACY = {"sia-controller-source-batch-v1", "sia-controller-source-batch-v2"}
_PARENT_SCHEMAS = _LEGACY | {"sia-controller-source-batch-v3"}
_CAPACITIES = (
    "MAX_STATE_JSON_BYTES", "MAX_CONFIG_PATH_CHARS", "MAX_SOURCE_REPLAY_EVENTS",
    "MAX_SOURCE_REPLAY_SOURCES", "MAX_CONFIG_TEXT_CHARS", "MAX_CONFIG_TAGS",
    "MAX_SOURCE_NAME_CHARS",
)
_OWNER_REFERENCES = (
    "json", "hashlib", "math", "os", "_validated_custom_sense_entry",
    "_canonical_utc_timestamp",
)
_ERRORS = (ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError, OSError)


class ControllerDeliveryWrapperRefusal(ValueError):
    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = getattr(upstream, "non_claims", ())
        super().__init__("controller delivery wrapper refused: " + reason)


def _refuse(reason):
    raise ControllerDeliveryWrapperRefusal(reason)


def _keys(value, expected, reason):
    if type(value) is not dict or set(value) != set(expected) \
            or any(type(key) is not str for key in value):
        _refuse(reason + "-shape")


def _pin(pin):
    if not live._digest(pin):
        _refuse("digest-shape")


def _same(owner, left, right):
    return source.native_bytes(owner, left) == source.native_bytes(owner, right)


def _own(owner, value, field):
    return source.native_sha(owner, {
        key: item for key, item in value.items() if key != field})


def _owner_basis(owner):
    if type(owner) is not dict:
        _refuse("owner-shape")
    capacities = {}
    for name in _CAPACITIES:
        value = owner.get(name)
        if type(value) is not int or value <= 0:
            _refuse("owner-capacity-contract")
        capacities[name] = value
    if type(owner.get("_SENSE_ORGAN")) is not dict:
        _refuse("owner-source-catalog-contract")
    claims = owner.get("LIVE_PUBLICATION_NON_CLAIMS")
    if type(claims) not in (list, tuple) or not claims \
            or len(claims) > capacities["MAX_STATE_JSON_BYTES"]:
        _refuse("owner-live-nonclaims-contract")
    if any(type(claim) is not str for claim in claims):
        _refuse("owner-live-nonclaims-contract")
    key = owner.get("NOTIFY_BASELINE_ATTEMPT_KEY")
    if type(key) is not str or not key:
        _refuse("owner-notification-key-contract")
    for name in ("_validated_custom_sense_entry", "_canonical_utc_timestamp"):
        if not callable(owner.get(name)):
            _refuse("owner-pure-operation-contract")
    for name, method in (("json", "dumps"), ("hashlib", "sha256"),
                         ("math", "isfinite")):
        if not callable(getattr(owner.get(name), method, None)):
            _refuse("owner-serializer-contract")
    if not callable(getattr(getattr(owner.get("os"), "path", None), "isabs", None)) \
            or not callable(getattr(getattr(owner.get("os"), "path", None), "normpath", None)):
        _refuse("owner-path-contract")
    return {
        "capacities": capacities, "source_organs": owner["_SENSE_ORGAN"],
        "live_publication_non_claims": list(claims), "notification_key": key,
    }


class _Admission:
    """Bound every original occurrence before any deepcopy or binder call."""

    def __init__(self, owner, supplied):
        basis = _owner_basis(owner)
        self.original_owner, self.supplied = owner, supplied
        self.references = {name: owner[name] for name in _OWNER_REFERENCES}
        self.owner = {**self.references, **basis["capacities"]}
        self.original = source.native_bytes(self.owner, {
            "owner_basis": basis, "request": supplied})
        self.basis = copy.deepcopy(basis)
        self.admitted = copy.deepcopy(supplied)
        self.owner.update({
            "_SENSE_ORGAN": self.basis["source_organs"],
            "LIVE_PUBLICATION_NON_CLAIMS": self.basis["live_publication_non_claims"],
            "NOTIFY_BASELINE_ATTEMPT_KEY": self.basis["notification_key"],
        })
        self.current()

    def current(self):
        if any(self.original_owner.get(name) is not value
               for name, value in self.references.items()):
            _refuse("owner-pure-operation-changed")
        basis = _owner_basis(self.original_owner)
        for value in ({"owner_basis": basis, "request": self.supplied},
                      {"owner_basis": self.basis, "request": self.admitted}):
            if source.native_bytes(self.owner, value) != self.original:
                _refuse("input-or-owner-changed")


class PreparationAdmissionV1:
    """Explicit compound preparation contract; never an _Admission fallback.

    The closed slot roster bounds the aggregate without serializing another
    copy of the complete batch and parent into one single-artifact envelope.
    Every slot, including all nested occurrences, retains the original native
    byte limit. No slots are copied until all originals have passed that cap.
    This representation admission grants no storage or publication authority;
    callers must still validate the batch and full independent parent identity.
    """

    schema = "sia-live-preparation-compound-v1"
    _fields = ("batch", "previous_generation",
               "expected_previous_generation_sha256")

    def __init__(self, owner, supplied):
        basis = _owner_basis(owner)
        self.original_owner, self.supplied = owner, supplied
        self.references = {name: owner[name] for name in _OWNER_REFERENCES}
        self.owner = {**self.references, **basis["capacities"]}
        self._limit = self.owner["MAX_STATE_JSON_BYTES"]
        self.original = self._slots(basis, supplied)
        self.basis = copy.deepcopy(basis)
        self.admitted = copy.deepcopy(supplied)
        self.owner.update({
            "_SENSE_ORGAN": self.basis["source_organs"],
            "LIVE_PUBLICATION_NON_CLAIMS": self.basis["live_publication_non_claims"],
            "NOTIFY_BASELINE_ATTEMPT_KEY": self.basis["notification_key"],
        })
        self.current()

    def _slots(self, basis, request):
        _keys(request, self._fields, "preparation-compound-v1")
        if type(request["batch"]) is not dict \
                or type(request["previous_generation"]) is not dict:
            _refuse("preparation-compound-v1-artifact-shape")
        _pin(request["expected_previous_generation_sha256"])
        return (source.native_bytes(self.owner, basis),
                *(source.native_bytes(self.owner, request[key])
                  for key in self._fields))

    def current(self):
        if self.owner.get("MAX_STATE_JSON_BYTES") != self._limit:
            _refuse("input-or-owner-changed")
        if any(self.original_owner.get(name) is not value
               or self.owner.get(name) is not value
               for name, value in self.references.items()):
            _refuse("owner-pure-operation-changed")
        for owner, request in ((self.original_owner, self.supplied),
                               (self.owner, self.admitted)):
            if self._slots(_owner_basis(owner), request) != self.original:
                _refuse("input-or-owner-changed")


def _fence(owner, view, marker):
    if marker is None:
        _keys(view, _VIEW_KEYS, "held-view")
        if view["schema"] != "sia-controller-delivery-epoch-view-v1" \
                or view["status"] != "held-not-consumed" \
                or not _same(owner, view["non_claims"], list(epoch_api.HELD_NON_CLAIMS)):
            _refuse("ordinary-held-view-contract")
        return
    _keys(view, _VIEW_KEYS | _FENCE_KEYS, "capture-held-view")
    _keys(marker, {"v", "id", "started_at"}, "notification-fence")
    if type(marker["v"]) is not int or marker["v"] != 1 \
            or type(marker["id"]) is not str \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or type(marker["started_at"]) is not str \
            or owner["_canonical_utc_timestamp"](marker["started_at"]) != marker["started_at"]:
        _refuse("notification-fence-contract")
    pin = view["expected_notification_baseline_attempt_sha256"]
    _pin(pin)
    if view["schema"] != "sia-controller-delivery-epoch-capture-view-v1" \
            or view["status"] != "held-capturable-not-ready" \
            or not _same(owner, view["non_claims"], list(epoch_api.CAPTURE_HELD_NON_CLAIMS)) \
            or not _same(owner, marker, view["notification_baseline_attempt"]) \
            or source.native_sha(owner, marker) != pin:
        _refuse("capture-held-fence-binding")


def _receipt(value):
    _keys(value, _RECEIPT_KEYS, "represented-live-receipt")
    if value["schema"] != "sia-live-publication-receipt-v1" \
            or type(value["publication_id"]) is not str \
            or re.fullmatch(r"[0-9a-f]{32}", value["publication_id"]) is None \
            or not live._integer(value["pulse_seq"]) \
            or not live._token(value["epoch_id"]):
        _refuse("represented-live-receipt-contract")
    for field in ("state_sha256", "transition_sha256", "candidate_sha256",
                  "generation_sha256", "status_sha256"):
        _pin(value[field])
    if value["parent_generation_sha256"] is not None:
        _pin(value["parent_generation_sha256"])


def _generation(owner, view, epoch, observed_at):
    committed = view["parent_committed"]
    _keys(committed, source._COMMITTED_KEYS, "represented-source-commit")
    for value in committed.values():
        _pin(value)
    generation = view["parent_generation"]
    _keys(generation, _GENERATION_KEYS, "represented-live-generation")
    _pin(view["expected_parent_generation_sha256"])
    if generation["parent_committed"] is not None:
        _receipt(generation["parent_committed"])
    _receipt({
        "schema": "sia-live-publication-receipt-v1",
        **{key: generation[key] for key in (
            "publication_id", "pulse_seq", "epoch_id", "state_sha256",
            "transition_sha256", "candidate_sha256", "generation_sha256", "status_sha256")},
        "parent_generation_sha256": None if generation["parent_committed"] is None
            else generation["parent_committed"]["generation_sha256"],
    })
    if generation["schema"] != "sia-live-committed-generation-v1" \
            or generation["generation_sha256"] != view["expected_parent_generation_sha256"] \
            or generation["generation_sha256"] != committed["live_generation_sha256"] \
            or live._own(generation, "generation_sha256") != generation["generation_sha256"] \
            or not _same(owner, generation["non_claims"], owner["LIVE_PUBLICATION_NON_CLAIMS"]):
        _refuse("represented-live-generation-binding")
    predecessor = epoch["predecessor"]
    if predecessor is None or not _same(owner, predecessor, {
            "source_batch_sha256": committed["source_batch_sha256"],
            "live_generation_sha256": generation["generation_sha256"]}):
        _refuse("successor-parent-binding")
    transition = generation["transition"]
    _keys(transition, _TRANSITION_KEYS, "represented-live-transition")
    state = transition["state"]
    _keys(state, live._STATE_KEYS, "represented-live-state")
    if transition["schema"] != "sia-live-loop-transition-v1" \
            or transition["status"] != "planned" \
            or type(transition["gist_pages"]) is not list \
            or not _same(owner, transition["non_claims"], list(live.NON_CLAIMS)) \
            or transition["transition_sha256"] != generation["transition_sha256"] \
            or live._own(transition, "transition_sha256") != generation["transition_sha256"] \
            or transition["state_sha256"] != generation["state_sha256"] \
            or live._sha(state) != generation["state_sha256"]:
        _refuse("represented-live-transition-binding")
    if state["epoch_id"] != epoch["epoch_id"] \
            or generation["epoch_id"] != epoch["epoch_id"] \
            or not _same(owner, state["intake"]["started_at"], epoch["started_at"]) \
            or state["policy_sha256"] != epoch["expected_live_policy_sha256"] \
            or not _same(owner, state["policy"], epoch["live_policy"]) \
            or not live._integer(state["observed_at"]) \
            or state["observed_at"] > observed_at:
        _refuse("represented-parent-epoch-or-clock-binding")
    capture = live._capture(state, generation["state_sha256"])
    if not _same(owner, transition["history_capture"], capture) \
            or transition["history_capture_sha256"] != capture["capture_sha256"]:
        _refuse("represented-parent-history-capture-binding")
    # The actual binder separately reconstructs the parent's typed uses and
    # checks its retained workspace receipt. A full historical transition
    # replay needs the original candidate inputs, not present in this wrapper.
    return generation


def _adoption(owner, request, generation):
    view, epoch = request["epoch_view"], request["epoch"]
    adopted = view["epoch_adoption"]
    _keys(adopted, _ADOPTED_KEYS, "epoch-adoption-result")
    birth, adoption = adopted["birth"], adopted["adoption"]
    _keys(birth, epoch_api._BIRTH_KEYS, "epoch-birth")
    _keys(adoption, epoch_api._ADOPTION_KEYS, "epoch-adoption")
    for pin in (request["expected_adoption_sha256"], adopted["expected_adoption_sha256"],
                adopted["expected_birth_sha256"]):
        _pin(pin)
    identity = view["records_identity"]
    _keys(identity, epoch_api._IDENTITY_KEYS, "records-identity")
    if any(type(value) is not int or not 0 <= value <= epoch_api._IDENTITY_CEILING
           for value in identity.values()) \
            or not stat.S_ISDIR(identity["mode"]) or stat.S_IMODE(identity["mode"]) != 0o700:
        _refuse("represented-records-identity-contract")
    journal_api._limits(birth["limits"])
    epoch_key = epoch_api._sha(owner, {
        "schema": "sia-controller-delivery-epoch-path-v1",
        "epoch_id": epoch["epoch_id"], "started_at": epoch["started_at"],
    })
    # _validate_birth is a pure validator; no _Transaction or held object is
    # constructed. Its entire context is represented data and fixed limits.
    expected = epoch_api._seal(owner, {
        "schema": "sia-controller-delivery-epoch-birth-v1", "status": "birth-pending",
        "epoch_id": epoch["epoch_id"], "started_at": epoch["started_at"],
        "epoch_key_sha256": epoch_key,
        "bootstrap_parent": {
            "source_batch_sha256": view["parent_committed"]["source_batch_sha256"],
            "live_generation_sha256": generation["generation_sha256"],
            "state_sha256": generation["state_sha256"],
        },
        "policy_sha256": epoch["expected_live_policy_sha256"],
        "limits": birth["limits"],
        "limits_sha256": epoch_api._sha(owner, birth["limits"]),
        "non_claims": list(epoch_api.NON_CLAIMS),
    }, "birth_sha256")
    context = SimpleNamespace(
        owner=owner, epoch=epoch, epoch_key=epoch_key, limits=birth["limits"],
        admitted={"expected_journal_limits_sha256": expected["limits_sha256"]},
        legacy=request["parent_source_schema"] in _LEGACY)
    epoch_api._validate_birth(context, birth, expected)
    if adopted["expected_birth_sha256"] != birth["birth_sha256"] \
            or not _same(owner, adoption, epoch_api._adoption(owner, birth, identity)) \
            or not _same(owner, adopted, epoch_api._result(birth, adoption)) \
            or adoption["adoption_sha256"] != request["expected_adoption_sha256"]:
        _refuse("adoption-birth-identity-or-external-pin")
    for value in (birth, adoption, adopted):
        epoch_api._wire(owner, value, birth["limits"])
    directory = source._canonical_path(owner, view["records_directory"])
    if ".gbrain" in directory.split(os.sep) \
            or os.path.basename(directory) != "records" \
            or os.path.basename(os.path.dirname(directory)) != epoch_key:
        _refuse("represented-records-path-binding")
    return birth


def _projection(owner, request):
    value, epoch = request["projection"], request["epoch"]
    _keys(value, _PROJECTION_KEYS, "intake-projection")
    _pin(request["expected_projection_sha256"])
    _pin(value["intake_sha256"])
    if value["schema"] != "sia-event-live-intake-projection-v1" \
            or value["status"] != "prepared-not-published" \
            or value["projection_sha256"] != request["expected_projection_sha256"] \
            or intake_api._sha(owner, {key: item for key, item in value.items()
                                      if key != "projection_sha256"}) != value["projection_sha256"] \
            or intake_api._sha(owner, value["intake"]) != value["intake_sha256"] \
            or not _same(owner, value["non_claims"], list(intake_api.NON_CLAIMS)):
        _refuse("intake-projection-pin-or-contract")
    bindings = value["bindings"]
    _keys(bindings, {name + "_sha256" for name in intake_api._DOCUMENTS}
          | {"observed_at"}, "projection-bindings")
    for name in intake_api._DOCUMENTS:
        _pin(bindings[name + "_sha256"])
        # The current collector return is appended during projection. Its
        # complete history pin is not the epoch's predecessor-only history
        # pin; source.validate_batch checks that full replay separately.
        if name != "history" and bindings[name + "_sha256"] \
                != epoch["expected_" + name + "_sha256"]:
            _refuse("projection-document-binding")
    if not live._integer(bindings["observed_at"]) \
            or bindings["observed_at"] != request["observed_at"]:
        _refuse("projection-clock-binding")
    upstream = value["source_non_claims"]
    _keys(upstream, {"configuration", "source_catalog", "profile", "history",
                     "source_returns", "event_batches", "live_loop"}, "projection-source-nonclaims")
    for name in ("configuration", "source_catalog", "profile", "history"):
        if not _same(owner, upstream[name], epoch[name]["non_claims"]):
            _refuse("projection-source-boundary")
    if not _same(owner, upstream["live_loop"], list(live.NON_CLAIMS)):
        _refuse("projection-live-boundary")
    for name, pin_field, claims in (
            ("source_returns", "returns_sha256", intake_api.SOURCE_NON_CLAIMS),
            ("event_batches", "batch_sha256", source._pages.BATCH_NON_CLAIMS)):
        if type(upstream[name]) is not list:
            _refuse("projection-upstream-roster")
        for row in upstream[name]:
            _keys(row, {pin_field, "non_claims"}, "projection-upstream-row")
            _pin(row[pin_field])
            if not _same(owner, row["non_claims"], list(claims)):
                _refuse("projection-upstream-boundary")
    if type(value["associations"]) is not list:
        _refuse("projection-associations-shape")
    # Associations and complete history joins are retained, not invented or
    # reconstructed from an unavailable current collector closure here.
    intake = value["intake"]
    live._pages(intake, request["observed_at"], epoch["live_policy"])
    if intake["epoch_id"] != epoch["epoch_id"] \
            or not _same(owner, intake["started_at"], epoch["started_at"]):
        _refuse("projection-epoch-binding")


def _journal(owner, request, birth, generation):
    journal = request["journal"]
    _keys(journal, binding_api._JOURNAL_KEYS, "delivery-journal")
    _pin(request["expected_journal_sha256"])
    if journal["schema"] != "sia-live-delivery-journal-v1" \
            or journal["complete"] is not True \
            or type(journal["pending"]) is not list or journal["pending"] \
            or type(journal["records"]) is not list \
            or len(journal["records"]) > birth["limits"]["max_requests"] \
            or journal["epoch_id"] != request["epoch"]["epoch_id"] \
            or not _same(owner, journal["non_claims"], list(journal_api.NON_CLAIMS)) \
            or live._sha(journal) != request["expected_journal_sha256"]:
        _refuse("complete-journal-binding")
    if request["parent_source_schema"] in _LEGACY:
        previous = generation["transition"]["state"]["deliveries"]
        expected = {"schema": "sia-live-deliveries-v1", "epoch_id": journal["epoch_id"],
                    "complete": True, "records": []}
        if not _same(owner, previous, expected) or journal["records"] \
                or request["expected_journal_sha256"] != epoch_api._empty(owner, journal["epoch_id"]):
            _refuse("legacy-bootstrap-must-be-empty")


def _binding(owner, value, request, generation):
    """Independently check the returned envelope before granting an outer pin."""
    _keys(value, _BINDING_KEYS, "delivery-binding")
    previous = generation["transition"]["state"]["deliveries"]["records"]
    consumed = {row["id"] for row in previous}
    records = previous + [row for row in request["journal"]["records"] if row["id"] not in consumed]
    deliveries = {"schema": "sia-live-deliveries-v1", "epoch_id": request["epoch"]["epoch_id"],
                  "complete": True, "records": records}
    expected = {
        "schema": "sia-controller-delivery-binding-v1", "status": "bound-not-consumed",
        "epoch_id": request["epoch"]["epoch_id"], "observed_at": request["observed_at"],
        "journal_sha256": request["expected_journal_sha256"],
        "previous_state_sha256": generation["state_sha256"],
        "intake_sha256": request["projection"]["intake_sha256"],
        "policy_sha256": request["epoch"]["expected_live_policy_sha256"],
        "deliveries": deliveries, "deliveries_sha256": live._sha(deliveries),
        "journal_non_claims": list(journal_api.NON_CLAIMS),
        "non_claims": list(binding_api.NON_CLAIMS),
    }
    expected["binding_sha256"] = live._sha(expected)
    if not _same(owner, value, expected):
        _refuse("delivery-binding-result-contract")


def _make(owner, request):
    schema = request["parent_source_schema"]
    if type(schema) is not str or schema not in _PARENT_SCHEMAS:
        _refuse("parent-source-schema")
    if not live._integer(request["observed_at"]):
        _refuse("explicit-controller-clock")
    _pin(request["expected_epoch_view_sha256"])
    if source.native_sha(owner, request["epoch_view"]) != request["expected_epoch_view_sha256"]:
        _refuse("held-view-native-pin")
    source._validate_epoch(owner, request["epoch"], request["expected_epoch_sha256"],
                           request["observed_at"], initial=False)
    _fence(owner, request["epoch_view"], request["notification_baseline_attempt"])
    generation = _generation(owner, request["epoch_view"], request["epoch"], request["observed_at"])
    birth = _adoption(owner, request, generation)
    _projection(owner, request)
    _journal(owner, request, birth, generation)
    value = binding_api.bind(
        journal=request["journal"], expected_journal_sha256=request["expected_journal_sha256"],
        previous_state=generation["transition"]["state"],
        expected_previous_state_sha256=generation["state_sha256"],
        intake=request["projection"]["intake"],
        expected_intake_sha256=request["projection"]["intake_sha256"],
        policy=request["epoch"]["live_policy"],
        expected_policy_sha256=request["epoch"]["expected_live_policy_sha256"],
        observed_at=request["observed_at"])
    # Do not trust a returned self-hash or status label as an envelope check.
    source.native_bytes(owner, value)
    _binding(owner, value, request, generation)
    result = {
        "schema": _SCHEMA, "status": "bound-not-consumed",
        **{name: request[name] for name in (
            "parent_source_schema", "epoch_view", "expected_epoch_view_sha256",
            "expected_adoption_sha256", "journal", "expected_journal_sha256")},
        "binding": value, "expected_binding_sha256": value["binding_sha256"],
        "non_claims": list(NON_CLAIMS),
    }
    source.native_bytes(owner, {**result, "input_sha256": "0" * 64})
    result["input_sha256"] = source.native_sha(owner, result)
    return result


def build(owner, *, parent_source_schema, epoch_view,
          expected_epoch_view_sha256, expected_adoption_sha256,
          journal, expected_journal_sha256,
          epoch, expected_epoch_sha256,
          projection, expected_projection_sha256,
          observed_at, notification_baseline_attempt):
    """Return an inert detached wrapper; acquire no authority or clock."""
    try:
        request = {key: value for key, value in locals().items() if key != "owner"}
        admitted = _Admission(owner, request)
        result = _make(admitted.owner, admitted.admitted)
        raw = source.native_bytes(admitted.owner, result)
        admitted.current()
        detached = copy.deepcopy(result)
        if source.native_bytes(admitted.owner, result) != raw \
                or source.native_bytes(admitted.owner, detached) != raw:
            _refuse("wrapper-changed-during-final-copy")
        admitted.current()
        return detached
    except ControllerDeliveryWrapperRefusal:
        raise
    except _ERRORS as exc:
        raise ControllerDeliveryWrapperRefusal("wrapper-domain-refused", upstream=exc) from exc


def validate(owner, *, delivery_input, expected_input_sha256,
             epoch, expected_epoch_sha256,
             projection, expected_projection_sha256,
             observed_at, notification_baseline_attempt):
    """Check the whole represented wrapper with a fresh complete binder replay."""
    try:
        request = {key: value for key, value in locals().items() if key != "owner"}
        admitted = _Admission(owner, request)
        value = admitted.admitted["delivery_input"]
        _keys(value, _KEYS, "source-delivery-input")
        _pin(expected_input_sha256)
        if value["schema"] != _SCHEMA or value["status"] != "bound-not-consumed" \
                or not _same(admitted.owner, value["non_claims"], list(NON_CLAIMS)) \
                or value["input_sha256"] != expected_input_sha256 \
                or _own(admitted.owner, value, "input_sha256") != expected_input_sha256:
            _refuse("source-delivery-input-contract-or-pin")
        supplied = {key: admitted.admitted[key] for key in (
            "epoch", "expected_epoch_sha256", "projection", "expected_projection_sha256",
            "observed_at", "notification_baseline_attempt")}
        supplied.update({key: value[key] for key in (
            "parent_source_schema", "epoch_view", "expected_epoch_view_sha256",
            "expected_adoption_sha256", "journal", "expected_journal_sha256")})
        expected = _make(admitted.owner, supplied)
        if not _same(admitted.owner, expected, value):
            _refuse("complete-wrapper-replay-differs")
        admitted.current()
        return None
    except ControllerDeliveryWrapperRefusal:
        raise
    except _ERRORS as exc:
        raise ControllerDeliveryWrapperRefusal("wrapper-domain-refused", upstream=exc) from exc
