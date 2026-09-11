"""Source-bound delivery-journal adoption and descriptor-held observation.

Storage adoption is deliberately separate from output authorization. This
module durably prepares an empty legacy epoch or recovers an already pinned
epoch. Its separate held reader checks existing generations without flushing
or repairing them. A held view is not a durability recovery or writer permit.
Neither interface captures delivery input or emits output. A source-v3
completion retaining the adoption is required by the separate writer gate.

The additive capture-only hold observes the same existing storage after one
explicitly pinned notification-baseline fence. It retains that full fenced
memo, not a completed/readiness substitute, and cannot prepare or repair it.
"""

import contextlib
import copy
import hashlib
import os
import re
import stat

import siadelivery as journal
import siasourceack as acknowledgment
import siasourcebatch as source
import siasourcepublication as publication


NON_CLAIMS = (
    "Birth and adoption establish a bounded local storage transaction, not delivery, pulse consumption, source acknowledgment or writer authorization.",
    "New writers require a fully acknowledged source-v3 batch retaining this exact adoption; legacy source completion or an adopted memo marker alone cannot enable output recording.",
    "Bootstrap requires an acknowledged legacy parent with no prior live deliveries; no legacy touch history or missing journal records are reconstructed.",
    "Directory and file joins concern the checked local descriptor generations, not protection against hostile same-user mutation or complete historical recall.",
    "No output is emitted and no clock is sampled by adoption; no human receipt, JACKAL assurance, biological cognition or held-out retrieval win is established.",
    "All source, live-loop and delivery-journal nonclaims remain controlling.",
)
HELD_NON_CLAIMS = (
    "Held observation validates current retained descriptor generations; it does not replay durability barriers or repair an interrupted adoption.",
    "The caller holds the ordinary corpus lease; this reader does not request the resident brainstem lease or create, publish, flush or repair epoch, memo or journal storage.",
    "This held view is not writer authorization; a separate writer gate must admit an acknowledged source-v3 batch retaining the exact adoption.",
    "Legacy empty-epoch observation can support construction of the first source-v3 input, not output recording or a replacement for prepare_epoch durability recovery.",
    "No delivery is consumed or emitted and no clock is acquired; this view establishes no human receipt, biological cognition or held-out retrieval win.",
    "Directory identities describe checked local generations, not hostile same-user protection or complete historical recall; all adoption, source, live-loop and journal nonclaims remain controlling.",
)
CAPTURE_HELD_NON_CLAIMS = (
    "A held capturable predecessor is not readiness or source acknowledgment; its notification-baseline fence remains pending and is not cleared or hidden.",
    "Capture-only observation does not replay durability barriers, repair adoption, reserve a sequence, sample a clock, or publish a source batch; it is not a substitute for prepare_epoch.",
    "The caller holds the ordinary corpus lease; this reader does not acquire a missing scope, request the resident brainstem lease, or create, publish, flush or repair epoch, memo or journal storage.",
    "This held view is not writer authorization and emits no output or delivery; a separate writer gate must admit an acknowledged source-v3 batch retaining the exact adoption.",
    "The exact parent and pinned fence can support bounded input construction, not independent authorization of another capture or adoption of a fixed-slot orphan.",
    "No complete machine history, human receipt, biological cognition or held-out retrieval win is established; directory identities describe checked local generations, not hostile same-user protection.",
    "All capture-only source-predecessor, adoption, ordinary held-epoch, live-loop and delivery-journal nonclaims remain controlling.",
)
_MARKER = "controller_delivery_epoch"
_ROOT = "CONTROLLER_DELIVERY_EPOCH_ROOT"
_BOUNDARY = "_controller_delivery_epoch_boundary"
_BIRTH_KEYS = {
    "schema", "status", "epoch_id", "started_at", "epoch_key_sha256",
    "bootstrap_parent", "policy_sha256", "limits", "limits_sha256",
    "non_claims", "birth_sha256",
}
_ADOPTION_KEYS = {
    "schema", "status", "epoch_id", "started_at", "birth_sha256",
    "records_identity", "initial_journal_sha256", "non_claims",
    "adoption_sha256",
}
_MARKER_KEYS = {
    "schema", "epoch_id", "started_at", "birth_sha256", "adoption_sha256",
}
_IDENTITY_KEYS = {"dev", "ino", "mode", "uid", "gid"}
# A declared representation ceiling, reserved before directory creation. An
# observed identity outside it refuses; it is not rounded or stringified.
_IDENTITY_CEILING = (1 << 64) - 1
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError)
# A held read can retain thirteen separately bounded document images: request,
# two memo images, status, graph, live state, live candidate, two source
# archives, parent generation, birth, adoption and the outer held view.
# Arithmetic evidence: status=exact, parsed=13*16777216,
# exact=218103808. Exact rational arithmetic outside the Lean certificate
# chain; NOT formal-bounded.
MAX_HELD_AUTHORITY_DOCUMENTS = 13
MAX_HELD_AUTHORITY_BYTES = 218_103_808


class ControllerDeliveryEpochRefusal(ValueError):
    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = copy.deepcopy(getattr(upstream, "non_claims", ()))
        super().__init__("controller delivery epoch refused: " + reason)


def _refuse(reason):
    raise ControllerDeliveryEpochRefusal(reason)


def _keys(value, names, label):
    if type(value) is not dict or set(value) != names:
        _refuse(label + "-shape")


def _digest(value):
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _refuse("digest-shape")


def _held_authority_basis(owner):
    if type(MAX_HELD_AUTHORITY_DOCUMENTS) is not int \
            or MAX_HELD_AUTHORITY_DOCUMENTS <= 0 \
            or type(MAX_HELD_AUTHORITY_BYTES) is not int \
            or MAX_HELD_AUTHORITY_BYTES <= 0:
        _refuse("held-authority-capacity-contract")
    scaled = MAX_HELD_AUTHORITY_DOCUMENTS * owner["MAX_STATE_JSON_BYTES"]
    return {
        "max_documents": MAX_HELD_AUTHORITY_DOCUMENTS,
        "hard_bytes": MAX_HELD_AUTHORITY_BYTES,
        "effective_bytes": min(scaled, MAX_HELD_AUTHORITY_BYTES),
    }


def _raw(owner, value, *, ceiling=None):
    return source._component_bytes(owner, value, ceiling=ceiling)


def _sha(owner, value):
    return hashlib.sha256(_raw(owner, value)).hexdigest()


def _seal(owner, value, field):
    return {**value, field: _sha(owner, value)}


def _own(owner, value, field):
    return _sha(owner, {key: item for key, item in value.items() if key != field})


def _same(owner, left, right):
    return _raw(owner, left) == _raw(owner, right)


def _wire(owner, value, limits):
    ceiling = min(owner["MAX_STATE_JSON_BYTES"], limits["max_document_bytes"])
    raw = _raw(owner, value, ceiling=ceiling)
    if len(raw) >= ceiling:
        _refuse("document-wire-capacity")
    return raw + b"\n"


def _identity(info):
    value = {key: getattr(info, "st_" + key) for key in _IDENTITY_KEYS}
    if any(type(item) is not int or not 0 <= item <= _IDENTITY_CEILING
           for item in value.values()):
        _refuse("directory-identity-capacity")
    return value


def _empty(owner, epoch_id):
    value = {
        "schema": "sia-live-delivery-journal-v1", "epoch_id": epoch_id,
        "complete": True, "records": [], "pending": [],
        "non_claims": list(journal.NON_CLAIMS),
    }
    return _sha(owner, value)


def _marker(birth, adoption_sha256):
    return {
        "schema": "sia-controller-delivery-epoch-marker-v1",
        "epoch_id": birth["epoch_id"], "started_at": birth["started_at"],
        "birth_sha256": birth["birth_sha256"],
        "adoption_sha256": adoption_sha256,
    }


def _adoption(owner, birth, identity):
    return _seal(owner, {
        "schema": "sia-controller-delivery-epoch-adoption-v1",
        "status": "adopted-not-enabled", "epoch_id": birth["epoch_id"],
        "started_at": birth["started_at"], "birth_sha256": birth["birth_sha256"],
        "records_identity": identity,
        "initial_journal_sha256": _empty(owner, birth["epoch_id"]),
        "non_claims": list(NON_CLAIMS),
    }, "adoption_sha256")


def _result(birth, adoption):
    return {
        "schema": "sia-controller-delivery-epoch-v1",
        "status": "adopted-not-enabled", "birth": birth,
        "expected_birth_sha256": birth["birth_sha256"],
        "adoption": adoption,
        "expected_adoption_sha256": adoption["adoption_sha256"],
        "non_claims": list(NON_CLAIMS),
    }


class _Transaction:
    """Retain input and descriptor joins for preparation or held reads."""

    def __init__(self, owner, memo, request, stack, *, readonly=False):
        self.owner, self.memo, self.stack = owner, memo, stack
        if type(readonly) is not bool:
            _refuse("transaction-mode-contract")
        self.readonly = readonly
        if type(owner) is not dict or type(memo) is not dict:
            _refuse("owner-or-memo-shape")
        operations = ("corpus_owner", "_load_live_publication",
                      "_read_committed_live_generation")
        if not readonly:
            operations += ("brainstem_owner", "_memo_text", _BOUNDARY)
        for name in operations:
            if not callable(owner.get(name)):
                _refuse("owner-operation-contract")
        for name in ("MAX_STATE_JSON_BYTES", "MAX_MEMO_BYTES", "MAX_CONFIG_PATH_CHARS"):
            if type(owner.get(name)) is not int or owner[name] <= 0:
                _refuse("owner-capacity-contract")
        self.paths = {name: source._canonical_path(owner, owner[name]) for name in (
            _ROOT, "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH", "LIVE_STATE_PATH",
            "LIVE_CANDIDATE_PATH", "CONTROLLER_SOURCE_BATCH_PATH",
            "CONTROLLER_SOURCE_ARCHIVE_DIR", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
            "CORPUS", "STATE", "SHARE")}
        root = self.paths[_ROOT]
        if root == os.sep or ".gbrain" in root.split(os.sep) \
                or os.path.commonpath((root, self.paths["CORPUS"])) == self.paths["CORPUS"]:
            _refuse("epoch-root-authority-scope")
        self.capacities = {key: owner[key] for key in (
            "MAX_STATE_JSON_BYTES", "MAX_MEMO_BYTES", "MAX_CONFIG_PATH_CHARS")}
        self.held_authority = _held_authority_basis(owner)
        self.authority_ceiling = self.held_authority["effective_bytes"]
        self.owner_basis = source.native_bytes(owner, {
            "paths": self.paths,
            "capacities": self.capacities,
            "held_authority": self.held_authority,
        })
        self.request = request
        self.request_raw = source.native_bytes(owner, request)
        self.admitted = copy.deepcopy(request)
        if source.native_bytes(owner, self.admitted) != self.request_raw \
                or source.native_bytes(owner, request) != self.request_raw:
            _refuse("input-changed-during-admission")
        self.memo_raw = source.native_bytes(owner, memo, ceiling=owner["MAX_MEMO_BYTES"])
        self.limits = self.admitted["journal_limits"]
        journal._limits(self.limits)
        _digest(self.admitted["expected_journal_limits_sha256"])
        if _sha(owner, self.limits) != self.admitted["expected_journal_limits_sha256"]:
            _refuse("journal-limits-pin")
        self.external = self.admitted["expected_adoption_sha256"]
        if self.external is not None:
            _digest(self.external)
        self.files, self.directories = {}, {}
        self.epoch_directory = None
        self.epoch_entries = None
        self.record_directory = None
        self.legacy = None
        self.generation_raw = None
        self.budget = len(self.request_raw) + len(self.memo_raw)
        self.observe("memo", self.paths["MEMO_PATH"], owner["MAX_MEMO_BYTES"], required=True)
        if source.native_bytes(owner, self.files["memo"].value,
                               ceiling=owner["MAX_MEMO_BYTES"]) != self.memo_raw:
            _refuse("memo-authority")
        self.observe("source-slot", self.paths["CONTROLLER_SOURCE_BATCH_PATH"],
                     owner["MAX_STATE_JSON_BYTES"])
        self.admit_source_slot()

    def admit_source_slot(self):
        if self.files["source-slot"].raw is not None:
            _refuse("successor-wal-must-be-recovered-first")

    def observe(self, name, path, ceiling, *, required=False, document=False):
        held = source.HeldFile(self.owner, path, ceiling, allow_absent=not required)
        self.stack.callback(held.close)
        if held.generation is not None and stat.S_IMODE(held.generation["mode"]) != 0o600:
            _refuse("authority-file-not-private")
        if document and held.raw is not None and held.raw != _wire(self.owner, held.value, self.limits):
            _refuse("epoch-document-not-canonical")
        previous = self.files.get(name)
        before = 0 if previous is None or previous.raw is None else len(previous.raw)
        after = 0 if held.raw is None else len(held.raw)
        self.budget += after - before
        if self.budget > self.authority_ceiling:
            _refuse("complete-authority-byte-capacity")
        self.files[name] = held
        return held

    def hold_directory(self, name, path):
        held = source._DirectoryChain(self.owner, path, private_terminal=True)
        self.stack.callback(held.close)
        self.directories[name] = held
        return held

    def inputs_current(self):
        owner = self.owner
        current_basis = {
            "paths": {name: owner.get(name) for name in self.paths},
            "capacities": {key: owner.get(key) for key in (
                "MAX_STATE_JSON_BYTES", "MAX_MEMO_BYTES", "MAX_CONFIG_PATH_CHARS")},
            "held_authority": _held_authority_basis(owner),
        }
        if source.native_bytes(owner, current_basis,
                               ceiling=self.capacities["MAX_STATE_JSON_BYTES"]) != self.owner_basis:
            _refuse("owner-path-or-capacity-changed")
        if source.native_bytes(owner, self.request) != self.request_raw \
                or source.native_bytes(owner, self.admitted) != self.request_raw \
                or source.native_bytes(owner, self.memo, ceiling=owner["MAX_MEMO_BYTES"]) != self.memo_raw:
            _refuse("input-or-memo-changed")
        if self.generation_raw is not None:
            if _raw(owner, self.generation,
                    ceiling=self.capacities["MAX_STATE_JSON_BYTES"]) != self.generation_raw \
                    or self.generation.get("generation_sha256") \
                    != self.admitted["committed"]["live_generation_sha256"]:
                _refuse("held-parent-generation-changed")

    def current(self):
        self.inputs_current()
        for directory in self.directories.values():
            directory.current()
        for name, held in self.files.items():
            held.current()
            if name in ("birth", "adoption") and held.raw is not None \
                    and _wire(self.owner, held.value, self.limits) != held.raw:
                _refuse("retained-epoch-document-value-changed")
        if self.epoch_directory is not None:
            with os.scandir(self.epoch_directory.fd) as entries:
                names = set()
                for entry in entries:
                    if entry.name not in {"birth.json", "adoption.json", "records"}:
                        _refuse("epoch-unrecognized-entry")
                    names.add(entry.name)
            if names != self.epoch_entries:
                _refuse("epoch-entry-roster-changed")
        if self.record_directory is not None and self.legacy:
            with os.scandir(self.record_directory.fd) as entries:
                if next(entries, None) is not None:
                    _refuse("legacy-epoch-has-unadmitted-records")
        self.inputs_current()

    def boundary(self, phase):
        self.require_preparation()
        self.current()
        self.owner[_BOUNDARY](phase)
        self.current()

    def require_preparation(self):
        if self.readonly:
            _refuse("held-epoch-effect-not-authorized")

    def source_predecessor(self):
        """The ordinary transaction requires the strict completed reader."""
        completed = acknowledgment.read_completed(
            self.owner, memo=self.memo,
            admitted_status=self.admitted["admitted_status"])
        _keys(completed, {"status", "batch", "committed"}, "completed-source-view")
        if completed["status"] != "available":
            _refuse("actual-source-predecessor-differs")
        return completed["batch"], completed["committed"]

    def parent(self):
        owner, request = self.owner, self.admitted
        retained, committed, status = (request[key] for key in (
            "retained_batch", "committed", "admitted_status"))
        _keys(committed, set(publication.COMMITTED_KEYS), "completed-source")
        for value in committed.values():
            _digest(value)
        if not _same(owner, self.memo.get("controller_source_committed"), committed) \
                or publication.SUCCESSOR_PENDING_KEYS.intersection(self.memo):
            _refuse("completed-source-authority")
        owner["_load_live_publication"]()
        for name in ("STATUS_PATH", "GRAPH_PATH", "LIVE_STATE_PATH", "LIVE_CANDIDATE_PATH"):
            self.observe(name, self.paths[name], owner["MAX_STATE_JSON_BYTES"], required=True)
        self.observe("source-archive", os.path.join(self.paths["CONTROLLER_SOURCE_ARCHIVE_DIR"],
                     committed["source_batch_sha256"] + ".json"), owner["MAX_STATE_JSON_BYTES"], required=True)
        self.observe("effects-archive", os.path.join(self.paths["CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR"],
                     committed["source_effects_receipt_sha256"] + ".json"), owner["MAX_STATE_JSON_BYTES"], required=True)
        observed_batch, observed_committed = self.source_predecessor()
        if not _same(owner, observed_batch, retained) \
                or not _same(owner, observed_committed, committed):
            _refuse("actual-source-predecessor-differs")
        view = owner["_read_committed_live_generation"](memo=self.memo, admitted_status=status)
        if type(view) is not dict or view.get("status") != "available" \
                or type(view.get("generation")) is not dict:
            _refuse("actual-live-predecessor-unavailable")
        generation = view["generation"]
        if generation.get("generation_sha256") != committed["live_generation_sha256"] \
                or _own(owner, generation, "generation_sha256") != committed["live_generation_sha256"]:
            _refuse("actual-live-predecessor-pin")
        transition = generation["transition"]
        state = transition["state"]
        if _own(owner, transition, "transition_sha256") != generation["transition_sha256"] \
                or transition["transition_sha256"] != generation["transition_sha256"] \
                or _sha(owner, state) != generation["state_sha256"] \
                or transition["state_sha256"] != generation["state_sha256"]:
            _refuse("actual-live-state-binding")
        epoch = retained["epoch"]
        if state["epoch_id"] != epoch["epoch_id"] \
                or state["intake"]["started_at"] != epoch["started_at"] \
                or state["policy_sha256"] != epoch["expected_live_policy_sha256"] \
                or not _same(owner, state["policy"], epoch["live_policy"]):
            _refuse("actual-source-live-epoch-binding")
        schema = retained["schema"]
        self.legacy = schema in ("sia-controller-source-batch-v1", "sia-controller-source-batch-v2")
        if self.legacy:
            deliveries = state["deliveries"]
            _keys(deliveries, {"schema", "epoch_id", "complete", "records"}, "legacy-deliveries")
            if deliveries["schema"] != "sia-live-deliveries-v1" \
                    or deliveries["epoch_id"] != epoch["epoch_id"] \
                    or deliveries["complete"] is not True \
                    or type(deliveries["records"]) is not list or deliveries["records"]:
                _refuse("legacy-parent-must-have-no-deliveries")
        elif schema == "sia-controller-source-batch-v3":
            wrapper = retained.get("delivery_input")
            if type(wrapper) is not dict or self.external is None \
                    or wrapper.get("expected_adoption_sha256") != self.external:
                _refuse("parent-v3-adoption-pin-required")
        else:
            _refuse("parent-source-schema")
        self.current()
        if self.readonly:
            generation_raw = _raw(
                owner, generation, ceiling=self.capacities["MAX_STATE_JSON_BYTES"])
            self.budget += len(generation_raw)
            if self.budget > self.authority_ceiling:
                _refuse("complete-held-authority-byte-capacity")
            detached_generation = copy.deepcopy(generation)
            if _raw(owner, generation) != generation_raw \
                    or _raw(owner, detached_generation) != generation_raw:
                _refuse("held-parent-generation-copy-changed")
            generation = detached_generation
            self.generation_raw = generation_raw
        self.epoch, self.generation = epoch, generation
        self.epoch_key = _sha(owner, {
            "schema": "sia-controller-delivery-epoch-path-v1",
            "epoch_id": epoch["epoch_id"], "started_at": epoch["started_at"],
        })
        # All destination and staging paths are statically known now. Admit
        # their capacities before creating any part of the storage tree.
        epoch_path = os.path.join(self.paths[_ROOT], self.epoch_key)
        self.epoch_paths = {name: source._canonical_path(owner, path)
                            for name, path in {
                                "epoch": epoch_path,
                                "birth": os.path.join(epoch_path, "birth.json"),
                                "adoption": os.path.join(epoch_path, "adoption.json"),
                                "records": os.path.join(epoch_path, "records"),
                            }.items()}
        self.staging_paths = {}
        if not self.readonly:
            roots = tuple(self.paths[name] for name in (_ROOT, "CORPUS", "STATE", "SHARE"))
            for name, path in {"memo": self.paths["MEMO_PATH"],
                               "birth": self.epoch_paths["birth"],
                               "adoption": self.epoch_paths["adoption"]}.items():
                staging = source._canonical_path(
                    owner, owner["siaqueue"].staging_dir_for(path, authority_roots=roots))
                for leaf in (owner["siaqueue"].STAGING_LOCK_NAME,
                             owner["siaqueue"].STAGING_PAYLOAD_NAME):
                    source._canonical_path(owner, os.path.join(staging, leaf))
                self.staging_paths[name] = staging
        birth = _seal(owner, {
            "schema": "sia-controller-delivery-epoch-birth-v1",
            "status": "birth-pending", "epoch_id": epoch["epoch_id"],
            "started_at": epoch["started_at"], "epoch_key_sha256": self.epoch_key,
            "bootstrap_parent": {
                "source_batch_sha256": retained["batch_sha256"],
                "live_generation_sha256": committed["live_generation_sha256"],
                "state_sha256": generation["state_sha256"],
            },
            "policy_sha256": epoch["expected_live_policy_sha256"],
            "limits": copy.deepcopy(self.limits),
            "limits_sha256": request["expected_journal_limits_sha256"],
            "non_claims": list(NON_CLAIMS),
        }, "birth_sha256")
        if self.readonly:
            # Existing-only observation does not need prospective writer
            # staging paths or future memo images. The full held view has its
            # own combined representation admission before its first copy.
            self.current()
            return birth
        # Reserve both documents, result and both complete future memo images
        # before root or records creation. The actual identity must fit this
        # declared integer representation; every retained byte is rechecked.
        prototype = _adoption(owner, birth, {key: _IDENTITY_CEILING for key in _IDENTITY_KEYS})
        reserved = self.budget
        for value in (birth, prototype, _result(birth, prototype)):
            reserved += len(_wire(owner, value, self.limits))
        future_memo = len(self.files["memo"].raw)
        for pin in (None, prototype["adoption_sha256"]):
            prospective = {**self.memo, _MARKER: _marker(birth, pin)}
            future_memo = max(future_memo, len(source.native_bytes(
                owner, prospective, ceiling=owner["MAX_MEMO_BYTES"])))
            owner["_memo_text"](prospective)
        reserved += future_memo - len(self.files["memo"].raw)
        if reserved > self.authority_ceiling:
            _refuse("complete-adoption-reservation-capacity")
        self.current()
        return birth

    def directories_for(self, *, must_exist, persist=True):
        if type(must_exist) is not bool or type(persist) is not bool \
                or (not persist and not must_exist):
            _refuse("epoch-directory-mode-contract")
        if persist:
            self.require_preparation()
        root = self.paths[_ROOT]
        parent = source._DirectoryChain(self.owner, os.path.dirname(root))
        self.stack.callback(parent.close)
        self.directories["root-parent"] = parent
        for name, path, leaf in (("root", root, os.path.basename(root)),
                                 ("epoch", self.epoch_paths["epoch"], self.epoch_key)):
            self.current()
            try:
                observed = os.stat(leaf, dir_fd=parent.fd, follow_symlinks=False)
            except FileNotFoundError:
                if must_exist:
                    _refuse("pinned-epoch-directory-missing")
                os.mkdir(leaf, 0o700, dir_fd=parent.fd)
            else:
                if not stat.S_ISDIR(observed.st_mode):
                    _refuse("epoch-directory-not-ordinary")
            # Retry may see mkdir's entry before the creating process
            # persisted it. Flush its held parent even for an existing leaf,
            # before any child directory or publication can depend on it.
            if persist:
                os.fsync(parent.fd)
            parent.current()
            parent = self.hold_directory(name, path)
            if persist:
                os.fsync(parent.fd)
        self.epoch_directory = parent
        with os.scandir(parent.fd) as entries:
            self.epoch_entries = set()
            for entry in entries:
                if entry.name not in {"birth.json", "adoption.json", "records"}:
                    _refuse("epoch-unrecognized-entry")
                self.epoch_entries.add(entry.name)
        ceiling = min(self.owner["MAX_STATE_JSON_BYTES"], self.limits["max_document_bytes"])
        for name in ("birth", "adoption"):
            self.observe(name, self.epoch_paths[name], ceiling, document=True)
        if "records" in self.epoch_entries:
            self.record_directory = self.hold_directory("records", self.epoch_paths["records"])
        self.current()

    def publish_document(self, name, value):
        self.require_preparation()
        raw = _wire(self.owner, value, self.limits)
        held = self.files[name]
        if held.raw is not None:
            if held.raw != raw:
                _refuse("immutable-epoch-document-differs")
            self.current()
            return
        self.current()
        self.owner["siaqueue"].fixed_atomic_publish(
            held.path, raw, mode=0o600, exclusive=True, nonblocking=True,
            destination_dir_fd=self.epoch_directory.fd,
            staging_dir=self.staging_paths[name])
        refreshed = self.observe(name, held.path, held.ceiling, required=True, document=True)
        self.epoch_entries.add(name + ".json")
        if refreshed.raw != raw or refreshed.parent_identity != held.parent_identity:
            _refuse("epoch-publication-readback")
        self.current()

    def publish_marker(self, marker):
        self.require_preparation()
        owner = self.owner
        if _MARKER in self.memo and _same(owner, self.memo[_MARKER], marker):
            self.current()
            return
        updated = {**self.memo, _MARKER: marker}
        raw = source.native_bytes(owner, updated, ceiling=owner["MAX_MEMO_BYTES"])
        owner["_memo_text"](updated)
        detached = copy.deepcopy(updated)
        if source.native_bytes(owner, detached, ceiling=owner["MAX_MEMO_BYTES"]) != raw:
            _refuse("memo-copy-changed")
        self.current()
        prior = self.files["memo"]
        owner["siaqueue"].fixed_atomic_publish(
            prior.path, raw, mode=0o600, exclusive=False, nonblocking=True,
            destination_dir_fd=prior.directories.fd,
            staging_dir=self.staging_paths["memo"])
        self.inputs_current()
        held = self.observe("memo", prior.path, owner["MAX_MEMO_BYTES"], required=True)
        if held.raw != raw or held.parent_identity != prior.parent_identity:
            _refuse("epoch-memo-publication-readback")
        self.memo.clear()
        self.memo.update(detached)
        self.memo_raw = raw
        self.current()

    def persist_retained_marker(self):
        self.require_preparation()
        # A previous process can die after replacing the memo but before its
        # parent-directory flush. Readable bytes alone do not close that cut.
        # Sync the held parent without replacing the retained memo generation.
        self.current()
        os.fsync(self.files["memo"].directories.fd)
        self.current()

    def records_create(self):
        self.require_preparation()
        if self.record_directory is not None:
            self.current()
            return
        self.current()
        os.mkdir("records", 0o700, dir_fd=self.epoch_directory.fd)
        os.fsync(self.epoch_directory.fd)
        self.record_directory = self.hold_directory(
            "records", self.epoch_paths["records"])
        self.epoch_entries.add("records")
        os.fsync(self.record_directory.fd)
        self.current()


class _CaptureTransaction(_Transaction):
    """Read-only parent observation for one immutable, explicitly pinned fence.

    Preparation and ordinary held reads never instantiate this transaction.
    Its distinct predecessor reader validates capturability, not completion;
    the shared parent checks receive only its joined batch and commit images.
    """

    def __init__(self, owner, memo, request, stack):
        if type(owner) is not dict:
            _refuse("owner-contract")
        self.notification_key = owner.get("NOTIFY_BASELINE_ATTEMPT_KEY")
        if type(self.notification_key) is not str or not self.notification_key:
            _refuse("capture-notification-key-contract")
        _keys(request, {
            "admitted_status", "retained_batch", "committed", "journal_limits",
            "expected_journal_limits_sha256", "expected_adoption_sha256",
            "notification_baseline_attempt",
            "expected_notification_baseline_attempt_sha256",
        }, "capture-epoch-request")
        super().__init__(owner, memo, request, stack, readonly=True)
        marker = self.admitted["notification_baseline_attempt"]
        pin = self.admitted["expected_notification_baseline_attempt_sha256"]
        _digest(pin)
        actual = source._notification_marker(owner, memo)
        if marker is None or actual is None \
                or not _same(owner, marker, actual) \
                or source.native_sha(owner, marker) != pin:
            _refuse("capture-notification-fence-pin")
        self.current()

    def inputs_current(self):
        if self.owner.get("NOTIFY_BASELINE_ATTEMPT_KEY") != self.notification_key:
            _refuse("capture-notification-key-changed")
        super().inputs_current()
        if self.owner.get("NOTIFY_BASELINE_ATTEMPT_KEY") != self.notification_key:
            _refuse("capture-notification-key-changed")

    def source_predecessor(self):
        owner, request = self.owner, self.admitted
        view = acknowledgment.read_capturable_predecessor(
            owner, memo=self.memo, admitted_status=request["admitted_status"],
            committed=request["committed"],
            notification_baseline_attempt=request["notification_baseline_attempt"],
            expected_notification_baseline_attempt_sha256=
                request["expected_notification_baseline_attempt_sha256"])
        _keys(view, {
            "schema", "status", "batch", "committed",
            "notification_baseline_attempt",
            "expected_notification_baseline_attempt_sha256", "non_claims",
        }, "capturable-source-view")
        if view["schema"] != "sia-controller-source-capturable-predecessor-v1" \
                or view["status"] != "capturable-not-ready" \
                or not _same(owner, view["notification_baseline_attempt"],
                             request["notification_baseline_attempt"]) \
                or view["expected_notification_baseline_attempt_sha256"] \
                != request["expected_notification_baseline_attempt_sha256"] \
                or view["non_claims"] != list(acknowledgment.CAPTURE_NON_CLAIMS):
            _refuse("capturable-source-view-binding")
        self.current()
        return view["batch"], view["committed"]


def _validate_birth(tx, value, expected):
    owner = tx.owner
    _keys(value, _BIRTH_KEYS, "birth")
    _digest(value["birth_sha256"])
    _keys(value["bootstrap_parent"], {
        "source_batch_sha256", "live_generation_sha256", "state_sha256"}, "birth-parent")
    for pin in value["bootstrap_parent"].values():
        _digest(pin)
    if value["schema"] != "sia-controller-delivery-epoch-birth-v1" \
            or value["status"] != "birth-pending" \
            or value["epoch_id"] != tx.epoch["epoch_id"] \
            or not _same(owner, value["started_at"], tx.epoch["started_at"]) \
            or value["epoch_key_sha256"] != tx.epoch_key \
            or value["policy_sha256"] != tx.epoch["expected_live_policy_sha256"] \
            or not _same(owner, value["limits"], tx.limits) \
            or value["limits_sha256"] != tx.admitted["expected_journal_limits_sha256"] \
            or value["non_claims"] != list(NON_CLAIMS) \
            or _own(owner, value, "birth_sha256") != value["birth_sha256"]:
        _refuse("birth-epoch-or-content-binding")
    if tx.legacy and not _same(owner, value, expected):
        _refuse("legacy-bootstrap-parent-changed")


def _validate_marker(tx, marker, birth):
    _keys(marker, _MARKER_KEYS, "epoch-marker")
    if marker["adoption_sha256"] is not None:
        _digest(marker["adoption_sha256"])
    if not _same(tx.owner, marker, _marker(birth, marker["adoption_sha256"])):
        _refuse("epoch-marker-birth-binding")


def _finish(tx, birth):
    adoption = tx.files["adoption"].value
    if adoption is None or tx.record_directory is None:
        _refuse("adopted-storage-missing")
    _keys(adoption, _ADOPTION_KEYS, "adoption")
    expected = _adoption(tx.owner, birth, _identity(os.fstat(tx.record_directory.fd)))
    if not _same(tx.owner, adoption, expected):
        _refuse("adoption-directory-or-content-binding")
    if tx.external is not None and adoption["adoption_sha256"] != tx.external:
        _refuse("external-adoption-pin-differs")
    if not _same(tx.owner, tx.memo.get(_MARKER), _marker(birth, adoption["adoption_sha256"])):
        _refuse("adopted-memo-binding")
    result = _result(birth, adoption)
    encoded = _wire(tx.owner, result, tx.limits)
    tx.current()
    detached = copy.deepcopy(result)
    if _wire(tx.owner, detached, tx.limits) != encoded \
            or _wire(tx.owner, result, tx.limits) != encoded:
        _refuse("epoch-result-copy-changed")
    tx.current()
    return detached


class _HeldEpoch:
    """An existing generation held only through its caller's context body."""

    def __init__(self, tx, adopted):
        self._tx = tx
        self._closed = False
        tx.current()
        view = self._make_view(tx, adopted)
        # A full generation is deliberately exposed, not an unpinned summary.
        # Admit its complete outer view together with held authority bytes
        # before copying. Journal document limits still govern the retained
        # birth/adoption documents, not a newly invented journal record.
        self._view_raw = self._encode(view)
        if tx.budget + len(self._view_raw) > tx.authority_ceiling:
            _refuse("complete-held-view-byte-capacity")
        self._view = copy.deepcopy(view)
        if self._encode(view) != self._view_raw \
                or self._encode(self._view) != self._view_raw:
            _refuse("held-epoch-view-copy-changed")
        self.current()

    def _make_view(self, tx, adopted):
        return {
            "schema": "sia-controller-delivery-epoch-view-v1",
            "status": "held-not-consumed",
            "epoch_adoption": adopted,
            "parent_committed": tx.admitted["committed"],
            "parent_generation": tx.generation,
            "expected_parent_generation_sha256":
                tx.admitted["committed"]["live_generation_sha256"],
            "records_directory": tx.record_directory.path,
            "records_identity": adopted["adoption"]["records_identity"],
            "non_claims": list(HELD_NON_CLAIMS),
        }

    def _encode(self, value):
        return _raw(self._tx.owner, value,
                    ceiling=self._tx.capacities["MAX_STATE_JSON_BYTES"])

    def current(self):
        try:
            if self._closed:
                _refuse("held-epoch-closed")
            self._tx.current()
            if self._encode(self._view) != self._view_raw:
                _refuse("held-epoch-view-changed")
            self._tx.current()
        except ControllerDeliveryEpochRefusal:
            raise
        except _ERRORS as exc:
            raise ControllerDeliveryEpochRefusal(
                "held-epoch-domain-refused", upstream=exc) from exc

    def read(self):
        try:
            self.current()
            detached = copy.deepcopy(self._view)
            if self._encode(detached) != self._view_raw \
                    or self._encode(self._view) != self._view_raw:
                _refuse("held-epoch-view-copy-changed")
            self.current()
            return detached
        except ControllerDeliveryEpochRefusal:
            raise
        except _ERRORS as exc:
            raise ControllerDeliveryEpochRefusal(
                "held-epoch-domain-refused", upstream=exc) from exc

    def _retire(self):
        # Refuse access before descriptor numbers can be closed and recycled.
        self._closed = True


class _HeldCapturableEpoch(_HeldEpoch):
    """The same immutable lifetime with a distinct non-readiness view."""

    def _make_view(self, tx, adopted):
        view = super()._make_view(tx, adopted)
        view.update({
            "schema": "sia-controller-delivery-epoch-capture-view-v1",
            "status": "held-capturable-not-ready",
            "notification_baseline_attempt":
                tx.admitted["notification_baseline_attempt"],
            "expected_notification_baseline_attempt_sha256":
                tx.admitted["expected_notification_baseline_attempt_sha256"],
            "non_claims": list(CAPTURE_HELD_NON_CLAIMS),
        })
        return view


def _require_entered_corpus(owner):
    """Check the core's entered scope without creating or acquiring a lease.

    A raw inherited descriptor is not an entered scope. Its caller must
    first use the ordinary core owner context, which validates that handoff.
    This check never closes or changes the caller's descriptor or lock.
    """
    depth = owner["_CORPUS_OWNER_DEPTH"].get()
    descriptor = owner["_CORPUS_OWNER_FD"].get()
    if type(depth) is not int or depth <= 0 \
            or type(descriptor) is not int or descriptor < 0:
        _refuse("entered-corpus-scope-required")
    observed = os.fstat(descriptor)
    if not stat.S_ISREG(observed.st_mode) \
            or observed.st_uid != os.geteuid() \
            or stat.S_IMODE(observed.st_mode) != 0o600 \
            or observed.st_nlink != 1:
        _refuse("entered-corpus-descriptor-contract")
    path = source._canonical_path(owner, owner["CORPUS_OWNER_LOCK"])
    if path == os.sep or ".gbrain" in path.split(os.sep):
        _refuse("entered-corpus-path-contract")
    with contextlib.closing(source._DirectoryChain(
            owner, os.path.dirname(path))) as parent:
        named = os.stat(os.path.basename(path), dir_fd=parent.fd,
                        follow_symlinks=False)
        if _identity(named) != _identity(observed) or named.st_nlink != 1:
            _refuse("entered-corpus-descriptor-name-binding")
        parent.current()
        current = os.fstat(descriptor)
        if _identity(current) != _identity(observed) or current.st_nlink != 1:
            _refuse("entered-corpus-descriptor-changed")


@contextlib.contextmanager
def hold_epoch(owner, *, memo, admitted_status, retained_batch, committed,
               journal_limits, expected_journal_limits_sha256,
               expected_adoption_sha256):
    """Hold an existing source-bound epoch without storage effects.

    The caller already owns the ordinary corpus lease; this reader nests it
    for its entire lifetime and never requests the resident brainstem lease.
    Unentered or invalid scoped ownership refuses before any owner call.
    Existing marker/adoption generations must match the nonnull external pin.
    This is an observation, not a replay of prepare_epoch's durability steps.
    Legacy first-v3 capture must settle that preparation before entering here.

    Journal acquisition and its independent directory-identity join remain
    separate. Close this handle before publishing a successor source slot,
    retaining the caller's outer corpus lease across the phase boundary.
    Normal exit revalidates; exceptional exit preserves the caller exception.
    """
    with contextlib.ExitStack() as stack:
        try:
            if type(owner) is not dict or not callable(owner.get("corpus_owner")):
                _refuse("owner-contract")
            _digest(expected_adoption_sha256)
            _require_entered_corpus(owner)
            stack.enter_context(owner["corpus_owner"]())
            tx = _Transaction(owner, memo, {
                "admitted_status": admitted_status, "retained_batch": retained_batch,
                "committed": committed, "journal_limits": journal_limits,
                "expected_journal_limits_sha256": expected_journal_limits_sha256,
                "expected_adoption_sha256": expected_adoption_sha256,
            }, stack, readonly=True)
            expected_birth = tx.parent()
            marker = memo.get(_MARKER)
            _keys(marker, _MARKER_KEYS, "epoch-marker")
            if marker["adoption_sha256"] != tx.external:
                _refuse("external-adoption-marker-pin")
            tx.directories_for(must_exist=True, persist=False)
            if tx.files["birth"].raw is None:
                _refuse("retained-birth-document-missing")
            birth = tx.files["birth"].value
            _validate_birth(tx, birth, expected_birth)
            _validate_marker(tx, marker, birth)
            adopted = _finish(tx, birth)
            held = _HeldEpoch(tx, adopted)
            held.current()
        except ControllerDeliveryEpochRefusal:
            raise
        except _ERRORS as exc:
            raise ControllerDeliveryEpochRefusal(
                "held-epoch-domain-refused", upstream=exc) from exc

        # Do not place the yield under the entry-domain error conversion.
        # A caller's ValueError, RuntimeError, SystemExit or KeyboardInterrupt
        # remains that original exception, even if its body changed a file.
        try:
            yield held
        except BaseException:
            raise
        else:
            held.current()
        finally:
            held._retire()


@contextlib.contextmanager
def hold_capturable_epoch(
        owner, *, memo, admitted_status, retained_batch, committed,
        journal_limits, expected_journal_limits_sha256,
        expected_adoption_sha256, notification_baseline_attempt,
        expected_notification_baseline_attempt_sha256):
    """Hold existing adopted storage under one explicit notification fence.

    Enter only after preparation and the collector's permitted memo mutation,
    while the caller continuously owns the ordinary corpus lease. Both the
    actual fenced memo and separately supplied marker/pin remain immutable
    throughout this handle. Neither this context nor its parent reader
    establishes readiness, clears a fence, repairs storage or enables output.

    The source slot must remain absent. Acquire a separate held journal and
    join its observed directory identity to this adoption before constructing
    delivery input. Close both handles after final input copies but before
    fixed-slot publication, retaining the caller's outer corpus lease.
    """
    with contextlib.ExitStack() as stack:
        try:
            if type(owner) is not dict or not callable(owner.get("corpus_owner")):
                _refuse("owner-contract")
            _digest(expected_adoption_sha256)
            _digest(expected_notification_baseline_attempt_sha256)
            _require_entered_corpus(owner)
            stack.enter_context(owner["corpus_owner"]())
            tx = _CaptureTransaction(owner, memo, {
                "admitted_status": admitted_status, "retained_batch": retained_batch,
                "committed": committed, "journal_limits": journal_limits,
                "expected_journal_limits_sha256": expected_journal_limits_sha256,
                "expected_adoption_sha256": expected_adoption_sha256,
                "notification_baseline_attempt": notification_baseline_attempt,
                "expected_notification_baseline_attempt_sha256":
                    expected_notification_baseline_attempt_sha256,
            }, stack)
            expected_birth = tx.parent()
            marker = memo.get(_MARKER)
            _keys(marker, _MARKER_KEYS, "epoch-marker")
            if marker["adoption_sha256"] != tx.external:
                _refuse("external-adoption-marker-pin")
            tx.directories_for(must_exist=True, persist=False)
            if tx.files["birth"].raw is None:
                _refuse("retained-birth-document-missing")
            birth = tx.files["birth"].value
            _validate_birth(tx, birth, expected_birth)
            _validate_marker(tx, marker, birth)
            adopted = _finish(tx, birth)
            held = _HeldCapturableEpoch(tx, adopted)
            held.current()
        except ControllerDeliveryEpochRefusal:
            raise
        except _ERRORS as exc:
            raise ControllerDeliveryEpochRefusal(
                "capture-held-epoch-domain-refused", upstream=exc) from exc

        # As in ordinary hold_epoch, body exceptions keep their own identity;
        # successful exit performs a final check before owned handles retire.
        try:
            yield held
        except BaseException:
            raise
        else:
            held.current()
        finally:
            held._retire()


class _CheckpointWALSlot:
    def __init__(self, *args, checkpoint_batch, expected_checkpoint_batch_sha256, **kwargs):
        self.checkpoint_batch = checkpoint_batch
        self.checkpoint_pin = expected_checkpoint_batch_sha256
        self.checkpoint_raw = None
        super().__init__(*args, **kwargs)

    def admit_source_slot(self):
        import siasourcecheckpoint
        raw = source.native_bytes(self.owner, self.checkpoint_batch)
        siasourcecheckpoint.validate_capture(self.owner, self.checkpoint_batch, self.checkpoint_pin)
        if self.checkpoint_batch["schema"] != "sia-controller-source-checkpoint-capture-v3" \
                or self.files["source-slot"].raw != raw \
                or not _same(self.owner, self.checkpoint_batch["epoch"]["predecessor"], self.admitted["committed"]) \
                or not _same(self.owner, self.checkpoint_batch["notification_baseline_attempt"],
                             source._notification_marker(self.owner, self.memo)):
            _refuse("checkpoint-wal-source-binding")
        self.checkpoint_raw = raw

    def inputs_current(self):
        super().inputs_current()
        if self.checkpoint_raw is not None and (
                source.native_bytes(self.owner, self.checkpoint_batch) != self.checkpoint_raw \
                or self.checkpoint_batch["batch_sha256"] != self.checkpoint_pin):
            _refuse("checkpoint-wal-input-changed")


class _CheckpointWALTransaction(_CheckpointWALSlot, _Transaction):
    pass


class _CheckpointWALCaptureTransaction(_CheckpointWALSlot, _CaptureTransaction):
    pass


@contextlib.contextmanager
def hold_checkpoint_wal_epoch(owner, *, memo, admitted_status, retained_batch, committed,
                              journal_limits, expected_journal_limits_sha256, expected_adoption_sha256,
                              checkpoint_batch, expected_checkpoint_batch_sha256,
                              notification_baseline_attempt, expected_notification_baseline_attempt_sha256):
    """Observe only an exact validated compact WAL under its actual predecessor.

    Ordinary holds retain their absent-slot contract. This recovery-only hold
    neither adopts that WAL nor permits output, clears a fence or repairs data.
    The original request, held-authority and artifact ceilings still apply.
    """
    with contextlib.ExitStack() as stack:
        _digest(expected_adoption_sha256)
        _require_entered_corpus(owner)
        stack.enter_context(owner["corpus_owner"]())
        request = dict(admitted_status=admitted_status, retained_batch=retained_batch, committed=committed,
                       journal_limits=journal_limits, expected_journal_limits_sha256=expected_journal_limits_sha256,
                       expected_adoption_sha256=expected_adoption_sha256)
        options = dict(checkpoint_batch=checkpoint_batch, expected_checkpoint_batch_sha256=expected_checkpoint_batch_sha256)
        if notification_baseline_attempt is None:
            if expected_notification_baseline_attempt_sha256 is not None:
                _refuse("checkpoint-wal-absent-fence-pin")
            tx = _CheckpointWALTransaction(owner, memo, request, stack, readonly=True, **options)
            held_type = _HeldEpoch
        else:
            request.update(notification_baseline_attempt=notification_baseline_attempt,
                           expected_notification_baseline_attempt_sha256=expected_notification_baseline_attempt_sha256)
            tx = _CheckpointWALCaptureTransaction(owner, memo, request, stack, **options)
            held_type = _HeldCapturableEpoch
        expected_birth = tx.parent()
        marker = memo.get(_MARKER)
        _keys(marker, _MARKER_KEYS, "epoch-marker")
        if marker["adoption_sha256"] != tx.external:
            _refuse("external-adoption-marker-pin")
        tx.directories_for(must_exist=True, persist=False)
        if tx.files["birth"].raw is None:
            _refuse("retained-birth-document-missing")
        birth = tx.files["birth"].value
        _validate_birth(tx, birth, expected_birth)
        _validate_marker(tx, marker, birth)
        held = held_type(tx, _finish(tx, birth))
        try:
            held.current()
            yield held
            held.current()
        finally:
            held._retire()


def prepare_epoch(owner, *, memo, admitted_status, retained_batch, committed,
                  journal_limits, expected_journal_limits_sha256,
                  expected_adoption_sha256):
    """Prepare exact adopted storage, or refuse without fabricating history.

    The caller's memo is synchronized only after each durable marker readback.
    A killed process must reload that memo before retrying. An already adopted
    epoch replays directory durability barriers without replacing retained
    publications; it is not another adoption or output. Use hold_epoch only
    for the separate existing-generation, no-fsync observation contract.
    """
    try:
        if type(owner) is not dict \
                or not callable(owner.get("brainstem_owner")) \
                or not callable(owner.get("corpus_owner")):
            _refuse("owner-contract")
        with owner["brainstem_owner"](), owner["corpus_owner"](), contextlib.ExitStack() as stack:
            tx = _Transaction(owner, memo, {
                "admitted_status": admitted_status, "retained_batch": retained_batch,
                "committed": committed, "journal_limits": journal_limits,
                "expected_journal_limits_sha256": expected_journal_limits_sha256,
                "expected_adoption_sha256": expected_adoption_sha256,
            }, stack)
            expected_birth = tx.parent()
            marker = memo.get(_MARKER)
            if _MARKER in memo:
                _keys(marker, _MARKER_KEYS, "epoch-marker")
            committed_adoption = marker is not None and marker["adoption_sha256"] is not None
            if tx.external is not None or not tx.legacy:
                if not committed_adoption:
                    _refuse("externally-pinned-adoption-marker-missing")
                if marker["adoption_sha256"] != tx.external:
                    _refuse("external-adoption-marker-pin")
            if tx.legacy and marker is not None:
                _validate_marker(tx, marker, expected_birth)
            tx.directories_for(must_exist=(marker is not None or tx.external is not None or not tx.legacy))
            birth_file, adoption_file = tx.files["birth"], tx.files["adoption"]
            if marker is not None and birth_file.raw is None:
                _refuse("retained-birth-document-missing")
            if marker is None and (adoption_file.raw is not None or tx.record_directory is not None):
                _refuse("unadmitted-epoch-storage")
            if birth_file.raw is None:
                if not tx.legacy or tx.external is not None:
                    _refuse("birth-bootstrap-not-authorized")
                tx.publish_document("birth", expected_birth)
                tx.boundary("birth-durable")
            birth = tx.files["birth"].value
            _validate_birth(tx, birth, expected_birth)
            if marker is not None:
                _validate_marker(tx, marker, birth)
                tx.persist_retained_marker()
            if committed_adoption:
                return _finish(tx, birth)
            if not tx.legacy or tx.external is not None:
                _refuse("adoption-repair-not-authorized")
            if marker is None:
                tx.publish_marker(_marker(birth, None))
                tx.boundary("birth-pending")
            if tx.files["adoption"].raw is not None and tx.record_directory is None:
                _refuse("adoption-receipt-records-directory-missing")
            if tx.record_directory is None:
                tx.records_create()
                tx.boundary("records-directory-durable")
            adoption = _adoption(owner, birth, _identity(os.fstat(tx.record_directory.fd)))
            if tx.files["adoption"].raw is None:
                tx.publish_document("adoption", adoption)
                tx.boundary("adoption-receipt-durable")
            elif not _same(owner, tx.files["adoption"].value, adoption):
                _refuse("immutable-adoption-receipt-differs")
            tx.publish_marker(_marker(birth, adoption["adoption_sha256"]))
            tx.boundary("adoption-memo-durable")
            return _finish(tx, birth)
    except ControllerDeliveryEpochRefusal:
        raise
    except _ERRORS as exc:
        raise ControllerDeliveryEpochRefusal("epoch-domain-refused", upstream=exc) from exc
