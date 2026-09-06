"""Lazy live-generation publication, owned by the active sialib instance.

This child imports no SIA module. The core supplies the pure live pipeline only
after an actual live operation; legacy startup, restore fences and status do
not need the optional live implementation merely to import sialib.

Bindings and descriptor instances remain per-owner across dynamic core aliases.
Context entry, yielded guard/write calls and exit each restore the owning
namespace under the same lock. No lock is held across external caller code.
"""

import contextlib as _contextlib
import threading as _threading

def _live_upstream_refusal(reason, exc):
    error = RuntimeError("live publication refused: " + reason)
    error.non_claims = list(LIVE_PUBLICATION_NON_CLAIMS)
    error.upstream_non_claims = list(getattr(exc, "non_claims", ()))
    error.upstream_reason = getattr(exc, "reason", None)
    raise error from exc


def _live_bytes(value, ceiling=None):
    if ceiling is None:
        ceiling = MAX_STATE_JSON_BYTES
    try:
        return sialiveloop._canonical(value, ceiling)
    except sialiveloop.LiveLoopRefusal as exc:
        _live_upstream_refusal("complete JSON admission failed", exc)


def _live_same(left, right):
    return _live_bytes(left) == _live_bytes(right)


def _live_sha(value):
    return hashlib.sha256(_live_bytes(value)).hexdigest()


def _live_memo_bytes(value):
    """Preserve native memo integers under its existing whole-file ceiling.

    Filesystem nanosecond witnesses are native JSON integers, not live-loop
    mathematical inputs. They stay unchanged; only candidate/status/generation
    values enter the pure module's stricter numerical domain.
    """
    active = set()

    def admit(item, depth):
        if depth > 64:
            _live_refuse("native memo JSON nesting exceeds its boundary")
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active:
                _live_refuse("native memo JSON is cyclic")
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        _live_refuse("native memo JSON key is not text")
                    admit(child, depth + 1)
            else:
                for child in item:
                    admit(child, depth + 1)
            active.remove(id(item))
        elif kind not in (str, int, bool, float, type(None)) \
                or kind is float and not math.isfinite(item):
            _live_refuse("native memo contains a non-JSON value")

    admit(value, 0)
    # The original spaced ASCII wire image is at least as large as this
    # canonical ASCII image. Bound it before canonicalization or copying.
    _memo_text(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _live_memo_sha(value):
    return hashlib.sha256(_live_memo_bytes(value)).hexdigest()


def _live_own(value, field):
    return _live_sha({key: item for key, item in value.items() if key != field})


class _PublicationFileImplementation:
    """One bounded named/descriptor generation, held through final copies."""

    def __init__(self, path, ceiling, *, native_memo=False):
        self.path, self.ceiling, self.fd, self.parent_fd = path, ceiling, None, None
        self.native_memo = native_memo
        self.retired = False
        try:
            parent = os.path.dirname(os.path.abspath(path))
            self.parent_path = parent
            self.parent_fd = _open_source_nofollow(parent, os.O_RDONLY | os.O_DIRECTORY)
            info = os.fstat(self.parent_fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                _live_refuse("publication parent is not an owned ordinary directory")
            self.parent_identity = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)
            try:
                self.fd = _open_source_nofollow(path, os.O_RDONLY)
            except FileNotFoundError:
                self.value, self.generation, self.wire_sha256 = None, None, None
            else:
                info = os.fstat(self.fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 \
                        or not 0 < info.st_size <= ceiling:
                    _live_refuse("publication file is not a bounded private ordinary generation")
                self.generation = self.identity(info)
                raw = os.pread(self.fd, info.st_size + 1, 0)
                if len(raw) != info.st_size:
                    _live_refuse("publication file changed while read")
                self.wire_sha256 = hashlib.sha256(raw).hexdigest()
                self.value = _strict_json_loads(raw)
                self.encode(self.value)
            self.current()
        except (OSError, ValueError) as exc:
            self.close()
            _live_upstream_refusal("publication file admission failed", exc)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def encode(self, value):
        raw = _live_memo_bytes(value) if self.native_memo else _live_bytes(value, self.ceiling)
        if len(raw) > self.ceiling:
            _live_refuse("publication image exceeds its original byte capacity")
        return raw

    def named_current(self):
        """Check held and freshly named authority without further hashing."""
        if self.retired:
            return
        try:
            parent = _open_source_nofollow(self.parent_path, os.O_RDONLY | os.O_DIRECTORY)
        except OSError as exc:
            _live_upstream_refusal("publication parent is unsafe", exc)
        try:
            for info in (os.fstat(self.parent_fd), os.fstat(parent)):
                if (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid) != self.parent_identity:
                    _live_refuse("publication parent generation changed")
        finally:
            os.close(parent)
        try:
            named = _open_source_nofollow(self.path, os.O_RDONLY)
        except FileNotFoundError:
            if self.fd is not None:
                _live_refuse("publication named generation disappeared")
            return
        except OSError as exc:
            raise RuntimeError("live publication named generation is unsafe") from exc
        try:
            if self.fd is None or self.identity(os.fstat(named)) != self.generation \
                    or self.identity(os.fstat(self.fd)) != self.generation:
                _live_refuse("publication named or descriptor generation changed")
        finally:
            os.close(named)

    def current(self):
        if self.retired:
            return
        self.named_current()
        if self.fd is None:
            return
        digest, offset = hashlib.sha256(), 0
        while True:
            block = os.pread(self.fd, 65536, offset)
            if not block:
                break
            offset += len(block)
            if offset > self.ceiling:
                _live_refuse("publication byte capacity changed")
            digest.update(block)
        if offset != self.generation[6] or digest.hexdigest() != self.wire_sha256 \
                or self.identity(os.fstat(self.fd)) != self.generation:
            _live_refuse("publication descriptor bytes changed")
        # Hashing may outlive the named parent or leaf generation even when
        # this retained descriptor's bytes and metadata remain unchanged.
        self.named_current()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.parent_fd is not None:
            os.close(self.parent_fd)
            self.parent_fd = None


@_contextlib.contextmanager
def _live_files():
    with contextlib.ExitStack() as stack:
        files = {}
        for name, path, ceiling in (
                ("memo", MEMO_PATH, MAX_MEMO_BYTES), ("status", STATUS_PATH, MAX_STATE_JSON_BYTES),
                ("graph", GRAPH_PATH, MAX_STATE_JSON_BYTES),
                ("candidate", LIVE_CANDIDATE_PATH, MAX_STATE_JSON_BYTES),
                ("generation", LIVE_STATE_PATH, MAX_STATE_JSON_BYTES)):
            owned = _LivePublicationFile(path, ceiling, native_memo=name == "memo")
            stack.callback(owned.close)
            files[name] = owned

        def current():
            for owned in files.values():
                owned.current()
            # A later member's hash may have outlived an earlier member's
            # named check. Close the complete roster after all hash work;
            # no result copies or additional hashes follow this sweep.
            for owned in files.values():
                owned.named_current()

        def write(name, value, *, status=False):
            old = files[name]
            raw = old.encode(value)
            current()
            if status:
                _live_status_image(value)
                export_status(value)
            else:
                atomic_write(old.path, raw.decode("utf-8"), mode=0o600)
            updated = _LivePublicationFile(old.path, old.ceiling, native_memo=old.native_memo)
            stack.callback(updated.close)
            if updated.encode(updated.value) != raw:
                _live_refuse("published bytes differ from the preflight image")
            # This exact replacement is ours. Retain its old descriptor until
            # scope exit, but make only the newly admitted generation current.
            old.retired = True
            files[name] = updated
            current()

        yield files, current, write
        current()


def _live_receipt_shape(receipt):
    _live_keys(receipt, _LIVE_RECEIPT_KEYS)
    if receipt["schema"] != "sia-live-publication-receipt-v1" \
            or type(receipt["publication_id"]) is not str \
            or re.fullmatch(r"[0-9a-f]{32}", receipt["publication_id"]) is None \
            or not _nonnegative_status_integer(receipt["pulse_seq"]) \
            or type(receipt["epoch_id"]) is not str or not receipt["epoch_id"]:
        _live_refuse("compact receipt identity is invalid")
    for key in ("state_sha256", "transition_sha256", "candidate_sha256", "generation_sha256", "status_sha256"):
        if type(receipt[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", receipt[key]) is None:
            _live_refuse("compact receipt digest is invalid")
    parent = receipt["parent_generation_sha256"]
    if parent is not None and (type(parent) is not str or re.fullmatch(r"[0-9a-f]{64}", parent) is None):
        _live_refuse("compact parent identity is invalid")


def _live_generation(candidate):
    transition, status = candidate["transition"], candidate["status"]
    generation = {
        "schema": "sia-live-committed-generation-v1", "publication_id": status["publication_id"],
        "pulse_seq": status["pulse_seq"], "epoch_id": transition["state"]["epoch_id"],
        "state_sha256": transition["state_sha256"], "transition_sha256": transition["transition_sha256"],
        "candidate_sha256": candidate["candidate_sha256"], "status_sha256": candidate["status_sha256"],
        "parent_committed": candidate["parent_committed"], "transition": transition,
        "non_claims": list(LIVE_PUBLICATION_NON_CLAIMS),
    }
    generation["generation_sha256"] = _live_sha(generation)
    return generation


def _live_receipt(generation):
    parent = generation["parent_committed"]
    return {"schema": "sia-live-publication-receipt-v1", **{key: generation[key] for key in (
        "publication_id", "pulse_seq", "epoch_id", "state_sha256", "transition_sha256",
        "candidate_sha256", "generation_sha256", "status_sha256")},
        "parent_generation_sha256": None if parent is None else parent["generation_sha256"]}


def _live_graph_status(status, graph):
    if _recoverable_status_integrity(status) is None or status.get("version") != VERSION:
        _live_refuse("frozen status is not canonical for this runtime")
    snapshot = _recoverable_graph_snapshot(graph, observed_by=status["ts"])
    if snapshot is None or graph.get("snapshot", {}).get("complete") is not True:
        _live_refuse("graph snapshot is not complete and canonical")
    for status_key, graph_key in (("graph_publication_id", "publication_id"),
                                  ("graph_nodes", "nodes"), ("graph_edges", "edges"), ("pages", "pages")):
        if not _live_same(status[status_key], snapshot[graph_key]):
            _live_refuse("frozen status does not bind the current graph generation")


def _live_status_image(status):
    # export_status retains its existing spaced/ASCII JSON wire format. Its
    # complete bytes, not just the smaller canonical hash image, must fit
    # before staging can publish any candidate.
    _live_bytes(status)
    raw = json.dumps(status, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_STATE_JSON_BYTES:
        _live_refuse("complete status wire image exceeds its byte capacity")
    return raw


def _live_prepare_replay(inputs):
    try:
        return sialiveloop.prepare_pulse(**inputs)
    except sialiveloop.LiveLoopRefusal as exc:
        _live_upstream_refusal("complete original pure replay failed", exc)


def _live_replay_candidate(candidate):
    _live_bytes(candidate)
    _live_keys(candidate, _LIVE_CANDIDATE_KEYS)
    if candidate["schema"] != "sia-live-publication-candidate-v1" \
            or not _live_same(candidate["non_claims"], list(LIVE_PUBLICATION_NON_CLAIMS)) \
            or candidate["candidate_sha256"] != _live_own(candidate, "candidate_sha256") \
            or candidate["prepare_inputs_sha256"] != _live_sha(candidate["prepare_inputs"]) \
            or candidate["status_sha256"] != _live_sha(candidate["status"]):
        _live_refuse("candidate byte bindings differ")
    _live_keys(candidate["prepare_inputs"], _LIVE_PREPARE_KEYS)
    parent = candidate["parent_committed"]
    if parent is not None:
        _live_receipt_shape(parent)
        inputs = candidate["prepare_inputs"]
        if inputs["expected_previous_state_sha256"] != parent["state_sha256"] \
                or inputs["previous_state"] is None \
                or _live_sha(inputs["previous_state"]) != parent["state_sha256"]:
            _live_refuse("candidate does not continue its committed parent")
    elif candidate["prepare_inputs"]["previous_state"] is not None \
            or candidate["prepare_inputs"]["expected_previous_state_sha256"] is not None:
        _live_refuse("initial candidate has an uncommitted parent")
    replayed = _live_prepare_replay(candidate["prepare_inputs"])
    if not _live_same(replayed, candidate["transition"]):
        _live_refuse("candidate differs from complete original pure replay")
    return _live_generation(candidate)


def _live_parent_generation(generation, receipt):
    _live_receipt_shape(receipt)
    _live_keys(generation, _LIVE_GENERATION_KEYS)
    if generation["schema"] != "sia-live-committed-generation-v1" \
            or generation["generation_sha256"] != _live_own(generation, "generation_sha256") \
            or not _live_same(_live_receipt(generation), receipt) \
            or generation["transition_sha256"] != _live_own(generation["transition"], "transition_sha256") \
            or generation["state_sha256"] != _live_sha(generation["transition"]["state"]):
        _live_refuse("committed parent generation differs from its durable receipt")


def _live_controller_source_pending(memo):
    if "controller_source_pending" not in memo:
        return None
    receipt = memo["controller_source_pending"]
    _live_keys(receipt, {
        "schema", "epoch_id", "batch_id", "epoch_sha256", "batch_sha256",
        "batch_wire_sha256", "batch_bytes", "parent_batch_sha256",
    })
    if receipt["schema"] != "sia-controller-source-pending-v1" \
            or not sialiveloop._token(receipt["epoch_id"]) \
            or type(receipt["batch_id"]) is not str \
            or re.fullmatch(r"[0-9a-f]{64}", receipt["batch_id"]) is None \
            or not _nonnegative_status_integer(receipt["batch_bytes"]) \
            or receipt["batch_bytes"] == 0 \
            or receipt["batch_bytes"] > MAX_STATE_JSON_BYTES:
        _live_refuse("controller source pending receipt is invalid")
    for key in ("epoch_sha256", "batch_sha256", "batch_wire_sha256"):
        if type(receipt[key]) is not str \
                or re.fullmatch(r"[0-9a-f]{64}", receipt[key]) is None:
            _live_refuse("controller source pending receipt is invalid")
    parent = receipt["parent_batch_sha256"]
    if parent is not None and (type(parent) is not str
            or re.fullmatch(r"[0-9a-f]{64}", parent) is None):
        _live_refuse("controller source pending receipt is invalid")
    return receipt


def _live_authority_memo(memo, durable):
    if type(memo) is not dict or type(durable) is not dict:
        _live_refuse("durable memo is unavailable")
    # Pulse owns new history/counters in the proposed memo. Its live authority
    # may never come from an in-memory receipt ahead of the durable memo.
    for key in ("live_loop_pending", "live_loop_committed",
                "controller_source_pending",
                "controller_source_live_pending"):
        if (key in memo) != (key in durable) or not _live_same(memo.get(key), durable.get(key)):
            _live_refuse("live memo authority differs from durable receipt")
    _live_controller_source_pending(memo)
    _live_controller_source_pending(durable)
    try:
        _controller_source_live_binding_marker(memo)
        _controller_source_live_binding_marker(durable)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError):
        _live_refuse("controller source live binding is invalid")


def _live_final_memo(memo, candidate, receipt):
    _live_memo_bytes(memo)
    source_pending = _live_controller_source_pending(memo)
    try:
        source_binding = _controller_source_live_binding_marker(memo)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError):
        _live_refuse("controller source live binding is invalid")
    updated = copy.deepcopy(memo)
    marker = _pending_pulse_marker(updated)
    if marker is not None:
        ledger = marker.get("ledger")
        if marker["id"] != receipt["publication_id"] or marker["seq"] != receipt["pulse_seq"] \
                or type(ledger) is not dict or ledger.get("arg2") not in {
                    "ok", "published-after-recovery"} \
                or candidate["status"]["ledger_transition"]["state"] != "signed":
            _live_refuse("active pulse is not the candidate's completed publication")
        updated.pop("pulse_publication")
        updated.pop("sync_needed", None)
    elif updated.get("sync_needed", False) is not False:
        _live_refuse("unrelated corpus publication debt is pending")
    if any(key in updated for key in ("dream_publication", "consolidation_pending", "source_replay_pending",
                                      "brainstem_failure_pending")):
        _live_refuse("unrelated recovery debt is pending")
    updated.pop("pulse_status_effects_pending", None)
    updated.pop("live_loop_pending", None)
    updated["live_loop_committed"] = receipt
    if source_pending is None:
        updated["ready"] = {"v": 1, "completed_at": candidate["status"]["ts"],
                            "kind": "pulse", "identity": receipt["publication_id"]}
        _ready_receipt(updated)
    else:
        if not _live_same(updated.get("controller_source_pending"), source_pending):
            _live_refuse("controller source pending receipt changed")
        updated.pop("ready", None)
    if source_binding is not None \
            and not _live_same(
                updated.get("controller_source_live_pending"),
                source_binding):
        _live_refuse("controller source live binding changed")
    _live_memo_bytes(updated)
    _memo_text(updated)
    return updated


def _stage_live_generation(*, memo, status, prepare_inputs, expected_prepare_inputs_sha256):
    with corpus_owner(), _live_files() as (files, current, write):
        _live_memo_bytes(memo)
        _memo_text(memo)
        _live_bytes(status)
        _live_bytes(prepare_inputs, sialiveloop.MAX_INPUT_BYTES)
        _live_keys(prepare_inputs, _LIVE_PREPARE_KEYS)
        if type(expected_prepare_inputs_sha256) is not str \
                or _live_sha(prepare_inputs) != expected_prepare_inputs_sha256:
            _live_refuse("independent complete prepare input pin differs")
        durable = files["memo"].value
        _live_authority_memo(memo, durable)
        _live_graph_status(status, files["graph"].value)
        if not _nonnegative_status_integer(memo.get("pulse_seq")) \
                or status["pulse_seq"] > memo["pulse_seq"]:
            _live_refuse("candidate sequence exceeds the reserved allocator")
        parent = memo.get("live_loop_committed")
        if parent is not None:
            _live_parent_generation(files["generation"].value, parent)
        elif files["generation"].value is not None and "live_loop_pending" not in memo:
            _live_refuse("an orphan generation cannot start a controller")
        original = (_live_sha(prepare_inputs), _live_sha(status), _live_memo_sha(memo))
        transition = _live_prepare_replay(prepare_inputs)
        candidate = {"schema": "sia-live-publication-candidate-v1", "prepare_inputs": prepare_inputs,
            "prepare_inputs_sha256": expected_prepare_inputs_sha256, "transition": transition,
            "status": status, "status_sha256": _live_sha(status), "parent_committed": parent,
            "non_claims": list(LIVE_PUBLICATION_NON_CLAIMS)}
        candidate["candidate_sha256"] = _live_sha(candidate)
        generation = _live_replay_candidate(candidate)
        receipt = _live_receipt(generation)
        pending = copy.deepcopy(memo)
        pending["live_loop_pending"] = receipt
        pending.pop("ready", None)
        final = _live_final_memo(pending, candidate, receipt)
        # Every complete candidate/generation/status and BOTH whole memo
        # images fit before the first candidate replacement is attempted.
        for value in (candidate, generation, status):
            _live_bytes(value)
        _live_status_image(status)
        _live_bytes({"schema": "sia-live-generation-view-v1", "status": "available",
                     "generation": generation, "non_claims": list(LIVE_PUBLICATION_NON_CLAIMS)})
        for value in (pending, final):
            _live_memo_bytes(value)
            _memo_text(value)
        retained = files["candidate"].value
        if retained is not None and not _live_same(retained, candidate):
            if "live_loop_pending" in memo or parent is None \
                    or retained.get("candidate_sha256") != parent["candidate_sha256"]:
                _live_refuse("retained candidate is not an exact retry or committed predecessor")
        if "live_loop_pending" in memo and not _live_same(memo["live_loop_pending"], receipt):
            _live_refuse("pending receipt differs from the exact candidate")
        detached_candidate, detached_pending = copy.deepcopy((candidate, pending))
        if (_live_sha(prepare_inputs), _live_sha(status), _live_memo_sha(memo)) != original:
            _live_refuse("candidate inputs changed during final copy")
        current()
        if retained is None or not _live_same(retained, candidate):
            write("candidate", detached_candidate)
        write("memo", detached_pending)
        memo.clear()
        memo.update(detached_pending)
        current()
        return None


def _publish_staged_live_generation(*, memo):
    with corpus_owner(), _live_files() as (files, current, write):
        _live_memo_bytes(memo)
        _live_authority_memo(memo, files["memo"].value)
        pending = memo.get("live_loop_pending")
        if pending is None:
            _live_refuse("no pending live candidate is durably bound")
        _live_receipt_shape(pending)
        candidate = files["candidate"].value
        generation = _live_replay_candidate(candidate)
        receipt = _live_receipt(generation)
        if not _live_same(pending, receipt) or not _live_same(candidate["parent_committed"], memo.get("live_loop_committed")):
            _live_refuse("pending or parent receipt differs from the frozen candidate")
        _live_graph_status(candidate["status"], files["graph"].value)
        if not _nonnegative_status_integer(memo.get("pulse_seq")) or memo["pulse_seq"] < generation["pulse_seq"]:
            _live_refuse("recovery allocator precedes candidate sequence")
        retained = files["generation"].value
        if retained is not None and not _live_same(retained, generation):
            parent = candidate["parent_committed"]
            if parent is None:
                _live_refuse("generation is neither exact candidate nor committed parent")
            _live_parent_generation(retained, parent)
        final = _live_final_memo(memo, candidate, receipt)
        for value in (generation, candidate["status"]):
            _live_bytes(value)
        _live_status_image(candidate["status"])
        _memo_text(final)
        original = _live_memo_sha(memo)
        result, final, status = copy.deepcopy((generation, final, candidate["status"]))
        if _live_memo_sha(memo) != original:
            _live_refuse("memo changed during final publication copy")
        current()
        write("generation", result)
        write("status", status, status=True)
        write("memo", final)
        memo.clear()
        memo.update(final)
        current()
        return result


def _read_committed_live_generation(*, memo, admitted_status):
    with corpus_owner(), _live_files() as (files, current, _write):
        durable = files["memo"].value
        if type(memo) is not dict or type(durable) is not dict:
            _live_refuse("reader durable memo is unavailable")
        if _live_memo_bytes(memo) != _live_memo_bytes(durable) \
                or not _live_same(admitted_status, files["status"].value):
            _live_refuse("reader inputs differ from the durable memo or admitted status")
        _live_controller_source_pending(memo)
        _live_controller_source_pending(durable)
        pending, committed = durable.get("live_loop_pending"), durable.get("live_loop_committed")
        candidate, generation = files["candidate"].value, files["generation"].value
        if pending is None and committed is None:
            if candidate is not None or generation is not None:
                _live_refuse("orphan live publication is not absence")
            state, value = "not-started", None
        else:
            expected = _live_replay_candidate(candidate)
            if pending is not None:
                _live_receipt_shape(pending)
                if not _live_same(pending, _live_receipt(expected)) \
                        or not _live_same(candidate["parent_committed"], committed):
                    _live_refuse("pending reader receipt differs from its candidate")
                state, value = "pending", None
            else:
                _live_receipt_shape(committed)
                if not _live_same(committed, _live_receipt(expected)) or not _live_same(generation, expected) \
                        or not _live_same(admitted_status, candidate["status"]):
                    _live_refuse("committed generation or frozen status binding differs")
                _live_graph_status(admitted_status, files["graph"].value)
                state, value = "available", expected
        result = copy.deepcopy({"schema": "sia-live-generation-view-v1", "status": state,
                                 "generation": value, "non_claims": list(LIVE_PUBLICATION_NON_CLAIMS)})
        _live_bytes(result)
        if _live_memo_bytes(memo) != _live_memo_bytes(durable) \
                or not _live_same(admitted_status, files["status"].value):
            _live_refuse("reader inputs changed during final copy")
        current()
        return result


def _recover_pending_live_generation(*, memo):
    with corpus_owner():
        if not _live_started(memo):
            return False
        if "live_loop_pending" in memo:
            return _publish_staged_live_generation(memo=memo)
        if "live_loop_committed" not in memo:
            _live_refuse("orphan live candidate requires an exact staging retry")
        with _live_files() as (files, current, _write):
            status = copy.deepcopy(files["status"].value)
            current()
        view = _read_committed_live_generation(memo=memo, admitted_status=status)
        if view["status"] != "available":
            _live_refuse("committed live generation is not available")
        return False


# Capture only plain function definitions; the descriptor implementation is
# exposed through an owner-bound class, not a shared unbound class façade.
_EXPORTED_FUNCTIONS = tuple(
    name for name, value in globals().items()
    if getattr(value, "__module__", None) == __name__
    and not isinstance(value, type))
_CHILD_FUNCTIONS = frozenset(_EXPORTED_FUNCTIONS)
_ORIGINAL_CHILD_FUNCTIONS = {
    name: globals()[name] for name in _EXPORTED_FUNCTIONS}
_CONTEXT_EXPORTS = frozenset({"_live_files"})
_FILE_CLASS = _PublicationFileImplementation
_MISSING = object()
_BIND_LOCK = _threading.RLock()
_BIND_CONTROL_NAMES = frozenset({
    "_EXPORTED_FUNCTIONS", "_CHILD_FUNCTIONS", "_ORIGINAL_CHILD_FUNCTIONS",
    "_CONTEXT_EXPORTS", "_FILE_CLASS", "_PublicationFileImplementation",
    "_MISSING", "_BIND_LOCK", "_BIND_CONTROL_NAMES", "_BoundInvocationContext",
    "_owned_call", "file_class", "bind", "invoke",
})


def bind(parent_globals):
    """Bind one core without leaking another alias's patched helpers."""
    if not isinstance(parent_globals, dict):
        raise TypeError("sialib live publication context must be a globals dictionary")
    for name, value in parent_globals.items():
        if name.startswith("__") or name in _CHILD_FUNCTIONS or name in _BIND_CONTROL_NAMES:
            continue
        globals()[name] = value
    for name, original in _ORIGINAL_CHILD_FUNCTIONS.items():
        value = parent_globals.get(name, _MISSING)
        if value is _MISSING or getattr(value, "__dict__", {}).get("_sia_senses_delegate") is True:
            globals()[name] = original
        else:
            globals()[name] = value


def _owned_call(parent_globals, target, *args, **kwargs):
    with _BIND_LOCK:
        bind(parent_globals)
        return target(*args, **kwargs)


def file_class(parent_globals):
    """Return a patchable descriptor class belonging to exactly one core."""
    class BoundPublicationFile(_FILE_CLASS):
        def __init__(self, *args, **kwargs):
            self._owner_globals = parent_globals
            _owned_call(parent_globals, _FILE_CLASS.__init__, self, *args, **kwargs)

        def encode(self, value):
            return _owned_call(self._owner_globals, _FILE_CLASS.encode, self, value)

        def named_current(self):
            return _owned_call(self._owner_globals, _FILE_CLASS.named_current, self)

        def current(self):
            return _owned_call(self._owner_globals, _FILE_CLASS.current, self)

        def close(self):
            return _owned_call(self._owner_globals, _FILE_CLASS.close, self)

    return BoundPublicationFile


class _BoundInvocationContext:
    def __init__(self, parent_globals, target, args, kwargs):
        self._parent_globals, self._target = parent_globals, target
        self._args, self._kwargs = args, kwargs
        self._manager, self._state = None, "new"

    def __enter__(self):
        if self._state != "new":
            raise RuntimeError("SIA live publication context is single-use")
        self._state = "opening"
        with _BIND_LOCK:
            bind(self._parent_globals)
            try:
                self._manager = self._target(*self._args, **self._kwargs)
                files, current, write = self._manager.__enter__()
            except BaseException:
                self._manager, self._state = None, "closed"
                raise
        self._state = "entered"

        def owned_current():
            return _owned_call(self._parent_globals, current)

        def owned_write(*args, **kwargs):
            return _owned_call(self._parent_globals, write, *args, **kwargs)

        return files, owned_current, owned_write

    def __exit__(self, exc_type, exc_value, traceback):
        if self._state != "entered":
            raise RuntimeError("SIA live publication context is not entered")
        manager = self._manager
        self._manager, self._state = None, "closed"
        return _owned_call(self._parent_globals, manager.__exit__, exc_type, exc_value, traceback)


def invoke(parent_globals, name, *args, **kwargs):
    target = _ORIGINAL_CHILD_FUNCTIONS.get(name)
    if target is None:
        raise AttributeError("unknown SIA live publication export: " + name)
    if name in _CONTEXT_EXPORTS:
        return _BoundInvocationContext(parent_globals, target, args, kwargs)
    return _owned_call(parent_globals, target, *args, **kwargs)
