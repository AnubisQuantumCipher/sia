# Installed recall and Codex timeout alignment

Status: narrow installed observation and configuration repair; whole-system
assurance and release acceptance remain incomplete.

The installed no-touch CLI query completed with exit 0 in
102.84651241602842 seconds under the existing 240-second request ceiling.
Process/lock observations first showed the CLI waiting for the daemon's corpus
lease, then holding the corpus and engine leases while gbrain ran. The returned
boundary reported live senses, passing chains, a complete graph and semantic
recall. This is one successful request, not a latency guarantee or proof that
every earlier timeout had the same cause. Retrieved memories are excluded from
this public evidence bundle.

The selected installed CLI, daemon, library, source-engine adapter and MCP
server match main source 514779ddf9ba6dcd4b5d1dafabac602910751cb3.
They are not the experimental assurance branch. These selected matches do not
establish the identity or acceptance of the complete installed runtime.

The machine's Codex SIA registration had no tool_timeout_sec field. The official
[Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
states a default of 60 seconds. The owner added only tool_timeout_sec = 240 to
the existing SIA table. Byte comparison verifies that removing that single line
reconstructs the original configuration hash. Both the standalone and desktop
bundled Codex executables read back 240. Server, proof and test budgets were not
changed; command, arguments and approval settings were preserved.

A subsequent actual connected MCP no-touch search succeeded in 4775 ms and
returned the same healthy boundary. Because that call finished within the old
default, it does not prove that the active connection reloaded its timeout or
that an MCP call lasting more than 60 seconds now succeeds. That acceptance
observation remains open. Configuration readback is not a substitute.

The installer now prints the explicit Codex timeout instruction. It still does
not write user configuration. The manual and agent skill describe the setting,
verification command and reload limitation. Whole installer shell syntax and
the extracted print function passed; all three client registration commands
were checked. The unchanged original configuration-ownership regression passed
under the existing isolated 60-second test envelope. These scoped checks do
not establish full installer, upgrade or uninstall acceptance.

The existing actual GPT-6.1 reviewer inspected the three changed files and raw
receipts, found no concrete blocker at this scope and performed no independent
execution. Its report is retained alongside the observations. An initial
measurement launch failed because /usr/bin/time was absent; no SIA request ran
in that attempt. The completed observation used Python's monotonic clock.
An initial installed-source comparison used repository paths that do not exist;
the retained corrected comparison maps installed filenames to their actual
repository names. Neither preliminary failure is treated as SIA failure.

Next: verify the effective client deadline through a supported connection
lifecycle, address measured contention/search costs without bypassing leases,
and continue all original proof, continuity, workload and installed lifecycle
gates. R05 remains unresolved. No universal recall, capture, compaction or
avionics assurance claim follows, and no release or marketplace update is
accepted by this checkpoint.
