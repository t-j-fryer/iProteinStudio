"""Durable, human-readable preparation status shared by native workflows."""
from contextvars import ContextVar
from pathlib import Path

from .common import StudioError, atomic_json, project_root, runtime_root, utc_now, validate_slug

_reporter = ContextVar('submission_reporter', default=None)


def progress(stage, message):
    reporter = _reporter.get()
    if reporter:
        reporter(stage, message)


def submit(request):
    from .desktop import desktop_plan
    from .broker import start_job
    project = validate_slug(request.get('project', ''))
    workspace = ((runtime_root() / 'target_predictions').resolve()
                 if request.get('workflow') == 'target_prepare' else project_root(project))
    output = Path(request.get('output', '')).resolve()
    if workspace not in output.parents or not output.is_dir():
        raise StudioError('The saved submission must belong to its workspace.')
    def report(stage, message):
        atomic_json(output / 'studio_submission_status.json',
                    dict(stage=stage, message=message, updated_at=utc_now()))
    token = _reporter.set(report)
    try:
        progress('validating', 'Validating saved inputs and settings. Prediction has not started yet.')
        plan = desktop_plan(request)
        progress('registering', 'Registering the verified job in the queue…')
        state = start_job(plan['id'], plan['sha256'])
        atomic_json(output / 'studio_job.json', dict(id=state['id'], plan_id=plan['id'], sha256=plan['sha256']))
        progress('submitted', 'Job registered. Follow progress in Jobs.')
        return state
    except Exception as exc:
        progress('failed', 'Submission failed: ' + str(exc))
        raise StudioError(str(exc)) from exc
    finally:
        _reporter.reset(token)
