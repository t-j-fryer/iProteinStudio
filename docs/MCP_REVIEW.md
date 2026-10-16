# MCP and agent workflow review

Reviewed 2 October 2026 against the source bridge, current user guides and
installed app 0.2.22 (68), followed by the bridge-v41 implementation. Source
capabilities below are not a claim that the running installed app was upgraded.
RCSB was installed and exercised in an isolated qualification runtime.

## What Studio already provides

Studio already has typed planners for prediction, target preparation, Protein
Hunter, ligand NISE and three RFdiffusion3 modes; immutable plan execution;
durable monitoring/cancellation/resume; grouped result queries; and run resources.
Read, run and admin access are separate. The optional remote gateway uses the
same broker. Replacing this with a generic shell agent would lose useful
scientific contracts and reproducibility.

The immediate documentation addition is the portable `iprotein-studio` operating
skill and [assistant guide](AI_ASSISTANTS.md). The bridge's recipe-authoring
tools describe and validate non-executing recipes, as explained in the
[MCP guide](../Sources/iProteinStudio/Resources/pipeline/mcp/README.md).
Keep operational use, method authoring and developer extension as distinct tasks.

## Implemented in bridge v41

- Official RCSB MCP in an optional, checksum-pinned managed runtime, with a native
  install button, upstream schema discovery, read queries and explicit assembly
  import receipts. Live metadata, UniProt mapping and assembly retrieval passed.
- Typed ProteinHunter engine/scaffold batches and public native ligand-screening
  options. Existing planners and the durable broker retain execution authority.
- Exact candidate IDs, snapshot-bound pagination, portable checked ZIP exports,
  chunk retrieval and predictor/context-specific threshold summaries.
- Supported executable v2 recipes, with full parameters and recipe digest bound
  into immutable scientific plans. v1 workshop recipes remain non-executing.
- Portable skill resources, a workflow prompt and output schemas for new candidate
  and plan tools. Skills remain client-neutral and do not grant permissions.

Contract tests exercise fake-engine execution, completion receipts, stale outputs,
profile restrictions, recipe validation and ligand-verification handoffs. They do
not qualify new model performance or establish experimental binding.

## Remaining scope

A visual pipeline builder and guided engine-adapter development remain future
work. The v2 compiler deliberately accepts supported native workflows rather
than arbitrary graphs. General timing aggregation and fully standardized output
schemas for historical tools also remain separate work. Real scientific trials
should qualify any newly combined methods before large campaigns.

## External components worth evaluating

**RCSB PDB MCP is the best first complement.** The RCSB-maintained server covers
structure discovery, entry/assembly/ligand inspection and sequence-coordinate
mapping. It supports target selection before Studio imports a frozen structure.
Keep it as an optional research connection: record the PDB accession, biological
assembly, chains, retrieval date and downloaded structure checksum, then validate
the local input through Studio. The optional v41 integration uses the official published server; public metadata,
sequence-coordinate mapping and explicit assembly import were tested. [RCSB MCP](https://github.com/rcsb/rcsb-mcp).

**BioMCP is useful for literature and biological context.** Its documented data
sources include UniProt and biomedical literature services. Evaluate it for
target background and cited evidence, outside the local design execution path.
Avoid adding its full dependency/API surface merely to retrieve a structure.
[BioMCP](https://github.com/genomoncology/biomcp).

**ProteinMCP is relevant published precedent.** It demonstrates MCP-based
orchestration of a collection of protein-engineering tools. Cite it when
positioning agentic access, and assess individual components for missing science.
Do not treat “MCP for protein design” as unique to Studio. Studio's argument is
the native local application, managed Apple-silicon execution, connected
scientific workflows and shared reproducible records.
[Paper](https://pubmed.ncbi.nlm.nih.gov/41877581/),
[implementation](https://github.com/charlesxu90/ProteinMCP).

**Paper2Agent is a development precedent.** Its paper-to-tool workflow is relevant
to future guided adapter creation. It does not establish that generated adapters
preserve an upstream method or work efficiently on Apple silicon; those remain
local qualification tasks. [Paper2Agent](https://github.com/jmiao24/Paper2Agent).

Use the open [Agent Skills format](https://agentskills.io/specification) for
portable procedural guidance, and standard MCP
[resources/prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts)
for discovery in clients without skill loading. MCP
[structured outputs and output schemas](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
are a better basis for automated result handling than free-text reports alone.

External discovery services need network access. They should not become mandatory
dependencies for local inference, and unpublished inputs should not be sent to
them without authorization for that use.
