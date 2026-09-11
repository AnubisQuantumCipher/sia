"""Retain an actual predecessor graph before replacing the current graph."""

import contextlib
import os

import siasourceack as ack
import siasourcebatch as source
import siasourceeffects as effects
import sialiveloop as live


@contextlib.contextmanager
def hold_graph(owner, *, directory, committed):
    """Select exact retained bytes, or retain the original current-file policy.

    Absence never permits a historical graph mismatch: the original receipt
    validator then requires the current graph. A present wrong file refuses.
    The acknowledged receipt supplies the expected hash, not the saved file.
    """
    with contextlib.ExitStack() as stack:
        parent = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(parent.close)
        receipt_file = ack._EffectsArchiveSlot(owner, source, committed["source_effects_receipt_sha256"], required=True)
        stack.callback(receipt_file.close)
        receipt = owner["_strict_json_loads"](receipt_file.raw.decode("utf-8", errors="strict"))
        keys = effects.RECEIPT_KEYS | effects.CONTENT_FIELDS if receipt.get("schema") == "sia-controller-source-effects-committed-v2" else effects.RECEIPT_KEYS
        effects._self_hash(source, live, receipt, "receipt_sha256", keys, "checkpoint-parent-effects")
        if receipt["receipt_sha256"] != committed["source_effects_receipt_sha256"]:
            source.refuse("checkpoint-parent-effects-pin")
        expected = receipt["graph_generation"]
        pin = expected["raw_sha256"]
        source._hex(pin, "checkpoint-parent-graph-pin")
        path = os.path.join(directory, "parent-graph-" + pin + ".json")
        held = ack._HeldRaw(owner, source, path, owner["MAX_STATE_JSON_BYTES"])
        stack.callback(held.close)
        if held.raw is not None:
            graph = owner["_strict_json_loads"](held.raw.decode("utf-8", errors="strict"))
            generation, _ = effects._graph_generation_value(owner, source, live, held.raw, graph)
            if generation != expected:
                source.refuse("checkpoint-parent-graph-generation")
        yield held, expected
        held.current()
        receipt_file.current()
        parent.current()


def retain_graph(owner, *, directory, committed):
    """Copy only the current receipt-matching parent graph, before export.

    Caller holds the ordinary owner leases and has admitted its full parent.
    This never creates readiness or replaces a differing retained artifact.
    """
    with hold_graph(owner, directory=directory, committed=committed) as (saved, expected):
        if saved.raw is not None:
            return False
        destination = saved.path
        parent_identity = os.fstat(saved.directories.fd)
        with contextlib.closing(ack._HeldRaw(owner, source, owner["GRAPH_PATH"], owner["MAX_STATE_JSON_BYTES"], allow_absent=False)) as current:
            graph = owner["_strict_json_loads"](current.raw.decode("utf-8", errors="strict"))
            generation, _ = effects._graph_generation_value(owner, source, live, current.raw, graph)
            if generation != expected:
                source.refuse("checkpoint-parent-current-graph-differs")
            raw = bytes(current.raw)
            current.current()
        # The absence descriptor must retire before the exact file is created.
    owner["siaqueue"].fixed_atomic_publish(destination, raw, mode=0o600, exclusive=True,
        staging_dir=owner["siaqueue"].staging_dir_for(destination,
            authority_roots=(owner["CORPUS"], owner["STATE"], owner["SHARE"])))
    with hold_graph(owner, directory=directory, committed=committed) as (saved, _expected):
        if saved.raw != raw or not os.path.samestat(parent_identity, os.fstat(saved.directories.fd)):
            source.refuse("checkpoint-parent-graph-retention-differs")
    return True
