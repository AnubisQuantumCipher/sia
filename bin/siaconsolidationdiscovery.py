"""Experimental read-only traversal of an admitted snapshot.

Returned candidates are not live-source completeness or deletion authority.
Callers must persist each result together with its cursor before consuming it.
No production dispatch, legacy-state migration or pin retirement is enabled here.
"""
import re

import siaconsolidationadmission as admission
import siaconsolidationsnapshot as snapshot

SCHEMA = "sia-consolidation-discovery-v1"
MAX_DEPTH = 3  # corpus root, events root, one organ


def _frame(relative, tree, offset=0):
    return {"relative": relative, "tree": tree, "offset": offset}


def _relative(value):
    if not isinstance(value, str) or value not in {"", "events"} \
            and re.fullmatch(r"events/[a-z0-9][a-z0-9._-]{0,199}", value) is None:
        raise ValueError("snapshot discovery path is invalid")
    return value


def canonical(value, record):
    if not isinstance(value, dict) or set(value) != {
            "schema", "admission", "frames", "complete"} \
            or value["schema"] != SCHEMA \
            or value["admission"] != record \
            or not isinstance(value["complete"], bool) \
            or not isinstance(value["frames"], list) \
            or len(value["frames"]) > MAX_DEPTH \
            or value["complete"] != (not value["frames"]):
        raise ValueError("snapshot discovery state is invalid")
    frames = []
    for raw in value["frames"]:
        if not isinstance(raw, dict) or set(raw) != {"relative", "tree", "offset"}:
            raise ValueError("snapshot discovery frame is invalid")
        relative = _relative(raw["relative"])
        snapshot.object_id(raw["tree"])
        offset = raw["offset"]
        if isinstance(offset, bool) or not isinstance(offset, int) \
                or not 0 <= offset <= snapshot.MAX_TREE_ENTRIES:
            raise ValueError("snapshot discovery offset is invalid")
        expected_parent = "" if relative == "events" else "events"
        if not frames and relative != "" \
                or frames and (not relative
                               or frames[-1]["relative"] != expected_parent):
            raise ValueError("snapshot discovery ancestry is invalid")
        frames.append(_frame(relative, raw["tree"], offset))
    return dict(value, admission=dict(record), frames=frames)


def _validate_anchors(run, corpus, frames, root):
    if frames and frames[0]["tree"] != root:
        raise ValueError("snapshot discovery root differs from admission")
    for parent, child in zip(frames, frames[1:]):
        if parent["offset"] == 0:
            raise ValueError("snapshot discovery child lacks a visited parent")
        page = snapshot.tree_page(
            run, corpus, parent["tree"], parent["offset"] - 1, 1)
        expected = child["relative"].rsplit("/", 1)[-1]
        if len(page["entries"]) != 1 or page["entries"][0] != {
                "name": expected, "mode": "040000", "kind": "tree",
                "object": child["tree"]}:
            raise ValueError("snapshot discovery child differs from parent")


def _child(relative, entry):
    if relative == "" and entry["name"] == "events":
        if entry["kind"] != "tree":
            raise ValueError("snapshot events root is not a tree")
        return "events"
    if relative == "events" and entry["kind"] == "tree":
        path = relative + "/" + entry["name"]
        _relative(path)
        return path
    return None


def _candidate(owner, relative, entry, cutoff):
    if not relative.startswith("events/") or entry["kind"] != "blob":
        return None
    path = relative + "/" + entry["name"]
    try:
        organ, date, part = owner._event_source_parts(path)
    except ValueError:
        return None
    if date >= cutoff:
        return None
    return {"relative": path, "blob": entry["object"],
            "organ": organ, "date": date, "part": part}


def _advance(owner, record, state, budget):
    run, corpus = owner._run_bounded_text_process, owner.CORPUS
    frames, found = state["frames"], []
    remaining = budget
    # One budget unit per entry or exhausted frame. Leaf entries are batched;
    # ancestors use one entry so their offset remains bound to the active child.
    for _unit in range(budget):
        if not frames or not remaining:
            break
        frame = frames[-1]
        leaf = frame["relative"].startswith("events/")
        limit = remaining if leaf else 1
        page = snapshot.tree_page(run, corpus, frame["tree"], frame["offset"], limit)
        remaining -= max(1, len(page["entries"]))
        if not page["entries"]:
            frames.pop()
            continue
        frame["offset"] = page["next"]
        for entry in page["entries"]:
            child = _child(frame["relative"], entry)
            if child is not None:
                frames.append(_frame(child, entry["object"]))
                continue
            candidate = _candidate(owner, frame["relative"], entry,
                                   record["cutoff"])
            if candidate is not None:
                found.append(candidate)
    state["complete"] = not frames
    return {"cursor": canonical(state, record), "candidates": found}


def discover(owner, expected, cursor=None, *, budget=32):
    """Read one bounded page under the real lease and exact admitted pin.

    The persisted journal must already be admitted; this never creates a pin.
    Shape/ancestry checks do not authenticate a supplied cursor's history.
    """
    record = admission.canonical(expected)
    if record["phase"] != "admitted":
        raise ValueError("snapshot discovery requires admitted state")
    if isinstance(budget, bool) or not isinstance(budget, int) \
            or not 1 <= budget <= snapshot.MAX_PAGE_ENTRIES:
        raise ValueError("snapshot discovery budget is invalid")
    with owner.corpus_owner():
        retained = owner.read_state_json(
            admission._path(owner), None, "snapshot admission", expected_type=dict)
        if admission.canonical(retained) != record:
            raise ValueError("snapshot discovery admission differs")
        run, corpus = owner._run_bounded_text_process, owner.CORPUS
        snapshot.check_pin(run, corpus, record["generation"], record["commit"])
        root = snapshot.commit_tree(run, corpus, record["commit"])
        if cursor is None:
            cursor = {"schema": SCHEMA, "admission": dict(record),
                      "frames": [_frame("", root)], "complete": False}
        state = canonical(cursor, record)
        _validate_anchors(run, corpus, state["frames"], root)
        return _advance(owner, record, state, budget)
