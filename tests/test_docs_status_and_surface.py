#!/usr/bin/env python3
"""Docs must state the CURRENT shipped status and the WHOLE CLI surface.

These pin three ways the prose drifted away from the code while still
reading as confident and specific:

  * the whitepaper kept advertising the associative tie-breaker as
    release-selected policy long after the 2026-09-02 measurement demoted
    it to default-off, and justified it with "it matched dense" — a bar
    the paper's own freeze rule does not accept;
  * the manual and the continuity boundary described version-conditional
    behaviour without ever saying which version they described;
  * the manual omitted `sia backup check`, `--no-touch`, and four other
    real commands, so an operator following only the manual could not
    finish a clean-machine recovery or audit memory without reinforcing
    the memories being audited.

Prose that is stale is not a cosmetic defect here: every one of these
sends a reader to do the wrong thing with a straight face.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import ast
import io
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relative):
    path = os.path.join(REPO, relative)
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    return " ".join(text.split())


def _section(document, heading):
    """Return one '## ' section, so a claim cannot pass by appearing
    somewhere else in the file."""
    lines = document.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith(heading):
            start = index
            break
    assert start is not None, "missing heading: " + heading
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _release_version():
    manifest = json.loads(_read("manifest.json"))
    return manifest["version"]


class ShippedStatusIsStatedHonestly(unittest.TestCase):
    """FINDING 10 / FINDING 11."""

    def test_whitepaper_limits_section_states_default_off(self):
        section = _flat(_section(_read("docs/WHITEPAPER.md"),
                                 "## 11. Limitations"))
        # The demotion, not a stale promotion.
        self.assertIn("default-off", section)
        self.assertIn("retrieval.associative_rerank", section)
        # The actual 2026-09-02 numbers, so the claim is falsifiable.
        for measurement in ("0.86", "0.91", "0.67", "0.71",
                            "0.50", "0.59"):
            self.assertIn(measurement, section)

    def test_whitepaper_limits_section_drops_the_matched_justification(self):
        section = _flat(_section(_read("docs/WHITEPAPER.md"),
                                 "## 11. Limitations"))
        # "it matched dense" is the freeze rule's failure case, never its
        # promotion case. Promotion requires beating the alternative.
        self.assertNotIn(
            "the tested release-selected policy because it matched", section)
        self.assertNotRegex(
            section, r"because it matched dense retrieval")

    def test_freeze_rule_requires_beating_not_tying(self):
        section = _flat(_section(_read("docs/WHITEPAPER.md"),
                                 "## 11. Limitations"))
        self.assertIn("beating the plain alternative", section)
        # A tie must be named as insufficient, or the rule reads as
        # satisfied by the very measurement that demoted the mechanism.
        self.assertIn("Matching the plain alternative is not promotion",
                      section)

    def test_limits_and_retrieval_sections_do_not_contradict(self):
        whitepaper = _read("docs/WHITEPAPER.md")
        limits = _flat(_section(whitepaper, "## 11. Limitations"))
        # Whatever §4.3 says about the flag, §11 must say the same thing.
        self.assertIn("default-off", _flat(whitepaper))
        self.assertIn("default-off", limits)

    def test_abstract_does_not_list_hipporag_unqualified(self):
        abstract = _flat(_section(_read("docs/WHITEPAPER.md"),
                                  "## Abstract"))
        self.assertIn("HippoRAG", abstract)
        # Listing it bare among implemented layers overstates the ship.
        self.assertNotIn("retrieval (HippoRAG), dopaminergic", abstract)
        head = abstract.split("HippoRAG", 1)[1][:220]
        self.assertIn("default-off", head)


class DocumentsAreVersionStamped(unittest.TestCase):
    """FINDING 14."""

    def test_manual_and_continuity_carry_the_release_stamp(self):
        version = _release_version()
        for relative in ("docs/MANUAL.md", "docs/CONTINUITY.md"):
            with self.subTest(document=relative):
                head = _flat("\n".join(
                    _read(relative).splitlines()[:12]))
                self.assertIn("v" + version, head)

    def test_whitepaper_header_version_matches_the_release(self):
        version = _release_version()
        head = _flat("\n".join(_read("docs/WHITEPAPER.md")
                               .splitlines()[:6]))
        self.assertIn("v" + version, head)
        # The stamp that drifted; it described far later behaviour.
        self.assertNotIn("v1.5", head)

    def test_stamps_are_dates_not_bare_versions(self):
        for relative in ("docs/WHITEPAPER.md", "docs/MANUAL.md",
                         "docs/CONTINUITY.md"):
            with self.subTest(document=relative):
                head = "\n".join(_read(relative).splitlines()[:12])
                self.assertRegex(head, r"20\d\d-\d\d-\d\d")


class ManualCoversTheWholeCliSurface(unittest.TestCase):
    """FINDING 12 / FINDING 13."""

    def test_backup_check_is_in_the_manual_setup_block(self):
        manual = _read("docs/MANUAL.md")
        self.assertIn("sia backup check", manual)
        # It must be in the runnable block, not only in prose: a reader
        # copies the block.
        block = manual.split("sia backup setup", 1)[1][:2000]
        self.assertIn("sia backup check", block)

    def test_backup_check_closes_the_recovery_walkthrough(self):
        manual = _read("docs/MANUAL.md")
        tail = manual.split("sia restore recover", 1)[1]
        tail_flat = _flat(tail)
        self.assertIn("sia backup check", tail_flat)
        # And it must say WHY, or it reads as an optional extra.
        self.assertIn("latest", tail_flat)
        self.assertIn("ready health", tail_flat)

    def test_no_touch_is_documented_for_ask_and_recall(self):
        manual = _read("docs/MANUAL.md")
        section = _section(manual, "## 3. The CLI")
        self.assertIn("--no-touch", section)
        flat = _flat(section)
        self.assertIn("sia ask \"question\" --no-touch", flat)
        self.assertIn("sia recall <slug> --no-touch", flat)
        # The audit rationale is the reason it exists.
        self.assertIn("audit", flat.lower())

    def test_ask_docs_name_dense_default_and_optional_rerank(self):
        section = _flat(
            _section(_read("docs/MANUAL.md"), "## 3. The CLI")).lower()
        tree = ast.parse(_read("bin/sia"), filename="bin/sia")
        command = next(
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "cmd_ask")
        docstring = _flat(ast.get_docstring(command) or "").lower()

        for surface, text in (("manual", section), ("cli", docstring)):
            with self.subTest(surface=surface):
                self.assertIn("origin-weighted dense", text)
                self.assertIn("measured default", text)
                self.assertIn("retrieval.associative_rerank", text)
                self.assertIn("optional", text)

        self.assertNotIn(
            "dense embeddings seeded through the knowledge graph", section)

    def test_manual_documents_every_advertised_command(self):
        section = _flat(_section(_read("docs/MANUAL.md"), "## 3. The CLI"))
        for command in ("sia version", "sia note", "sia judge-audit",
                        "sia query"):
            with self.subTest(command=command):
                self.assertIn(command, section)

    def test_manual_surface_matches_the_cli_usage_banner(self):
        """The usage banner in bin/sia is the contract; §3 must not
        silently fall behind it again."""
        banner = "\n".join(_read("bin/sia").splitlines()[:52])
        advertised = set(re.findall(r"^  sia ([a-z-]+)", banner,
                                    re.MULTILINE))
        section = _flat(_section(_read("docs/MANUAL.md"), "## 3. The CLI"))
        manual_all = _flat(_read("docs/MANUAL.md"))
        missing = sorted(
            verb for verb in advertised
            if "sia " + verb not in section
            and "sia " + verb not in manual_all)
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
