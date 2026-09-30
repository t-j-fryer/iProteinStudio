#!/usr/bin/env python3
"""Managed OpenFold launch with explicit profiles and measured CPU preparation."""
import json
from pathlib import Path
import sys
from prediction_profiles import profile, cap_a3m, record, _atomic


def prepare_query(source, output, settings):
    source, output = Path(source), Path(output)
    data = json.loads(source.read_text())
    for query in data['queries'].values():
        for chain in query['chains']:
            paths = []
            for path in chain.get('main_msa_file_paths') or []:
                capped = cap_a3m(path, settings['msa_depth'], output / '_profile_msas')
                if capped != Path(path).resolve():
                    # OpenFold dispatches by the ColabFold filename convention.
                    named = capped.parent / capped.stem / Path(path).name
                    _atomic(named, capped.read_bytes())
                    capped = named
                paths.append(str(capped))
            if paths:
                chain['main_msa_file_paths'] = paths
    target = output / '_profile_inputs' / source.name
    _atomic(target, (json.dumps(data, indent=2) + '\n').encode())
    record(output, 'openfold-3-mlx', settings)
    return target


def main():
    arguments = list(sys.argv[1:])
    if not arguments or arguments[0] != 'predict':
        from openfold3.run_openfold import cli
        return cli(args=arguments)
    def value(name):
        return arguments[arguments.index(name) + 1]
    settings = profile('openfold-3-mlx')
    output = Path(value('--output_dir'))
    query_index = arguments.index('--query_json') + 1
    arguments[query_index] = str(prepare_query(arguments[query_index], output, settings))
    from openfold3.entry_points.experiment_runner import InferenceExperimentRunner
    setup = InferenceExperimentRunner.setup
    def configured_setup(runner):
        shared = runner.model_config.architecture.shared
        shared.num_recycles = settings['recycles']
        shared.diffusion.no_full_rollout_steps = settings['diffusion_steps']
        return setup(runner)
    InferenceExperimentRunner.setup = configured_setup
    from inference_optimizations import OpenFoldPreparation
    optimizations = OpenFoldPreparation(InferenceExperimentRunner)
    try:
        from openfold3.run_openfold import cli
        return cli(args=arguments)
    finally:
        optimizations.close()
        InferenceExperimentRunner.setup = setup


if __name__ == '__main__':
    main()
