#!/usr/bin/env python3
"""Summarize an explicitly supplied natural-reference table; never infer cutoffs.

No coordinates are downloaded and no prediction or sequence design is performed.
Input provenance and biological annotations are supplied by the cohort curator.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def summarize(rows, width=10):
    if width <= 0 or 100 % width:
        raise ValueError('Bin width must be a positive integer divisor of 100')
    if not rows:
        raise ValueError('No reference proteins supplied; a natural distribution cannot be fabricated')
    clusters = set()
    methods = set()
    bins = defaultdict(Counter)
    excluded = []
    for row in rows:
        if row['origin'] != 'natural' or not row['source'].strip():
            raise ValueError('Each reference needs declared natural origin and a source')
        cluster = row['cluster_id'].strip()
        if not cluster or cluster in clusters:
            raise ValueError('Require one representative per nonempty sequence cluster')
        clusters.add(cluster)
        methods.add((row['assignment_method'], row['assignment_version']))
        if row['assignment_method'] != 'PSEA' or not row['assignment_version']:
            raise ValueError('Require an explicit PSEA version; do not mix assignment methods')
        counts = [int(row[key]) for key in ('helix_residues','sheet_residues','coil_residues','unassigned_residues')]
        length = int(row['length'])
        if length <= 0 or min(counts) < 0 or sum(counts) != length:
            raise ValueError('Assignment counts must account for every residue exactly once')
        if counts[3]:
            excluded.append({'reference_id': row['reference_id'], 'reason': 'incomplete assignment',
                             'unassigned_residues': counts[3]})
            continue
        stratum = (row['fold_class'], row['support_class'])
        if not all(stratum):
            raise ValueError('Declare fold and cofactor/disulfide/complex support strata')
        cell = tuple(min(100//width-1, int(100*count/length//width)) for count in counts[:3])
        bins[stratum][cell] += 1
    if len(methods) != 1:
        raise ValueError('All references must use the same assignment method and version')
    strata = []
    for (fold, support), cells in sorted(bins.items()):
        n = sum(cells.values())
        strata.append({'fold_class':fold,'support_class':support,'proteins':n,
                       'bins':[{'lower_percent':dict(zip(('helix','sheet','coil'),(v*width for v in cell))),
                                'upper_percent':dict(zip(('helix','sheet','coil'),((v+1)*width for v in cell))),
                                'count':count,'fraction_within_stratum':count/n}
                               for cell,count in sorted(cells.items())]})
    return {'status':'descriptive_only','acceptance_thresholds':None,
            'provenance':'Input annotations are curator-supplied, not independently verified by this script',
            'bin_width_percentage_points':width,'upper_bound_rule':'Upper bounds excluded except 100%',
            'assignment_method':next(iter(methods)), 'input_proteins':len(rows),
            'complete_proteins':len(rows)-len(excluded),'excluded':excluded,'strata':strata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--bin-width',type=int,default=10)
    args = parser.parse_args()
    with args.input.open(newline='') as handle:
        result = summarize(list(csv.DictReader(handle)),args.bin_width)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'complete_proteins':result['complete_proteins'],
                      'excluded':len(result['excluded']),'acceptance_thresholds':None}))


if __name__ == '__main__':
    main()
