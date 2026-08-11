#!/usr/bin/env python3
"""Write the OpenFold-3 runner YAML.

The two variants below are copied from `write_openfold_runner_yaml` in
`nanohunter_run.sh`. The GPU variant is the one that matters: it enables the MLX
attention, triangle and activation kernels, which is what makes OpenFold-3 usable
on Apple silicon at all.

Usage:  openfold_runner_yaml.py OUT_YAML [--cpu]
"""

import sys

GPU = """experiment_settings:
  mode: predict

pl_trainer_args:
  accelerator: gpu
  devices: 1

model_update:
  presets: ["predict", "pae_enabled"]
  custom:
    settings:
      memory:
        eval:
          use_deepspeed_evo_attention: false
          use_lma: false
          use_mlx_attention: true
          use_mlx_triangle_kernels: true
          use_mlx_activation_functions: true
"""

CPU = """experiment_settings:
  mode: predict

pl_trainer_args:
  accelerator: cpu
  devices: 1

model_update:
  presets: ["predict", "pae_enabled"]
  custom:
    settings:
      memory:
        eval:
          use_deepspeed_evo_attention: false
"""


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: openfold_runner_yaml.py OUT_YAML [--cpu]")
    cpu = "--cpu" in sys.argv[2:]
    with open(sys.argv[1], "w") as handle:
        handle.write(CPU if cpu else GPU)


if __name__ == "__main__":
    main()
