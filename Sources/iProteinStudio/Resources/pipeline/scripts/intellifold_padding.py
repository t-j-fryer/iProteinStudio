"""Measured Flash padding policy; all upstream larger buckets are preserved."""
UPSTREAM_BUCKETS = '256,512,768,1024,1280,1536,2048,2560,3072,3584,4096,4608,5120'

def default_buckets(model):
    # Full-v2 remains on its existing default pending broader qualification.
    return '128,' + UPSTREAM_BUCKETS if model == 'v2-flash' else UPSTREAM_BUCKETS

def launcher_arguments(arguments):
    result = list(arguments)
    if any(value == '--buckets' or value.startswith('--buckets=') for value in result):
        return result
    model = 'v2-flash'
    for index, value in enumerate(result):
        if value.startswith('--model='):
            model = value.split('=', 1)[1]
        elif value == '--model' and index + 1 < len(result):
            model = result[index + 1]
    return result + ['--buckets', default_buckets(model)]
