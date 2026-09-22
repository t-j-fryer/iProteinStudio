"""Durable operation receipts around the upstream ligand-NISE science.

The search can be replayed from the beginning: completed sampling and folding
operations return their audited on-disk results. This also recovers Phase 0,
empty cycles and patience exactly, without treating an incomplete CSV as state.
"""
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def input_digest(directory):
    h = hashlib.sha256()
    for path in sorted(Path(directory).glob("*.yaml")):
        h.update(path.name.encode()); h.update(b"\0")
        h.update(path.read_bytes()); h.update(b"\0")
    return h.hexdigest()


class Journal:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def load(self, path, specification):
        if not path.exists():
            return None
        saved = json.loads(path.read_text())
        if saved["input"] != specification:
            raise RuntimeError(f"Saved NISE inputs changed: {path}")
        for name, checksum in saved["files"].items():
            artifact = self.root / name
            if not artifact.is_file() or digest(artifact) != checksum:
                raise RuntimeError(f"Completed NISE artifact is missing or changed: {artifact}")
        return saved["result"]

    def save(self, path, specification, result, files=()):
        atomic(path, {"schema": 1, "input": specification, "result": result,
                      "files": {str(Path(p).resolve().relative_to(self.root)): digest(p) for p in files}})


class ResidentClient:
    worker_script = "resident_predictor.py"
    def __init__(self, root, output, scripts, seed, potentials, allow_affinity):
        self.queue = Path(output) / "sessions" / uuid.uuid4().hex
        self.queue.mkdir(parents=True)
        self.log = self.queue / "worker.log"
        config = dict(root=str(root), engine="boltz", model="boltz2", queue=str(self.queue),
                      owner_pid=os.getpid(), use_potentials=potentials, allow_affinity=allow_affinity,
                      engine_args=["--accelerator", "gpu", "--devices", "1", "--num_workers", "0",
                                   "--output_format", "pdb", "--cache", str(root / "models/boltz2"),
                                   "--seed", str(seed)])
        self.config = self.queue / "config.json"
        atomic(self.config, config)
        env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="0", BOLTZ_CACHE=str(root / "models/boltz2"))
        self.stream = self.log.open("w")
        self.process = subprocess.Popen([str(root / "venvs/NanoHunter_boltz/bin/python"),
                                         str(scripts / self.worker_script), "--config", str(self.config)],
                                        stdout=self.stream, stderr=subprocess.STDOUT, env=env)
        self.loaded_affinity = False
        try:
            self.ready = self.wait(self.queue / "ready.json")
            if (self.ready.get("device") != "mps" or self.ready.get("fallback") != 0
                    or self.ready.get("model_load_count") != 1
                    or self.ready.get("pid") != self.process.pid
                    or self.ready.get("config_sha256") != digest(self.config)):
                raise RuntimeError("Invalid NISE resident-worker readiness receipt")
        except BaseException:
            self.close()
            raise

    def wait(self, path):
        deadline = time.monotonic() + 1800
        while not path.exists():
            if self.process.poll() is not None:
                raise RuntimeError(f"NISE predictor exited; see {self.log}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"NISE predictor timed out; see {self.log}")
            time.sleep(0.1)
        return json.loads(path.read_text())

    def predict(self, source, output, affinity, phase="complete", prediction_seed=None):
        identifier = uuid.uuid4().hex
        name = "request_" + identifier + ".json"
        checksum = input_digest(source)
        atomic(self.queue / "requests" / name, dict(request_id=identifier,
               input_dir=str(source), output_dir=str(output), expected_jobs=1, input_sha256=checksum, phase=phase, prediction_seed=prediction_seed))
        receipt = self.wait(self.queue / "responses" / name)
        if prediction_seed is not None and receipt.get("prediction_seed") != prediction_seed:
            raise RuntimeError("NISE prediction returned the wrong sampling seed")
        expected_loads = 2 if affinity or self.loaded_affinity else 1
        if (not receipt.get("ok") or receipt.get("request_id") != identifier
                or receipt.get("input_sha256") != checksum or receipt.get("completed_jobs") != 1
                or receipt.get("model_load_count") != expected_loads
                or (phase != "complete" and receipt.get("phase") != phase)):
            raise RuntimeError(f"NISE prediction failed: {receipt.get('error', 'invalid receipt')}; see {self.log}")
        self.loaded_affinity = self.loaded_affinity or affinity
        return {**receipt, "session": str(self.queue), "startup_seconds": self.ready["startup_seconds"]}

    def close(self):
        if self.process.poll() is None:
            atomic(self.queue / "stop.json", {})
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait()
        self.stream.close()


class Backend:
    def __init__(self, root, output, settings, scripts):
        import nise_lib
        self.science = nise_lib
        self.root, self.output, self.scripts = Path(root), Path(output), Path(scripts)
        self.settings = settings
        self.journal = Journal(output)
        self.worker = None
        self.nesso_worker = None
        self.nesso_scores = {}
        self.ligand_manifest = None
        self.atom_checks = {}
        self.geometry_executor = None

    def close(self):
        if self.geometry_executor is not None:
            self.geometry_executor.close(); self.geometry_executor = None
        if self.nesso_worker is not None:
            self.nesso_worker.close(); self.nesso_worker = None
        if self.worker is not None:
            self.worker.close(); self.worker = None

    def freeze_config(self, cfg):
        path = self.output / "config.json"
        if path.exists() and self.settings.get("search_policy_version") == 1:
            prior = json.loads(path.read_text())
            # Old requests use the historical exhaustive policy. Preserve their
            # original config rather than injecting newly added disabled flags.
            additions = {"early_score_gate": 0.0, "selective_affinity": False,
                         "adaptive_proposals": False, "initial_proposals": 16,
                         "affinity_batch_size": 8}
            cfg = {k: v for k, v in cfg.items() if k in prior or k not in additions or v != additions[k]}
        if path.exists() and self.settings.get("search_policy_version", 1) < 3:
            prior = json.loads(path.read_text())
            additions = dict(first_cycle_seqs=cfg.get("nise_seqs"), partial_noising=False,
                             noise_radius=6.0, noise_percent=25.0, noise_predictions=32,
                             noise_mpnn_seqs=32, noise_advance=1)
            cfg = {k: v for k, v in cfg.items() if k in prior or k not in additions or v != additions[k]}
        if path.exists() and json.loads(path.read_text()) != cfg:
            raise RuntimeError("Saved scientific settings differ from this NISE request")
        if not path.exists():
            atomic(path, cfg)

    def atom_manifest(self, smiles=None):
        if self.ligand_manifest is None:
            from ligand_atoms import resolve, validate_selection
            self.ligand_manifest = resolve(self.settings.get("smiles") or smiles)
            validate_selection(self.settings, self.ligand_manifest)
        return self.ligand_manifest

    def initial_contacts(self, smiles, count):
        from ligand_atoms import contact_atoms
        manifest = self.atom_manifest(smiles)
        excluded = list(self.settings.get("exposed_atoms", []))
        if self.settings.get("exposure_mode") == "biotin-carboxamide-v1":
            from biotin_exit import roles
            terminal = roles(manifest)
            excluded += [terminal[k] for k in ("carbonyl", "oxygen", "leaving")]
        return self.settings.get("hotspot_atoms") or contact_atoms(manifest, count, excluded)

    def check_atom_requirements_batch(self, predictions):
        if (not self.settings.get("hotspot_atoms") and not self.settings.get("exposed_atoms")
                and self.settings.get("exposure_mode", "sasa") == "sasa"):
            return {name: True for name in predictions}
        # Preserve the lightweight legacy route. The new exit calculations use
        # reusable CPU processes, per-structure receipts and bounded memory.
        if self.settings.get("exposure_mode", "sasa") == "sasa":
            from atom_geometry import measure
            results = {name: measure(pred.pdb, self.settings, self.atom_manifest())
                       for name, pred in predictions.items()}
        else:
            from geometry_runtime import GeometryExecutor
            if self.geometry_executor is None:
                self.geometry_executor = GeometryExecutor(self.output, self.settings, self.atom_manifest())
            results = self.geometry_executor.check(predictions)
        self.atom_checks.update(results)
        return {name: result["passed"] for name,result in results.items()}

    def check_atom_requirements(self, prediction):
        return self.check_atom_requirements_batch({prediction.name: prediction})[prediction.name]

    def initial_backbones(self, smiles, directory, args):
        from rfd3_initial import generate
        # An initial generator owns the GPU before either folding/screening model.
        self.close()
        return generate(self, smiles, Path(directory))

    def design(self, pdb, directory, n, smiles, args, seq_temp, fs_temp, seed, designed, constrain_ss):
        directory = Path(directory)
        spec = dict(pdb_sha256=digest(pdb), count=n, smiles=smiles, seq_temp=seq_temp,
                    fs_temp=fs_temp, seed=seed, designed=designed, constrain_ss=constrain_ss,
                    fs_distance=args.fs_distance, ala_budget=args.ala_budget, gly_budget=args.gly_budget)
        receipt = directory / "sampling.json"
        saved = self.journal.load(receipt, spec)
        if saved is not None:
            return saved
        pairs = self.science.lasermpnn_design(pdb, directory, n, smiles, seq_temp=seq_temp,
                  fs_temp=fs_temp, fs_distance=args.fs_distance, ala_budget=args.ala_budget,
                  gly_budget=args.gly_budget, constrain_ss=constrain_ss, designed=designed,
                  device="cpu", seed=seed)
        sequences = [s for s, _ in pairs]
        if len(sequences) != n or any(not re.fullmatch("[ACDEFGHIKLMNPQRSTVWY]+", s) for s in sequences):
            raise RuntimeError("LASErMPNN returned invalid sequences or the wrong number of designs")
        self.journal.save(receipt, spec, sequences, [directory / "designs/designs.fasta"])
        return sequences

    def screen_initial(self, sequences, smiles, directory, owners, stage):
        if not self.settings.get("phase0_nesso_screen"):
            return sequences
        from nesso_screen import screen
        if stage == "refinement":
            count, total = self.settings["phase0_nesso_refine_top_k"], None
        elif stage == "expansion":
            count, total = 1, self.settings["phase0_nesso_expand_top_k"]
        else:
            raise ValueError("Initial NESSO screening is supported only in refinement and expansion")
        return screen(self, sequences, smiles, directory, owners=owners, per_lineage=count, total=total)

    def fold(self, sequences, smiles, directory, args, pocket=None, apo=False):
        import preorg
        from types import SimpleNamespace
        directory = Path(directory)
        predictions = {}
        phase = "complete" if apo else getattr(args, "boltz_phase", "complete")
        if self.settings.get("nesso_screen") and not getattr(args, "skip_nesso", False) and not apo and sequences and all(
                re.fullmatch(r"c\d+_t\d+_n\d+_s\d+", name) for name in sequences):
            from nesso_screen import screen
            sequences = screen(self, sequences, smiles, directory.parent / "nesso",
                               allow_empty=self.settings.get("adaptive_proposals", False) or self.settings.get("partial_noising", False))
        try:
            for name, sequence in sequences.items():
                unit = directory / name
                unit.mkdir(parents=True, exist_ok=True)
                source, out = unit / "yaml", unit / "out"
                source.mkdir(exist_ok=True)
                yaml = source / (name + ".yaml")
                spec = dict(sequence=sequence, smiles=None if apo else smiles, pocket=pocket,
                            affinity=not apo, seed=args.seed, potentials=False if apo else args.use_potentials)
                seed_override = getattr(args, "prediction_seeds", {}).get(name)
                if seed_override is not None:
                    spec["seed"] = seed_override
                    spec["prediction_seed"] = seed_override
                if phase != "complete":
                    spec["phase"] = phase
                receipt_path = unit / "completed.json"
                saved = self.journal.load(receipt_path, spec)
                if saved is not None:
                    if not apo:
                        from ligand_atoms import audit_atoms
                        audit_atoms(saved["prediction"]["pdb"], self.atom_manifest(smiles))
                    predictions[name] = SimpleNamespace(**saved["prediction"])
                    continue
                if apo:
                    preorg.write_apo_yaml(yaml, sequence)
                else:
                    self.science.write_boltz_yaml(yaml, sequence, smiles, affinity=True, pocket=pocket)
                if self.worker is None:
                    self.worker = ResidentClient(self.root, self.output, self.scripts, args.seed,
                                                 not apo and args.use_potentials, not apo)
                seed_options = {"prediction_seed": seed_override} if seed_override is not None else {}
                timing = (self.worker.predict(source, out, False, phase="structure", **seed_options) if phase == "structure"
                          else self.worker.predict(source, out, not apo, **seed_options))
                pred = self.science.parse_prediction(out, name)
                if pred is None:
                    raise RuntimeError(f"Missing prediction for {name}")
                if phase == "structure":
                    pred.pbind = None
                if not apo and phase == "complete":
                    self.science.rank_score(pred, "ligand_plddt+pbind")
                self.audit_structure(pred.pdb, sequence, not apo)
                if not apo:
                    from ligand_atoms import audit_atoms
                    audit_atoms(pred.pdb, self.atom_manifest(smiles))
                files = [yaml] + sorted((Path(pred.pdb).parent).glob("*.json")) + [Path(pred.pdb)]
                if phase == "structure":
                    # Bind every input needed by the later affinity head.
                    files = [yaml] + sorted(p for p in out.rglob("*") if p.is_file()
                                           and not p.name.startswith("affinity_"))
                values = {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                          for k, v in asdict(pred).items()}
                self.journal.save(receipt_path, spec, dict(prediction=values, timing=timing), files)
                predictions[name] = pred
                atomic(self.output / "progress.json", dict(message=f"Completed {name}", scheduler=self.settings["scheduler"]))
                print(f"NISE|completed|{name}", flush=True)
        finally:
            if self.settings["scheduler"] == "cycle-wave" and phase != "structure":
                self.close()
        return predictions

    def affinity(self, predictions, directory, args):
        """Evaluate only the affinity head on verified structure-stage artifacts."""
        from types import SimpleNamespace
        result = {}
        for name, prediction in predictions.items():
            unit = Path(directory) / name
            structure_receipt = unit / "completed.json"
            saved = json.loads(structure_receipt.read_text())
            if saved["input"].get("phase") != "structure":
                raise RuntimeError("Selective affinity requires a structure-stage receipt")
            self.journal.load(structure_receipt, saved["input"])
            spec = dict(structure_receipt_sha256=digest(structure_receipt))
            receipt = unit / "affinity_completed.json"
            scored = self.journal.load(receipt, spec)
            if scored is None:
                if self.worker is None:
                    self.worker = ResidentClient(self.root, self.output, self.scripts, args.seed,
                                                 args.use_potentials, True)
                seed_options = {"prediction_seed": saved["input"]["prediction_seed"]} if "prediction_seed" in saved["input"] else {}
                timing = self.worker.predict(unit / "yaml", unit / "out", True, phase="affinity", **seed_options)
                pred = self.science.parse_prediction(unit / "out", name)
                self.science.rank_score(pred, "ligand_plddt+pbind")
                self.journal.load(structure_receipt, saved["input"])
                values = dict(saved["result"]["prediction"], pbind=pred.pbind)
                scored = dict(prediction=values, timing=timing)
                self.journal.save(receipt, spec, scored,
                                  [Path(pred.pdb).parent / f"affinity_{name}.json"])
            result[name] = SimpleNamespace(**scored["prediction"])
            atomic(self.output / "progress.json", dict(message=f"Affinity scored {name}"))
        return result

    def finish_scoring_stage(self):
        if self.settings["scheduler"] == "cycle-wave":
            self.close()

    @staticmethod
    def audit_structure(path, sequence, ligand):
        import gemmi
        structure = gemmi.read_structure(str(path))
        model = structure[0]
        chain = model.find_chain("A")
        if chain is None:
            raise RuntimeError("NISE prediction has no binder chain A")
        residues = [r for r in chain if r.find_atom("CA", "*")]
        observed = "".join(gemmi.find_tabulated_residue(r.name).one_letter_code.upper() for r in residues)
        if len(observed) != len(sequence) or any(a != "X" and a != b for a, b in zip(sequence, observed)):
            raise RuntimeError("NISE prediction sequence does not match its saved input")
        if ligand and model.find_chain("B") is None:
            raise RuntimeError("NISE prediction has no ligand chain B")
        if any(not all(math.isfinite(v) for v in (a.pos.x, a.pos.y, a.pos.z))
               for c in model for r in c for a in r):
            raise RuntimeError("Non-finite coordinates in NISE prediction")

    def record_candidate(self, node, passed, prediction):
        row = asdict(node)
        match = re.search(r"_t(\d+)_", node.name)
        row["trajectory"] = int(match.group(1)) if match else None
        row["intermediate_passed"] = passed if row.get("branch") == "masked-backbone" else None
        row["passed"] = passed and row.get("branch") != "masked-backbone"
        row["final_eligible"] = row["passed"] and re.fullmatch("[ACDEFGHIKLMNPQRSTVWY]+", node.sequence) is not None
        if node.name in getattr(self, "atom_checks", {}):
            row["atom_checks"] = self.atom_checks[node.name]
        if node.name in getattr(self, "nesso_scores", {}):
            row[self.nesso_scores[node.name].get("engine", "nesso")] = self.nesso_scores[node.name]
        row["pdb"] = str(Path(node.pdb).resolve().relative_to(self.output.resolve()))
        row["ref_pdb"] = str(Path(node.ref_pdb).resolve().relative_to(self.output.resolve()))
        atomic(self.output / "candidates" / (node.name + ".json"), row)

    def record_advancement(self, cycle, trajectories):
        atomic(self.output / f"cycle{cycle:02d}" / "advancement.json", {
            "beam": self.settings["beam"], "selection": "Reserved normal/noising places after Boltz scoring and self-consistency" if self.settings.get("partial_noising") and cycle >= 2 else "Boltz combined score after self-consistency",
            "trajectories": [dict(trajectory=t["tid"], alive=t["alive"], no_improve=t["no_improve"],
                selected=[n.name for n in t["current"]] if t["alive"] else [],
                current_beam=[asdict(n) for n in t["current"]],
                best_node=asdict(t["best_node"]),
                last_improving_beam=[asdict(n) for n in t.get("best_beam", [t["best_node"]])],
                structure_sha256={n.pdb: digest(n.pdb) for n in
                    t["current"] + t.get("best_beam", []) + [t["best_node"]]}) for t in trajectories],
            "rollback": False, "rescue": False})

    def write_summary(self, summary):
        folds = [json.loads(p.read_text()) for p in self.output.rglob("completed.json")
                 if p.parent.parent.name in {"fold", "cycle00"}]
        affinity = list(self.output.rglob("affinity_completed.json"))
        sampling = [json.loads(p.read_text()) for p in self.output.rglob("sampling.json")]
        cost = dict(structure_evaluations=len(folds),
                    affinity_evaluations=len(affinity) + sum(
                        r["input"].get("affinity", False) and r["input"].get("phase", "complete") == "complete"
                        for r in folds),
                    sampled_sequences=sum(len(r["result"]) for r in sampling),
                    interpretation="Completed unique operations, including reused receipts; not a speed benchmark.",
                    rollback=False, rescue=False)
        atomic(self.output / "search_cost.json", cost)
        summary["evaluation_cost"] = cost
        atomic(self.output / "search_summary.json", summary)
        self.write_atom_report()

    def write_atom_report(self):
        if self.settings.get("hotspot_atoms") or self.settings.get("exposed_atoms") or self.settings.get("exposure_mode", "sasa") != "sasa":
            import csv, io
            table = io.StringIO()
            writer = csv.writer(table)
            writer.writerow(["candidate", "cycle", "passed_all_checks", "atom_checks_passed", "failures", "hotspot_distances_A", "exposure", "linker_exit"])
            for path in sorted((self.output / "candidates").glob("*.json")):
                row = json.loads(path.read_text()); checks = row.get("atom_checks", {})
                writer.writerow([row["name"], row["cycle"], row["passed"], checks.get("passed"),
                                 "; ".join(checks.get("failures", [])), json.dumps(checks.get("hotspot_distance_a", {})),
                                 json.dumps(checks.get("exposure", {})), json.dumps(checks.get("linker_exit"))])
            target = self.output / "atom_checks.csv"
            temporary = target.with_suffix(".csv.part")
            temporary.write_text(table.getvalue()); temporary.replace(target)

    def preorganisation(self, args):
        import metrics
        import preorg
        self.close()  # Apo has no affinity, pocket restraint or steering.
        rows = [json.loads(p.read_text()) for p in (self.output / "candidates").glob("*.json")]
        candidates = sorted((r for r in rows if r["passed"] and r["trajectory"] is not None and r.get("branch") != "masked-backbone" and r.get("score") is not None and re.fullmatch("[ACDEFGHIKLMNPQRSTVWY]+", r["sequence"])),
                            key=lambda r: (-r["score"], r["name"]))[:self.settings["top_x"]]
        if not candidates:
            atomic(self.output / "preorg.json", dict(ranked=[], shortlist=[], status="no_candidates"))
            return
        apo = self.fold({r["name"]: r["sequence"] for r in candidates}, None,
                        self.output / "preorganisation", args, apo=True)
        ranked = []
        for row in candidates:
            name = row["name"]
            holo = self.output / row["pdb"]
            pocket = metrics.pocket_residues(holo)
            pre = metrics.preorganisation(holo, apo[name].pdb, pocket)
            if not math.isfinite(pre.preorg_rmsd) or not math.isfinite(pre.global_ca_rmsd):
                raise RuntimeError(f"Preorganisation could not be measured for {name}")
            score, pterm, fterm = preorg.combine(row["score"], pre)
            ranked.append(dict(name=name, base_score=row["score"], combined_score=score,
                               preorg_rmsd=pre.preorg_rmsd, global_ca_rmsd=pre.global_ca_rmsd,
                               pocket_displacement=pre.pocket_displacement if math.isfinite(pre.pocket_displacement) else None,
                               apo_pdb=str(Path(apo[name].pdb).relative_to(self.output)),
                               holo_pdb=row["pdb"], preorg_term=pterm, fold_term=fterm))
        atomic(self.output / "preorg.json", dict(ranked=sorted(ranked, key=lambda r: -r["combined_score"]),
               shortlist=[r["name"] for r in candidates], status="completed",
               scope="Final shortlist only; search objective unchanged", weights=dict(preorg=0.5, fold=0.25)))
