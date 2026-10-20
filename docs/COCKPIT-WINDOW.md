# Detachable cockpit

Operator requirement, 2026-10-20. Implemented on the experimental assurance
branch. Qualification is scoped below; this is not an installed-desktop or
marketplace release claim.

## Architecture and scope

The existing interface is QML, including its graph, controls and command
callbacks. Quickshell already provides a normal desktop `FloatingWindow`.
Use that surface instead of adding a Tauri/WebView renderer. `Cockpit.qml`
keeps one visual tree, one `Model.js` import and its existing readers and
process controllers. Selecting a presentation reparents the same visual tree.
The overlay remains the default for bar summons.

`sia cockpit --window` requests the window through the running Omarchy
shell's existing plugin call interface. `sia cockpit --overlay` and
`sia cockpit` select the overlay. The command does not start another shell,
memory service, database connection or authority core. The normal CLI
lifecycle lease surrounds dispatch. Subsequent UI commands retain their own
existing lifecycle/corpus and publication checks; no new lifetime database
lease is claimed.

The plugin returns a versioned presentation acknowledgment. CLI success
confirms the loaded component accepted the requested local presentation state;
it does not establish that the compositor displayed it or that memory is
ready. An unavailable or older plugin, unexpected response, output overflow
or timeout is a failure. A timeout has an uncertain outcome; no automatic
retry or fabricated success follows it.

Repeated requests reuse the loaded component and preserve pending operation
identities and inputs. Native window close follows the existing dismiss path.
The compositor manages the desktop window's workspace; the overlay-only
workspace lock control is hidden there. First-light setup remains guarded;
only the overlay yields to the installer terminal after its start is observed.
Initial window size leaves room for desktop bars and decorations, with a
960×640 minimum client area. Smaller displays, unusual scaling and other
compositors require separate qualification; this is not a guarantee that every
desktop can fit that minimum.

## Acceptance plan and limits

1. Validate CLI arguments, bounded IPC, versioned acknowledgment and failure
   handling, including preservation of the lifecycle lease.
2. Exercise the actual QML presentation functions and retain existing cockpit
   integrity, attempt-identity, first-light and live-view controls.
3. Load the complete QML component using the installed Quickshell binary in a
   disposable home. Exercise overlay/window switches, repeated requests,
   resize, close/reopen and setup controls. Confirm one component and unchanged
   reader identities. An offscreen probe alone cannot establish Wayland
   behavior.
4. Independently review the change. Bind retained test output, source hashes,
   host dependency identities and failures to the exact candidate.
5. Verify whichever installed path is claimed before publication. Preserve
   the marketplace release gates and report compatibility limitations.

## Retained development evidence

The local campaign is under
`/home/sicarii/Work/sia-assurance-evidence-20261019/`. Each GUI run retains its
source copies, SHA-256 roster, tool hashes, stdout, compositor replies and
fixture screenshots. These are controlled fixture data, not live memory.

| Check | Evidence and result | Boundary |
|---|---|---|
| CLI and existing cockpit contracts | `cockpit-status-wrap-regression-v1.log`: 176 tests passed on the follow-up layout repair; earlier release controls: seven passed | Python tests include mocks; source-wiring checks do not prove UI behavior |
| Complete component lifecycle | `cockpit-window-development-v12`: TESTED | Installed Quickshell, private headless Sway, minimal IPC host; switches retain actual component members, inputs and operation identity |
| Actual Omarchy loader | `cockpit-omarchy-development-v6`: TESTED | Unmodified packaged host/registry in disposable configuration; enabled candidate loaded from its normal user-plugin location |
| Actual-host controls | CLI window/repeat/overlay/window, native close/reopen, disabled-plugin refusal; initial decorated geometry inside the output | One controlled display; current user's Hyprland shell and daemon untouched |
| Geometry negatives and CLI | `cockpit-window-unit-v2.log`: 12 tests passed | Includes independent clipped-header/edge, hidden-window, parent-coordinate and invalid-workspace controls |
| Independent review | `cockpit-window-review-final.txt` and `continuity-incremental-and-cockpit-review-v1.txt`: existing GPT-6.1 reviewer found no remaining blocker within the tested scope | Follow-up review binds the layout repair to v12/v6; model-origin review is not formal proof |
| Existing CI fixture repairs | `cockpit-ci-repair-v1`: 35 tests passed with global/system Git configuration disabled | Restores early test-home isolation and supplies a command-scoped fixture identity; all assertions retained |
| Full Python suite | `cockpit-candidate-v1`: timeout, exit 124 at its 600-second limit | Incomplete; focused results do not replace full CI acceptance |

The original [checkpoint evidence](COCKPIT-WINDOW-EVIDENCE.json) is preserved.
The [layout follow-up evidence](COCKPIT-WINDOW-LAYOUT-EVIDENCE.json) binds the
later source, regression output, GUI receipts and visual inspection. The evidence records distinct tested
snapshots; their combination still requires the complete CI gate. The earlier
base CI run failed four isolation checks and three fixture Git commits; the
focused repair above does not turn that failed run into a pass.

Failures are retained. Early component probes could not use Qt's offscreen
backend for a layer-shell surface; an overlong socket path and incorrect
fixture object selection also failed. V5–v7 failed resize assertions because
the fixture conflated decorated and client geometry. The corrected oracle
checks both independently using the compositor's reported geometry. Actual-host
v1 raced asynchronous component loading; its replacement waits for a
side-effect-free invalid-mode refusal before testing the valid request.
Actual-host v2 passed its then-declared lifecycle checks but a later screenshot
review found the oversized initial window clipped its header. The visual
failure and tree are retained; v3 adds the geometry repair and a new assertion.
Review then required checking all decoration edges in the documented parent
coordinate space. V4/v5 use that stronger oracle and its negative controls.
Component v10 also exposed a test race: Close reached Sway before the reopened
window mapped. V11 observes the compositor mapping with bounded read-only
queries before sending the single Close command; it does not retry the action.

Screenshot review after actual-host v5 identified another visible defect:
the status grid clipped its long usage-count value. The follow-up bounds and
wraps count values and gives the usage label/value their own full-width rows.
Its expressions, source-admission checks and operations are unchanged.
Component v12 and actual-host v6 pass the same lifecycle/geometry controls;
the retained v6 image shows the repaired fixture counts. That image is a visual
observation for one display, not an automated all-content visibility proof.
The earlier v5 lifecycle pass remains valid within its recorded scope and
does not erase the later visual failure.

Both runners are opt-in and create a new output directory:

```sh
python3 tests/cockpit_window_smoke.py --run --output /absolute/new/component-run
python3 tests/cockpit_omarchy_smoke.py --run --output /absolute/new/host-run
```

Their child environment is allowlisted and their home, runtime directory,
compositor and configuration are disposable. UI command processes use a
refusing fixture CLI; the public presentation CLI is tested separately.
No real restore, provider call or backup is requested. These tests do not
establish OS-enforced network containment. The expected missing-Hyprland
warning under Sway is retained, not counted as zero-warning compliance.

UNPROVEN/UNRUN: live Hyprland activation, protected runtime authority, real
backend-operation reconciliation from the window, cross-version portability
and marketplace installation. Publication needs a qualified candidate,
source/version readback, live desktop lifecycle checks and the existing
release gates. A preview image or an IPC acknowledgment cannot close those
obligations.

Power of Ten adaptation: new dispatch and presentation routines have explicit
inputs, bounded response handling, short control flow and checked results.
The QML/Qt and Python runtimes allocate dynamically and do not provide proved
execution or memory bounds. The existing large QML component remains a
reviewability gap; adding a window does not establish P10 compliance, SPARK
proof of UI behavior, whole-system assurance or certification.

Primary API references:
[FloatingWindow](https://quickshell.org/docs/v0.3.0/types/Quickshell/FloatingWindow/),
[Sway IPC geometry](https://man.archlinux.org/man/sway-ipc.7.en)
and the installed Quickshell QML type declarations. The first runtime target
is this machine's Quickshell 0.3.1; other versions need qualification.
