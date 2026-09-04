#!/usr/bin/env python3
"""The ROADMAP rules that used to be enforced by nobody.

Two of the project's own standing gates were written as prose and enforced
socially. This file runs the machinery that now enforces them:

- **The marketplace freeze.** Verify issue #4078 was retargeted three times
  because a push moved `main` off the bound commit, and the maintainer's
  constraint is not "bind a good commit" but "bind the commit that is
  currently HEAD". ROADMAP.md now carries one machine-readable binding and
  CI's `marketplace-freeze` job refuses a push that breaks it. These tests
  run that job's *actual* shell — extracted from `.github/workflows/ci.yml`,
  never a copy — against constructed repositories.
- **The changelog's own numbering.** 1.7.4 was built, bumped, and then folded
  into 1.7.5 before either was tagged. The log has to say so; a version that
  exists in the history and nowhere in CHANGELOG.md is a silent gap.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(".github", "workflows", "ci.yml")
STEP = "- name: marketplace freeze gate"
BOUND = "8a624efc911457ae393a72758ade8729de5ba45d"


def _read(relative):
    with open(os.path.join(REPO, relative), "r", encoding="utf-8") as stream:
        return stream.read()


def _freeze_script():
    """The shipped gate's shell, lifted out of the workflow verbatim.

    Reading the real block is the whole point: a test that reimplemented the
    refusal would pass while CI did nothing.
    """
    lines = _read(WORKFLOW).splitlines()
    starts = [index for index, line in enumerate(lines)
              if line.strip() == STEP]
    if len(starts) != 1:
        raise AssertionError(
            f"{WORKFLOW} must define exactly one '{STEP}' step; "
            f"found {len(starts)}")
    run = None
    for index in range(starts[0] + 1, len(lines)):
        if lines[index].strip() == "run: |":
            run = index
            break
    if run is None:
        raise AssertionError("the freeze gate step has no 'run: |' block")
    indent = len(lines[run]) - len(lines[run].lstrip())
    body = []
    for line in lines[run + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line[indent + 2:] if line.strip() else "")
    return "\n".join(body) + "\n"


def _git(root, *argv):
    subprocess.run(("git",) + argv, cwd=root, check=True,
                   capture_output=True)


def _fixture(declaration, second_commit=("work.txt",),
             initial_roadmap=None, second_roadmap=None):
    """A two-commit repository whose HEAD changed the named files."""
    root = tempfile.mkdtemp(prefix="sia-freeze-")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "freeze@test")
    _git(root, "config", "user.name", "freeze")
    for name, body in (("ROADMAP.md", initial_roadmap or "base\n"),
                       ("work.txt", "base\n")):
        with open(os.path.join(root, name), "w", encoding="utf-8") as stream:
            stream.write(body)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    for name in second_commit:
        mode = "w" if name == "ROADMAP.md" and second_roadmap is not None \
            else "a"
        with open(os.path.join(root, name), mode, encoding="utf-8") as stream:
            stream.write(second_roadmap if mode == "w" else "second\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second")
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    # Written after committing on purpose: no commit can name its own SHA,
    # which is exactly why the gate has to tolerate a rebinding commit.
    with open(os.path.join(root, "ROADMAP.md"), "w",
              encoding="utf-8") as stream:
        stream.write(declaration.replace("{HEAD}", head))
    return root, head


def _run_gate(declaration, head=None, event="push", ref_type="branch",
              ref_name="main", second_commit=("work.txt",),
              initial_roadmap=None, second_roadmap=None):
    root, real_head = _fixture(
        declaration, second_commit, initial_roadmap, second_roadmap)
    script = os.path.join(root, "gate.sh")
    with open(script, "w", encoding="utf-8") as stream:
        stream.write(_freeze_script())
    environment = dict(os.environ)
    environment.update({
        "SIA_FREEZE_EVENT": event,
        "SIA_FREEZE_REF_TYPE": ref_type,
        "SIA_FREEZE_REF_NAME": ref_name,
        "SIA_FREEZE_HEAD": real_head if head is None else head,
    })
    try:
        return subprocess.run(("bash", script), cwd=root, env=environment,
                              capture_output=True, text=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


PENDING = "    sia-freeze: state=pending branch=main sha=" + BOUND + "\n"
PENDING_HEAD = "    sia-freeze: state=pending branch=main sha={HEAD}\n"
PREVIOUS_PENDING = (
    "    sia-freeze: state=pending branch=main sha=" + "0" * 40 + "\n")


class MarketplaceFreezeGate(unittest.TestCase):
    """ROADMAP's `main` freeze, as CI actually enforces it."""

    def test_the_workflow_declares_the_gate_with_a_visible_parent(self):
        # Short messages on purpose: the workflow is long, and assertIn would
        # otherwise print the whole file for a one-line absence.
        workflow = _read(WORKFLOW)
        for fragment in ("marketplace-freeze:", STEP,
                         # HEAD^ is what separates a rebinding commit from
                         # landed work; a shallow checkout would make the gate
                         # refuse every push.
                         "fetch-depth: 2",
                         "SIA_FREEZE_HEAD: ${{ github.sha }}"):
            self.assertIn(fragment, workflow,
                          f"{WORKFLOW} does not carry {fragment!r}")

    def test_roadmap_carries_one_readable_binding(self):
        roadmap = _read("ROADMAP.md")
        lines = [line for line in roadmap.splitlines()
                 if line.strip().startswith("sia-freeze:")]
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(
            lines[0].strip(),
            r"^sia-freeze: state=(pending|none) branch=\S+ sha=[0-9a-f]{40}$")

    def test_a_push_that_moves_the_frozen_branch_is_refused(self):
        result = _run_gate(PENDING)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("refusing: marketplace verification is pending",
                      result.stderr)
        self.assertIn(BOUND, result.stderr)

    def test_the_bound_commit_itself_passes(self):
        result = _run_gate(PENDING_HEAD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HEAD is the bound commit", result.stdout)

    def test_a_roadmap_only_rebinding_commit_passes(self):
        result = _run_gate(
            PENDING, second_commit=("ROADMAP.md",),
            initial_roadmap=PREVIOUS_PENDING, second_roadmap=PENDING)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rebinding commit", result.stdout)

    def test_unrelated_roadmap_prose_is_not_a_rebinding_commit(self):
        result = _run_gate(
            PENDING, second_commit=("ROADMAP.md",),
            initial_roadmap=PREVIOUS_PENDING + "old prose\n",
            second_roadmap=PENDING + "changed prose\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("refusing: marketplace verification is pending",
                      result.stderr)

    def test_work_smuggled_in_beside_a_roadmap_edit_is_refused(self):
        result = _run_gate(PENDING,
                           second_commit=("ROADMAP.md", "work.txt"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("refusing: marketplace verification is pending",
                      result.stderr)

    def test_closing_the_cycle_lifts_the_gate(self):
        result = _run_gate(
            "    sia-freeze: state=none branch=main sha=" + BOUND + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no marketplace verification is pending", result.stdout)

    def test_another_branch_is_announced_and_not_checked(self):
        result = _run_gate(PENDING, ref_name="fix/audit-30")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing about the binding was checked", result.stdout)

    def test_a_pull_request_is_announced_and_not_checked(self):
        result = _run_gate(PENDING, event="pull_request")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing about the binding was checked", result.stdout)

    def test_a_missing_declaration_fails_rather_than_passing_quietly(self):
        result = _run_gate("no declaration here\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("exactly one sia-freeze", result.stderr)

    def test_two_declarations_are_ambiguous_and_refused(self):
        result = _run_gate(PENDING + PENDING)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("exactly one sia-freeze", result.stderr)

    def test_an_unreadable_state_fails(self):
        result = _run_gate(
            "    sia-freeze: state=maybe branch=main sha=" + BOUND + "\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unreadable sia-freeze state", result.stderr)

    def test_a_short_sha_is_not_a_binding(self):
        # `df37702…` is how the ROADMAP prose named it; an abbreviation cannot
        # be compared to github.sha, so the gate demands the full 40.
        result = _run_gate(
            "    sia-freeze: state=pending branch=main sha=df37702\n")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("full 40-hex", result.stderr)


def _sections(changelog):
    """Each `## <version>` entry's body, keyed by version."""
    found, current, body = {}, None, []
    for line in changelog.splitlines():
        heading = re.match(r"^## (\d+\.\d+\.\d+) ", line)
        if heading:
            if current is not None:
                found[current] = "\n".join(body)
            current, body = heading.group(1), []
            continue
        if current is not None:
            body.append(line)
    if current is not None:
        found[current] = "\n".join(body)
    return found


class ChangelogNumbering(unittest.TestCase):
    """A version that existed and was never released still has to be told."""

    def test_every_skipped_patch_version_is_accounted_for(self):
        changelog = _read("CHANGELOG.md")
        sections = _sections(changelog)
        versions = [tuple(int(part) for part in version.split("."))
                    for version in re.findall(
                        r"(?m)^## (\d+\.\d+\.\d+) ", changelog)]
        self.assertGreater(len(versions), 1, "no changelog entries parsed")
        gaps = []
        for higher, lower in zip(versions, versions[1:]):
            if higher[:2] != lower[:2]:
                continue
            for patch in range(lower[2] + 1, higher[2]):
                gaps.append((".".join(str(part) for part in higher),
                             f"{lower[0]}.{lower[1]}.{patch}"))
        for entry, missing in gaps:
            # assertTrue, not assertIn: the container is a whole release
            # entry, and printing it would bury the one sentence that matters.
            self.assertTrue(
                missing in sections[entry],
                f"CHANGELOG.md jumps over {missing} without a word: the "
                f"entry for {entry} must say where that number went")

    def test_the_1_7_4_fold_is_the_gap_the_check_was_written_for(self):
        # Named explicitly so the check above cannot be satisfied by deleting
        # the release it is about.
        note = _sections(_read("CHANGELOG.md"))["1.7.5"]
        for fragment in ("1.7.4", "8cdfa3e"):
            self.assertTrue(fragment in note,
                            f"the 1.7.5 entry never mentions {fragment}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
