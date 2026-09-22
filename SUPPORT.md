# Support

iProteinStudio is alpha research software for Apple-silicon Macs running macOS
14 or later. It is not a clinical or diagnostic product.

## Before reporting a problem

1. Confirm that the app is in `/Applications` and that only one current copy is
   installed.
2. Open **Engines** and check whether the required engine is installed, complete
   and current.
3. Use the in-app **Show log** action for installation failures.
4. For an interrupted campaign, use its recorded Resume action rather than
   starting a different run with the same name.

Installer logs are retained under `~/.iproteinstudio/logs/installer`. Individual
campaign folders contain their own commands, provenance and stage logs.

## “macOS GPU temporary storage is not responding”

Studio checks access to Apple's temporary GPU workspace before starting a managed
GPU job. If this message appears, save work in your applications, restart the Mac,
then use **Resume** for the stopped job. Completed results remain available.

If the message returns, report the exact error and job ID using the details below.
The job's `gpu_storage.json` records the bounded check result for support. A
persistent failure needs investigation; restarting is a first recovery step, not
a guaranteed repair. Avoid manually deleting shared Apple GPU folders while ML
applications are running. Studio does not reset those folders automatically.

## Asking for help

Use the GitHub issue tracker:

<https://github.com/t-j-fryer/iProteinStudio/issues>

Include:

- iProteinStudio version and build;
- Mac model/chip, memory and macOS version;
- workflow and selected engines;
- the exact visible error; and
- the smallest sanitized log excerpt that demonstrates the failure.

Do not attach model weights, AlphaFold 3 parameters, unpublished sequences,
confidential structures, API credentials or an entire project directory. Replace
local usernames and sensitive project names before posting logs.

Report security problems privately as described in [SECURITY.md](SECURITY.md).
