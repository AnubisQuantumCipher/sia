"""Literal singleton recall output through the existing source-bound writer.

This additive API does not activate CLI recall. It retains actual corpus,
epoch, engine and projection scopes across the existing writer and checks
their enclosing normal exits before returning its unchanged completion.
"""

import copy
import hashlib
import json
import math

import siacontrollerdeliveryepoch as epoch_api
import siacontrollerdeliverywrapper as wrapper_api
import siacontrollerdeliverywriter as writer_api
import siacontrollerrecallprojection as projection_api
import siadelivery as journal_api
import siagetrenderadmit as consistency_api
import siainstalledengine as engine_api
import sialiveloop as live
import siasourcebatch as source


NON_CLAIMS = (
    "This additive regular-recall API composes actual acknowledged source-v3, original adoption, fixed-host installed engine and matched singleton projection holds; represented receipts do not replace the existing writer's separate actual source and journal admission.",
    "The returned original journal completion records write-all-and-flush-returned at the supplied binary sink, not human receipt, reading, understanding, downstream use, source acknowledgment or consumption by a later controller pulse.",
    "The literal body follows the current recall origin header, existing control-strip provider and cortex metaphor boundary; it is a singleton full-source recall, not query ranking, an engine score, ask output or proof that remembered prose is true.",
    "Legacy JACKAL assurance notices remain a separate non-delivery path. This regular API refuses eligible legacy-assurance source text and nonempty sanitized GET stderr; future CLI activation must preserve existing diagnostic behavior rather than silently discard it.",
    "Ordinary GET may perform migrations or retrieval bookkeeping, and projection transport uses local request scratch; an output-not-started refusal is not a claim that those preceding engine operations had no effects.",
    "Request identity, observation time, engine expectations, render configuration, adoption pin, binary sink and output clock are explicit caller inputs. No clock or UUID is allocated, no fallback or resend is attempted, and callbacks are not a sandbox.",
    "The existing result-body-before-queue-health-footer-v1 scope remains unchanged; this API emits only the recall result body, no health footer, stderr diagnostic or legacy touch-queue effect.",
    "Enclosing normal exits are checked through retained bounded input and result pins after their handles retire; these callback-free tails are not fresh filesystem authority after release or hostile same-user immutability protection.",
    "No default activation, CLI/MCP change, JACKAL assurance, biological cognition claim, cognitive-mechanism warrant or held-out retrieval win is established; all original source, epoch, engine, projection, writer and journal nonclaims remain controlling.",
)
_BOUNDARY = "“Brain” is a product metaphor for auditable local machine memory; it is not a biological brain and does not establish cognition or neuroscience."
_LEGACY_TERMS = ("formal-receipt", "formal receipt", "lean-checked mathematics")
_PHASES = frozenset({"not-started", "unknown", "completed-unrecorded"})
_ERRORS = (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError,
           AttributeError, OverflowError, RecursionError)


class ControllerRecallOutputRefusal(ValueError):
    def __init__(self, reason, *, output_state="not-started", upstream=None):
        self.reason, self.output_state = reason, output_state
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = {
            "non_claims": getattr(upstream, "non_claims", ()),
            "upstream_non_claims": getattr(upstream, "upstream_non_claims", ()),
        }
        self.upstream_status = getattr(upstream, "upstream_status", None)
        self.upstream_mismatch_reasons = getattr(upstream, "upstream_mismatch_reasons", ())
        super().__init__("controller recall output refused: " + reason)


def _fail(reason):
    raise ControllerRecallOutputRefusal(reason)


class _Request:
    """Bound original scalar selections and documents before any first copy."""

    def __init__(self, owner, arguments, binary_sink, clock):
        if type(owner) is not dict:
            _fail("owner-contract")
        self.owner, self.arguments = owner, arguments
        self.documents, self.pins = {}, {}
        self.values = {key: owner.get(key) for key in (
            *writer_api._PATHS, *writer_api._CAPACITIES,
            *engine_api._PATHS, *engine_api._CAPACITIES,
            "GBRAIN_SOURCE", "VERSION", "NOTIFY_BASELINE_ATTEMPT_KEY",
            "BRAIN_METAPHOR_BOUNDARY")}
        self.references = {key: owner.get(key) for key in (
            *engine_api._OPERATIONS, *engine_api._CONTEXTS,
            *wrapper_api._OWNER_REFERENCES, "strip_controls",
            "_contains_legacy_jackal_assurance", "unicodedata")}
        for key in {*writer_api._CAPACITIES, *engine_api._CAPACITIES}:
            if type(self.values[key]) is not int or self.values[key] <= 0:
                _fail("owner-capacity")
        for key in (*engine_api._OPERATIONS, "strip_controls", "_contains_legacy_jackal_assurance"):
            if not callable(self.references[key]):
                _fail("owner-operation")
        if type(self.values["BRAIN_METAPHOR_BOUNDARY"]) is not str \
                or self.values["BRAIN_METAPHOR_BOUNDARY"] != _BOUNDARY:
            _fail("current-cortex-boundary-required")
        if self.values["GBRAIN_SOURCE"] != "sia" or type(self.values["GBRAIN_SOURCE"]) is not str \
                or type(self.values["VERSION"]) is not str or not self.values["VERSION"] \
                or type(self.values["NOTIFY_BASELINE_ATTEMPT_KEY"]) is not str \
                or not self.values["NOTIFY_BASELINE_ATTEMPT_KEY"]:
            _fail("owner-selection")
        terms = owner.get("_LEGACY_JACKAL_ASSURANCE_TERMS")
        if type(terms) is not tuple or len(terms) != len(_LEGACY_TERMS) \
                or any(type(term) is not str for term in terms) or terms != _LEGACY_TERMS:
            _fail("current-legacy-assurance-classifier-required")
        self.terms = terms
        self.terms_pin = writer_api._plain_pin(terms)
        self.ceiling = min(self.values["MAX_STATE_JSON_BYTES"], live.MAX_INPUT_BYTES)
        self.native_owner = {"json": json, "hashlib": hashlib, "math": math,
                             "MAX_STATE_JSON_BYTES": self.ceiling}
        # Reuse the source wrapper's actual bounded owner basis, not a fake
        # source/rank request. Its provider identities were captured above.
        basis = wrapper_api._owner_basis(owner)
        self.size({"arguments": arguments, "arguments_copy": arguments,
                   "owner_values": self.values, "owner_basis": basis,
                   "legacy_terms": list(terms)})
        self.argument_pin = writer_api._plain_pin(arguments)
        self.owner_pins = {key: writer_api._plain_pin(owner.get(key)) for key in (
            *wrapper_api._CAPACITIES, "_SENSE_ORGAN", "LIVE_PUBLICATION_NON_CLAIMS")}
        self.current(admitted=False)
        for key in {*writer_api._PATHS, *engine_api._PATHS}:
            source._canonical_path(owner, self.values[key])
        if type(arguments["retained_batch"]) is not dict \
                or arguments["retained_batch"].get("schema") != "sia-controller-source-batch-v3":
            _fail("acknowledged-source-v3-required")
        for key in ("expected_adoption_sha256", "expected_journal_limits_sha256",
                    "expected_engine_expectations_sha256", "expected_render_config_sha256"):
            consistency_api._hex(arguments[key], "external-output-pin")
        journal_api._limits(arguments["journal_limits"])
        if live._sha(arguments["journal_limits"]) != arguments["expected_journal_limits_sha256"]:
            _fail("journal-limits-pin")
        writer_api._render_config(
            arguments["render_config"], arguments["expected_render_config_sha256"],
            arguments["journal_limits"], self.ceiling)
        if arguments["render_config"]["display_limit"] != 1:
            _fail("literal-singleton-display-required")
        subject = arguments["subject"]
        # Current cmd_recall's length ceiling, within the stricter shared
        # canonical source subject grammar; no widened CLI slug contract.
        if type(subject) is not str or not 0 < len(subject) <= 200 \
                or engine_api._GET_SUBJECT.fullmatch(subject) is None:
            _fail("canonical-recall-subject")
        if type(arguments["timeout"]) is not int \
                or not 0 < arguments["timeout"] <= self.values["MAX_JSON_SAFE_INTEGER"] \
                or not live._integer(arguments["observed_at"]):
            _fail("explicit-time-inputs")
        journal_api._request_id(arguments["request_id"])
        self.admitted = copy.deepcopy(arguments)
        self.current()
        # Capture caller operations once. No dynamic property lookup occurs
        # in the callback-free release tail or selects a replacement sink.
        self.write = getattr(binary_sink, "write", None)
        self.flush = getattr(binary_sink, "flush", None)
        self.clock = clock
        if not callable(self.write) or not callable(self.flush) or not callable(clock):
            _fail("explicit-output-and-clock-required")
        self.current()

    def size(self, value):
        return source._json_size(self.native_owner, value, self.ceiling, ascii_only=True)

    def wire(self, value):
        return source.native_bytes(self.native_owner, value)

    def sha(self, value):
        return hashlib.sha256(self.wire(value)).hexdigest()

    def budget(self, **prospective):
        self.size({"original": self.arguments, "admitted": self.admitted,
                   "retained": self.documents, "prospective": prospective})
        self.current()

    def retain(self, name, value):
        self.size(value)
        pin = writer_api._plain_pin(value)
        self.budget(**{name: value})
        self.documents[name], self.pins[name] = value, pin
        self.current()

    def current(self, *, admitted=True):
        """Callback-free bounded equality; valid even after every owner exits."""
        if any(type(self.owner.get(key)) is not type(value) or self.owner.get(key) != value
               for key, value in self.values.items()) \
                or any(self.owner.get(key) is not value for key, value in self.references.items()) \
                or not writer_api._plain_same(self.owner.get("_LEGACY_JACKAL_ASSURANCE_TERMS"), self.terms_pin) \
                or any(not writer_api._plain_same(self.owner.get(key), pin)
                       for key, pin in self.owner_pins.items()):
            _fail("owner-basis-changed")
        if not writer_api._plain_same(self.arguments, self.argument_pin) \
                or admitted and not writer_api._plain_same(self.admitted, self.argument_pin) \
                or any(not writer_api._plain_same(value, self.pins[name])
                       for name, value in self.documents.items()):
            _fail("retained-input-or-result-changed")
        if admitted and consistency_api._containers(self.arguments) \
                & consistency_api._containers(self.admitted):
            _fail("input-copy-not-detached")


class _Output:
    """Guard actual callbacks and remember conservative existing phases."""

    def __init__(self, request):
        self.request = request
        self.phase = "not-started"
        self.projection = None
        self.renderer_result = None
        self.body = None
        self.refs_pin = None
        self.epoch_tx = self.engine_admission = None

    def tail(self):
        self.request.current()
        data = self.request.admitted
        if self.epoch_tx is not None and (
                self.epoch_tx.owner is not self.request.owner
                or self.epoch_tx.readonly is not True or self.epoch_tx.legacy is not False
                or type(self.epoch_tx.external) is not str
                or self.epoch_tx.external != data["expected_adoption_sha256"]):
            _fail("retained-adoption-selection-changed")
        if self.engine_admission is not None and (
                self.engine_admission.owner is not self.request.owner
                or type(self.engine_admission.expected) is not str
                or self.engine_admission.expected != data["expected_engine_expectations_sha256"]):
            _fail("retained-engine-expectation-selection-changed")
        if self.renderer_result is not None:
            value = self.renderer_result
            if type(value) is not dict or len(value) != 2 \
                    or any(type(key) is not str for key in value) \
                    or set(value) != {"emitted_row_refs", "output_utf8"} \
                    or not writer_api._plain_same(value["emitted_row_refs"], self.refs_pin) \
                    or type(value["output_utf8"]) is not bytes or value["output_utf8"] != self.body:
                _fail("literal-renderer-result-changed")

    def current(self):
        self.tail()
        if self.projection is None:
            _fail("active-projection-required")
        self.projection.current()
        self.tail()
        return None

    def write(self, value):
        self.current()
        # Any attempted real sink callback has an unknown outcome until an
        # actual flush returns, including a callback which itself raises.
        self.phase = "unknown"
        result = self.request.write(value)
        self.current()
        return result

    def flush(self):
        self.current()
        self.phase = "unknown"
        result = self.request.flush()
        self.phase = "completed-unrecorded"
        self.current()
        return result

    def clock(self):
        self.current()
        if self.phase != "completed-unrecorded":
            _fail("output-clock-before-flush")
        result = self.request.clock()
        self.current()
        return result

    def classify(self):
        self.current()
        observation = self.request.documents["projection"]
        page = observation["source_version"]
        if page["subject"].startswith(("events/jackal/", "epochs/jackal/", "thoughts/")):
            result = self.request.references["_contains_legacy_jackal_assurance"](page["content"])
            self.current()
            if type(result) is not bool:
                _fail("legacy-assurance-classifier-result")
            if result:
                _fail("unverified-jackal-separate-nondelivery-required")
        diagnostic = self.request.references["strip_controls"](
            observation["get_transport"]["stderr"])
        self.current()
        if type(diagnostic) is not str:
            _fail("control-strip-result")
        if diagnostic:
            _fail("get-stderr-requires-separate-diagnostic-path")

    def render(self, *, ranked, expected_ranked_sha256, config, expected_config_sha256):
        request, data = self.request, self.request.admitted
        self.current()
        if self.renderer_result is not None:
            _fail("literal-renderer-reentry")
        request.retain("ranked", ranked)
        request.retain("callback_config", config)
        observation = request.documents["projection"]
        generation = request.documents["epoch_view"]["parent_generation"]
        writer_api._rank_current(request.owner, ranked, {
            "observed_at": data["observed_at"], "rows": observation["rows"],
            "expected_rows_sha256": observation["rows_sha256"],
        }, generation)
        version = observation["source_version"]["version_sha256"]
        if type(expected_ranked_sha256) is not str or expected_ranked_sha256 != ranked["rank_sha256"] \
                or type(expected_config_sha256) is not str \
                or expected_config_sha256 != data["expected_render_config_sha256"] \
                or not writer_api._plain_same(config, writer_api._plain_pin(data["render_config"])) \
                or type(ranked["order"]) is not list or ranked["order"] != [version]:
            _fail("actual-singleton-rank-or-config-join")
        self.current()
        cleaned = request.references["strip_controls"](observation["get_stdout"])
        self.current()
        if type(cleaned) is not str:
            _fail("control-strip-result")
        subject, origin = observation["subject"], observation["source_version"]["origin"]
        parts = [f"[origin:{origin}] {subject}\n"]
        if subject == "sia/cortex":
            parts.append(request.values["BRAIN_METAPHOR_BOUNDARY"] + "\n")
            cleaned = cleaned.replace(request.values["BRAIN_METAPHOR_BOUNDARY"], "")
        parts.append(cleaned)
        request.budget(literal_parts=parts, literal_body_copy=parts)
        # Bound exact UTF-8 bytes incrementally before joining the body or
        # handing it to the journal's existing base64/terminal reservation.
        remaining = config["max_body_bytes"]
        encoded = []
        for part in parts:
            raw = consistency_api._utf8(part, remaining, "literal-body-byte-capacity")
            remaining -= len(raw)
            encoded.append(raw)
        body = b"".join(encoded)
        text = "".join(parts)
        refs = [version]
        request.retain("literal_body", {"text": text, "emitted_row_refs": refs})
        self.body, self.refs_pin = body, writer_api._plain_pin(refs)
        self.renderer_result = {"emitted_row_refs": refs, "output_utf8": body}
        # Actual rank/body/identity, with a maximal retained-clock prototype
        # solely for capacity reservation. No clock is sampled and this is
        # neither a returned completion nor evidence that output occurred.
        intent = journal_api._new_intent(
            ranked=ranked, expected_ranked_sha256=ranked["rank_sha256"],
            emitted_row_refs=refs, output_utf8=body, request_id=data["request_id"],
            consumer="cli.recall", limits=data["journal_limits"])
        request.retain("intent", intent)
        terminal = journal_api._completion(intent, journal_api._pure(
            intent, body, live.MAX_SAFE_INTEGER))
        request.budget(prospective_completion=terminal, prospective_completion_copy=terminal)
        self.current()
        return self.renderer_result


def recall_and_deliver(owner, *, memo, admitted_status, retained_batch, committed,
                       journal_limits, expected_journal_limits_sha256,
                       expected_adoption_sha256, engine_expectations,
                       expected_engine_expectations_sha256, render_config,
                       expected_render_config_sha256, subject, timeout,
                       observed_at, request_id, binary_sink, clock):
    """Send one literal current recall body, retaining all enclosing exits.

    Every input is mandatory; consumer is fixed to cli.recall. No caller
    renderer, fallback, ambient clock, generated request ID, legacy touch,
    diagnostic sink or CLI activation is supplied by this entry point.
    The original existing journal completion is returned without extension.
    """
    output = None
    try:
        request = _Request(owner, {
            "memo": memo, "admitted_status": admitted_status,
            "retained_batch": retained_batch, "committed": committed,
            "journal_limits": journal_limits,
            "expected_journal_limits_sha256": expected_journal_limits_sha256,
            "expected_adoption_sha256": expected_adoption_sha256,
            "engine_expectations": engine_expectations,
            "expected_engine_expectations_sha256": expected_engine_expectations_sha256,
            "render_config": render_config,
            "expected_render_config_sha256": expected_render_config_sha256,
            "subject": subject, "timeout": timeout, "observed_at": observed_at,
            "request_id": request_id,
        }, binary_sink, clock)
        data = request.admitted
        output = _Output(request)
        preserve = engine_api._preserve_exception
        with preserve(request.references["corpus_owner"]()):
            request.current()
            with preserve(epoch_api.hold_epoch(
                    owner, memo=data["memo"], admitted_status=data["admitted_status"],
                    retained_batch=data["retained_batch"], committed=data["committed"],
                    journal_limits=data["journal_limits"],
                    expected_journal_limits_sha256=data["expected_journal_limits_sha256"],
                    expected_adoption_sha256=data["expected_adoption_sha256"])) as epoch:
                output.epoch_tx = epoch._tx
                output.tail()
                request.budget(epoch_view=epoch._view, epoch_view_copy=epoch._view)
                request.retain("epoch_view", epoch.read())
                view = request.documents["epoch_view"]
                generation = view["parent_generation"]
                if not writer_api._plain_same(view["parent_committed"], writer_api._plain_pin(data["committed"])) \
                        or generation["generation_sha256"] != data["committed"]["live_generation_sha256"] \
                        or view["expected_parent_generation_sha256"] != generation["generation_sha256"] \
                        or view["epoch_adoption"]["expected_adoption_sha256"] != data["expected_adoption_sha256"]:
                    _fail("actual-output-epoch-join")
                writer_api._render_config(
                    data["render_config"], data["expected_render_config_sha256"],
                    data["journal_limits"], request.ceiling,
                    policy=generation["transition"]["state"]["policy"])

                def source_current():
                    request.current()
                    epoch.current()
                    request.current()
                    return None

                source_current()
                with preserve(engine_api.hold_overlay_engine(
                        owner, expectations=data["engine_expectations"],
                        expected_expectations_sha256=data["expected_engine_expectations_sha256"],
                        authority_current=source_current)) as engine:
                    output.engine_admission = engine.admission
                    output.tail()
                    request.budget(engine_binding=engine.binding, engine_binding_copy=engine.binding)
                    request.retain("engine_binding", engine.read())
                    binding = request.documents["engine_binding"]
                    source_current()
                    with preserve(projection_api.hold_recall_projection(
                            owner, held_epoch=epoch, held_engine=engine,
                            expected_epoch_view_sha256=request.sha(view),
                            expected_engine_binding_sha256=binding["binding_sha256"],
                            expected_engine_expectations_sha256=data["expected_engine_expectations_sha256"],
                            subject=data["subject"], timeout=data["timeout"])) as projection:
                        output.projection = projection
                        request.budget(projection=projection.documents["result"],
                                       projection_copy=projection.documents["result"])
                        request.retain("projection", projection.read())
                        observation = request.documents["projection"]
                        if observation["parent_generation_sha256"] != generation["generation_sha256"] \
                                or observation["parent_state_sha256"] != generation["state_sha256"] \
                                or observation["adoption_sha256"] != data["expected_adoption_sha256"] \
                                or observation["expected_epoch_view_sha256"] != request.sha(view):
                            _fail("actual-output-projection-join")
                        output.classify()
                        completed = writer_api.render_and_deliver(
                            owner, memo=data["memo"], admitted_status=data["admitted_status"],
                            retained_batch=data["retained_batch"], committed=data["committed"],
                            journal_limits=data["journal_limits"],
                            expected_journal_limits_sha256=data["expected_journal_limits_sha256"],
                            expected_adoption_sha256=data["expected_adoption_sha256"],
                            rows=observation["rows"], expected_rows_sha256=observation["rows_sha256"],
                            observed_at=data["observed_at"], render_config=data["render_config"],
                            expected_render_config_sha256=data["expected_render_config_sha256"],
                            renderer=output.render, request_id=data["request_id"],
                            consumer="cli.recall", binary_sink=output, clock=output.clock)
                        # Includes exact completed retry: a later refusal must
                        # not deny the completion already returned by writer.
                        output.phase = "completed-unrecorded"
                        request.retain("completed", completed)
                        output.current()
                        intent = request.documents["intent"]
                        replay = journal_api._completion(intent, journal_api._pure(
                            intent, output.body, completed["record"]["completed_at"]))
                        if journal_api._wire(completed, data["journal_limits"]) \
                                != journal_api._wire(replay, data["journal_limits"]):
                            _fail("unchanged-writer-completion-required")
                        output.current()
                    # Projection has retired; do not call it again. Its copied
                    # observation and our completion remain pinned through all
                    # still-enclosing owner exit callbacks.
                    output.projection = None
                    output.tail()
                    engine.current()
                    source_current()
                    output.tail()
                # Engine owners and descriptor cleanup have completed.
                source_current()
                output.tail()
            # Epoch ownership has ended. Only callback-free retained checks
            # are permitted from here; no path or closed handle is reopened.
            output.tail()
        # Last outer corpus exit has completed. No copy/provider/serializer
        # follows these retained comparisons before returning original result.
        output.tail()
        return completed
    except _ERRORS as exc:
        observed = "not-started" if output is None else output.phase
        upstream = getattr(exc, "output_state", "not-started")
        phase = observed if observed != "not-started" else upstream
        if type(phase) is not str or phase not in _PHASES:
            phase = "unknown"
        reason = exc.reason if isinstance(exc, ControllerRecallOutputRefusal) else "recall-output-domain-refused"
        raise ControllerRecallOutputRefusal(reason, output_state=phase, upstream=exc) from exc
    except BaseException as exc:
        # Cancellation keeps its exact identity. Attaching an informational
        # phase note is best-effort and must never mask the original exception.
        if output is not None and output.phase != "not-started":
            try:
                BaseException.add_note(exc, "controller recall output state: " + output.phase)
            except BaseException:
                pass
        raise
