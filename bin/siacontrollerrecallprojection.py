"""Borrowed-handle singleton recall projection; no output or CLI activation.

The caller retains actual ordinary epoch and installed-engine contexts under
its corpus scope. This adapter neither acquires nor closes those contexts.
Its normal exit checks only its own lifetime. A later output compositor must
also check mutations occurring during the enclosing owners' normal exits.
"""

import contextlib
import copy
import hashlib
import json
import math

import siacontrollerdeliveryepoch as epoch_api
import siagetrenderadmit as consistency_api
import siainstalledengine as engine_api
import sialiveloop as live
import siasourcebatch as source


NON_CLAIMS = (
    "This observation composes the actual borrowed acknowledged source-v3 epoch and installed-engine handles; its pins are caller-supplied joins, not self-selected runtime authority or a replacement for those handles' admission.",
    "Current means the retained current-version roster and checked local descriptor generations during these holds, not a new observation clock, guaranteed freshness, complete machine history or hostile same-user protection.",
    "The singleton row is an explicitly constructed full-source recall reference with the original version and origin, not an engine query row, title, score or chunk identity; GET rendition remains separate from original source bytes.",
    "The fixed host brain selector does not authenticate or restrict trusted host backend configuration; ordinary GET may perform migrations or retrieval bookkeeping, and only the separate projection probe carries its stated no-write scope.",
    "No output is emitted, ranked, journaled or consumed here; this is not delivery, human reading, successful use, acknowledgment, writer authorization, CLI activation or a no-touch mode change.",
    "The caller owns the enclosing corpus, epoch and engine contexts. This adapter never closes borrowed descriptors; its exit cannot check later enclosing-owner exit callbacks, which require the final compositor's own retained input and output checks.",
    "Retained copies are observations, not fresh authority after this handle or either borrowed handle retires; every original source, epoch, engine, GET and supplied-consistency nonclaim remains controlling.",
    "No JACKAL assurance, biological cognition claim, cognitive-mechanism warrant or held-out retrieval win is established.",
)
_VIEW_KEYS = frozenset({
    "schema", "status", "epoch_adoption", "parent_committed",
    "parent_generation", "expected_parent_generation_sha256",
    "records_directory", "records_identity", "non_claims",
})
_BINDING_KEYS = frozenset({
    "schema", "status", "source_id", "expected_expectations_sha256",
    "pin_fields", "artifacts", "corpus", "non_claims", "binding_sha256",
})
_TRANSPORT_KEYS = frozenset({
    "schema", "status", "operation", "source_id", "binding_sha256",
    "expected_expectations_sha256", "request_sha256", "returncode", "timeout",
    "stdout", "stderr", "stdout_sha256", "stderr_sha256", "non_claims",
    "transport_sha256",
})
_CONSISTENCY_KEYS = frozenset({
    "schema", "status", "source_id", "source_version",
    "source_version_native_sha256", "get_stdout", "get_stdout_sha256",
    "projection_stdout", "projection_stdout_sha256", "projection_receipt",
    "projection_receipt_native_sha256", "non_claims", "consistency_sha256",
})
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError)


class ControllerRecallProjectionRefusal(ValueError):
    """A projection refusal has no output phase and makes no delivery claim."""

    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = {
            "non_claims": getattr(upstream, "non_claims", ()),
            "upstream_non_claims": getattr(upstream, "upstream_non_claims", ()),
        }
        self.upstream_status = getattr(upstream, "upstream_status", None)
        self.upstream_mismatch_reasons = getattr(upstream, "upstream_mismatch_reasons", ())
        super().__init__("controller recall projection refused: " + reason)


def _fail(reason):
    raise ControllerRecallProjectionRefusal(reason)


def _keys(value, expected, reason):
    if type(value) is not dict or len(value) != len(expected) \
            or any(type(key) is not str for key in value) or set(value) != expected:
        _fail(reason)


def _pin(value):
    """Freeze already natively bounded data; retain native float spelling."""
    kind = type(value)
    if kind is dict:
        return kind, tuple((key, _pin(child)) for key, child in value.items())
    if kind is list:
        return kind, tuple(_pin(child) for child in value)
    if kind is float:
        return kind, value.hex()
    return kind, value


def _same(value, pin):
    kind, expected = pin
    if type(value) is not kind:
        return False
    if kind is dict:
        return len(value) == len(expected) and all(type(key) is str for key in value) \
            and all(key in value and _same(value[key], child) for key, child in expected)
    if kind is list:
        return len(value) == len(expected) and all(
            _same(child, prior) for child, prior in zip(value, expected))
    if kind is float:
        return value.hex() == expected
    if kind is str:
        return len(value) == len(expected) and value == expected
    return value == expected


class _HeldRecallProjection:
    def __init__(self, owner, held_epoch, held_engine, request):
        self._closed = False
        self.owner, self.epoch, self.engine = owner, held_epoch, held_engine
        self.documents, self.pins, self.returned = {}, {}, []
        if type(owner) is not dict or type(held_epoch) is not epoch_api._HeldEpoch \
                or type(held_engine) is not engine_api._Engine:
            _fail("actual-borrowed-handles-required")
        self.tx = held_epoch._tx
        self.admission = held_engine.admission
        if type(self.tx) is not epoch_api._Transaction \
                or type(self.admission) is not engine_api._Admission \
                or self.tx.owner is not owner or self.admission.owner is not owner \
                or self.tx.readonly is not True or self.tx.legacy is not False:
            _fail("ordinary-source-v3-owner-required")
        self.boundary = held_engine.boundary
        self.corpus_lease, self.engine_lease = held_engine.corpus_lease, held_engine.engine_lease
        self.corpus_fd = self.corpus_lease.fd
        self.adoption_pin = self.tx.external
        self.basis = {key: owner.get(key) for key in (
            *self.tx.paths, *self.tx.capacities,
            *self.admission.paths, *self.admission.capacities, "GBRAIN_SOURCE")}
        self.references = {key: owner.get(key) for key in (
            *engine_api._OPERATIONS, *engine_api._CONTEXTS,
            "json", "hashlib", "math", "os")}
        capacities = {key: owner.get(key) for key in (
            "MAX_STATE_JSON_BYTES", "MAX_CONFIG_BYTES", "MAX_EXTERNAL_OUTPUT_BYTES")}
        if any(type(value) is not int or value <= 0 for value in capacities.values()):
            _fail("owner-capacity")
        self.ceiling = min(capacities["MAX_STATE_JSON_BYTES"], live.MAX_INPUT_BYTES)
        self.native_owner = {"json": json, "hashlib": hashlib, "math": math,
                             **capacities, "MAX_STATE_JSON_BYTES": self.ceiling}
        self.request = request
        self._size(request)
        self.request_pin = _pin(request)
        for key in ("expected_epoch_view_sha256", "expected_engine_binding_sha256",
                    "expected_engine_expectations_sha256"):
            consistency_api._hex(request[key], "external-adapter-pin")
        subject = request["subject"]
        if type(subject) is not str or not 0 < len(subject) <= engine_api.MAX_GET_SUBJECT_BYTES \
                or engine_api._GET_SUBJECT.fullmatch(subject) is None:
            _fail("recall-subject")
        if type(request["timeout"]) is not int \
                or not 0 < request["timeout"] <= self.admission.capacities["MAX_JSON_SAFE_INTEGER"]:
            _fail("explicit-process-timeout")
        self.current()
        # Reserve prospective borrowed-reader copies before invoking them.
        self._budget(epoch_view=self.epoch._view, epoch_view_copy=self.epoch._view)
        self._retain("epoch_view", self.epoch.read())
        self._source_view()
        self.current()
        self._budget(engine_binding=self.engine.binding, engine_binding_copy=self.engine.binding)
        self._retain("engine_binding", self.engine.read())
        self._engine_binding()
        self.current()
        timeout = request["timeout"]
        self._retain("version_transport", self.engine.version(timeout=timeout))
        self._transport("version_transport", "--version", None)
        self.current()
        self._retain("get_transport", self.engine.get(subject=subject, timeout=timeout))
        get_envelope = {"operation": "get", "source_id": "sia",
                        "subject": subject, "timeout": timeout}
        self._transport("get_transport", "get", self._sha(get_envelope))
        get = self.documents["get_transport"]
        projection_request = {
            "source_id": "sia", "source_version": self.documents["source_version"],
            "get_stdout": get["stdout"],
            "expected_get_stdout_sha256": get["stdout_sha256"],
        }
        self._retain("projection_request", projection_request)
        self._size(projection_request, self.admission.limits["max_request_bytes"])
        self._budget(projection_request_wire=projection_request)
        request_utf8 = self._wire(projection_request)
        projection_pin = hashlib.sha256(request_utf8).hexdigest()
        self.current()
        self._retain("projection_transport", self.engine.project(
            operation=engine_api.PROJECTION_OPERATION, request_utf8=request_utf8,
            expected_request_sha256=projection_pin, timeout=timeout))
        self._transport("projection_transport", engine_api.PROJECTION_OPERATION, projection_pin)
        self.current()
        project = self.documents["projection_transport"]
        # Reserve the consistency component's complete request/receipt/result
        # and defensive copy inside the remaining aggregate representation.
        # Its owner is capacities-only and carries no source/engine authority;
        # the actual caller owner remains checked by input_current below.
        remaining = self.ceiling - self._budget()
        if remaining <= 0:
            _fail("complete-consistency-capacity")
        component_owner = {
            "MAX_STATE_JSON_BYTES": remaining,
            "MAX_CONFIG_BYTES": self.native_owner["MAX_CONFIG_BYTES"],
            "MAX_EXTERNAL_OUTPUT_BYTES": self.native_owner["MAX_EXTERNAL_OUTPUT_BYTES"],
        }
        admitted = consistency_api.admit(
            component_owner, source_version=self.documents["source_version"],
            expected_source_version_native_sha256=self._sha(self.documents["source_version"]),
            get_stdout=get["stdout"], expected_get_stdout_sha256=get["stdout_sha256"],
            projection_stdout=project["stdout"],
            expected_projection_stdout_sha256=project["stdout_sha256"],
            input_current=self.current)
        self._retain("consistency", admitted)
        self._consistency()
        self._result(projection_pin)
        self.current()

    def _size(self, value, ceiling=None):
        return source._json_size(
            self.native_owner, value,
            self.ceiling if ceiling is None else min(self.ceiling, ceiling),
            ascii_only=True)

    def _wire(self, value):
        return source.native_bytes(self.native_owner, value)

    def _sha(self, value):
        return hashlib.sha256(self._wire(value)).hexdigest()

    def _own(self, value, field):
        return self._sha({key: child for key, child in value.items() if key != field})

    def _budget(self, **prospective):
        return self._size({"request": self.request, "retained": self.documents,
                           "returned": [value for value, _prior in self.returned],
                           "prospective": prospective})

    def _retain(self, name, value):
        self._size(value)
        pin = _pin(value)
        self._budget(**{name: value})
        self.documents[name], self.pins[name] = value, pin
        self._plain_current()

    def _plain_current(self):
        if self._closed:
            _fail("retired-recall-projection")
        if self.epoch._tx is not self.tx or self.engine.admission is not self.admission \
                or self.engine.boundary is not self.boundary \
                or self.engine.corpus_lease is not self.corpus_lease \
                or self.engine.engine_lease is not self.engine_lease \
                or self.tx.owner is not self.owner or self.admission.owner is not self.owner \
                or self.epoch._closed is not False or self.engine.alive is not True \
                or self.tx.readonly is not True or self.tx.legacy is not False \
                or type(self.tx.external) is not type(self.adoption_pin) \
                or self.tx.external != self.adoption_pin \
                or type(self.admission.expected) is not str \
                or self.admission.expected != self.request["expected_engine_expectations_sha256"]:
            _fail("borrowed-handle-lifetime-or-owner-changed")
        if any(type(self.owner.get(key)) is not type(value) or self.owner.get(key) != value
               for key, value in self.basis.items()) \
                or any(self.owner.get(key) is not value for key, value in self.references.items()):
            _fail("owner-basis-changed")
        if not _same(self.request, self.request_pin) \
                or any(not _same(value, self.pins[name]) for name, value in self.documents.items()) \
                or any(not _same(value, prior) for value, prior in self.returned):
            _fail("retained-recall-input-or-result-changed")
        # Copy-time detachment remains controlling after every borrowed
        # authority callback, not only immediately after deepcopy returns.
        retained = consistency_api._containers(self.documents)
        for value, _prior in self.returned:
            containers = consistency_api._containers(value)
            if retained & containers:
                _fail("recall-result-copy-not-detached")
            retained.update(containers)

    def current(self):
        try:
            self._plain_current()
            self.epoch.current()
            self.engine.current()
            self.epoch.current()
            if self.corpus_lease.context.get() != self.corpus_fd \
                    or type(self.corpus_lease.context.get()) is not int:
                _fail("borrowed-corpus-scope-changed")
            # Refuse use of the pre-correction engine draft. This is a fixed
            # engine environment prerequisite, never a caller brain selector.
            environment = self.engine._environment()
            if type(environment) is not dict or type(environment.get("GBRAIN_BRAIN_ID")) is not str \
                    or environment["GBRAIN_BRAIN_ID"] != "host":
                _fail("installed-engine-fixed-host-required")
            self._plain_current()
            return None
        except BaseException as exc:
            self._closed = True
            if isinstance(exc, ControllerRecallProjectionRefusal):
                raise
            if isinstance(exc, _ERRORS):
                raise ControllerRecallProjectionRefusal("recall-currentness", upstream=exc) from exc
            raise

    def _source_view(self):
        view = self.documents["epoch_view"]
        _keys(view, _VIEW_KEYS, "epoch-view-contract")
        retained, committed = self.tx.admitted["retained_batch"], self.tx.admitted["committed"]
        if type(retained) is not dict or retained.get("schema") != "sia-controller-source-batch-v3" \
                or self.tx.legacy is not False:
            _fail("acknowledged-source-v3-required")
        if view["schema"] != "sia-controller-delivery-epoch-view-v1" \
                or view["status"] != "held-not-consumed" \
                or not _same(view["non_claims"], _pin(list(epoch_api.HELD_NON_CLAIMS))) \
                or self._sha(view) != self.request["expected_epoch_view_sha256"] \
                or not _same(view["parent_committed"], _pin(committed)) \
                or not _same(view["parent_generation"], _pin(self.tx.generation)) \
                or retained["batch_sha256"] != committed["source_batch_sha256"]:
            _fail("actual-epoch-view-binding")
        generation = view["parent_generation"]
        transition, state = generation["transition"], generation["transition"]["state"]
        if view["expected_parent_generation_sha256"] != committed["live_generation_sha256"] \
                or generation["generation_sha256"] != committed["live_generation_sha256"] \
                or epoch_api._own(self.native_owner, generation, "generation_sha256") \
                != committed["live_generation_sha256"] \
                or epoch_api._own(self.native_owner, transition, "transition_sha256") \
                != generation["transition_sha256"] \
                or transition["transition_sha256"] != generation["transition_sha256"] \
                or epoch_api._sha(self.native_owner, state) != generation["state_sha256"] \
                or transition["state_sha256"] != generation["state_sha256"]:
            _fail("actual-full-generation-binding")
        adopted = view["epoch_adoption"]
        wrapper = retained["delivery_input"]
        if self.tx.external is None or adopted["expected_adoption_sha256"] != self.tx.external \
                or wrapper["expected_adoption_sha256"] != self.tx.external \
                or not _same(adopted, _pin(wrapper["epoch_view"]["epoch_adoption"])) \
                or not epoch_api.view_identity_bound(self.native_owner, view):
            _fail("original-adoption-binding")
        live._policy(state["policy"])
        versions = live._pages(state["intake"], state["observed_at"], state["policy"])
        selected = [versions[version] for version in state["intake"]["current_versions"]
                    if versions[version]["subject"] == self.request["subject"]]
        if len(selected) != 1:
            _fail("unique-current-source-version-required")
        page = selected[0]
        raw = consistency_api._utf8(page["content"], live.MAX_CONTENT_BYTES, "source-content-capacity")
        if hashlib.sha256(raw).hexdigest() != page["source_sha256"]:
            _fail("raw-current-source-pin")
        self._retain("source_version", page)
        version = page["version_sha256"]
        rows = [{"row_ref": version, "version_sha256": version,
                 "row": {"slug": page["subject"], "origin": page["origin"],
                         "chunk_text": page["content"]}}]
        live._rows(rows, versions, state["policy"], current=state["intake"]["current_versions"])
        self._retain("rows", rows)

    def _engine_binding(self):
        binding = self.documents["engine_binding"]
        _keys(binding, _BINDING_KEYS, "engine-binding-contract")
        if binding["schema"] != "sia-installed-overlay-engine-binding-v1" \
                or binding["status"] != "bound-installed-artifacts" or binding["source_id"] != "sia" \
                or not _same(binding, _pin(self.engine.binding)) \
                or binding["expected_expectations_sha256"] \
                != self.request["expected_engine_expectations_sha256"] \
                or self.admission.expected != self.request["expected_engine_expectations_sha256"] \
                or self._own(binding, "binding_sha256") != self.request["expected_engine_binding_sha256"] \
                or binding["binding_sha256"] != self.request["expected_engine_binding_sha256"] \
                or not _same(binding["non_claims"], _pin(list(engine_api.NON_CLAIMS))):
            _fail("actual-engine-binding")

    def _transport(self, name, operation, request_sha256):
        value = self.documents[name]
        get_mode = operation == "get"
        _keys(value, _TRANSPORT_KEYS | ({"subject"} if get_mode else set()), "transport-keys")
        schema = ("sia-installed-overlay-engine-get-transport-v1" if get_mode
                  else "sia-installed-overlay-engine-transport-v1")
        status = ("captured-unadmitted-get" if get_mode else
                  "observed-version-only" if operation == "--version" else "captured-unadmitted-projection")
        expected = {"schema": schema, "status": status, "operation": operation,
                    "source_id": "sia", "binding_sha256": self.request["expected_engine_binding_sha256"],
                    "expected_expectations_sha256": self.request["expected_engine_expectations_sha256"],
                    "request_sha256": request_sha256, "returncode": 0,
                    "timeout": self.request["timeout"]}
        if any(type(value[key]) is not type(item) or value[key] != item for key, item in expected.items()):
            _fail("transport-source-request-or-runtime-join")
        if get_mode and (type(value["subject"]) is not str or value["subject"] != self.request["subject"]):
            _fail("get-transport-subject")
        claims = engine_api.GET_NON_CLAIMS if get_mode else engine_api.NON_CLAIMS
        if not _same(value["non_claims"], _pin(list(claims))) \
                or value["transport_sha256"] != self._own(value, "transport_sha256"):
            _fail("transport-digest-or-nonclaims")
        total = 0
        for field in ("stdout", "stderr"):
            raw = consistency_api._utf8(value[field], self.admission.limits["max_output_bytes"],
                                        "transport-output-capacity")
            total += len(raw)
            if value[field + "_sha256"] != hashlib.sha256(raw).hexdigest():
                _fail("transport-output-pin")
        if total > self.admission.limits["max_output_bytes"]:
            _fail("transport-output-capacity")
        if operation == "--version" and (
                value["stderr"] != "" or value["stdout"]
                != "gbrain " + self.documents["engine_binding"]["pin_fields"]["version"] + "\n"):
            _fail("actual-engine-version")

    def _consistency(self):
        value = self.documents["consistency"]
        _keys(value, _CONSISTENCY_KEYS, "consistency-result-keys")
        get, project = self.documents["get_transport"], self.documents["projection_transport"]
        if value["schema"] != "sia-get-render-consistency-v1" \
                or value["status"] != "supplied-match-consistent-not-observed" or value["source_id"] != "sia" \
                or not _same(value["source_version"], self.pins["source_version"]) \
                or value["source_version_native_sha256"] != self._sha(self.documents["source_version"]) \
                or value["get_stdout"] != get["stdout"] or value["get_stdout_sha256"] != get["stdout_sha256"] \
                or value["projection_stdout"] != project["stdout"] \
                or value["projection_stdout_sha256"] != project["stdout_sha256"] \
                or value["projection_receipt_native_sha256"] != self._sha(value["projection_receipt"]) \
                or not _same(value["non_claims"], _pin(list(consistency_api.NON_CLAIMS))) \
                or value["consistency_sha256"] != self._own(value, "consistency_sha256"):
            _fail("consistency-transport-source-join")

    def _result(self, projection_pin):
        view = self.documents["epoch_view"]
        generation = view["parent_generation"]
        get = self.documents["get_transport"]
        result = {
            "schema": "sia-controller-recall-projection-v1",
            "status": "observed-current-render-not-delivered", "source_id": "sia",
            "subject": self.request["subject"],
            "expected_epoch_view_sha256": self.request["expected_epoch_view_sha256"],
            "expected_engine_binding_sha256": self.request["expected_engine_binding_sha256"],
            "expected_engine_expectations_sha256": self.request["expected_engine_expectations_sha256"],
            "parent_committed": view["parent_committed"],
            "parent_generation_sha256": generation["generation_sha256"],
            "parent_state_sha256": generation["state_sha256"],
            "policy_sha256": generation["transition"]["state"]["policy_sha256"],
            "adoption_sha256": view["epoch_adoption"]["expected_adoption_sha256"],
            "source_version": self.documents["source_version"],
            "source_version_native_sha256": self._sha(self.documents["source_version"]),
            "get_stdout": get["stdout"], "get_stdout_sha256": get["stdout_sha256"],
            "rows": self.documents["rows"], "rows_sha256": live._sha(self.documents["rows"]),
            "engine_binding": self.documents["engine_binding"],
            "version_transport": self.documents["version_transport"],
            "get_transport": get, "projection_request": self.documents["projection_request"],
            "projection_request_sha256": projection_pin,
            "projection_transport": self.documents["projection_transport"],
            "consistency": self.documents["consistency"], "non_claims": list(NON_CLAIMS),
            "observation_sha256": "0" * 64,
        }
        self._budget(result=result, result_copy=result)
        result["observation_sha256"] = self._own(result, "observation_sha256")
        self._retain("result", result)

    def read(self):
        try:
            self.current()
            result, pin = self.documents["result"], self.pins["result"]
            self._budget(result_copy=result)
            detached = copy.deepcopy(result)
            if not _same(detached, pin):
                _fail("recall-result-copy-changed")
            retained = consistency_api._containers(self.documents)
            if retained & consistency_api._containers(detached):
                _fail("recall-result-copy-not-detached")
            self.returned.append((detached, pin))
            self.current()
            self._plain_current()
            return detached
        except BaseException as exc:
            self._closed = True
            if isinstance(exc, ControllerRecallProjectionRefusal):
                raise
            if isinstance(exc, _ERRORS):
                raise ControllerRecallProjectionRefusal("recall-read", upstream=exc) from exc
            raise


@contextlib.contextmanager
def hold_recall_projection(owner, *, held_epoch, held_engine,
                           expected_epoch_view_sha256, expected_engine_binding_sha256,
                           expected_engine_expectations_sha256, subject, timeout):
    """Observe one actual current-version GET projection through borrowed holds.

    The view pin is canonical source-native ASCII JSON, as in existing source
    delivery wrappers. Engine binding and expectations pins are also native
    document pins. No pin is selected from a returned receipt as permission.
    The caller must retain both actual enclosing handles and its corpus scope.
    This context cannot check later enclosing exits; a final output compositor
    remains mandatory. Body exceptions keep their original identity.
    """
    request = {
        "expected_epoch_view_sha256": expected_epoch_view_sha256,
        "expected_engine_binding_sha256": expected_engine_binding_sha256,
        "expected_engine_expectations_sha256": expected_engine_expectations_sha256,
        "subject": subject, "timeout": timeout,
    }
    try:
        held = _HeldRecallProjection(owner, held_epoch, held_engine, request)
    except ControllerRecallProjectionRefusal:
        raise
    except _ERRORS as exc:
        raise ControllerRecallProjectionRefusal("recall-entry", upstream=exc) from exc
    try:
        yield held
    except BaseException:
        raise
    else:
        held.current()
    finally:
        # No borrowed close, retirement, owner exit, descriptor or reacquisition.
        held._closed = True
