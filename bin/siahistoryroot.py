"""Prepare a retained history root from acknowledged source authority.

The root references the entire legacy source archive (including its prefix)
and a retained block for its final entry. It does not relabel that entry as
complete machine history or activate a new epoch. No mutable head is written.
"""

import contextlib
import hashlib
import json
import os

import siahistoryblock as blocks
import siahistoryblockstore as store
import siasourceack as ack
import siasourcebatch as source


NON_CLAIMS = (
    "This root binds an acknowledged source generation revalidated through the existing reader while the ordinary owner scopes are held; it does not activate segmented continuation.",
    "The legacy prefix remains in the referenced source archive, not the final-entry block. Later replay must retain and validate that archive and its original nonclaims.",
    "Root retention is not source acknowledgment, cursor advancement, a replacement epoch, a complete-chain audit, cognitive authorization or a held-out win.",
    "A failed call may leave unactivated exact block/root files. Their presence alone is not authority; activation requires independent admission and its own durable protocol.",
    "Owner coordination and descriptor checks are not protection against hostile same-user mutation or proof of source truth or storage hardware reliability.",
    "All source, history-block and block-retention nonclaims remain controlling.",
)


def prepare(owner, *, memo, admitted_status, directory):
    """Retain a root candidate without modifying the acknowledged source.

    The private destination already exists. Source authority is read through
    the existing completed-source boundary before and after publication.
    No collectors, supplied clocks, source acknowledgers or active-head writes
    are invoked. Existing source readers keep their original admission rules.
    """
    memo_raw = blocks._wire(memo)
    status_raw = blocks._wire(admitted_status)

    def inputs_current():
        if blocks._wire(memo) != memo_raw or blocks._wire(admitted_status) != status_raw:
            blocks._refuse("root-input-changed")

    with owner["brainstem_owner"](), owner["corpus_owner"](), contextlib.ExitStack() as stack:
        inputs_current()
        root_dir = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(root_dir.close)
        view = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
        if type(view) is not dict or set(view) != {"status", "batch", "committed"} \
                or view["status"] != "available" \
                or view["committed"] != memo.get("controller_source_committed"):
            blocks._refuse("root-completed-source-view")
        batch, committed = view["batch"], view["committed"]
        batch_raw, committed_raw = blocks._wire(batch), blocks._wire(committed)

        def source_current():
            inputs_current()
            current = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
            if current.get("status") != "available" \
                    or blocks._wire(current.get("batch")) != batch_raw \
                    or blocks._wire(current.get("committed")) != committed_raw:
                blocks._refuse("root-source-changed")
            inputs_current()

        block = blocks.prepare_captured(
            owner, batch=batch, expected_batch_sha256=committed["source_batch_sha256"],
            parent=None, expected_parent_sha256=None)
        block_raw = blocks._wire(block)
        block_pin = hashlib.sha256(block_raw).hexdigest()
        root = {
            "schema": "sia-source-history-root-v1", "status": "root-retained-not-activated",
            "epoch_id": batch["epoch"]["epoch_id"],
            "committed": json.loads(committed_raw),
            "legacy_epoch_sha256": batch["epoch_sha256"],
            "legacy_history_sha256": batch["epoch"]["expected_history_sha256"],
            "final_entry_block_sha256": block_pin, "non_claims": list(NON_CLAIMS),
        }
        root_raw = blocks._wire(root)
        root_pin = hashlib.sha256(root_raw).hexdigest()
        detached = json.loads(root_raw)
        inputs_current()
        store.retain(directory=directory, block=block, expected_block_sha256=block_pin)
        source_current()
        held_block = store._observe(stack, owner, directory, block_pin, required=True)
        if held_block.raw != block_raw:
            blocks._refuse("root-block-changed")
        path = os.path.join(directory, "root-" + root_pin + ".json")
        root_dir.current()
        try:
            store.queue.fixed_atomic_publish(
                path, root_raw, mode=0o600, exclusive=True,
                destination_dir_fd=root_dir.fd,
                staging_dir=os.path.join(directory, ".history-root-staging"))
        except (OSError, ValueError) as exc:
            raise blocks.HistoryBlockRefusal("root-publication") from exc
        held_root = ack._HeldRaw(owner, source, path, blocks.MAX_DOCUMENT_BYTES, allow_absent=False)
        stack.callback(held_root.close)
        if held_root.raw != root_raw:
            blocks._refuse("retained-root-changed")
        source_current()
        if blocks._wire(detached) != root_raw or blocks._wire(root) != root_raw \
                or blocks._wire(block) != block_raw or blocks._wire(batch) != batch_raw \
                or blocks._wire(committed) != committed_raw:
            blocks._refuse("root-output-changed")
        result = {"root": detached, "root_sha256": root_pin}
        held_block.current()
        held_root.current()
        root_dir.current()
        return result


SEED_NON_CLAIMS = NON_CLAIMS + (
    "This seed retains an incremental checkpoint whose intake matches the acknowledged source projection; it is not activation or permission to publish a successor.",
    "The referenced root and original source archive remain required. File presence alone cannot authorize recovery or a mutable head.",
)


def prepare_checkpoint(owner, *, memo, admitted_status, directory, expected_root_sha256):
    """Retain a source/root-bound v2 checkpoint and an inert seed receipt."""
    import siaeventcheckpoint as checkpoints

    if not blocks._digest(expected_root_sha256):
        blocks._refuse("seed-root-pin")
    wire = lambda value: checkpoints._wire(owner, value)
    memo_raw, status_raw = wire(memo), wire(admitted_status)
    limit = min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES)
    with owner["brainstem_owner"](), owner["corpus_owner"](), contextlib.ExitStack() as stack:
        directory_hold = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(directory_hold.close)

        def hold(prefix, pin):
            path = os.path.join(directory, prefix + pin + ".json")
            held = ack._HeldRaw(owner, source, path, limit, allow_absent=False)
            stack.callback(held.close)
            blocks._pin(held.raw, pin)
            return held

        root_file = hold("root-", expected_root_sha256)
        root = json.loads(root_file.raw)
        if wire(root) != root_file.raw:
            blocks._refuse("seed-root-image")
        view = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
        if view.get("status") != "available" or view.get("committed") != memo.get("controller_source_committed"):
            blocks._refuse("seed-source-authority")
        batch, committed = view["batch"], view["committed"]
        batch_raw, committed_raw = wire(batch), wire(committed)
        block = blocks.prepare_captured(owner, batch=batch,
                                        expected_batch_sha256=committed["source_batch_sha256"],
                                        parent=None, expected_parent_sha256=None)
        block_raw = wire(block)
        block_pin = hashlib.sha256(block_raw).hexdigest()
        expected_root = {
            "schema": "sia-source-history-root-v1", "status": "root-retained-not-activated",
            "epoch_id": batch["epoch"]["epoch_id"], "committed": committed,
            "legacy_epoch_sha256": batch["epoch_sha256"],
            "legacy_history_sha256": batch["epoch"]["expected_history_sha256"],
            "final_entry_block_sha256": block_pin, "non_claims": list(NON_CLAIMS),
        }
        if wire(expected_root) != root_file.raw:
            blocks._refuse("seed-root-source-binding")
        block_file = hold("", block_pin)
        if block_file.raw != block_raw:
            blocks._refuse("seed-final-entry-binding")

        def current():
            if wire(memo) != memo_raw or wire(admitted_status) != status_raw:
                blocks._refuse("seed-input-changed")
            observed = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
            if observed.get("status") != "available" or wire(observed.get("batch")) != batch_raw \
                    or wire(observed.get("committed")) != committed_raw:
                blocks._refuse("seed-source-changed")
            root_file.current()
            block_file.current()
            directory_hold.current()

        history = json.loads(wire(batch["epoch"]["history"]))
        history["entries"].append(json.loads(wire(block["entry"])))
        request = {"history": history, "expected_history_sha256": source._component_sha(owner, history),
                   "observed_at": batch["observed_at"],
                   **{key: batch["epoch"][key] for key in checkpoints._CONTEXT_KEYS
                      if key != "expected_history_sha256"}}
        request_raw = wire(request)
        checkpoint = checkpoints.bootstrap_incremental(
            owner, request=request, expected_request_sha256=hashlib.sha256(request_raw).hexdigest())
        if wire(checkpoint["intake"]) != wire(batch["intake_projection"]["intake"]) \
                or wire(checkpoint["source_non_claims"]) != wire(batch["intake_projection"]["source_non_claims"]):
            blocks._refuse("seed-intake-fidelity")
        checkpoint_raw = wire(checkpoint)
        checkpoint_pin = hashlib.sha256(checkpoint_raw).hexdigest()
        seed = {"schema": "sia-source-checkpoint-seed-v1", "status": "seed-retained-not-activated",
                "root_sha256": expected_root_sha256, "checkpoint_sha256": checkpoint_pin,
                "committed": json.loads(committed_raw), "non_claims": list(SEED_NON_CLAIMS)}
        seed_raw = wire(seed)
        seed_pin = hashlib.sha256(seed_raw).hexdigest()
        detached = json.loads(seed_raw)

        def publish(prefix, pin, raw):
            current()
            try:
                store.queue.fixed_atomic_publish(
                    os.path.join(directory, prefix + pin + ".json"), raw,
                    mode=0o600, exclusive=True, destination_dir_fd=directory_hold.fd,
                    staging_dir=os.path.join(directory, ".history-seed-staging"))
            except (OSError, ValueError) as exc:
                raise blocks.HistoryBlockRefusal("seed-publication") from exc
            held = hold(prefix, pin)
            if held.raw != raw:
                blocks._refuse("seed-retained-image")
            current()
            return held

        checkpoint_file = publish("checkpoint-", checkpoint_pin, checkpoint_raw)
        seed_file = publish("seed-", seed_pin, seed_raw)
        if wire(detached) != seed_raw or wire(seed) != seed_raw or wire(checkpoint) != checkpoint_raw \
                or wire(batch) != batch_raw or wire(block) != block_raw or wire(request) != request_raw:
            blocks._refuse("seed-final-image-changed")
        current()
        checkpoint_file.current()
        seed_file.current()
        return detached
