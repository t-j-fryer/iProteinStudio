"""Durable, human-readable preparation status shared by native workflows."""
from contextvars import ContextVar
from pathlib import Path

from .common import StudioError, atomic_json, canonical_digest, load_json, project_root, runtime_root, utc_now, validate_slug

_reporter = ContextVar('submission_reporter', default=None)


def progress(stage, message):
    reporter = _reporter.get()
    if reporter:
        reporter(stage, message)


def submit(request, *, prepare_only=False):
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
        # An override draft allows the user to review unsupported/large workloads.
        # It is never queued by this path; confirmation starts the exact digest.
        plan = desktop_plan({**request, 'memory_policy': 'override'} if prepare_only else request)
        if prepare_only:
            from .memory_estimate import for_plan, describe
            report = for_plan(plan)
            review = dict(plan_id=plan['id'], plan_sha256=plan['sha256'], report=report)
            atomic_json(output / 'studio_memory_review.json', review)
            progress('awaiting_confirmation', 'Review the memory estimate before submitting this run.')
            return dict(plan_id=plan['id'], plan_sha256=plan['sha256'],
                        report_sha256=canonical_digest(review), message=describe(report),
                        warning=report['warning'])
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


def confirm(plan_id, plan_sha256, report_sha256):
    """Explicit, per-run approval. No scientific settings or global defaults change."""
    from .plans import load_plan
    from .broker import start_job
    plan = load_plan(plan_id, plan_sha256)
    output = Path(plan['normalized_request']['output'])
    review = load_json(output / 'studio_memory_review.json')
    if (review.get('plan_id') != plan_id or review.get('plan_sha256') != plan_sha256
            or canonical_digest(review) != report_sha256):
        raise StudioError('The memory review changed. Review this saved run again before starting.')
    atomic_json(output / 'studio_memory_confirmation.json',
                dict(**review, report_sha256=report_sha256, accepted_at=utc_now(), choice='proceed'))
    state = start_job(plan_id, plan_sha256)
    atomic_json(output / 'studio_job.json', dict(id=state['id'], plan_id=plan_id, sha256=plan_sha256))
    return state
