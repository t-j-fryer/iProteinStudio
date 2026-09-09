#!/usr/bin/env python3
"""Stage an upstream refresh for review; apply only checksum-approved copies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(upstream, repo=REPO):
    vendor = repo / "Sources/iProteinStudio/Resources/pipeline"
    manifest = json.loads((repo / "tools/pipeline-vendor-manifest.json").read_text())
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(upstream), "status", "--porcelain"], text=True).strip())
    (repo / "build").mkdir(exist_ok=True)
    review = Path(tempfile.mkdtemp(prefix="vendor-review-", dir=repo / "build"))
    files = {}
    for relative, rule in manifest["files"].items():
        source, destination = upstream / relative, vendor / relative
        if not source.is_file():
            raise ValueError("Required upstream file is missing: " + relative)
        copied = review / "files" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copied)
        files[relative] = {"before": digest(destination), "incoming": digest(copied),
                           "policy": rule["policy"], "baseline": rule["studio_sha256"]}
    report = {"schema": 1, "upstream_revision": revision, "upstream_dirty": dirty,
              "manifest_sha256": digest(repo / "tools/pipeline-vendor-manifest.json"), "files": files}
    (review / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    return review


def apply(review, repo=REPO):
    report = json.loads((review / "review.json").read_text())
    manifest_path = repo / "tools/pipeline-vendor-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    vendor = repo / "Sources/iProteinStudio/Resources/pipeline"
    if report["manifest_sha256"] != digest(manifest_path) or set(report["files"]) != set(manifest["files"]):
        raise ValueError("Vendor ownership changed; stage a new review.")
    changes = []
    # Validate the entire change before writing any destination. Policies come
    # from the tracked manifest, never editable review metadata.
    for relative, item in report["files"].items():
        incoming, destination = review / "files" / relative, vendor / relative
        if digest(destination) != item["before"] or digest(incoming) != item["incoming"]:
            raise ValueError("File changed after review: " + relative)
        rule = manifest["files"][relative]
        if item["incoming"] == item["before"]:
            continue
        if rule["policy"] == "manual-merge" or item["before"] != rule["studio_sha256"]:
            raise ValueError("Preserve Studio changes by manually merging " + relative + "; automatic replacement refused.")
        changes.append((relative, incoming, destination))
    # Back up the whole set first, then roll back already-replaced files if an
    # I/O failure interrupts application. The review retains the original bytes.
    originals = {destination: review / "before" / relative for relative, _, destination in changes}
    for relative, _, destination in changes:
        backup = review / "before" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, backup)
    replaced = []
    try:
        for relative, incoming, destination in changes:
            temporary = destination.with_name(destination.name + ".vendor-stage")
            shutil.copy2(incoming, temporary)
            temporary.replace(destination)
            replaced.append(destination)
            manifest["files"][relative]["studio_sha256"] = digest(destination)
        manifest["last_reviewed_upstream_revision"] = report["upstream_revision"]
        manifest["last_reviewed_upstream_dirty"] = report["upstream_dirty"]
        temporary = manifest_path.with_suffix(".json.vendor-stage")
        temporary.write_text(json.dumps(manifest, indent=2) + "\n")
        temporary.replace(manifest_path)
    except OSError:
        for destination in reversed(replaced):
            temporary = destination.with_name(destination.name + ".vendor-rollback")
            shutil.copy2(originals[destination], temporary)
            temporary.replace(destination)
        raise
    return len(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", nargs="?", type=Path)
    parser.add_argument("--apply", type=Path, metavar="REVIEW_DIRECTORY")
    args = parser.parse_args()
    try:
        if args.apply:
            print(json.dumps({"applied_files": apply(args.apply.resolve())}))
        elif args.upstream:
            print(json.dumps({"review": str(stage(args.upstream.resolve())),
                              "next": "Inspect review.json and files. The runner requires a manual merge; run contract tests after integration."}))
        else:
            parser.error("Supply the upstream checkout path, or --apply with a reviewed staging directory.")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
