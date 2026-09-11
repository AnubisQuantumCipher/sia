"""Exclusive retention of history blocks, without a mutable head or ACK.

The caller selects an existing private directory. No resident configuration,
memo, corpus page or root authority is changed here. Source/archive admission
and owner-bound adoption remain separate operations. The existing fixed-slot
publisher supplies no-replace publication and its crash-replay fsync rules.
"""

import contextlib
import json
import os

import siahistoryblock as blocks
import siaqueue as queue
import siasourceack as archive
import siasourcebatch as source


NON_CLAIMS = (
    "Retention observes matching private file bytes and completed publisher durability steps; it is not source acknowledgment, root adoption or live readiness.",
    "An immediate parent is checked during retention, not the transitive chain, durable source archive, complete history or source semantics.",
    "A failed call may leave exact unadopted bytes for idempotent retry; no mutable head or source cursor is advanced by this operation.",
    "Descriptor/name checks do not protect against hostile same-user mutation after return or establish storage hardware durability beyond the operating-system fsync contract.",
    "All block and nested source nonclaims remain controlling; this is not cognitive authorization, a held-out win or JACKAL assurance.",
)


def _owner():
    return {"os": os, "MAX_CONFIG_PATH_CHARS": 4096}


def _name(pin):
    if not blocks._digest(pin):
        blocks._refuse("storage-pin")
    return pin + ".json"


def _observe(stack, owner, directory, pin, *, required):
    held = archive._HeldRaw(owner, source, os.path.join(directory, _name(pin)),
                            blocks.MAX_DOCUMENT_BYTES, allow_absent=not required)
    stack.callback(held.close)
    return held


def _decode(held, pin):
    if held.raw is None:
        blocks._refuse("stored-block-absent")
    blocks._pin(held.raw, pin)
    try:
        value = json.loads(held.raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise blocks.HistoryBlockRefusal("stored-block-json") from exc
    if blocks._wire(value) != held.raw:
        blocks._refuse("stored-block-canonical-image")
    blocks._parent(value)
    held.current()
    return value


def read(*, directory, expected_block_sha256):
    """Read one externally pinned block, not a complete-chain proof."""
    _name(expected_block_sha256)
    owner = _owner()
    with contextlib.ExitStack() as stack:
        root = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(root.close)
        held = _observe(stack, owner, directory, expected_block_sha256, required=True)
        value = _decode(held, expected_block_sha256)
        root.current()
        held.current()
        return value


def retain(*, directory, block, expected_block_sha256):
    """Retain exact bytes exclusively; replay repairs publication durability.

    Neither this function nor its receipt may be used as an adoption marker.
    Existing differing bytes, unsafe files, missing parents and input drift
    refuse. The selected directory must already exist with private mode.
    """
    raw = blocks._wire(block)
    blocks._pin(raw, expected_block_sha256)
    blocks._parent(block)
    owner = _owner()
    with contextlib.ExitStack() as stack:
        root = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(root.close)
        parent_held = None
        parent = None
        if block["parent_sha256"] is not None:
            parent_held = _observe(stack, owner, directory, block["parent_sha256"], required=True)
            parent = _decode(parent_held, block["parent_sha256"])
        rebuilt = blocks.prepare(
            epoch_id=block["epoch_id"], entry=block["entry"],
            expected_entry_sha256=block["entry_sha256"],
            source_batch_sha256=block["source_batch_sha256"],
            observed_at=block["observed_at"], parent=parent,
            expected_parent_sha256=block["parent_sha256"])
        if blocks._wire(rebuilt) != raw or blocks._wire(block) != raw:
            blocks._refuse("stored-link-binding")
        prior = _observe(stack, owner, directory, expected_block_sha256, required=False)
        if prior.raw is not None and prior.raw != raw:
            blocks._refuse("existing-block-differs")
        prior.current()
        root.current()
        if parent_held is not None:
            parent_held.current()
        try:
            queue.fixed_atomic_publish(
                os.path.join(directory, _name(expected_block_sha256)), raw,
                mode=0o600, exclusive=True, destination_dir_fd=root.fd,
                staging_dir=os.path.join(directory, ".history-block-staging"))
        except (OSError, ValueError) as exc:
            raise blocks.HistoryBlockRefusal("block-publication") from exc
        published = _observe(stack, owner, directory, expected_block_sha256, required=True)
        if published.raw != raw:
            blocks._refuse("retained-block-differs")
        receipt = {"schema": "sia-history-block-retention-v1",
                   "status": "retained-not-adopted", "block_sha256": expected_block_sha256,
                   "parent_sha256": block["parent_sha256"], "non_claims": list(NON_CLAIMS)}
        if blocks._wire(block) != raw:
            blocks._refuse("retention-input-changed")
        if parent_held is not None:
            parent_held.current()
        published.current()
        root.current()
        return receipt
