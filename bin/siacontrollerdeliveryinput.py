"""Pure append-only delivery input bound to a supplied committed parent.

An outer descriptor-owning controller must supply a complete inspected epoch
and its source-authorized parent. This component opens nothing, publishes
nothing and acknowledges nothing. It retains the inspection's boundary: a
pure completion record does not itself witness an output or consumer use.
"""

import copy

import siadelivery as journal_api
import sialiveloop as live


NON_CLAIMS = (
    "The caller supplies the complete inspected delivery epoch, committed parent, source authority and clock; this pure binding acquires none of them.",
    "Binding is not pulse consumption, publication, acknowledgment, observed output, human receipt or successful use.",
    "Journal v1 inspection retains completion records, not complete rank intents; their rank hashes do not independently reconstruct historical ranking or output.",
    "Prior delivery records remain byte-exact; new records retain derived origin and their supplied-bytes-admitted-not-observed-output-v1 boundary.",
    "No legacy touch history is reconstructed, no incomplete output is repaired and no source version is manufactured.",
    "Local state reconstruction is computed-unverified; no JACKAL assurance, biological cognition or held-out retrieval win is established.",
    "The complete journal and live-loop nonclaims remain controlling.",
)
_JOURNAL_KEYS = {"schema", "epoch_id", "complete", "records", "pending", "non_claims"}


class ControllerDeliveryInputRefusal(ValueError):
    def __init__(self, reason, upstream_non_claims=()):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_non_claims = upstream_non_claims
        super().__init__("controller delivery input refused: " + reason)


def _fail(reason):
    raise ControllerDeliveryInputRefusal(reason)


def _same(left, right):
    return live._canonical(left) == live._canonical(right)


def bind(*, journal, expected_journal_sha256,
         previous_state, expected_previous_state_sha256,
         intake, expected_intake_sha256, policy, expected_policy_sha256,
         observed_at):
    """Return detached complete delivery input, or a closed refusal.

    Full inspection is sorted by completion clock and identity. Previously
    consumed records instead retain their committed prefix order, including
    equal-clock deliveries whose later identity sorts before an earlier one.
    """
    try:
        supplied = locals().copy()
        live._budget(policy, supplied)
        original = live._canonical(supplied)
        admitted = copy.deepcopy(supplied)
        if live._canonical(supplied) != original or live._canonical(admitted) != original:
            _fail("input-changed-during-admission")
        journal = admitted["journal"]
        previous_state = admitted["previous_state"]
        intake, policy = admitted["intake"], admitted["policy"]
        if previous_state is None or not live._integer(observed_at):
            _fail("explicit-parent-and-clock-required")
        for value, pin in (
                (journal, expected_journal_sha256),
                (previous_state, expected_previous_state_sha256),
                (intake, expected_intake_sha256),
                (policy, expected_policy_sha256)):
            live._pin(value, pin)
        live._keys(journal, _JOURNAL_KEYS, "controller-delivery-journal")
        if journal["schema"] != "sia-live-delivery-journal-v1" \
                or journal["complete"] is not True \
                or type(journal["pending"]) is not list or journal["pending"] \
                or journal["non_claims"] != list(journal_api.NON_CLAIMS) \
                or journal["epoch_id"] != intake["epoch_id"]:
            _fail("complete-journal-epoch-contract")

        parent_versions = live._state(
            previous_state, expected_previous_state_sha256, policy, observed_at)
        live._pages(intake, observed_at, policy)
        # The successor may add perceptions, but may not rewrite retained
        # pages/observations or use new pages to backfill an earlier recall.
        live._continuation(previous_state, intake, previous_state["deliveries"])
        for field in ("pages", "observations"):
            old = previous_state["intake"][field]
            if not _same(intake[field][:len(old)], old):
                _fail("typed-parent-intake-prefix-changed")
        if not _same(previous_state["policy"], policy):
            _fail("typed-parent-policy-changed")

        inspected = {
            "schema": "sia-live-deliveries-v1", "epoch_id": journal["epoch_id"],
            "complete": True, "records": journal["records"],
        }
        live._delivery_roster(inspected, previous_state["intake"], parent_versions,
                              policy, observed_at)
        records = inspected["records"]
        for record in records:
            journal_api._request_id(record["id"])
        if [row["id"] for row in records] != [row["id"] for row in sorted(
                records, key=lambda row: (row["completed_at"], row["id"]))]:
            _fail("noncanonical-journal-order")
        by_id = {row["id"]: row for row in records}
        previous = previous_state["deliveries"]["records"]
        consumed = {row["id"] for row in previous}
        for row in previous:
            if row["id"] not in by_id or not _same(row, by_id[row["id"]]):
                _fail("committed-delivery-missing-or-changed")
        fresh = [row for row in records if row["id"] not in consumed]
        for row in fresh:
            if row["state_sha256"] != expected_previous_state_sha256 \
                    or row["ranked_at"] < previous_state["observed_at"] \
                    or row["completed_at"] < previous_state["observed_at"]:
                _fail("new-delivery-parent-state-or-clock-binding")
        deliveries = {**inspected, "records": previous + fresh}
        live._delivery_roster(deliveries, intake, parent_versions, policy, observed_at)
        result = {
            "schema": "sia-controller-delivery-binding-v1",
            "status": "bound-not-consumed", "epoch_id": journal["epoch_id"],
            "observed_at": observed_at, "journal_sha256": expected_journal_sha256,
            "previous_state_sha256": expected_previous_state_sha256,
            "intake_sha256": expected_intake_sha256,
            "policy_sha256": expected_policy_sha256,
            "deliveries": deliveries, "deliveries_sha256": live._sha(deliveries),
            "journal_non_claims": list(journal["non_claims"]),
            "non_claims": list(NON_CLAIMS),
        }
        live._size({**result, "binding_sha256": "0" * 64},
                   policy["limits"]["max_output_bytes"])
        result["binding_sha256"] = live._sha(result)
        final = copy.deepcopy(result)
        if not _same(result, final) or live._canonical(supplied) != original \
                or live._canonical(admitted) != original:
            _fail("input-or-binding-changed-before-return")
        return final
    except ControllerDeliveryInputRefusal:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError,
            OverflowError, RecursionError) as exc:
        raise ControllerDeliveryInputRefusal(
            "delivery-binding-domain-refused", {
                "non_claims": getattr(exc, "non_claims", []),
                "upstream_non_claims": getattr(exc, "upstream_non_claims", []),
            }) from exc
