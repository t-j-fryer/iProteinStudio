"""Qualified native-search oracle profile: structure 3/25, affinity 5/50."""
import argparse
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--config', required=True)
    args = parser.parse_args(); path = Path(args.config)
    config = json.loads(path.read_text())
    config['engine_args'] += ['--recycling_steps','3','--sampling_steps','25','--diffusion_samples','1',
        '--num_subsampled_msa','128','--sampling_steps_affinity','50','--diffusion_samples_affinity','1',
        '--preprocessing-threads','1']
    path.write_text(json.dumps(config, indent=2) + '\n')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nise'))
    from batch_worker import main
    main(path)
