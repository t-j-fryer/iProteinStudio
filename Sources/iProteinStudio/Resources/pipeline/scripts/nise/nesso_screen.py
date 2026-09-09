"""Durable screening adapter; NESSO never replaces a Boltz search score."""
import csv
import json
import os
from pathlib import Path
import subprocess
import uuid

from nesso_contract import installation, shortlist, shortlist_by_lineage, validate_scores, placement_score, RANKING_POLICY
from runtime import ResidentClient, atomic, digest


class NessoClient(ResidentClient):
    def __init__(self, root, output, scripts, seed):
        self.queue = Path(output) / 'sessions' / ('nesso-' + uuid.uuid4().hex)
        self.queue.mkdir(parents=True)
        self.log = self.queue / 'worker.log'
        self.config = self.queue / 'config.json'
        atomic(self.config, dict(root=str(root), output=str(output), queue=str(self.queue), seed=seed, owner_pid=os.getpid()))
        self.stream = self.log.open('w')
        env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK='0', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        self.process = subprocess.Popen([str(installation(root) / 'venv/bin/python'),
            str(Path(scripts) / 'nise/nesso_worker.py'), '--config', str(self.config)], env=env,
            stdout=self.stream, stderr=subprocess.STDOUT)
        try:
            self.ready = self.wait(self.queue / 'ready.json')
            if (self.ready.get('device') != 'mps' or self.ready.get('fallback') != 0
                    or self.ready.get('model_load_count') != 2 or self.ready.get('pid') != self.process.pid
                    or self.ready.get('config_sha256') != digest(self.config)):
                raise RuntimeError('Invalid NESSO readiness receipt')
        except BaseException:
            self.close()
            raise

    def score(self, sequence, smiles, directory):
        identifier = uuid.uuid4().hex
        request = self.queue / 'requests' / ('request_' + identifier + '.json')
        atomic(request, dict(request_id=identifier, sequence=sequence, smiles=smiles, directory=str(directory)))
        reply = self.wait(self.queue / 'responses' / request.name)
        if (not reply.get('ok') or reply.get('request_id') != identifier or reply.get('input_sha256') != digest(request)):
            raise RuntimeError(f"NESSO screening failed: {reply.get('error', 'invalid receipt')}; see {self.log}")
        result = reply['result']
        if (result.get('device') != 'mps' or result.get('precision') != 'float32'
                or result.get('recycling_steps') != 5 or result.get('refine_protein_inference') is not True
                or result.get('model_load_count') != 2):
            raise RuntimeError('Invalid NESSO model execution receipt')
        validate_scores(result['scores'])
        return {**result, 'session': str(self.queue), 'startup_seconds': self.ready['startup_seconds']}


def screen(backend, sequences, smiles, directory, *, owners=None, per_lineage=None, total=None):
    directory = Path(directory)
    scores = {}
    try:
        for name, sequence in sequences.items():
            unit = directory / name
            spec = dict(sequence=sequence, smiles=smiles, seed=backend.settings['seed'],
                        protocol='nesso-v1.0.0-mps-float32-refined-5',
                        installation_sha256=digest(installation(backend.root) / 'receipt.json'))
            receipt = unit / 'completed.json'
            saved = backend.journal.load(receipt, spec)
            if saved is None:
                if backend.nesso_worker is None:
                    backend.nesso_worker = NessoClient(backend.root, backend.output, backend.scripts, backend.settings['seed'])
                saved = backend.nesso_worker.score(sequence, smiles, unit)
                files = [p for p in unit.rglob('*') if p.is_file() and p.name != 'completed.json']
                backend.journal.save(receipt, spec, saved, files)
            scores[name] = validate_scores(saved['scores'])
            backend.nesso_scores[name] = {**scores[name], "screening_score": placement_score(scores[name])["score"],
                                          "ranking_policy": dict(RANKING_POLICY)}
            atomic(backend.output / 'progress.json', dict(message=f'NESSO screened {name}'))
        count = backend.settings['nesso_top_k'] if owners is None else per_lineage
        selected = (shortlist(sequences, scores, count) if owners is None else
                    shortlist_by_lineage(sequences, scores, owners, count, total))
        spec = dict(sequences=sequences, scores=scores, top_k=count,
                    ranking=dict(RANKING_POLICY),
                    assessments={name: placement_score(values) for name, values in scores.items()})
        if owners is not None:
            spec.update(owners=owners, total=total, selection='per-original-lineage-v1')
        receipt = directory / 'selection.json'
        prior = backend.journal.load(receipt, spec)
        if prior is None:
            backend.journal.save(receipt, spec, selected, [directory / name / 'completed.json' for name in sequences])
        elif prior != selected:
            raise RuntimeError('NESSO selection differs from its saved shortlist')
        write_report(backend.output)
        if sequences and not selected:
            raise RuntimeError("NESSO rejected every candidate: no valid protein-ligand placement entropy. "
                               "Inspect nesso_screening.csv and the saved affinity.json outputs; no Boltz fallback was used.")
        return {name: sequences[name] for name in selected}
    finally:
        if backend.settings['scheduler'] == 'cycle-wave' and backend.nesso_worker is not None:
            backend.nesso_worker.close(); backend.nesso_worker = None


def write_report(output):
    """A derived, portable table includes candidates that never received a fold."""
    output = Path(output)
    destination = output / "nesso_screening.csv"
    with destination.with_suffix(".csv.part").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["candidate", "stage", "cycle", "trajectory", "lineage", "sequence",
            "selected_for_boltz", "nesso_pbind", "nesso_affinity_log10_ic50_um",
            "nesso_placement_entropy", "nesso_screening_score", "nesso_eligible", "nesso_rejection_reason", "nesso_ranking_policy"])
        writer.writeheader()
        import re
        for path in sorted([*output.glob("cycle*/nesso/selection.json"), *output.glob("phase0/cycle*/nesso/selection.json")]):
            saved = json.loads(path.read_text())
            for name, seq in saved["input"]["sequences"].items():
                match = re.fullmatch(r"c(\d+)_t(\d+)_n\d+_s\d+", name)
                values = saved["input"]["scores"][name]
                assessment = saved["input"].get("assessments", {}).get(name)
                # Never relabel a historical probability-only selection as the new score.
                policy = saved["input"]["ranking"]
                initial = path.relative_to(output).parts[0] == "phase0"
                if not initial and match is None:
                    raise ValueError("Invalid optimization screening identity: " + name)
                writer.writerow(dict(candidate=name, stage="initial" if initial else "optimization",
                    cycle=int(path.parent.parent.name.removeprefix("cycle")),
                    trajectory="" if initial else int(match[2])+1,
                    lineage=saved["input"].get("owners", {}).get(name, ""),
                    sequence=seq, selected_for_boltz=name in saved["result"],
                    nesso_pbind=values["affinity_probability_binary"],
                    nesso_affinity_log10_ic50_um=values["affinity_pred_value"],
                    nesso_placement_entropy=values.get(policy["entropy_field"] if isinstance(policy, dict) else "entropy_pl"),
                    nesso_screening_score=assessment["score"] if assessment else "",
                    nesso_eligible=assessment["eligible"] if assessment else "",
                    nesso_rejection_reason=(assessment["rejection_reason"] or "") if assessment else "",
                    nesso_ranking_policy=policy["version"] if isinstance(policy, dict) else policy))
    destination.with_suffix(".csv.part").replace(destination)
