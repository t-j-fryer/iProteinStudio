#!/usr/bin/env python3
"""Native UI helper for the optional managed RCSB runtime."""
import argparse,json,sys
sys.dont_write_bytecode=True
from iprotein_mcp.research import install,status,tools_list
from iprotein_mcp.common import StudioError
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['status','install','test']);a=p.parse_args()
    try:
        value=install() if a.action=='install' else tools_list() if a.action=='test' else status()
        print(json.dumps(value))
    except Exception as exc:print(str(exc),file=sys.stderr);raise SystemExit(1)
