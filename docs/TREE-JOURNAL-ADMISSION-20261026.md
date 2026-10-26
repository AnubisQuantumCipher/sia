# Tree-CAS journal admission repair

The installer and uninstaller opened their recovery journal before checking
that its descriptor described a regular file. A journal replaced by a FIFO
without a writer could therefore block before that check. Both journal opens
now include `O_NONBLOCK`; their existing descriptor admission, recovery,
generation, rename and durability logic is retained. Three existing exception
handlers also preserve their explicit cause, resolving the complete helpers'
three inherited B904 findings under the unchanged frozen analyzer profile.

The private baseline reproduced two three-second FIFO timeouts, one per helper.
Both direct children were killed and reaped with return code -9. The other ten
baseline methods passed. Fourteen candidate methods pass, covering regular and
absent journals, native no-writer FIFOs, symlinks, directories, malformed JSON
and invalid schema for both complete extracted helpers. The two schema methods
were added after the baseline; no baseline execution of them is claimed.

All sixteen candidate child records retain actual reaped results without a
timeout. Final snapshots match the declared effects: existing lock bookkeeping,
creation of an absent lock, and retirement of a valid recovery journal. Target,
member, source, stage, archive, backup and link-target snapshots remain unchanged.
A later readback found every recorded private fixture root absent. These final
snapshots do not establish absence of transient writes, arbitrary descendant
custody, or installed-state qualification.

Seven unchanged original recovery, race, symlink, mode and isolation methods
pass. The complete updated CI static step passes locally with empty diagnostics;
both complete tree-CAS heredocs and the new test now participate in the frozen
profile and suppression scan. Fifteen private extraction controls pass. The
first observer attempt expected the wrong refusal for oversized installer input:
the earlier corpus guard correctly rejected it. That failed attempt is retained;
the observer's expected refusal and generated-file expectations were corrected,
with new receipt filenames; product code was unchanged. Both shell syntax checks and the
patch whitespace check pass. Full hosted CI is not claimed to pass.

Evidence remains under
`/home/sicarii/Work/sia-assurance-evidence-20261019/ownership-transfer-20261024/r13-tree-journal-admission-20261026-v1`.
`EVIDENCE-AUDIT.json` SHA256 is
`381562b6dfecaf0f60a74222fb9bdd39589fd1d879820bacd5be554a73eb6bee`.
Actual GPT-6.1 independently reviewed the exact production, test and CI sources
and baseline receipts with no unresolved finding. Its source-review receipt is
in the sibling `r13-tree-journal-review-20261026-v1` directory;
`INDEPENDENT-REVIEW.json` SHA256 is
`085d251c20706e460da9dfcd877064a6bccb88806557d8ad4c8b44092fcd4e25`.
That source disposition does not claim a second execution of the candidate.

This is a scoped tested repair. The complete reader inventory, R13/R40,
R05 BOTH, whole-project proof, native custody, actual compaction, judge,
installed composition, recovery and release gates remain open. The interrupted
proof remains interrupted; this change grants no proof replay or successor
authority. A new proof still requires qualified aggregate storage containment,
capacity and exact source/tool/custody admission.
