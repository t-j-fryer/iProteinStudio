#!/usr/bin/env python3
"""Run the upstream MCP implementation inside the optional locked environment."""
import asyncio,json,sys,os
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def run(request):
    params=StdioServerParameters(command=sys.executable,args=['-B','-X','pycache_prefix=/dev/null','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("rcsb_mcp.server",run_name="__main__")',os.environ['IPROTEINSTUDIO_RCSB_SITE']])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            listing=await session.list_tools()
            if request['operation']=='tools':return {'tools':[t.model_dump(exclude_none=True) for t in listing.tools]}
            known={t.name:t for t in listing.tools}
            if request.get('name') not in known:raise ValueError('Unknown upstream tool; call rcsb_tools first.')
            result=await session.call_tool(request['name'],request['arguments'])
            if result.isError:raise ValueError(str(result.content))
            return result.model_dump(exclude_none=True)

if __name__=='__main__':
    request=json.load(sys.stdin)
    print(json.dumps(asyncio.run(asyncio.wait_for(run(request),45))))
