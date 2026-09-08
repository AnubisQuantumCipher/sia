"""Construct one live candidate from the caller's retained source authority.

This component receives the actual resident namespace explicitly; it never
imports a canonical sialib or binds another alias's globals. The sialib facade
holds the brainstem and corpus owners around the complete ordinary function
call. No context manager or suspended generator crosses this boundary.

The existing retained-batch and committed-parent readers remain the authority.
Preparation executes the unchanged live input contracts and returns only their
detached candidate envelope. It does not collect a source, publish a candidate,
acknowledge a transaction, deliver output, or establish a cognitive win.
"""

import siacontrollerliveinput
import sialiveloop
import siasourcebatch


def prepare(owner, *, memo, admitted_status):
    """Build under the caller's continuously held brainstem/corpus scopes."""
    source_view = owner["_read_pending_controller_source_batch"](memo=memo)
    if source_view.get("status") != "pending" \
            or type(source_view.get("batch")) is not dict:
        siasourcebatch.refuse(
            "controller-source-pending-batch-required", phase="live-prepare")
    batch = source_view["batch"]
    previous_state = previous_sha256 = None
    generation = generation_sha256 = None
    if "live_loop_committed" in memo:
        live_view = owner["_read_committed_live_generation"](
            memo=memo, admitted_status=admitted_status)
        if live_view.get("status") != "available" \
                or type(live_view.get("generation")) is not dict:
            siasourcebatch.refuse(
                "controller-source-live-parent-unavailable",
                phase="live-prepare")
        generation = live_view["generation"]
        generation_sha256 = memo["live_loop_committed"]["generation_sha256"]
        previous_state = owner["copy"].deepcopy(generation["transition"]["state"])
        previous_sha256 = generation["state_sha256"]
    elif owner["_live_started"](memo):
        # An exact initial binding retry is a started transaction, but it
        # intentionally has no committed parent or live artifact yet.
        # Every other started shape remains an orphan refusal.
        try:
            binding = owner["_controller_source_live_binding_marker"](memo)
        except (TypeError, ValueError, KeyError, OverflowError,
                RecursionError) as exc:
            siasourcebatch.refuse(
                "controller-source-live-parent-unbound",
                phase="live-prepare", upstream=exc)
        if binding is None \
                or binding["parent_generation_sha256"] is not None \
                or binding["parent_state_sha256"] is not None \
                or "live_loop_pending" in memo \
                or owner["_live_present"](owner["LIVE_CANDIDATE_PATH"]) \
                or owner["_live_present"](owner["LIVE_STATE_PATH"]):
            siasourcebatch.refuse(
                "controller-source-live-parent-unbound",
                phase="live-prepare")
    try:
        if batch.get("schema") == "sia-controller-source-batch-v3":
            prepare_inputs = siacontrollerliveinput.prepare_inputs_v3(
                owner, batch=batch, previous_generation=generation,
                expected_previous_generation_sha256=generation_sha256)
        else:
            prepare_inputs = siacontrollerliveinput.prepare_inputs(
                batch=batch, previous_state=previous_state,
                expected_previous_state_sha256=previous_sha256)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        siasourcebatch.refuse(
            "controller-source-live-intake-continuation",
            phase="live-prepare", upstream=exc)
    # Execute the exact component contract now; live publication replays
    # the same pinned input before retaining a candidate.
    sialiveloop.prepare_pulse(**prepare_inputs)
    result = {
        "prepare_inputs": prepare_inputs,
        "expected_prepare_inputs_sha256": sialiveloop._sha(prepare_inputs),
    }
    frozen = sialiveloop._canonical(result)
    detached = owner["copy"].deepcopy(result)
    if sialiveloop._canonical(result) != frozen \
            or sialiveloop._canonical(detached) != frozen:
        siasourcebatch.refuse(
            "controller-source-live-input-changed", phase="live-prepare")
    return detached
