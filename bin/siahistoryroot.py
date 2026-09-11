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
