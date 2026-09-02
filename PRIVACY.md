# Privacy

Last updated: 1 September 2026

iProteinStudio is a local macOS application. It has no user account, advertising,
analytics SDK or application telemetry. Protein structures, design campaigns,
alignments, logs and installed engines are stored on the user's Mac.

## Information stored locally

Studio writes its managed runtime and user work under `~/.iproteinstudio`,
including:

- workspaces, sequences, structures and result tables;
- saved and generated MSAs;
- model environments and explicitly selected checkpoints;
- resumable download data, installation receipts and installer logs; and
- run commands, provenance and failure logs needed to reproduce or resume work.

Deleting `iProteinStudio.app` does not delete this directory. Engine removal in
the app does not remove projects, results or alignments.

## When information leaves the Mac

Network access is used only for user-visible functionality:

- **Installation:** source code, packages, chemical reference data and selected
  model checkpoints are downloaded from their documented upstream hosts.
- **MSA generation:** when the user requests a remote alignment and no valid
  cached alignment exists, the relevant protein sequence is sent to the
  selected ColabFold or Protenix-operated MSA service. Protein sequences may be
  confidential; users should choose explicit single-sequence/offline behavior
  or provide an existing MSA when remote disclosure is unacceptable.
- **Ligand/PDB evidence:** a ligand identity or structure query may be sent to
  RCSB PDB services when the user requests experimental matches.
- **Application updates:** trusted beta and future Developer ID-signed builds may
  contact the HTTPS Sparkle feed according to the user's update preferences.
  Users can disable automatic checks and automatic downloads in Settings.

iProteinStudio does not control the retention or logging policies of those
external providers. Their terms and privacy policies apply to data sent to them.

## What is not uploaded by Studio

Studio does not intentionally upload complete project directories, prediction
outputs, structures, metrics, local paths or installer logs to the project
maintainers. There is no automatic crash-reporting service. Data is shared with
the maintainers only if the user deliberately attaches it to a support report.

## Support and sensitive research

Before sharing a log or issue, remove unpublished sequences, structures, project
names, local usernames and other confidential information. Security reports
should use the private route described in [SECURITY.md](SECURITY.md).

This document describes iProteinStudio's own behavior. Optional scientific
engines and services remain subject to their upstream policies.
