"""Create a new immutable short follow-up after user cancels the second seed."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from common import sha, save, verified
from prepare import HERE, REPO


parent=Path(sys.argv[1]).resolve()
cfg=json.loads((parent/'frozen/config.json').read_text())
for arm in ('reference','light'):
    records=[verified(p.parent) for p in (parent/'r0'/arm).glob('*/completed.json')]
    assert sum(len(r['rows']) for r in records)==48
out=REPO/'Validation/output/biotin_affinity_efficiency_v1'/('cpu_followup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
frozen=out/'frozen';frozen.mkdir(parents=True)
for p in (parent/'frozen').glob('*.py'):shutil.copy2(p,frozen/p.name)
shutil.copy2(HERE/'run.py',frozen/'run.py')
shutil.copy2(HERE/'continue_efficiency.py',frozen/'continue_efficiency.py')
cfg.update(output=str(out),entrypoint='continue_efficiency.py',continued_from=str(parent),repeats=1,
           protocol_change='User stopped second seeded affinity repeat. Complete first 48-pair comparison retained; CPU geometry sweep and one same-seed serial/overlap pair only.')
for p in frozen.glob('*.py'):cfg['frozen_inputs_sha256'][str(p)]=sha(p)
for arm in ('reference','light'):
    for receipt in (parent/'r0'/arm).glob('*/completed.json'):
        cfg['frozen_inputs_sha256'][str(receipt)]=sha(receipt)
save(frozen/'config.json',cfg)
save(out/'manifest.json',dict(config_sha256=sha(frozen/'config.json'),continued_from=str(parent),
                             expected_affinity_evaluations=18,outer_structure_predictions=0,
                             geometry_evaluations=384,overlap_geometry_evaluations=16))
print(str(out))
