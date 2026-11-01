Error reporting
===============

The error dialog offers **Copy traceback** to copy the original, unredacted
traceback as plain text.

**Open GitHub issue…** opens an editable report preview. The unchecked diagnostic
option adds MNE system information, loaded plugins and dataset selection counts.
Custom plugins are anonymized; dataset names, paths and subject identifiers are
not collected. System-information collection does not check for updates.

Reports redact local usernames, hostnames, filesystem paths, email addresses,
IPv4 addresses and URLs. Automatic redaction cannot recognize every private
detail in exception messages or source code; relative filenames and other
identifiers may remain. Review and edit the preview before sharing it.

Confirming the preview opens a draft in the mne-nodes GitHub repository and
copies the reviewed report to the clipboard. Nothing is submitted automatically.
If the report is too long to prefill the issue, paste it from the clipboard.
Cancelling the preview does not open a browser or change the clipboard.
