"""Durable, unactivated preparation of an actual root-bound compact pulse.

Every artifact retains its original single-document ceiling. The manifest is
published last, exclusively, after descriptor-held readback of every member.
No source fixed slot, cursor, active head or corpus page is advanced. Capture
may perform the existing collector notification-baseline fence write; package
retention does not otherwise modify the memo or acknowledge that fence.
"""

import contextlib
import hashlib
import json
import os

import siacontrollerliveinput as inputs
import siahistoryblock as blocks
import siahistoryblockstore as store
import sialiveloop as live
import siaqueue as queue
import siasourceack as ack
import siasourcebatch as source
import siasourcecheckpoint as checkpoint


NON_CLAIMS = (
    "This manifest records preparation and retained artifact bytes, not source adoption, cursor acknowledgment, corpus publication, live readiness or a cognitive win.",
    "The actual root capture and predecessor are checked under ordinary owner scopes; source truth, complete machine history and hostile same-user safety are not established.",
    "All referenced root, capture, checkpoint, history-block and live nonclaims remain controlling. Original archives remain required.",
    "Failures may leave exact unactivated artifacts. Manifest absence is not permission to delete them; recovery must independently admit all references and current authority.",
    "Publisher fsync and descriptor checks do not establish storage hardware reliability or protect against mutation after return.",
)
READ_NON_CLAIMS = NON_CLAIMS + (
    "This read verifies retained representations and deterministic replay only. It does not authenticate the manifest's preparation claim or acquire current source, journal or publication authority.",
    "The externally supplied manifest and root pins are caller premises. A recovered package must be independently joined to current authority before any adoption or effects.",
)
_ARTIFACTS = ("capture", "checkpoint", "candidate", "transition", "block")


def read_prepared(owner, *, directory, expected_manifest_sha256, expected_root_sha256):
    """Read and replay the closed package under held descriptors, without writes.

    Output is a closed compound view, not another single-artifact envelope:
    manifest, root, parent and each named artifact retain their original cap.
    No caller-selected extra slots or transitive history are acquired.
    """
    references = dict(owner)
    source._hex(expected_manifest_sha256, "checkpoint-transaction-manifest-pin")
    source._hex(expected_root_sha256, "checkpoint-transaction-root-pin")
    limit = min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES)
    with contextlib.ExitStack() as stack:
        directory_hold = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(directory_hold.close)
        held, raw_slots, values = [], {}, {}

        def current():
            if any(owner.get(name) is not value for name, value in references.items()):
                source.refuse("checkpoint-transaction-reader-owner-changed")
            for value in held:
                value.current()
            directory_hold.current()

        def read(slot, name, pin):
            source._hex(pin, "checkpoint-transaction-member-pin")
            current()
            actual = ack._HeldRaw(owner, source, os.path.join(directory, name), limit, allow_absent=False)
            stack.callback(actual.close)
            held.append(actual)
            blocks._pin(actual.raw, pin)
            value = json.loads(actual.raw)
            if checkpoint._wire(owner, value) != actual.raw:
                source.refuse("checkpoint-transaction-member-canonical-image")
            raw_slots[slot], values[slot] = actual.raw, value
            current()
            return value

        manifest = read("manifest", "transaction-" + expected_manifest_sha256 + ".json", expected_manifest_sha256)
        source._keys(manifest, {"schema", "status", "root_sha256", "predecessor", "source_batch_sha256", "artifacts", "non_claims"},
                     "checkpoint-transaction-manifest")
        source._keys(manifest["artifacts"], set(_ARTIFACTS), "checkpoint-transaction-artifacts")
        if manifest["schema"] != "sia-checkpoint-transaction-preparation-v1" \
                or manifest["status"] != "retained-not-activated" \
                or manifest["non_claims"] != list(NON_CLAIMS) \
                or manifest["root_sha256"] != expected_root_sha256:
            source.refuse("checkpoint-transaction-manifest-contract")
        root = read("root", "root-" + expected_root_sha256 + ".json", expected_root_sha256)
        import siahistoryroot
        source._keys(root, {"schema", "status", "epoch_id", "committed", "legacy_epoch_sha256", "legacy_history_sha256",
                           "final_entry_block_sha256", "non_claims"}, "checkpoint-transaction-root")
        if root["schema"] != "sia-source-history-root-v1" or root["status"] != "root-retained-not-activated" \
                or root["non_claims"] != list(siahistoryroot.NON_CLAIMS) \
                or checkpoint._wire(owner, root["committed"]) != checkpoint._wire(owner, manifest["predecessor"]):
            source.refuse("checkpoint-transaction-root-contract")
        for key in ("legacy_epoch_sha256", "legacy_history_sha256", "final_entry_block_sha256"):
            source._hex(root[key], "checkpoint-transaction-root-reference")
        parent = read("parent", store._name(root["final_entry_block_sha256"]), root["final_entry_block_sha256"])
        blocks._parent(parent)
        artifacts = {}
        for name in _ARTIFACTS:
            pin = manifest["artifacts"][name]
            source._hex(pin, "checkpoint-transaction-member-pin")
            filename = store._name(pin) if name == "block" else name + "-" + pin + ".json"
            artifacts[name] = read(name, filename, pin)
        batch = artifacts["capture"]
        checkpoint.validate_capture(owner, batch, manifest["source_batch_sha256"])
        if batch["schema"] != "sia-controller-source-checkpoint-capture-v3" \
                or batch["epoch"]["root_sha256"] != expected_root_sha256 \
                or batch["epoch"]["epoch_id"] != root["epoch_id"] \
                or checkpoint._wire(owner, batch["epoch"]["predecessor"]) != checkpoint._wire(owner, manifest["predecessor"]) \
                or checkpoint._wire(owner, batch["intake_projection"]["checkpoint"]) != raw_slots["checkpoint"]:
            source.refuse("checkpoint-transaction-capture-binding")
        expected_block = blocks.prepare_checkpoint_capture(
            owner, batch=batch, expected_batch_sha256=manifest["source_batch_sha256"],
            parent=parent, expected_parent_sha256=root["final_entry_block_sha256"])
        if checkpoint._wire(owner, expected_block) != raw_slots["block"]:
            source.refuse("checkpoint-transaction-block-replay")
        generation = batch["delivery_input"]["epoch_view"]["parent_generation"]
        request = inputs.prepare_inputs_checkpoint(
            owner, batch=batch, previous_generation=generation,
            expected_previous_generation_sha256=generation["generation_sha256"])
        candidate = {"prepare_inputs": request, "expected_prepare_inputs_sha256": live._sha(request)}
        if checkpoint._wire(owner, candidate) != raw_slots["candidate"]:
            source.refuse("checkpoint-transaction-candidate-replay")
        transition = live.prepare_pulse(**request)
        if checkpoint._wire(owner, transition) != raw_slots["transition"]:
            source.refuse("checkpoint-transaction-transition-replay")
        detached = {name: json.loads(raw) for name, raw in raw_slots.items()}
        result = {"schema": "sia-checkpoint-transaction-view-v1", "status": "verified-retained-not-authorized",
                  "manifest_sha256": expected_manifest_sha256, "manifest": detached["manifest"],
                  "root": detached["root"], "parent": detached["parent"],
                  "artifacts": {name: detached[name] for name in _ARTIFACTS}, "non_claims": list(READ_NON_CLAIMS)}
        if any(checkpoint._wire(owner, values[name]) != raw or checkpoint._wire(owner, detached[name]) != raw
               for name, raw in raw_slots.items()):
            source.refuse("checkpoint-transaction-reader-image-changed")
        current()
        return result


def prepare_root(owner, *, memo, admitted_status, directory, expected_root_sha256,
                 observed_at, journal_limits, expected_journal_limits_sha256,
                 expected_adoption_sha256):
    """Capture, execute the pure pulse, and retain its unactivated package."""
    owner_references = dict(owner)
    with owner["brainstem_owner"](), owner["corpus_owner"](), contextlib.ExitStack() as stack:
        batch = checkpoint.capture_root_delivery(
            owner, memo=memo, admitted_status=admitted_status, directory=directory,
            expected_root_sha256=expected_root_sha256, observed_at=observed_at,
            journal_limits=journal_limits, expected_journal_limits_sha256=expected_journal_limits_sha256,
            expected_adoption_sha256=expected_adoption_sha256)
        raw_batch = checkpoint._wire(owner, batch)
        memo_raw, status_raw = checkpoint._wire(owner, memo), checkpoint._wire(owner, admitted_status)
        limit = min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES)
        directory_hold = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(directory_hold.close)
        files = source._CaptureFiles(owner)
        stack.callback(files.close)
        held = []

        def observe(name, *, required=True):
            value = ack._HeldRaw(owner, source, os.path.join(directory, name), limit, allow_absent=not required)
            stack.callback(value.close)
            return value

        root_file = observe("root-" + expected_root_sha256 + ".json")
        blocks._pin(root_file.raw, expected_root_sha256)
        root = json.loads(root_file.raw)
        parent_pin = root["final_entry_block_sha256"]
        blocks._pin(checkpoint._wire(owner, root), expected_root_sha256)
        parent_file = observe(store._name(parent_pin))
        parent = store._decode(parent_file, parent_pin)
        held.extend((root_file, parent_file))
        predecessor = batch["epoch"]["predecessor"]
        if root["committed"] != predecessor or root["epoch_id"] != batch["epoch"]["epoch_id"]:
            source.refuse("checkpoint-transaction-root-binding")

        def current():
            if any(owner.get(name) is not value for name, value in owner_references.items()) \
                    or checkpoint._wire(owner, memo) != memo_raw \
                    or checkpoint._wire(owner, admitted_status) != status_raw \
                    or checkpoint._wire(owner, batch) != raw_batch:
                source.refuse("checkpoint-transaction-input-changed")
            source._durable_successor_authority(owner, files, memo, predecessor)
            marker = source._notification_marker(owner, memo)
            if marker is None:
                view = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
                expected_status = "available"
            else:
                view = ack.read_capturable_predecessor(
                    owner, memo=memo, admitted_status=admitted_status, committed=predecessor,
                    notification_baseline_attempt=marker,
                    expected_notification_baseline_attempt_sha256=source.native_sha(owner, marker))
                expected_status = "capturable-not-ready"
            if view.get("status") != expected_status or view.get("committed") != predecessor:
                source.refuse("checkpoint-transaction-predecessor-changed")
            for value in held:
                value.current()
            files.current()
            directory_hold.current()

        current()
        generation = batch["delivery_input"]["epoch_view"]["parent_generation"]
        request = inputs.prepare_inputs_checkpoint(
            owner, batch=batch, previous_generation=generation,
            expected_previous_generation_sha256=generation["generation_sha256"])
        transition = live.prepare_pulse(**request)
        candidate = {"prepare_inputs": request, "expected_prepare_inputs_sha256": live._sha(request)}
        block = blocks.prepare_checkpoint_capture(
            owner, batch=batch, expected_batch_sha256=batch["batch_sha256"],
            parent=parent, expected_parent_sha256=parent_pin)
        artifacts = {"capture": batch, "checkpoint": batch["intake_projection"]["checkpoint"],
                     "candidate": candidate, "transition": transition, "block": block}
        # Admit every complete member before any new publication.
        raws = {name: checkpoint._wire(owner, value) for name, value in artifacts.items()}
        pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in raws.items()}
        manifest = {"schema": "sia-checkpoint-transaction-preparation-v1", "status": "retained-not-activated",
                    "root_sha256": expected_root_sha256, "predecessor": predecessor,
                    "source_batch_sha256": batch["batch_sha256"], "artifacts": pins,
                    "non_claims": list(NON_CLAIMS)}
        manifest_raw = checkpoint._wire(owner, manifest)
        manifest_pin = hashlib.sha256(manifest_raw).hexdigest()

        def images_current():
            current()
            if any(checkpoint._wire(owner, artifacts[name]) != raw for name, raw in raws.items()) \
                    or checkpoint._wire(owner, manifest) != manifest_raw:
                source.refuse("checkpoint-transaction-artifact-changed")

        def publish(name, raw):
            prior = observe(name, required=False)
            if prior.raw is not None and prior.raw != raw:
                source.refuse("checkpoint-transaction-existing-image-differs")
            images_current()
            prior.current()
            queue.fixed_atomic_publish(os.path.join(directory, name), raw, mode=0o600,
                exclusive=True, destination_dir_fd=directory_hold.fd,
                staging_dir=os.path.join(directory, ".checkpoint-transaction-staging"))
            actual = observe(name)
            if actual.raw != raw or not os.path.samestat(
                    os.fstat(actual.directories.fd), os.fstat(prior.directories.fd)):
                source.refuse("checkpoint-transaction-published-image-differs")
            held.append(actual)
            images_current()

        images_current()
        # Use the existing block publisher so future links find the same chain.
        store.retain(directory=directory, block=block, expected_block_sha256=pins["block"])
        actual_block = observe(store._name(pins["block"]))
        if actual_block.raw != raws["block"]:
            source.refuse("checkpoint-transaction-block-differs")
        held.append(actual_block)
        for name in ("capture", "checkpoint", "candidate", "transition"):
            publish(name + "-" + pins[name] + ".json", raws[name])
        publish("transaction-" + manifest_pin + ".json", manifest_raw)
        result = {"manifest": json.loads(manifest_raw), "manifest_sha256": manifest_pin}
        if checkpoint._wire(owner, result["manifest"]) != manifest_raw:
            source.refuse("checkpoint-transaction-result-changed")
        images_current()
        files.named_current()
        return result
