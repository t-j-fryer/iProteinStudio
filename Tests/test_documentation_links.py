"""Check local links in current-facing guides; historical artifacts stay historical."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = sorted(ROOT.glob('*.md')) + sorted((ROOT / 'docs').glob('*.md'))
    files += [ROOT / 'docs/research/README.md', ROOT / 'Validation/README.md',
              ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp/README.md']
    # The Lab Book is an immutable history index with local-only artifact links.
    files = [p for p in files if p.name != 'LAB_BOOK.md']
    failures = []
    links = 0
    for source in files:
        content = re.sub(r'```.*?```', '', source.read_text(), flags=re.S)
        for match in re.finditer(r'\[[^\]\n]+\]\(([^)\n]+)\)', content):
            target = match.group(1).strip().split(' "', 1)[0].strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = (source.parent / unquote(parsed.path)).resolve()
            links += 1
            if not path.is_relative_to(ROOT) or not path.exists():
                failures.append(f'{source.relative_to(ROOT)}: {target}')
    assert not failures, 'Broken current-guide links:\n' + '\n'.join(failures)
    print(f'Documentation links: {links} local targets across {len(files)} current guides passed')


if __name__ == '__main__':
    main()
