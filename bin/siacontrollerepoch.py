"""Construct pinned controller-source epochs without observation.

The live policy below is a checked-in engineering policy.  Construction
projects the active source registry and effective custom-source selection into
the document contracts already enforced by :mod:`siasourcebatch` and
:mod:`siaeventintake`.  It invokes no collector and performs no publication.
"""

import re

import siaeventintake as _intake
import sialiveloop as _live
import siasourcebatch as _source


# This is deliberately a literal production policy, not an import from a test
# fixture and not a tuned benchmark winner.  Its pin is checked before runtime
# source selection on every build.
LIVE_POLICY = {
    "schema": "sia-live-loop-policy-v2",
    "scope": "complete-controller-observations-since-declared-epoch-v1",
    "time_unit": "unix-seconds-integer",
    "encoding": {
        "v": 1, "algorithm": "dirichlet-prequential-information-v1",
        "time_unit": "unix-seconds-integer", "pseudocount": 1,
        "signal": "relative-novelty", "strength_base": 1,
        "strength_scale": 1, "strength_cap": 8,
        "max_events": 4096, "max_symbols": 256, "max_contexts": 256,
    },
    "activation": {
        "v": 1, "algorithm": "log-sum-power-law-v1",
        "time_unit": "unix-seconds-integer", "decay": 1,
        "age_offset_seconds": 1, "tie_break": "stable-input-order",
        "unavailable": "last", "max_uses": 4096,
        "max_total_uses": 4096, "max_candidates": 256,
    },
    "workspace": {
        "v": 1, "algorithm": "activation-competition-held-payload-v1",
        "time_unit": "unix-seconds-integer", "slots": 1,
        "ignition_threshold": -2, "hold_seconds": 10,
        "max_hold_seconds": 60, "tie_break": "stable-input-order",
        "release_policy": "expire-or-explicit",
        "consumer_roster": ["resident-status", "context-selection"],
        "max_candidates": 256, "max_consumers": 16,
        "max_content_bytes": 4096, "max_payload_bytes": 65536,
        "max_broadcast_bytes": 1048576,
    },
    "coretrieval": {
        "v": 1, "algorithm": "joint-activity-product-v1",
        "time_unit": "unix-seconds-integer", "learning_rate": 0.5,
        "excluded_subjects": [],
        "hygiene": {
            "algorithm": "elapsed-period-retention-v1", "period_seconds": 2,
            "retention_per_period": 0.5, "weight_floor": 0,
            "degree_cap": 256, "cap_order": "weight-desc-pair-id",
        },
        "max_nodes": 256, "max_deliveries": 4096,
        "max_activities_per_delivery": 256, "max_total_activities": 4096,
        "max_pair_updates": 4096, "max_pairs": 4096,
        "max_graph_edges": 4096,
    },
    "novelty_admission": {
        "comparison": "strength-at-least-v1", "threshold": 2,
        "aggregation": "any-admitted-occurrence-per-version-v1",
        "explicit_delivery": "admit-without-novelty-filter-v1",
    },
    "activation_events": ["encoding-admitted", "service-output-completed"],
    "workspace_release": "expiry-only-v1",
    "recall_order": "origin-slot-preserving-activation-v1",
    "delivery_body": "result-body-before-queue-health-footer-v1",
    "delivery_activity": 1,
    "idle": "bound-native-episodes-replay-gist-fresh-derived-only-v2",
    "limits": {
        "max_input_bytes": 16777216, "max_output_bytes": 16777216,
        "max_versions": 256, "max_observations": 4096,
        "max_deliveries": 4096, "max_rows": 256,
        "max_content_bytes": 1048576, "max_delivery_bytes": 1048576,
    },
}
EXPECTED_LIVE_POLICY_SHA256 = "299d4fb5ff7ffe8d466d997780b8c67346ac4201b96dd0b3d62801ccc486e787"

NON_CLAIMS = (
    "This builder projects supplied active configuration and callable identities; it does not observe config-file bytes, optional-source probes, collector execution, source availability, source truth, or complete machine history.",
    "The checked-in live policy is an explicit engineering selection, not JACKAL assurance, biological cognition, cognitive authorization, tuning evidence, or a held-out retrieval win.",
    "An empty complete history is complete only from this newly declared initial controller epoch; it does not reconstruct or deny pre-epoch observations.",
    "A successor preserves one validated retained history and appends one validated captured batch; it does not reconstruct a missing predecessor, bridge policy or configuration drift, or prove observations outside that epoch.",
    "The supplied compact commit is local continuation authority and a cross-pin, not independent proof that its effects receipt, live generation, or external delivery existed.",
    "Component and native hashes bind represented canonical bytes; they do not authenticate an author, historical correctness, uninterrupted runtime identity, or hostile same-user immutability.",
    "The returned detached request is not capture, durable staging, publication, cursor acknowledgment, consumer delivery, or readiness.",
    "All source-batch, source-intake, live-loop, and component nonclaims remain controlling.",
)
_REASON = re.compile(r"[a-z][a-z0-9-]*\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMITTED_KEYS = frozenset({
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
})


class ControllerEpochRefusal(ValueError):
    """The current runtime cannot be represented as the requested epoch."""

    def __init__(self, reason, *, upstream=None):
        self.reason = reason if type(reason) is str and _REASON.fullmatch(reason) else "closed-refusal"
        self.non_claims = list(NON_CLAIMS)
        upstream_reason = getattr(upstream, "reason", None)
        self.upstream_reason = (upstream_reason if type(upstream_reason) is str
                                and _REASON.fullmatch(upstream_reason) else None)
        self.upstream_non_claims = list(getattr(upstream, "non_claims", ()))[:64]
        super().__init__("controller source epoch refused: " + self.reason)


def _refuse(reason, *, upstream=None):
    raise ControllerEpochRefusal(reason, upstream=upstream)


def _component_sha(owner, value, reason):
    try:
        return _source._component_sha(owner, value)
    except _source.SourceBatchRefusal as exc:
        _refuse(reason, upstream=exc)


def _native_bytes(owner, value, reason):
    try:
        return _source.native_bytes(owner, value)
    except _source.SourceBatchRefusal as exc:
        _refuse(reason, upstream=exc)


def _current(owner, config_object, config_raw, policy_raw):
    errors = owner.get("CONFIG_ERRORS")
    if type(errors) is not list or errors:
        _refuse("active-configuration-errors")
    if owner.get("CONFIG") is not config_object:
        _refuse("active-configuration-drift")
    if _native_bytes(owner, config_object, "active-configuration-capacity") != config_raw:
        _refuse("active-configuration-drift")
    if _component_sha(owner, LIVE_POLICY, "live-policy-capacity") != \
            EXPECTED_LIVE_POLICY_SHA256 or _live._canonical(LIVE_POLICY) != policy_raw:
        _refuse("live-policy-pin")


def _canonical_custom(owner, entry, normalized):
    try:
        return _source._canonical_custom_selection_entry(
            owner, entry, normalized)
    except _source.SourceBatchRefusal as exc:
        _refuse(exc.reason, upstream=exc)


def _runtime_selection(owner, config):
    try:
        disabled = _source._disabled_policy(owner, config)
    except _source.SourceBatchRefusal as exc:
        _refuse(exc.reason, upstream=exc)
    organs, senses = owner.get("ORGANS"), owner.get("SENSES")
    if type(organs) is not dict or type(senses) is not list:
        _refuse("runtime-selection-shape")
    for organ, values in organs.items():
        if type(organ) is not str or type(values) is not tuple \
                or len(values) != 2 \
                or any(type(value) is not str for value in values):
            _refuse("runtime-organ-contract")

    names, sense_objects, exported = [], [], []
    for sense in senses:
        name = getattr(sense, "__name__", None)
        if not callable(sense) or type(name) is not str or not name:
            _refuse("runtime-sense-contract")
        if name in names or owner.get(name) is not sense:
            _refuse("runtime-sense-identity")
        names.append(name)
        sense_objects.append(sense)
        exported.append(owner.get(name))
    if not names or names[-1] != "sense_custom" \
            or names.count("sense_custom") != 1:
        _refuse("runtime-custom-sense-roster")

    native = names[:-1]
    native_rows = []
    for name in native:
        organ = owner.get("_SENSE_ORGAN", {}).get(name)
        if type(organ) is not str or organ not in organs \
                or owner["sanitize_slugpart"](organ) in disabled \
                or owner["sanitize_slugpart"](name) in disabled:
            _refuse("runtime-native-selection")
        native_rows.append({
            "source_id": name, "collector": name,
            "organ": organ, "custom_name": None,
        })

    configured = config.get("custom_senses", [])
    if type(configured) is not list \
            or len(configured) > owner["MAX_LEDGER_PENDING_RECORDS"]:
        _refuse("runtime-custom-selection")
    selected, custom_rows, seen = [], [], set()
    for entry in configured:
        try:
            normalized = owner["_validated_custom_sense_entry"](entry)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            _refuse("runtime-custom-selection", upstream=exc)
        if normalized is None:
            continue
        name, organ, source_id = (normalized.get("name"),
                                  normalized.get("organ"),
                                  normalized.get("source_id"))
        if any(type(value) is not str or not value
               for value in (name, organ, source_id)) \
                or name in seen:
            _refuse("runtime-custom-selection")
        seen.add(name)
        if name in disabled or organ in disabled:
            continue
        if organ not in organs:
            _refuse("runtime-custom-selection")
        selected.append(_canonical_custom(owner, entry, normalized))
        custom_rows.append({
            "source_id": source_id, "collector": "sense_custom",
            "organ": organ, "custom_name": name,
        })
    rows = native_rows + custom_rows
    if not rows or len(rows) > owner["MAX_SOURCE_REPLAY_SOURCES"] \
            or len({row["source_id"] for row in rows}) != len(rows):
        _refuse("no-active-source" if not rows else "runtime-source-catalog")
    try:
        _live.encoding._roster(
            [row["source_id"] for row in rows],
            LIVE_POLICY["encoding"]["max_symbols"], "symbols")
    except ValueError as exc:
        reason = getattr(exc, "reason", None)
        _refuse(reason if type(reason) is str else "source-roster-contract",
                upstream=exc)
    identities = {"senses": tuple(sense_objects), "exported": tuple(exported)}
    return native, selected, rows, identities


def _selection_raw(owner, native, custom, sources):
    return _native_bytes(owner, {
        "native_collectors": native,
        "custom_collectors": custom,
        "sources": sources,
    }, "runtime-selection-capacity")


def _selection_current(owner, config, expected_raw, expected_identities):
    native, custom, sources, identities = _runtime_selection(owner, config)
    if _selection_raw(owner, native, custom, sources) != expected_raw \
            or len(identities["senses"]) != len(expected_identities["senses"]) \
            or any(current is not original for current, original in zip(
                identities["senses"], expected_identities["senses"])) \
            or any(current is not original for current, original in zip(
                identities["exported"], expected_identities["exported"])):
        _refuse("runtime-selection-drift")


def build_initial(owner, *, observed_at):
    """Return exact ``capture`` kwargs for a new, empty source epoch.

    ``observed_at`` is caller-supplied authority and is used unchanged as the
    epoch start.  No clock is read and no source callable is invoked.
    """
    try:
        if type(owner) is not dict:
            _refuse("owner-shape")
        if not _live._integer(observed_at):
            _refuse("controller-clock")
        errors = owner.get("CONFIG_ERRORS")
        if type(errors) is not list or errors:
            _refuse("active-configuration-errors")

        expected_policy_sha256 = EXPECTED_LIVE_POLICY_SHA256
        policy_sha256 = _component_sha(owner, LIVE_POLICY, "live-policy-capacity")
        if policy_sha256 != expected_policy_sha256:
            _refuse("live-policy-pin")
        try:
            _live._policy(LIVE_POLICY)
            policy_raw = _live._canonical(LIVE_POLICY)
        except _live.LiveLoopRefusal as exc:
            _refuse("live-policy-contract", upstream=exc)

        config = owner.get("CONFIG")
        if type(config) is not dict:
            _refuse("active-configuration-shape")
        config_raw = _native_bytes(owner, config, "active-configuration-capacity")
        active_valid = owner.get("_active_config_load_valid")
        if active_valid is not None:
            if not callable(active_valid):
                _refuse("active-configuration-provenance")
            try:
                if active_valid() is not True:
                    _refuse("active-configuration-provenance")
            except ControllerEpochRefusal:
                raise
            except (TypeError, ValueError, RuntimeError, AttributeError) as exc:
                _refuse("active-configuration-provenance", upstream=exc)
        _current(owner, config, config_raw, policy_raw)
        native, custom, sources, identities = _runtime_selection(owner, config)
        selection_raw = _selection_raw(owner, native, custom, sources)
        _current(owner, config, config_raw, policy_raw)

        source_non_claims = list(_intake.SOURCE_NON_CLAIMS)
        configuration = {
            "schema": "sia-controller-source-selection-v1",
            "native_collectors": list(native),
            "custom_collectors": owner["copy"].deepcopy(custom),
            "non_claims": source_non_claims,
        }
        configuration_sha256 = _component_sha(
            owner, configuration, "configuration-capacity")
        source_catalog = {
            "schema": "sia-controller-source-catalog-v1",
            "configuration_sha256": configuration_sha256,
            "sources": owner["copy"].deepcopy(sources),
            "non_claims": list(_intake.SOURCE_NON_CLAIMS),
        }
        source_catalog_sha256 = _component_sha(
            owner, source_catalog, "source-catalog-capacity")
        try:
            _intake._catalog(owner, {
                "configuration": configuration,
                "source_catalog": source_catalog,
            })
        except ValueError as exc:
            reason = getattr(exc, "reason", None)
            _refuse(reason if type(reason) is str else "source-catalog-contract",
                    upstream=exc)
        live_policy = owner["copy"].deepcopy(LIVE_POLICY)
        if _component_sha(owner, live_policy, "live-policy-capacity") != policy_sha256:
            _refuse("live-policy-copy-drift")
        profile = {
            **_intake._PROFILE,
            "live_policy_sha256": policy_sha256,
            "non_claims": list(_intake.SOURCE_NON_CLAIMS),
        }
        profile_sha256 = _component_sha(owner, profile, "profile-capacity")
        epoch_seed = {
            "schema": "sia-controller-source-initial-epoch-id-v1",
            "observed_at": observed_at,
            "configuration_sha256": configuration_sha256,
            "source_catalog_sha256": source_catalog_sha256,
            "profile_sha256": profile_sha256,
            "live_policy_sha256": policy_sha256,
        }
        epoch_id = "controller-source-" + _source.native_sha(owner, epoch_seed)
        history = {
            "schema": "sia-controller-event-history-v1",
            "epoch_id": epoch_id, "started_at": observed_at,
            "complete": True, "entries": [],
            "non_claims": list(_intake.SOURCE_NON_CLAIMS),
        }
        history_sha256 = _component_sha(owner, history, "history-capacity")
        epoch = {
            "schema": "sia-controller-source-epoch-v1",
            "epoch_id": epoch_id, "started_at": observed_at,
            "configuration": configuration,
            "expected_configuration_sha256": configuration_sha256,
            "source_catalog": source_catalog,
            "expected_source_catalog_sha256": source_catalog_sha256,
            "profile": profile,
            "expected_profile_sha256": profile_sha256,
            "live_policy": live_policy,
            "expected_live_policy_sha256": policy_sha256,
            "history": history,
            "expected_history_sha256": history_sha256,
            "predecessor": None,
            "non_claims": list(_source.NON_CLAIMS),
        }
        epoch_sha256 = _source.native_sha(owner, epoch)
        result = {
            "epoch": epoch, "expected_epoch_sha256": epoch_sha256,
            "observed_at": observed_at,
        }
        result_raw = _native_bytes(owner, result, "initial-request-capacity")
        _current(owner, config, config_raw, policy_raw)
        try:
            _source._validate_epoch(
                owner, epoch, epoch_sha256, observed_at, initial=True)
        except _source.SourceBatchRefusal as exc:
            _refuse(exc.reason, upstream=exc)
        _selection_current(owner, config, selection_raw, identities)
        _current(owner, config, config_raw, policy_raw)
        detached = owner["copy"].deepcopy(result)
        if _native_bytes(owner, result, "initial-request-capacity") != result_raw \
                or _native_bytes(owner, detached, "initial-request-capacity") != result_raw:
            _refuse("initial-request-copy-drift")
        _current(owner, config, config_raw, policy_raw)
        _selection_current(owner, config, selection_raw, identities)
        if _native_bytes(owner, result, "initial-request-capacity") != result_raw \
                or _native_bytes(owner, detached, "initial-request-capacity") != result_raw:
            _refuse("initial-request-final-drift")
        return detached
    except ControllerEpochRefusal:
        raise
    except _source.SourceBatchRefusal as exc:
        _refuse(exc.reason, upstream=exc)
    except _live.LiveLoopRefusal as exc:
        _refuse("live-policy-contract", upstream=exc)
    except (KeyError, TypeError, ValueError, RuntimeError, AttributeError,
            RecursionError, UnicodeError, OverflowError) as exc:
        _refuse("initial-epoch-construction", upstream=exc)


def _successor_history_issue(owner, batch):
    """Name successor-only continuity faults without trusting their content."""
    if type(batch) is not dict:
        return None
    epoch = batch.get("epoch")
    returns = batch.get("source_returns")
    if type(epoch) is not dict or type(returns) is not dict:
        return None
    history = epoch.get("history")
    if type(history) is not dict or type(history.get("entries")) is not list:
        return None
    entries = history["entries"]
    batch_id = returns.get("batch_id")
    if type(batch_id) is str:
        for entry in entries:
            if type(entry) is dict \
                    and type(entry.get("source_returns")) is dict \
                    and entry["source_returns"].get("batch_id") == batch_id:
                return "successor-history-duplicate"
    maximum = owner.get("MAX_SOURCE_REPLAY_EVENTS")
    if type(maximum) is int and not isinstance(maximum, bool) \
            and maximum >= 0 and len(entries) >= maximum:
        return "successor-history-capacity"
    if epoch.get("predecessor") is not None and not entries:
        return "successor-history-gap"
    return None


def _validated_successor_inputs(owner, retained_batch, committed):
    """Validate and snapshot one retained batch and its compact commit."""
    if type(committed) is not dict or set(committed) != _COMMITTED_KEYS:
        _refuse("successor-commit-shape")
    if any(type(committed[name]) is not str
           or _HEX.fullmatch(committed[name]) is None
           for name in _COMMITTED_KEYS):
        _refuse("successor-commit-digest")
    if type(retained_batch) is dict \
            and retained_batch.get("batch_sha256") \
            != committed["source_batch_sha256"]:
        _refuse("successor-commit-mismatch")

    batch_raw = _native_bytes(
        owner, retained_batch, "successor-retained-batch-capacity")
    committed_raw = _native_bytes(
        owner, committed, "successor-commit-capacity")
    try:
        _source.validate_batch(
            owner, retained_batch, committed["source_batch_sha256"])
    except _source.SourceBatchRefusal as exc:
        issue = _successor_history_issue(owner, retained_batch)
        if issue is not None and exc.reason == "intake-projection-contract":
            _refuse(issue, upstream=exc)
        _refuse(exc.reason, upstream=exc)
    issue = _successor_history_issue(owner, retained_batch)
    if issue is not None:
        _refuse(issue)
    if _native_bytes(
            owner, retained_batch,
            "successor-retained-batch-capacity") != batch_raw \
            or _native_bytes(
                owner, committed,
                "successor-commit-capacity") != committed_raw:
        _refuse("successor-input-drift")
    retained = owner["copy"].deepcopy(retained_batch)
    marker = owner["copy"].deepcopy(committed)
    if _native_bytes(
            owner, retained,
            "successor-retained-batch-capacity") != batch_raw \
            or _native_bytes(
                owner, marker,
                "successor-commit-capacity") != committed_raw:
        _refuse("successor-input-copy-drift")
    return retained, marker, batch_raw, committed_raw


def _same_successor_document(owner, current, retained, reason):
    if _native_bytes(owner, current, reason + "-capacity") \
            != _native_bytes(owner, retained, reason + "-capacity"):
        _refuse(reason)


def build_successor(owner, *, retained_batch, committed, observed_at):
    """Return capture kwargs continuing one committed controller epoch.

    The retained capture and caller-supplied compact commit are revalidated
    before the currently admitted configuration is projected.  The exact
    retained intake history gains that capture once, and the supplied clock is
    returned unchanged.  No collector is invoked and no state is published.
    """
    try:
        if type(owner) is not dict:
            _refuse("owner-shape")
        retained, marker, batch_raw, committed_raw = \
            _validated_successor_inputs(owner, retained_batch, committed)
        if not _live._integer(observed_at):
            _refuse("controller-clock")
        if observed_at < retained["observed_at"]:
            _refuse("successor-clock-gap")

        current_request = build_initial(owner, observed_at=observed_at)
        current_epoch = current_request["epoch"]
        config = owner.get("CONFIG")
        if type(config) is not dict:
            _refuse("active-configuration-shape")
        config_raw = _native_bytes(
            owner, config, "active-configuration-capacity")
        try:
            policy_raw = _live._canonical(LIVE_POLICY)
        except _live.LiveLoopRefusal as exc:
            _refuse("live-policy-contract", upstream=exc)
        native, custom, sources, identities = _runtime_selection(owner, config)
        selection_raw = _selection_raw(owner, native, custom, sources)
        _current(owner, config, config_raw, policy_raw)

        prior_epoch = retained["epoch"]
        for field, reason in (
                ("configuration", "successor-configuration-drift"),
                ("source_catalog", "successor-source-catalog-drift"),
                ("profile", "successor-profile-drift"),
                ("live_policy", "successor-live-policy-drift")):
            _same_successor_document(
                owner, current_epoch[field], prior_epoch[field], reason)

        history = owner["copy"].deepcopy(prior_epoch["history"])
        event_batches = ([] if retained["event_closure"] is None else [
            {
                "batch": owner["copy"].deepcopy(batch),
                "expected_batch_sha256": batch["batch_sha256"],
            }
            for batch in retained["event_closure"]["batches"]
        ])
        history["entries"].append({
            "source_returns": owner["copy"].deepcopy(
                retained["source_returns"]),
            "expected_source_returns_sha256":
                retained["source_returns"]["returns_sha256"],
            "event_batches": event_batches,
        })
        history_sha256 = _component_sha(
            owner, history, "successor-history-capacity")
        epoch = {
            "schema": "sia-controller-source-epoch-v1",
            "epoch_id": prior_epoch["epoch_id"],
            "started_at": prior_epoch["started_at"],
            "configuration": owner["copy"].deepcopy(
                current_epoch["configuration"]),
            "expected_configuration_sha256":
                current_epoch["expected_configuration_sha256"],
            "source_catalog": owner["copy"].deepcopy(
                current_epoch["source_catalog"]),
            "expected_source_catalog_sha256":
                current_epoch["expected_source_catalog_sha256"],
            "profile": owner["copy"].deepcopy(current_epoch["profile"]),
            "expected_profile_sha256":
                current_epoch["expected_profile_sha256"],
            "live_policy": owner["copy"].deepcopy(
                current_epoch["live_policy"]),
            "expected_live_policy_sha256":
                current_epoch["expected_live_policy_sha256"],
            "history": history,
            "expected_history_sha256": history_sha256,
            "predecessor": {
                "source_batch_sha256": marker["source_batch_sha256"],
                "live_generation_sha256":
                    marker["live_generation_sha256"],
            },
            "non_claims": list(_source.NON_CLAIMS),
        }
        epoch_sha256 = _source.native_sha(owner, epoch)
        result = {
            "epoch": epoch,
            "expected_epoch_sha256": epoch_sha256,
            "observed_at": observed_at,
        }
        result_raw = _native_bytes(
            owner, result, "successor-request-capacity")
        _current(owner, config, config_raw, policy_raw)
        _selection_current(owner, config, selection_raw, identities)
        try:
            _source._validate_epoch(
                owner, epoch, epoch_sha256, observed_at, initial=False)
            _source._runtime_projection(owner, epoch)
        except _source.SourceBatchRefusal as exc:
            _refuse(exc.reason, upstream=exc)
        if _native_bytes(
                owner, retained_batch,
                "successor-retained-batch-capacity") != batch_raw \
                or _native_bytes(
                    owner, committed,
                    "successor-commit-capacity") != committed_raw:
            _refuse("successor-input-drift")
        _current(owner, config, config_raw, policy_raw)
        _selection_current(owner, config, selection_raw, identities)
        detached = owner["copy"].deepcopy(result)
        if _native_bytes(
                owner, result,
                "successor-request-capacity") != result_raw \
                or _native_bytes(
                    owner, detached,
                    "successor-request-capacity") != result_raw:
            _refuse("successor-request-copy-drift")
        _current(owner, config, config_raw, policy_raw)
        _selection_current(owner, config, selection_raw, identities)
        if _native_bytes(
                owner, retained_batch,
                "successor-retained-batch-capacity") != batch_raw \
                or _native_bytes(
                    owner, committed,
                    "successor-commit-capacity") != committed_raw \
                or _native_bytes(
                    owner, result,
                    "successor-request-capacity") != result_raw \
                or _native_bytes(
                    owner, detached,
                    "successor-request-capacity") != result_raw:
            _refuse("successor-final-drift")
        return detached
    except ControllerEpochRefusal:
        raise
    except _source.SourceBatchRefusal as exc:
        _refuse(exc.reason, upstream=exc)
    except _live.LiveLoopRefusal as exc:
        _refuse("live-policy-contract", upstream=exc)
    except (KeyError, TypeError, ValueError, RuntimeError, AttributeError,
            RecursionError, UnicodeError, OverflowError) as exc:
        _refuse("successor-epoch-construction", upstream=exc)
