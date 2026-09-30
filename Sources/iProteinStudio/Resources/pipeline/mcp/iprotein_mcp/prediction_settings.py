"""Use the exact lightweight profile contract shipped beside the MCP bridge."""
import importlib.util
from pathlib import Path
from .common import StudioError


def normalize(value=None):
    path = Path(__file__).resolve().parents[2] / 'scripts/prediction_profiles.py'
    spec = importlib.util.spec_from_file_location('studio_prediction_profiles_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.normalize(value)
    except (ValueError, TypeError) as exc:
        raise StudioError(str(exc)) from exc
