"""Read-only diffusion snapshots for a bounded validation job, not early killing.

Compile the installed sampler unchanged except for one observer call at the end
of its diffusion loop. The installed source is already fingerprinted by the plan;
record original and instrumented source hashes too. Never edit site-packages.
"""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import textwrap
import time
import types


def instrument_source(source):
    tree = ast.parse(textwrap.dedent(source))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "sample":
        raise ValueError("Unexpected installed diffusion sampler")
    loops = [n for n in ast.walk(functions[0]) if isinstance(n, ast.For)
             and isinstance(n.target, ast.Tuple) and isinstance(n.target.elts[0], ast.Name)
             and n.target.elts[0].id == "step_idx"]
    if len(loops) != 1:
        raise ValueError("Cannot identify exactly one diffusion-step loop")
    loop = loops[0]
    last = loop.body[-1]
    if (not isinstance(last, ast.Assign) or len(last.targets) != 1
            or not isinstance(last.targets[0], ast.Name) or last.targets[0].id != "atom_coords"
            or not isinstance(last.value, ast.Name) or last.value.id != "atom_coords_next"):
        raise ValueError("Installed sampler end-of-step contract changed")
    observer = ast.parse("self._studio_observe(step_idx + 1, atom_coords_denoised, atom_coords, sigma_t)").body[0]
    loop.body.append(observer)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def install(session, steps, directory):
    import numpy as np
    import torch
    from resident_predictor import atomic_json
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    module = session.model.structure_module
    original = type(module).sample
    source = inspect.getsource(original)
    instrumented = instrument_source(source)
    namespace = dict(original.__globals__)
    exec(compile(instrumented, "<studio_observed_boltz_sample>", "exec"), namespace)
    sampled = types.MethodType(namespace["sample"], module)
    provenance = dict(original_sample_sha256=hashlib.sha256(source.encode()).hexdigest(),
                      instrumented_sample_sha256=hashlib.sha256(instrumented.encode()).hexdigest(),
                      operation="Append read-only callback after atom_coords = atom_coords_next")
    atomic_json(directory / "observer_provenance.json", provenance)
    (directory / "instrumented_sample.py").write_text(instrumented)
    state = {}
    selected = set(steps)

    def observe(step, denoised, current, sigma):
        state["last_step"] = step
        if step not in selected:
            return
        started = time.perf_counter()
        # Detach/copy only; never expose a live view to an observer mutation.
        state["denoised"].append(denoised.detach().cpu().numpy().copy())
        state["current"].append(current.detach().cpu().numpy().copy())
        state["steps"].append(step)
        state["sigmas"].append(float(sigma))
        state["elapsed"].append(time.perf_counter() - state["started"])
        state["observer_seconds"] += time.perf_counter() - started

    module._studio_observe = observe
    def sample(*args, **kwargs):
        steering = kwargs["steering_args"]
        if (steering["fk_steering"] or not steering["physical_guidance_update"]
                or not steering["contact_guidance_update"] or kwargs.get("multiplicity") != 1):
            raise ValueError("Exposure trace requires one physically guided diffusion path")
        state["diffusion_started_seconds"] = time.perf_counter() - state["started"]
        return sampled(*args, **kwargs)
    module.sample = sample
    predict = session.model.predict_step
    def predict_step(batch, batch_idx, dataloader_idx=0):
        name = batch["record"][0].id
        state.clear()
        state.update(started=time.perf_counter(), steps=[], sigmas=[], denoised=[], current=[], elapsed=[], observer_seconds=0.)
        result = predict(batch, batch_idx, dataloader_idx)
        torch.mps.synchronize()
        total = time.perf_counter() - state["started"]
        if state["steps"] != steps or state.get("last_step") != 200 or result.get("exception"):
            raise ValueError("Incomplete diffusion trace")
        final = result["coords"].detach().cpu().numpy().copy()
        if not np.array_equal(state["current"][-1], final):
            raise ValueError("Final diffusion state differs from emitted prediction coordinates")
        leaf = directory / name
        leaf.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(leaf / "coordinates.npz", steps=np.array(steps),
            denoised=np.stack(state["denoised"]), current=np.stack(state["current"]), final=final,
            atom_mask=batch["atom_pad_mask"][0].detach().cpu().numpy().astype(bool))
        atomic_json(leaf / "metadata.json", dict(id=name, steps=steps, sigma_after_step=state["sigmas"],
            elapsed_seconds=state["elapsed"], diffusion_started_seconds=state["diffusion_started_seconds"],
            total_prediction_seconds=total, snapshot_callback_seconds=state["observer_seconds"],
            meaning="Denoised estimate after physical/contact corrections; current is the noisy diffusion state. No early stopping.",
            final_coordinates_exact=True, **provenance))
        print(f"EXPOSURE_TRACE|{name}|snapshots={len(steps)}", flush=True)
        return result
    session.model.predict_step = predict_step
