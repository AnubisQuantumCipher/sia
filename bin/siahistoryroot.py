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


SUCCESSOR_NON_CLAIMS = NON_CLAIMS + (
    "This successor extends the retained chain by exactly one entry from an independently acknowledged compact parent. It neither replaces the bootstrap root nor re-derives the legacy archive it references.",
    "Only the bootstrap root and the current head are held. Earlier links are referenced by pin, never traversed or embedded, and their own retention and nonclaims remain required.",
    "Successor retention is not source acknowledgment, cursor advancement, capture, publication, readiness or cognitive authorization. File presence alone is never authority.",
)

_ROOT_KEYS = {"schema", "status", "epoch_id", "committed", "legacy_epoch_sha256",
              "legacy_history_sha256", "final_entry_block_sha256", "non_claims"}
_SUCCESSOR_KEYS = {"schema", "status", "epoch_id", "root_sha256",
                   "legacy_epoch_sha256", "legacy_history_sha256", "parent_sha256",
                   "generation", "committed", "checkpoint_sha256",
                   "final_entry_block_sha256", "non_claims"}


def _successor_generation(owner, wire, head, head_raw, *, root, root_raw,
                          expected_root_sha256):
    """Carry the bootstrap pins forward from either chain-head schema."""
    if head_raw == root_raw:
        return 1
    source._keys(head, _SUCCESSOR_KEYS, "successor-head-shape")
    generation = head["generation"]
    if head["schema"] != "sia-source-history-successor-v1" \
            or head["status"] != "successor-retained-not-activated" \
            or head["non_claims"] != list(SUCCESSOR_NON_CLAIMS) \
            or head["root_sha256"] != expected_root_sha256 \
            or head["epoch_id"] != root["epoch_id"] \
            or head["legacy_epoch_sha256"] != root["legacy_epoch_sha256"] \
            or head["legacy_history_sha256"] != root["legacy_history_sha256"] \
            or type(generation) is not int or type(generation) is bool \
            or generation < 1 or generation >= owner["MAX_JSON_SAFE_INTEGER"]:
        blocks._refuse("successor-head-contract")
    for key in ("parent_sha256", "checkpoint_sha256", "final_entry_block_sha256"):
        if not blocks._digest(head[key]):
            blocks._refuse("successor-head-reference")
    return generation + 1


def prepare_successor(owner, *, memo, admitted_status, directory,
                      expected_root_sha256, expected_head_sha256):
    """Retain one single-link successor to the acknowledged compact parent.

    The bootstrap root and its legacy archive pins are read out of the
    retained root document and carried forward by value; they are never
    rebuilt, replaced or re-audited, and no epoch is re-bootstrapped. Exactly
    two chain documents are held — the bootstrap root and the current head —
    so a pulse never traverses or embeds whole ancestry. Every artifact keeps
    its original single-document cap.

    The parent is the independently acknowledged compact predecessor read
    through the retained-parent boundary, not the caller's memo copy: a memo
    naming a predecessor the archives do not hold is refused. That boundary's
    own precondition stands — the parent graph and live artifacts must already
    be retained by their durable protocol, and this call refuses rather than
    reconstructing them. Nothing here
    captures, adopts, publishes, acknowledges or activates anything, and a
    retained link is reread on retry rather than republished.
    """
    import siacheckpointparent as parents
    import siaeventcheckpoint as checkpoints

    if not blocks._digest(expected_root_sha256) or not blocks._digest(expected_head_sha256):
        blocks._refuse("successor-chain-pin")
    wire = lambda value: checkpoints._wire(owner, value)
    memo_raw, status_raw = wire(memo), wire(admitted_status)
    limit = min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES)
    committed = memo.get("controller_source_committed")
    if type(committed) is not dict:
        blocks._refuse("successor-source-authority")
    committed_raw = wire(committed)
    with owner["brainstem_owner"](), owner["corpus_owner"](), contextlib.ExitStack() as stack:
        # The retained-parent boundary admits historical bytes from a supplied
        # identity; it never reads the durable memo or the current ACK. So the
        # caller's memo is joined to actual durable state first: a stale or
        # forged copy, or a pre-acknowledgment archive, is refused here rather
        # than carried forward as current acknowledged authority.
        if wire(owner["load_memo"]()) != memo_raw:
            blocks._refuse("successor-durable-memo-differs")
        completed = ack.read_checkpoint_completed(
            owner, memo=memo, admitted_status=admitted_status)
        if type(completed) is not dict or completed.get("status") != "available" \
                or wire(completed.get("committed")) != committed_raw:
            blocks._refuse("successor-source-authority")
        acknowledged_raw = wire(completed["batch"])
        directory_hold = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(directory_hold.close)

        def hold(name, pin, *, required=True):
            held = ack._HeldRaw(owner, source, os.path.join(directory, name), limit,
                                allow_absent=not required)
            stack.callback(held.close)
            if held.raw is not None:
                blocks._pin(held.raw, pin)
            return held

        root_file = hold("root-" + expected_root_sha256 + ".json", expected_root_sha256)
        root = json.loads(root_file.raw)
        source._keys(root, _ROOT_KEYS, "successor-root-shape")
        if root["schema"] != "sia-source-history-root-v1" \
                or root["status"] != "root-retained-not-activated" \
                or root["non_claims"] != list(NON_CLAIMS) \
                or wire(root) != root_file.raw:
            blocks._refuse("successor-root-contract")
        if expected_head_sha256 == expected_root_sha256:
            head_file, head = root_file, root
        else:
            head_file = hold("successor-" + expected_head_sha256 + ".json", expected_head_sha256)
            head = json.loads(head_file.raw)
            if wire(head) != head_file.raw:
                blocks._refuse("successor-head-image")
        generation = _successor_generation(owner, wire, head, head_file.raw,
            root=root, root_raw=root_file.raw, expected_root_sha256=expected_root_sha256)
        parent_pin = head["final_entry_block_sha256"]
        # Hold the parent block open for the whole call; a detached read would
        # not notice the link being replaced underneath the new entry.
        parent_file = store._observe(stack, owner, directory, parent_pin, required=True)
        parent_block = store.read(directory=directory, expected_block_sha256=parent_pin)
        parent_raw = wire(parent_block)
        if parent_file.raw != parent_raw:
            blocks._refuse("successor-parent-block-image")

        def inputs_current():
            if wire(memo) != memo_raw or wire(admitted_status) != status_raw \
                    or wire(committed) != committed_raw \
                    or wire(parent_block) != parent_raw:
                blocks._refuse("successor-input-changed")
            root_file.current()
            head_file.current()
            parent_file.current()
            directory_hold.current()

        inputs_current()
        # The retained-parent boundary, not the memo, admits the predecessor.
        with parents.hold_checkpoint_live(owner, directory=directory,
                                          committed=committed) as historical:
            batch = historical["batch"]
            batch_raw = wire(batch)
            # The archived parent must be the same acknowledged batch the
            # current completed reader returned, and must itself be bound to
            # this exact bootstrap root and epoch. Matching only the final
            # entry block would let a rehashed unrelated root be carried
            # forward under a chain that never produced it.
            epoch = batch["epoch"]
            if batch_raw != acknowledged_raw \
                    or epoch["root_sha256"] != expected_root_sha256 \
                    or epoch["epoch_id"] != root["epoch_id"] \
                    or batch["epoch_sha256"] == root["legacy_epoch_sha256"]:
                blocks._refuse("successor-parent-root-binding")
            # The head must name this capture's own predecessor as a whole
            # triple. Block linkage alone binds only the source batch, so a
            # rehashed head keeping the block while altering its effects or
            # live identity would otherwise propagate inconsistent ancestry.
            if wire(head["committed"]) != wire(epoch["predecessor"]):
                blocks._refuse("successor-head-predecessor-binding")
            if head_file.raw != root_file.raw \
                    and head["checkpoint_sha256"] != epoch["checkpoint_sha256"]:
                blocks._refuse("successor-head-checkpoint-binding")
            projection = batch["intake_projection"]
            block = blocks.prepare_checkpoint_capture(owner, batch=batch,
                expected_batch_sha256=committed["source_batch_sha256"],
                parent=parent_block, expected_parent_sha256=parent_pin)
            block_raw = wire(block)
            block_pin = hashlib.sha256(block_raw).hexdigest()
            successor = {
                "schema": "sia-source-history-successor-v1",
                "status": "successor-retained-not-activated",
                "epoch_id": root["epoch_id"],
                "root_sha256": expected_root_sha256,
                "legacy_epoch_sha256": root["legacy_epoch_sha256"],
                "legacy_history_sha256": root["legacy_history_sha256"],
                "parent_sha256": expected_head_sha256,
                "generation": generation,
                "committed": json.loads(committed_raw),
                "checkpoint_sha256": projection["checkpoint_sha256"],
                "final_entry_block_sha256": block_pin,
                "non_claims": list(SUCCESSOR_NON_CLAIMS),
            }
            successor_raw = wire(successor)
            successor_pin = hashlib.sha256(successor_raw).hexdigest()
            detached = json.loads(successor_raw)
            inputs_current()
            store.retain(directory=directory, block=block, expected_block_sha256=block_pin)
            held_block = store._observe(stack, owner, directory, block_pin, required=True)
            if held_block.raw != block_raw:
                blocks._refuse("successor-block-changed")
            inputs_current()
            name = "successor-" + successor_pin + ".json"
            retained = hold(name, successor_pin, required=False)
            if retained.raw is None:
                try:
                    store.queue.fixed_atomic_publish(
                        os.path.join(directory, name), successor_raw,
                        mode=0o600, exclusive=True, destination_dir_fd=directory_hold.fd,
                        staging_dir=os.path.join(directory, ".history-successor-staging"))
                except (OSError, ValueError) as exc:
                    raise blocks.HistoryBlockRefusal("successor-publication") from exc
                retained = hold(name, successor_pin)
            if retained.raw != successor_raw:
                blocks._refuse("successor-retained-image")
            inputs_current()
            if wire(detached) != successor_raw or wire(successor) != successor_raw \
                    or wire(block) != block_raw or wire(batch) != batch_raw:
                blocks._refuse("successor-output-changed")
            result = {"successor": detached, "successor_sha256": successor_pin,
                      "parent_sha256": expected_head_sha256,
                      "batch": json.loads(batch_raw)}
            held_block.current()
            retained.current()
            inputs_current()
            return result
