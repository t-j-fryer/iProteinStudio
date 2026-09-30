"""Exact-token inference through IntelliFold's native overflow sizing path.

The upstream CLI accepts positive integer buckets. A sole bucket of one
selects the actual input token count for every input longer than one token;
a one-token input is already exact. This avoids rewriting model features or
patching the installed package, and applies to Flash and Full alike.
Explicit buckets remain available for reproducing older saved requests.
"""
UPSTREAM_BUCKETS = '256,512,768,1024,1280,1536,2048,2560,3072,3584,4096,4608,5120'

def default_buckets(model):
    return '1'

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
