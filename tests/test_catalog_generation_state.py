#!/usr/bin/env python3
"""Generation-scoped bounded catalog ingestion regressions."""

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
SOURCE_STATE_SCHEMA = "sia-source-entity-state-v1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentCatalogGeneration(unittest.TestCase):
    """Partial generations never become the authoritative agent catalog."""

    def setUp(self):
        self.sialib = _load(
            "sialib_agent_catalog_generation",
            os.path.join(BIN, "sialib.py"))
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.usage = os.path.join(
            self.home.name, ".local/state/omarchy/agents/usage")
        os.makedirs(self.usage)
        old_home = self.sialib.HOME
        self.sialib.HOME = self.home.name
        self.addCleanup(setattr, self.sialib, "HOME", old_home)
        page_bound = mock.patch.object(self.sialib, "MAX_CONFIG_TAGS", 1)
        page_bound.start()
        self.addCleanup(page_bound.stop)

    @staticmethod
    def _wrapped(rows):
        return [SOURCE_STATE_SCHEMA, copy.deepcopy(rows)]

    def _state(self, cursors):
        wrapped = cursors["agents.state"]
        self.assertEqual(wrapped[0], SOURCE_STATE_SCHEMA)
        return wrapped[1]

    def _write(self, name, *, tokens=0, limits=None):
        record = {"id": name, "todayTotalTokens": tokens}
        if limits is not None:
            record["limits"] = limits
        with open(os.path.join(self.usage, name + ".json"), "w") as stream:
            json.dump(record, stream)

    def _finish(self, cursors):
        events = []
        for _attempt in range(self.sialib.MAX_SOURCE_SCAN_ENTRIES):
            events.extend(self.sialib.sense_agents(cursors))
            if "source.agents.page" not in cursors:
                return events
        self.fail("agent catalog scan did not reach EOF")

    def test_partial_pages_preserve_authority_then_clean_eof_prunes(self):
        self._write("alpha", tokens=10)
        self._write("bravo", tokens=20)
        prior = {
            "alpha": {"tokens": 5, "limits": {}, "generation": 0},
            "vanished": {"tokens": 7, "limits": {}, "generation": 0},
        }
        cursors = {"agents.state": self._wrapped(prior)}

        self.sialib.sense_agents(cursors)

        self.assertIn("source.agents.page", cursors)
        self.assertEqual(self._state(cursors), prior)

        self._finish(cursors)
        self.assertEqual(set(self._state(cursors)), {"alpha", "bravo"})

    def test_tainted_generation_merges_valid_rows_without_pruning(self):
        self._write("alpha", tokens=10)
        with open(os.path.join(self.usage, "broken.json"), "w") as stream:
            stream.write("not-json")
        prior = {
            "alpha": {"tokens": 5, "limits": {}, "generation": 0},
            "unseen": {"tokens": 7, "limits": {}, "generation": 0},
        }
        cursors = {"agents.state": self._wrapped(prior)}

        events = self._finish(cursors)

        self.assertEqual(self._state(cursors)["alpha"]["tokens"], 10)
        self.assertIn("unseen", self._state(cursors))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))

    def test_directory_reset_discards_prior_generation_candidate_rows(self):
        self._write("alpha")
        self._write("bravo")
        cursors = {"agents.state": self._wrapped({})}

        self.sialib.sense_agents(cursors)

        self.assertEqual(self._state(cursors), {})
        scan = cursors["agents.scan"]
        captured = next(iter(scan["rows"]))
        os.unlink(os.path.join(self.usage, captured + ".json"))
        self._write("charlie")

        self._finish(cursors)
        self.assertNotIn(captured, self._state(cursors))
        self.assertEqual(set(self._state(cursors)),
                         {"alpha", "bravo", "charlie"} - {captured})

    def test_reset_replay_uses_the_same_transition_occurrence(self):
        self._write("alpha", tokens=600001)
        self._write("bravo", tokens=600002)
        prior = {
            "alpha": {"tokens": 0, "limits": {}, "generation": 0},
            "bravo": {"tokens": 0, "limits": {}, "generation": 0},
        }
        cursors = {"agents.state": self._wrapped(prior)}
        retry_cursors = copy.deepcopy(cursors)

        first = self.sialib.sense_agents(cursors)
        self.assertFalse(any(event.kind in {"usage", "limit"}
                             for event in first))
        self._write("charlie")
        replay = self._finish(cursors)
        retry = self._finish(retry_cursors)

        replayed = {event.occurrence for event in replay
                    if event.kind == "usage"}
        retried = {event.occurrence for event in retry
                   if event.kind == "usage"}
        self.assertEqual(replayed, retried)
        self.assertEqual(len(replayed),
                         len([event for event in replay
                              if event.kind == "usage"]))

    def test_unchanged_clean_catalog_does_not_repeat_transitions(self):
        self._write("alpha", tokens=600001)
        prior = {
            "alpha": {"tokens": 0, "limits": {}, "generation": 0},
        }
        cursors = {"agents.state": self._wrapped(prior)}

        first = self._finish(cursors)
        second = self._finish(cursors)

        self.assertTrue(any(event.kind == "usage" for event in first))
        self.assertFalse(any(event.kind in {"usage", "limit"}
                             for event in second))

    def test_escaped_agent_identity_survives_candidate_reload(self):
        self._write("first")
        self._write("second")
        with open(os.path.join(self.usage, "first.json"), "w") as stream:
            json.dump({"id": "Agent+One", "todayTotalTokens": 1}, stream)
        cursors = {"agents.state": self._wrapped({})}

        self.sialib.sense_agents(cursors)
        self._finish(cursors)

        token = self.sialib._source_entity_token("Agent+One", "agent")
        self.assertIn(token, self._state(cursors))

    def test_duplicate_agent_ids_taint_instead_of_last_writer_wins(self):
        self._write("first", tokens=600001)
        self._write("second", tokens=600002)
        for name in ("first", "second"):
            path = os.path.join(self.usage, name + ".json")
            with open(path) as stream:
                record = json.load(stream)
            record["id"] = "shared"
            with open(path, "w") as stream:
                json.dump(record, stream)
        prior = {
            "shared": {"tokens": 0, "limits": {}, "generation": 0},
            "unseen": {"tokens": 7, "limits": {}, "generation": 0},
        }
        cursors = {"agents.state": self._wrapped(prior)}

        events = self._finish(cursors)

        self.assertEqual(self._state(cursors)["shared"]["tokens"], 0)
        self.assertIn("unseen", self._state(cursors))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertFalse(any(event.kind in {"usage", "limit"}
                             for event in events))

    def test_duplicate_agent_id_cannot_create_new_authoritative_row(self):
        self._write("first", tokens=10)
        self._write("second", tokens=20)
        for name in ("first", "second"):
            path = os.path.join(self.usage, name + ".json")
            with open(path) as stream:
                record = json.load(stream)
            record["id"] = "shared"
            with open(path, "w") as stream:
                json.dump(record, stream)
        cursors = {"agents.state": self._wrapped({})}

        self._finish(cursors)

        self.assertNotIn("shared", self._state(cursors))

    def test_truncated_limits_merge_without_dropping_prior_labels(self):
        prior = {
            "alpha": {
                "tokens": 5, "generation": 0,
                "limits": {"retained": 2},
            },
        }
        self._write("alpha", tokens=10, limits=[
            {"label": "first", "percent": 0.5},
            {"label": "overflow", "percent": 0.6},
        ])
        cursors = {"agents.state": self._wrapped(prior)}

        events = self._finish(cursors)

        current = self._state(cursors)["alpha"]
        self.assertEqual(current["limits"]["first"], 50)
        self.assertEqual(current["limits"]["retained"], 2)
        self.assertTrue(any(event.kind == "source-truncated"
                            for event in events))

    def test_candidate_rows_have_an_exact_validated_shape(self):
        self._write("alpha")
        self._write("bravo")
        cursors = {"agents.state": self._wrapped({})}
        self.sialib.sense_agents(cursors)
        row = next(iter(cursors["agents.scan"]["rows"].values()))
        row["laundered"] = "not-source-state"

        with self.assertRaisesRegex(
                ValueError, "agent usage scan cursor is invalid"):
            self.sialib.sense_agents(cursors)

    def test_in_place_rewrite_of_prior_page_cannot_enter_clean_snapshot(self):
        self._write("alpha", tokens=10)
        self._write("bravo", tokens=20)
        prior = {
            "alpha": {"tokens": 1, "limits": {}, "generation": 0},
            "bravo": {"tokens": 2, "limits": {}, "generation": 0},
        }
        cursors = {"agents.state": self._wrapped(prior)}
        self.sialib.sense_agents(cursors)
        captured = next(iter(cursors["agents.scan"]["rows"]))
        source_state = cursors["agents.scan"]["sources"][captured]
        source = (source_state["name"] if isinstance(source_state, dict)
                  else source_state)
        with open(os.path.join(self.usage, source), "w") as stream:
            json.dump({"id": captured, "todayTotalTokens": 99}, stream)

        events = self._finish(cursors)

        self.assertEqual(self._state(cursors)[captured], prior[captured])
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))

    def test_malformed_authoritative_agent_state_refuses_without_mutation(self):
        cursors = {
            "agents.state": [
                "sia-source-entity-state-v1",
                {"lost": "malformed"},
            ],
        }
        before = copy.deepcopy(cursors)

        with self.assertRaisesRegex(
                ValueError, "source cursor agents.state is invalid"):
            self._finish(cursors)

        self.assertEqual(cursors, before)

    def test_legacy_agent_rows_migrate_with_source_directory_absent(self):
        raw_agent = "Legacy Agent"
        raw_limit = "Daily Limit"
        agent_id = self.sialib._source_entity_token(raw_agent, "agent")
        limit_id = self.sialib._source_entity_token(
            raw_limit, "agent-limit")
        legacy_row = {
            "tokens": 5,
            "limits": {raw_limit: 80},
        }
        cursors_by_format = (
            ({"agents.state": {
                raw_agent: copy.deepcopy(legacy_row)}}, agent_id),
            ({"agents.state": self._wrapped({
                "legacy": copy.deepcopy(legacy_row)})}, "legacy"),
            ({"agents.state": self._wrapped({
                "legacy_agent": copy.deepcopy(legacy_row)})},
             self.sialib._source_entity_token("legacy_agent", "agent")),
        )
        os.rmdir(self.usage)

        for cursors, expected_agent_id in cursors_by_format:
            with self.subTest(cursors=cursors):
                self.assertEqual(self.sialib.sense_agents(cursors), [])
                self.assertEqual(self._state(cursors), {
                    expected_agent_id: {
                        "tokens": 5,
                        "limits": {limit_id: 80},
                        "generation": 0,
                    },
                })

    def test_untagged_token_looking_legacy_ids_are_still_raw(self):
        os.rmdir(self.usage)
        cursors = {"agents.state": {
            "a_2bb": {
                "tokens": 5,
                "limits": {"daily_20limit": 80},
            },
        }}

        self.assertEqual(self.sialib.sense_agents(cursors), [])

        self.assertEqual(self._state(cursors), {
            "a_5f2bb": {
                "tokens": 5,
                "limits": {"daily_5f20limit": 80},
                "generation": 0,
            },
        })

    def test_ambiguous_tagged_legacy_agent_identity_refuses_atomically(self):
        legacy_row = {"tokens": 5, "limits": {}}
        ambiguous = (
            self.sialib._source_entity_token("Legacy Agent", "agent"),
            "a_2bb",
            "_e",
            "agent_h" + ("a" * 64),
        )
        os.rmdir(self.usage)
        for agent_id in ambiguous:
            cursors = {"agents.state": self._wrapped({
                agent_id: copy.deepcopy(legacy_row)})}
            before = copy.deepcopy(cursors)
            with self.subTest(agent_id=agent_id), self.assertRaisesRegex(
                    ValueError, "source cursor agents.state is invalid"):
                self.sialib.sense_agents(cursors)
            self.assertEqual(cursors, before)

    def test_modern_agent_row_supersedes_provable_legacy_shadow(self):
        raw_agent = "legacy_agent"
        agent_id = self.sialib._source_entity_token(raw_agent, "agent")
        limit_id = self.sialib._source_entity_token(
            "Daily Limit", "agent-limit")
        legacy_row = {
            "tokens": 5,
            "limits": {"Daily Limit": 70},
        }
        modern_row = {
            "tokens": 5,
            "limits": {limit_id: 85},
            "generation": 0,
        }
        self._write(raw_agent, tokens=5, limits=[
            {"label": "Daily Limit", "percent": 0.9},
        ])
        rows = (
            (raw_agent, legacy_row),
            (agent_id, modern_row),
        )
        for ordered in (rows, tuple(reversed(rows))):
            cursors = {"agents.state": self._wrapped(dict(ordered))}
            events = self._finish(cursors)
            self.assertFalse(any(event.kind == "limit" for event in events))
            self.assertEqual(self._state(cursors), {
                agent_id: {
                    "tokens": 5,
                    "limits": {limit_id: 90},
                    "generation": 0,
                },
            })

    def test_legacy_agent_row_migrates_before_live_source_replacement(self):
        self._write("legacy", tokens=10, limits=[
            {"label": "Daily Limit", "percent": 0.9},
        ])
        limit_id = self.sialib._source_entity_token(
            "Daily Limit", "agent-limit")
        legacy = {
            "legacy": {
                "tokens": 5,
                "limits": {"Daily Limit": 80},
            },
        }
        for stored in (legacy, self._wrapped(legacy)):
            cursors = {"agents.state": copy.deepcopy(stored)}
            with self.subTest(tagged=isinstance(stored, list)):
                self._finish(cursors)
                self.assertEqual(self._state(cursors)["legacy"], {
                    "tokens": 10,
                    "limits": {limit_id: 90},
                    "generation": 0,
                })

    def test_legacy_underscore_agent_id_keeps_upgrade_transition(self):
        raw_agent = "legacy_agent"
        agent_id = self.sialib._source_entity_token(raw_agent, "agent")
        limit_id = self.sialib._source_entity_token(
            "Daily Limit", "agent-limit")
        self._write(raw_agent, tokens=5, limits=[
            {"label": "Daily Limit", "percent": 0.9},
        ])
        cursors = {"agents.state": {
            raw_agent: {
                "tokens": 5,
                "limits": {"Daily Limit": 80},
            },
        }}

        events = self._finish(cursors)

        self.assertNotEqual(agent_id, raw_agent)
        self.assertEqual(set(self._state(cursors)), {agent_id})
        self.assertEqual(self._state(cursors)[agent_id], {
            "tokens": 5,
            "limits": {limit_id: 90},
            "generation": 0,
        })
        limits = [event for event in events if event.kind == "limit"]
        self.assertEqual(len(limits), 1)
        self.assertIn("90% (was 80%)", limits[0].summary)

    def test_malformed_legacy_agent_rows_refuse_without_mutation(self):
        malformed = (
            {"tokens": True, "limits": {}},
            {"tokens": 5, "limits": {"window": True}},
            {"tokens": 5, "limits": {"": 80}},
            {"tokens": 5, "limits": {"\ud800": 80}},
            {"tokens": 5, "limits": {"window": 101}},
            {"tokens": 5, "limits": {}, "unexpected": 0},
        )
        for row in malformed:
            for stored in (
                    {"legacy": copy.deepcopy(row)},
                    self._wrapped({"legacy": copy.deepcopy(row)})):
                cursors = {"agents.state": stored}
                before = copy.deepcopy(cursors)
                with self.subTest(row=row, tagged=isinstance(stored, list)), \
                        self.assertRaisesRegex(
                            ValueError,
                            "source cursor agents.state is invalid"):
                    self.sialib.sense_agents(cursors)
                self.assertEqual(cursors, before)

    def test_legacy_source_key_collisions_refuse_without_mutation(self):
        rows = (
            ("a+b", {"tokens": 5, "limits": {}, "generation": 0}),
            ("a_2bb", {"tokens": 7, "limits": {}, "generation": 0}),
        )
        for ordered in (rows, tuple(reversed(rows))):
            cursors = {"agents.state": dict(ordered)}
            before = copy.deepcopy(cursors)
            with self.subTest(keys=tuple(cursors["agents.state"])), \
                    self.assertRaisesRegex(
                        ValueError, "source cursor agents.state is invalid"):
                self.sialib.sense_agents(cursors)
            self.assertEqual(cursors, before)

    def test_malformed_agent_source_rows_cannot_replace_prior_state(self):
        prior = {
            "alpha": {
                "tokens": 5,
                "limits": {"retained": 80},
                "generation": 0,
            },
        }
        cases = (
            {"id": "alpha", "todayTotalTokens": 10.75, "limits": []},
            {"id": "alpha", "todayTotalTokens": 10, "limits": 0},
            {"id": 0, "todayTotalTokens": 10, "limits": []},
            {"id": "alpha", "todayTotalTokens": 10, "limits": [
                {"label": {"private": "nested"}, "percent": 10},
            ]},
            {"id": "alpha", "todayTotalTokens": 10, "limits": [
                {"label": "window", "percent": -20},
            ]},
            {"id": "alpha", "todayTotalTokens": 10, "limits": [
                {"label": "window", "percent": 101},
            ]},
            {"id": "alpha", "todayTotalTokens": 10, "limits": [
                {"label": "window", "percent": 10},
                {"label": "window", "percent": 90},
            ]},
        )
        for index, record in enumerate(cases):
            with self.subTest(record=record):
                for name in os.listdir(self.usage):
                    os.unlink(os.path.join(self.usage, name))
                with open(os.path.join(
                        self.usage, f"source-{index}.json"), "w") as stream:
                    json.dump(record, stream)
                cursors = {"agents.state": self._wrapped(prior)}

                with mock.patch.object(
                        self.sialib, "MAX_CONFIG_TAGS", 8):
                    events = self._finish(cursors)

                self.assertEqual(self._state(cursors), prior)
                self.assertTrue(any(
                    event.kind == "source-entry-refused" for event in events))
                self.assertNotIn("private", " ".join(
                    event.summary for event in events))


class SkillCatalogContinuation(unittest.TestCase):
    """Skill roots retain bounded continuation and candidate state."""

    def setUp(self):
        self.sialib = _load(
            "sialib_skill_catalog_continuation",
            os.path.join(BIN, "sialib.py"))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "skills")
        os.makedirs(self.root)
        self.sialib.SKILL_ROOTS = [self.root]
        self.original_entries = self.sialib._bounded_source_entries

    def _write(self, name, description=None):
        self._write_at(self.root, name, description)

    def _write_at(self, root, name, description=None):
        path = os.path.join(root, name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "SKILL.md"), "w") as stream:
            stream.write(
                "---\ndescription: " + (description or name) + "\n---\n")

    def _one_entry_page(self, directory, page_state=None, limit=None,
                        cleanup_legacy_atomic=False):
        return self.original_entries(
            directory, page_state, 1,
            cleanup_legacy_atomic=cleanup_legacy_atomic)

    def _finish(self, cursors):
        events = []
        for _attempt in range(self.sialib.MAX_SOURCE_SCAN_ENTRIES):
            events.extend(self.sialib.sense_skills(cursors))
            if "skills.scan" not in cursors:
                return events
        self.fail("skill catalog scan did not reach a complete aggregate")

    def test_later_pages_are_reachable_and_diff_only_at_complete_eof(self):
        self._write("alpha")
        self._write("bravo")
        self._write("charlie")
        cursors = {"skills.snapshot": {}}

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            first = self.sialib.sense_skills(cursors)
            self.assertEqual(cursors["skills.snapshot"], {})
            self.assertFalse(any(event.kind in {
                "installed", "updated", "removed"} for event in first))
            events = first + self._finish(cursors)

        self.assertEqual(set(cursors["skills.snapshot"]),
                         {"alpha", "bravo", "charlie"})
        self.assertEqual(
            {event.summary.split(": ", 1)[1].split(" —", 1)[0]
             for event in events if event.kind == "installed"},
            {"alpha", "bravo", "charlie"})

    def test_generation_reset_discards_prior_page_capture(self):
        self._write("alpha")
        self._write("bravo")
        cursors = {"skills.snapshot": {}}

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            self.sialib.sense_skills(cursors)
            scan = cursors["skills.scan"]
            captured = scan["rows"][0]["name"]
            shutil.rmtree(os.path.join(self.root, captured))
            self._write("charlie")
            events = self._finish(cursors)

        self.assertNotIn(captured, cursors["skills.snapshot"])
        self.assertFalse(any(
            captured in event.summary for event in events
            if event.kind in {"installed", "cataloged"}))

    def test_tainted_root_never_prunes_prior_snapshot(self):
        self._write("resident")
        cursors = {}
        self.sialib.sense_skills(cursors)
        prior = copy.deepcopy(cursors["skills.snapshot"])

        with mock.patch.object(
                self.sialib, "_skill_manifest_capture_matches",
                return_value=False):
            events = self.sialib.sense_skills(cursors)

        self.assertEqual(cursors["skills.snapshot"], prior)
        self.assertTrue(cursors["skills.partial"])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_manifest_io_refusal_never_proves_skill_removal(self):
        self._write("resident")
        cursors = {}
        self.sialib.sense_skills(cursors)
        prior = copy.deepcopy(cursors["skills.snapshot"])
        original = self.sialib._read_skill_manifest

        def refused(root, name):
            if name == "resident":
                raise PermissionError("manifest temporarily unreadable")
            return original(root, name)

        with mock.patch.object(
                self.sialib, "_read_skill_manifest",
                side_effect=refused):
            events = self.sialib.sense_skills(cursors)

        self.assertEqual(cursors["skills.snapshot"], prior)
        self.assertTrue(cursors["skills.partial"])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_manifest_descriptors_are_opened_nonblocking(self):
        self._write("resident")
        runtime_globals = self.sialib._read_skill_manifest.__globals__
        real_os = runtime_globals["os"]

        class CheckedOs:
            def __getattr__(self, name):
                return getattr(real_os, name)

            def open(self, path, flags, *args, **kwargs):
                if path == "SKILL.md":
                    self.assert_nonblocking(flags)
                return real_os.open(path, flags, *args, **kwargs)

            @staticmethod
            def assert_nonblocking(flags):
                if not flags & real_os.O_NONBLOCK:
                    raise AssertionError(
                        "skill manifest descriptor may block on a special file")

        with mock.patch.dict(runtime_globals, {"os": CheckedOs()}):
            self.sialib.sense_skills({})

    def test_malformed_authoritative_skill_state_refuses_without_mutation(self):
        cases = (
            {"skills.snapshot": []},
            {"skills.snapshot": {"broken": {"name": "broken"}}},
            {"skills.snapshot": {}, "skills.partial": "false"},
            {"skills.snapshot": {}, "skills.truncated": 0},
            {"skills.snapshot": {}, "skills.removal_guard": None},
            {"skills.snapshot": {}, "skills.root_history": None},
            {"skills.snapshot": {}, "skills.root_history": []},
            {"skills.snapshot": {}, "skills.root_history": [
                "sia-skill-root-history-v1", ["not-a-root-id"]]},
            {"skills.snapshot": {}, "skills.root_history": [
                "sia-skill-root-history-v1", [{"unhashable": True}]]},
        )
        for cursors in cases:
            with self.subTest(cursors=cursors):
                before = copy.deepcopy(cursors)
                with self.assertRaisesRegex(
                        ValueError, "skill catalog state is invalid"):
                    self.sialib.sense_skills(cursors)
                self.assertEqual(cursors, before)

    def test_partial_shared_skill_preserves_unreadable_root_provenance(self):
        second_root = os.path.join(self.tmp.name, "second-skills")
        os.makedirs(os.path.join(second_root, "shared"))
        with open(os.path.join(
                second_root, "shared", "SKILL.md"), "w") as stream:
            stream.write("---\ndescription: shared\n---\n")
        self._write("shared")
        self.sialib.SKILL_ROOTS = [self.root, second_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        prior = copy.deepcopy(cursors["skills.snapshot"])
        original = self.sialib._list_skill_entries

        def refuse_second(root, page_state=None):
            if root == second_root:
                raise OSError("second root unavailable")
            return original(root, page_state)

        with mock.patch.object(
                self.sialib, "_list_skill_entries",
                side_effect=refuse_second):
            events = self.sialib.sense_skills(cursors)

        self.assertEqual(cursors["skills.snapshot"], prior)
        self.assertTrue(cursors["skills.partial"])
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))
        self.assertFalse(any(event.kind == "updated" for event in events))

    def test_partial_shared_skill_overlays_observed_root_only(self):
        second_root = os.path.join(self.tmp.name, "second-skills")
        os.makedirs(os.path.join(second_root, "shared"))
        with open(os.path.join(
                second_root, "shared", "SKILL.md"), "w") as stream:
            stream.write("---\ndescription: second\n---\n")
        self._write("shared", "first")
        self.sialib.SKILL_ROOTS = [self.root, second_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        prior = copy.deepcopy(cursors["skills.snapshot"]["shared"])
        second_root_id = self.sialib._skill_root_id(second_root)
        prior_second = next(
            row for row in prior["roots"]
            if row["root_id"] == second_root_id)
        self._write("shared", "first updated")
        original = self.sialib._list_skill_entries

        def refuse_second(root, page_state=None):
            if root == second_root:
                raise OSError("second root unavailable")
            return original(root, page_state)

        with mock.patch.object(
                self.sialib, "_list_skill_entries",
                side_effect=refuse_second):
            events = self.sialib.sense_skills(cursors)

        current = cursors["skills.snapshot"]["shared"]
        current_second = next(
            row for row in current["roots"]
            if row["root_id"] == second_root_id)
        self.assertEqual(current_second, prior_second)
        self.assertEqual(
            [row["root_id"] for row in current["roots"]],
            [self.sialib._skill_root_id(self.root), second_root_id])
        self.assertEqual(current["description"], "first updated")
        self.assertTrue(any(event.kind == "updated" for event in events))

    def test_partial_shared_skill_drops_completed_root_provenance(self):
        second_root = os.path.join(self.tmp.name, "second-skills")
        os.makedirs(os.path.join(second_root, "shared"))
        with open(os.path.join(
                second_root, "shared", "SKILL.md"), "w") as stream:
            stream.write("---\ndescription: second\n---\n")
        self._write("shared", "first")
        self.sialib.SKILL_ROOTS = [self.root, second_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        first_root_id = self.sialib._skill_root_id(self.root)
        second_root_id = self.sialib._skill_root_id(second_root)
        shutil.rmtree(os.path.join(self.root, "shared"))
        original = self.sialib._list_skill_entries

        def refuse_second(root, page_state=None):
            if root == second_root:
                raise OSError("second root unavailable")
            return original(root, page_state)

        with mock.patch.object(
                self.sialib, "_list_skill_entries",
                side_effect=refuse_second):
            events = self.sialib.sense_skills(cursors)

        current = cursors["skills.snapshot"]["shared"]
        self.assertEqual(
            [row["root_id"] for row in current["roots"]],
            [second_root_id])
        self.assertNotIn(first_root_id, {
            row["root_id"] for row in current["roots"]})
        self.assertEqual(current["description"], "second")
        self.assertFalse(any(event.kind in {"updated", "removed"}
                             for event in events))

    def test_partial_absence_keeps_only_a_rootless_removal_guard(self):
        second_root = os.path.join(self.tmp.name, "second-skills")
        os.makedirs(second_root)
        self._write("resident", "first")
        self.sialib.SKILL_ROOTS = [self.root, second_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        shutil.rmtree(os.path.join(self.root, "resident"))
        original = self.sialib._list_skill_entries

        def refuse_second(root, page_state=None):
            if root == second_root:
                raise OSError("second root unavailable")
            return original(root, page_state)

        with mock.patch.object(
                self.sialib, "_list_skill_entries",
                side_effect=refuse_second):
            partial_events = self.sialib.sense_skills(cursors)

        guarded = cursors["skills.snapshot"]["resident"]
        self.assertEqual(guarded["roots"], [])
        self.assertEqual(guarded["description"], "")
        self.assertFalse(any(event.kind in {"updated", "removed"}
                             for event in partial_events))

        first_complete = self.sialib.sense_skills(cursors)
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertEqual(cursors["skills.snapshot"]["resident"]["roots"], [])
        self.assertFalse(any(event.kind == "removed"
                             for event in first_complete))

        second_complete = self.sialib.sense_skills(cursors)
        self.assertNotIn("resident", cursors["skills.snapshot"])
        self.assertTrue(any(event.kind == "removed"
                            for event in second_complete))

    def test_never_observed_absent_root_does_not_block_removal(self):
        missing_root = os.path.join(self.tmp.name, "never-installed-skills")
        self._write("resident", "present root")
        self.sialib.SKILL_ROOTS = [self.root, missing_root]
        cursors = {}

        initial = self.sialib.sense_skills(cursors)

        self.assertFalse(cursors["skills.partial"])
        self.assertFalse(any(event.kind == "source-refused"
                             for event in initial))
        shutil.rmtree(os.path.join(self.root, "resident"))

        removed = self.sialib.sense_skills(cursors)

        self.assertNotIn("resident", cursors["skills.snapshot"])
        self.assertFalse(cursors["skills.partial"])
        self.assertTrue(any(event.kind == "removed" for event in removed))

    def test_legacy_absence_guard_converges_with_missing_optional_root(self):
        missing_root = os.path.join(self.tmp.name, "never-installed-skills")
        self._write("resident", "present root")
        self.sialib.SKILL_ROOTS = [self.root, missing_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        cursors["skills.partial"] = True
        cursors["skills.removal_guard"] = True
        shutil.rmtree(os.path.join(self.root, "resident"))

        guarded = self.sialib.sense_skills(cursors)

        self.assertFalse(cursors["skills.partial"])
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertEqual(cursors["skills.snapshot"]["resident"]["roots"], [])
        self.assertFalse(any(event.kind == "removed" for event in guarded))

        converged = self.sialib.sense_skills(cursors)

        self.assertNotIn("resident", cursors["skills.snapshot"])
        self.assertTrue(any(event.kind == "removed" for event in converged))

    def test_previously_observed_root_disappearance_still_guards_removal(self):
        second_root = os.path.join(self.tmp.name, "observed-skills")
        os.makedirs(second_root)
        self._write("resident", "present root")
        self.sialib.SKILL_ROOTS = [self.root, second_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        shutil.rmtree(os.path.join(self.root, "resident"))
        os.rmdir(second_root)

        events = self.sialib.sense_skills(cursors)

        self.assertTrue(cursors["skills.partial"])
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertEqual(cursors["skills.snapshot"]["resident"]["roots"], [])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_absent_root_before_paginated_root_never_becomes_observed(self):
        missing_root = os.path.join(self.tmp.name, "never-installed-skills")
        self._write("alpha")
        self._write("bravo")
        self.sialib.SKILL_ROOTS = [missing_root, self.root]
        present_root_id = self.sialib._skill_root_id(self.root)
        cursors = {}

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            self.sialib.sense_skills(cursors)
            self.assertEqual(
                cursors["skills.root_history"][1], [present_root_id])
            self._finish(cursors)

        self.assertEqual(
            cursors["skills.root_history"][1], [present_root_id])
        shutil.rmtree(os.path.join(self.root, "alpha"))
        shutil.rmtree(os.path.join(self.root, "bravo"))

        removed = self.sialib.sense_skills(cursors)

        self.assertFalse(cursors["skills.partial"])
        self.assertEqual(cursors["skills.snapshot"], {})
        self.assertTrue(any(event.kind == "removed" for event in removed))

    def test_absent_root_is_rechecked_before_removal(self):
        missing_root = os.path.join(self.tmp.name, "initially-absent-skills")
        self._write("resident")
        self.sialib.SKILL_ROOTS = [missing_root, self.root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        self._write("alpha")
        self._write("bravo")
        shutil.rmtree(os.path.join(self.root, "resident"))

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            events = self.sialib.sense_skills(cursors)
            self.assertIn("skills.scan", cursors)
            appeared = os.path.join(missing_root, "resident")
            os.makedirs(appeared)
            with open(os.path.join(appeared, "SKILL.md"), "w") as stream:
                stream.write("---\ndescription: appeared\n---\n")
            events.extend(self._finish(cursors))

        self.assertTrue(cursors["skills.partial"])
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertIn(
            self.sialib._skill_root_id(missing_root),
            cursors["skills.root_history"][1])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_completed_empty_root_is_rechecked_before_removal(self):
        early_root = os.path.join(self.tmp.name, "early-skills")
        os.makedirs(early_root)
        self._write("resident")
        self.sialib.SKILL_ROOTS = [early_root, self.root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        self._write("alpha")
        self._write("bravo")
        shutil.rmtree(os.path.join(self.root, "resident"))

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            events = self.sialib.sense_skills(cursors)
            self.assertIn("skills.scan", cursors)
            self._write_at(early_root, "resident", "appeared")
            events.extend(self._finish(cursors))

        self.assertTrue(cursors["skills.partial"])
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_completed_root_rechecks_previously_manifestless_child(self):
        later_root = os.path.join(self.tmp.name, "later-skills")
        os.makedirs(later_root)
        os.makedirs(os.path.join(self.root, "resident"))
        self._write_at(later_root, "resident", "later root")
        self.sialib.SKILL_ROOTS = [self.root, later_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        self._write_at(later_root, "alpha")
        self._write_at(later_root, "bravo")
        shutil.rmtree(os.path.join(later_root, "resident"))

        events = []
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            for _attempt in range(self.sialib.MAX_SOURCE_SCAN_ENTRIES):
                events.extend(self.sialib.sense_skills(cursors))
                if cursors.get("skills.scan", {}).get("root_index") == 1:
                    break
            else:
                self.fail("skill scan did not reach the later root")
            self._write("resident", "appeared manifest")
            events.extend(self._finish(cursors))

        self.assertTrue(cursors["skills.partial"])
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_completed_root_rechecks_positive_manifest_capture(self):
        later_root = os.path.join(self.tmp.name, "later-skills")
        os.makedirs(later_root)
        self._write("resident", "before")
        self._write_at(later_root, "alpha")
        self._write_at(later_root, "bravo")
        self.sialib.SKILL_ROOTS = [self.root, later_root]
        cursors = {}
        self.sialib.sense_skills(cursors)
        self._write("resident", "middle")

        events = []
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            for _attempt in range(self.sialib.MAX_SOURCE_SCAN_ENTRIES):
                events.extend(self.sialib.sense_skills(cursors))
                if cursors.get("skills.scan", {}).get("root_index") == 1:
                    break
            else:
                self.fail("skill scan did not reach the later root")
            self._write("resident", "after")
            events.extend(self._finish(cursors))

        self.assertTrue(cursors["skills.partial"])
        self.assertEqual(
            cursors["skills.snapshot"]["resident"]["description"],
            "before")
        self.assertFalse(any(event.kind == "updated" for event in events))
        self.assertTrue(any(event.kind == "source-refused"
                            for event in events))

    def test_over_cap_catalog_reaches_later_manifests_without_removal(self):
        self._write("resident")
        cursors = {}
        self.sialib.sense_skills(cursors)
        shutil.rmtree(os.path.join(self.root, "resident"))
        self._write("new-alpha")
        self._write("new-bravo")

        with mock.patch.object(
                self.sialib, "MAX_SKILL_SNAPSHOT_ENTRIES", 1), \
                mock.patch.object(
                    self.sialib, "_bounded_source_entries",
                    side_effect=self._one_entry_page):
            events = self._finish(cursors)

        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertFalse(any(event.kind == "removed" for event in events))
        refused = [event for event in events
                   if event.kind == "source-entry-refused"]
        self.assertTrue(refused)
        self.assertTrue(any(event.kind == "catalog-truncated"
                            for event in events))
        self.assertTrue(any(
            name in " ".join(event.summary for event in refused)
            for name in ("new-alpha", "new-bravo")))

    def test_manifestless_coverage_over_cap_blocks_removal(self):
        self._write("resident")
        cursors = {}
        self.sialib.sense_skills(cursors)
        shutil.rmtree(os.path.join(self.root, "resident"))
        os.makedirs(os.path.join(self.root, "empty-alpha"))
        os.makedirs(os.path.join(self.root, "empty-bravo"))

        with mock.patch.object(
                self.sialib, "MAX_SKILL_SNAPSHOT_ENTRIES", 1), \
                mock.patch.object(
                    self.sialib, "_bounded_source_entries",
                    side_effect=self._one_entry_page):
            events = self._finish(cursors)

        self.assertTrue(cursors["skills.partial"])
        self.assertIn("resident", cursors["skills.snapshot"])
        self.assertFalse(any(event.kind == "removed" for event in events))
        self.assertTrue(any(event.kind == "source-entry-refused"
                            for event in events))
        self.assertTrue(any(event.kind == "catalog-truncated"
                            for event in events))

    def test_unchanged_stable_catalog_has_no_duplicate_diff_events(self):
        self._write("alpha")
        self._write("bravo")
        cursors = {"skills.snapshot": {}}

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            first = self._finish(cursors)
            second = self._finish(cursors)

        self.assertTrue(any(event.kind == "installed" for event in first))
        self.assertFalse(any(event.kind in {
            "installed", "updated", "removed"} for event in second))

    def test_clean_paginated_eof_can_prove_a_removal(self):
        self._write("alpha")
        self._write("bravo")
        cursors = {}
        self.sialib.sense_skills(cursors)
        shutil.rmtree(os.path.join(self.root, "bravo"))

        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            events = self._finish(cursors)

        self.assertNotIn("bravo", cursors["skills.snapshot"])
        self.assertTrue(any(
            event.kind == "removed" and "bravo" in event.summary
            for event in events))

    def test_persisted_candidate_name_cannot_escape_its_skill_root(self):
        self._write("alpha")
        self._write("bravo")
        _entries, _complete, _inspected, page = self.original_entries(
            self.root, limit=1)
        root_id = self.sialib._skill_root_id(self.root)
        hostile = "../outside"
        scan = {
            "schema": "sia-skill-catalog-scan-v1",
            "roots": [root_id], "root_index": 0, "page": page,
            "rows": [{
                "root_id": root_id, "name": hostile,
                "name_id": hashlib.sha256(
                    os.fsencode(hostile)).hexdigest(),
                "description": "private", "manifest": {},
            }],
            "tainted_roots": [], "truncated_roots": [],
            "prior_truncated": False, "prior_removal_guard": False,
        }

        with self.assertRaisesRegex(
                ValueError, "skill catalog scan cursor is invalid"):
            self.sialib._validated_skill_scan(scan, [root_id])

    def test_legacy_scan_restart_does_not_invent_a_missing_root(self):
        missing_root = os.path.join(self.tmp.name, "never-installed-skills")
        self._write("alpha")
        self._write("bravo")
        self.sialib.SKILL_ROOTS = [missing_root, self.root]
        cursors = {"skills.snapshot": {}}
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            self.sialib.sense_skills(cursors)

        legacy = copy.deepcopy(cursors["skills.scan"])
        missing_root_id, present_root_id = legacy["roots"]
        legacy["schema"] = "sia-skill-catalog-scan-v1"
        legacy.pop("entries")
        legacy.pop("known_roots")
        legacy.pop("absent_roots")
        legacy.pop("completed_roots")
        legacy["tainted_roots"] = [missing_root_id]
        before = copy.deepcopy(legacy)

        restarted = self.sialib._validated_skill_scan(
            legacy, legacy["roots"], known_root_ids=[])

        self.assertEqual(legacy, before)
        self.assertEqual(restarted["schema"], "sia-skill-catalog-scan-v2")
        self.assertEqual(restarted["known_roots"], [present_root_id])
        self.assertEqual(restarted["root_index"], 0)
        self.assertIsNone(restarted["page"])
        self.assertEqual(restarted["entries"], [])
        self.assertEqual(restarted["rows"], [])

    def test_skill_cursor_requires_exact_rows_and_page_index_pairing(self):
        self._write("alpha")
        self._write("bravo")
        cursors = {"skills.snapshot": {}}
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            self.sialib.sense_skills(cursors)
        scan = cursors["skills.scan"]
        extra = copy.deepcopy(scan)
        extra["rows"][0]["manifest"]["laundered"] = True
        finished_index = copy.deepcopy(scan)
        finished_index["root_index"] = len(finished_index["roots"])
        missing_history = copy.deepcopy(scan)
        missing_history.pop("known_roots")
        missing_absence = copy.deepcopy(scan)
        missing_absence.pop("absent_roots")
        missing_entries = copy.deepcopy(scan)
        missing_entries.pop("entries")
        missing_completions = copy.deepcopy(scan)
        missing_completions.pop("completed_roots")
        uncovered_row = copy.deepcopy(scan)
        uncovered_row["entries"] = []
        hostile_entry = copy.deepcopy(scan)
        hostile_entry["entries"][0]["name"] = "../outside"
        hostile_entry["entries"][0]["name_id"] = hashlib.sha256(
            os.fsencode("../outside")).hexdigest()
        unknown_history = copy.deepcopy(scan)
        unknown_history["known_roots"].append("0" * 64)
        duplicate_history = copy.deepcopy(scan)
        duplicate_history["known_roots"].append(
            duplicate_history["known_roots"][0])
        unknown_absence = copy.deepcopy(scan)
        unknown_absence["absent_roots"].append("0" * 64)
        overlapping_absence = copy.deepcopy(scan)
        overlapping_absence["absent_roots"].append(
            overlapping_absence["known_roots"][0])
        premature_completion = copy.deepcopy(scan)
        premature_completion["completed_roots"].append({
            "root_id": premature_completion["roots"][0],
            "generation": {
                field: premature_completion["page"][field]
                for field in self.sialib.SOURCE_TREE_GENERATION_FIELDS},
        })

        for invalid in (
                extra, finished_index, missing_history, missing_absence,
                missing_entries, missing_completions, uncovered_row,
                hostile_entry, unknown_history, duplicate_history,
                unknown_absence,
                overlapping_absence, premature_completion):
            with self.assertRaisesRegex(
                    ValueError, "skill catalog scan cursor is invalid"):
                self.sialib._validated_skill_scan(
                    invalid, invalid["roots"])

        cursors["skills.root_history"] = [
            "sia-skill-root-history-v1", []]
        before = copy.deepcopy(cursors)
        with self.assertRaisesRegex(
                ValueError, "skill catalog scan cursor is invalid"):
            self.sialib.sense_skills(cursors)
        self.assertEqual(cursors, before)

        for malformed in (None, [], "invalid"):
            malformed_cursors = {
                "skills.snapshot": {}, "skills.scan": malformed}
            before = copy.deepcopy(malformed_cursors)
            with self.assertRaisesRegex(
                    ValueError, "skill catalog scan cursor is invalid"):
                self.sialib.sense_skills(malformed_cursors)
            self.assertEqual(malformed_cursors, before)

    def test_completed_root_cursor_requires_exact_generation(self):
        early_root = os.path.join(self.tmp.name, "early-skills")
        os.makedirs(early_root)
        self._write("alpha")
        self._write("bravo")
        self.sialib.SKILL_ROOTS = [early_root, self.root]
        cursors = {"skills.snapshot": {}}
        with mock.patch.object(
                self.sialib, "_bounded_source_entries",
                side_effect=self._one_entry_page):
            self.sialib.sense_skills(cursors)
        scan = cursors["skills.scan"]
        known = cursors["skills.root_history"][1]
        self.assertEqual(len(scan["completed_roots"]), 1)

        missing_field = copy.deepcopy(scan)
        missing_field["completed_roots"][0]["generation"].pop("ctime_ns")
        boolean_field = copy.deepcopy(scan)
        boolean_field["completed_roots"][0]["generation"]["device"] = True
        duplicate = copy.deepcopy(scan)
        duplicate["completed_roots"].append(copy.deepcopy(
            duplicate["completed_roots"][0]))
        missing_completion = copy.deepcopy(scan)
        missing_completion["completed_roots"] = []

        for invalid in (
                missing_field, boolean_field, duplicate,
                missing_completion):
            with self.assertRaisesRegex(
                    ValueError, "skill catalog scan cursor is invalid"):
                self.sialib._validated_skill_scan(
                    invalid, invalid["roots"], known_root_ids=known)


if __name__ == "__main__":
    unittest.main()
