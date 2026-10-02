"""Exercise the real CLI seed helpers, without loading prediction models."""
import json
from pathlib import Path
import shlex
import subprocess
import unittest

PIPELINE = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline'


class NativeRegions(unittest.TestCase):
    def helpers(self):
        script = (PIPELINE / 'nanohunter_run.sh').read_text()
        names = ('generate_random_binder_seq', 'generate_partial_redesign_seed_seq', 'generate_motif_scaffold_bundle')
        functions = []
        for name in names:
            start = script.index(name + '() {')
            end = script.index('\n}\n', start) + 3
            functions.append(script[start:end])
        return '\n'.join([
            'set -euo pipefail',
            'SECONDARY_STRUCTURE_HELPER=' + shlex.quote(str(PIPELINE / 'scripts/secondary_structure_control.py')),
            'MOTIF_HELPER=' + shlex.quote(str(PIPELINE / 'motif_scaffolding_helper.py')),
            'SECONDARY_BIAS=none; SECONDARY_BIAS_SCOPE=seed-only; SEED_SAMPLING_ORDER=mask-first',
            *functions,
        ])

    def run_helper(self, command):
        return subprocess.check_output(['bash', '-c', self.helpers() + '\n' + command], text=True).strip()

    def test_partial_changes_only_selected_regions_and_replays_seed(self):
        source = 'ACDEFGHIKLMNPQRSTVWY'
        cmd = f'generate_partial_redesign_seed_seq {source} 3-5,10-12 100 0 0 0 boltz 123'
        self.assertEqual(self.run_helper(cmd), 'ACXXXGHIKXXXPQRSTVWY')
        mixed = cmd.replace(' 100 ', ' 50 ')
        first = self.run_helper(mixed)
        self.assertEqual(first, self.run_helper(mixed))
        for i in set(range(len(source))) - {2, 3, 4, 9, 10, 11}:
            self.assertEqual(first[i], source[i])

    def test_motifs_keep_residues_and_have_deterministic_placement(self):
        cmd = ('MOTIF_POSITIONS=3-5,10-12; MOTIF_SOURCE_SEQ=ACDEFGHIKLMNPQRSTVWY; '
               'MOTIF_FIXED_POSITIONS=""; MOTIF_GAP_BETWEEN=8; '
               'generate_motif_scaffold_bundle 40 50 123')
        first = self.run_helper(cmd)
        self.assertEqual(first, self.run_helper(cmd))
        bundle = json.loads(first)
        source = 'ACDEFGHIKLMNPQRSTVWY'
        seq = bundle['init_sequence']
        for motif in bundle['shifted_motifs']:
            original = source[motif['start_pos']:motif['end_pos'] + 1]
            self.assertEqual(seq[motif['shifted_start']:motif['shifted_end'] + 1], original)
        self.assertEqual(len(bundle['fixed_residues'].split()), 6)


if __name__ == '__main__':
    unittest.main()
