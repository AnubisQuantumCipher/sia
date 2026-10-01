"""Complete an explicitly pinned, already-adopted compact transaction.

This is not a package selector, collector or service activator. Callers must
retain the manifest/root pins across retries. Each phase reads actual durable
authority; no fabricated memo is used to make a predecessor reader accept it.
"""

import siacheckpointadoption as adoption
import siacheckpointeffects as effects
import siacheckpointlive as live
import siacontrollersourcerunner as runner
import siasourceack as ack


def complete_adopted(owner, *, directory, expected_manifest_sha256,
                     expected_root_sha256, started_at):
    """Drive adopted source through content, live publication and durable ACK.

    Returns the original completed reader's evidence view, not a cognitive
    verdict. Exceptions preserve the durable phase for a later explicit retry.
    Status is read again after publication, never substituted from a payload.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if type(started_at) is not str:
        adoption.source.refuse("checkpoint-runner-started-at")
    package_args = dict(directory=directory,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_root_sha256=expected_root_sha256)
    with owner["brainstem_owner"](), owner["corpus_owner"](), \
            adoption.transaction._hold_prepared(owner, **package_args) as (package, current):
        expected_batch = package["manifest"]["source_batch_sha256"]

        def actual():
            current()
            memo = owner["load_memo"]()
            owner["_require_status_memo_fields"](memo)
            return memo, runner._admit_status(owner, memo)

        def completed(memo, status):
            view = ack.read_checkpoint_completed(owner, memo=memo, admitted_status=status)
            if view["batch"]["batch_sha256"] != expected_batch:
                adoption.source.refuse("checkpoint-runner-completed-batch-differs")
            if status["history"][-1][0] != started_at:
                adoption.source.refuse("checkpoint-runner-completed-start-differs")
            current()
            return view

        memo, status = actual()
        if "controller_source_pending" not in memo:
            return completed(memo, status)
        pending = memo["controller_source_pending"]
        if type(pending) is not dict or pending.get("batch_sha256") != expected_batch:
            adoption.source.refuse("checkpoint-runner-pending-batch-differs")
        args = dict(**package_args, memo=memo, admitted_status=status)
        if "controller_source_effects_committed" not in memo:
            if "controller_source_effects_pending" not in memo:
                seq = runner._sequence(owner, memo)
                adoption.stage_live_binding(owner, **args, seq=seq)
                adoption.stage_status_effects(owner, **args, seq=seq, started_at=started_at)
                effects.stage(owner, **args)
            if memo["controller_source_effects_pending"]["status"]["history"][-1][0] != started_at:
                adoption.source.refuse("checkpoint-runner-pending-start-differs")
            current()
            live.finalize(owner, **args)
            memo, status = actual()
        if status["history"][-1][0] != started_at:
            adoption.source.refuse("checkpoint-runner-finalized-start-differs")
        current()
        ack.acknowledge_checkpoint(owner, memo=memo, admitted_status=status)
        memo, status = actual()
        return completed(memo, status)
