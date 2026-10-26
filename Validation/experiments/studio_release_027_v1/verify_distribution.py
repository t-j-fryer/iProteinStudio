"""Download and verify the published app assets and live Sparkle entry."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parents[3]


def run(*command):
    return subprocess.check_output(command, text=True).strip()


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): value.update(block)
    return value.hexdigest()


def verify(output, repository, version, build):
    output.mkdir(parents=True, exist_ok=False)
    tag = 'v' + version + '-beta'
    release = json.loads(run('gh', 'api', f'repos/{repository}/releases/tags/{tag}'))
    (output / 'github-release.json').write_text(json.dumps(release, indent=2) + '\n')
    run('gh', 'release', 'download', tag, '--repo', repository, '--dir', str(output))
    expected = {line.split()[1]: line.split()[0] for line in (output / 'SHA256SUMS.txt').read_text().splitlines()}
    for name, checksum in expected.items(): assert sha(output / name) == checksum
    for asset in release['assets']:
        path = output / asset['name']
        assert path.stat().st_size == asset['size']
        assert 'sha256:' + sha(path) == asset['digest']
    feed_url = f'https://raw.githubusercontent.com/{repository}/main/appcast.xml'
    with urllib.request.urlopen(feed_url, timeout=30) as response: feed = response.read()
    (output / 'live-appcast.xml').write_bytes(feed)
    ns = {'s': 'http://www.andymatuschak.org/xml-namespaces/sparkle'}
    entries = [item for item in ET.fromstring(feed).findall('./channel/item')
               if item.findtext('s:version', namespaces=ns) == str(build)]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.findtext('s:shortVersionString', namespaces=ns) == version
    enclosure = entry.find('enclosure')
    archive = output / enclosure.attrib['url'].rsplit('/', 1)[-1]
    assert enclosure.attrib['url'].startswith(f'https://github.com/{repository}/releases/download/{tag}/')
    assert int(enclosure.attrib['length']) == archive.stat().st_size
    signature = enclosure.attrib['{' + ns['s'] + '}edSignature']
    signer = REPO / '.build/artifacts/sparkle/Sparkle/bin/sign_update'
    verification = run(str(signer), '--verify', '--account', 'iproteinstudio', str(archive), signature)
    with zipfile.ZipFile(archive) as zipped:
        info = plistlib.loads(zipped.read('iProteinStudio.app/Contents/Info.plist'))
    assert info['CFBundleShortVersionString'] == version and info['CFBundleVersion'] == str(build)
    assert info['SUPublicEDKey'] == (REPO / 'release/sparkle_public_key.txt').read_text().strip()
    assert info['SUFeedURL'] == feed_url
    assert info['IPStudioSparkleUpdateBuild'] is True
    previous = run('git', '-C', str(REPO), 'show', 'v0.2.26-beta:release/sparkle_public_key.txt')
    assert previous == info['SUPublicEDKey']
    extracted = output / 'extracted'
    run('/usr/bin/ditto', '-x', '-k', str(archive), str(extracted))
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', str(extracted / 'iProteinStudio.app'))
    for dmg in output.glob('*.dmg'): run('/usr/bin/hdiutil', 'verify', str(dmg))
    report = dict(tag=tag, build=build, verified_downloads=expected, live_feed=feed_url,
                  sparkle_signature_verified=True, verification_tool_output=verification, previous_public_key_matches=True,
                  downloaded_bundle_signature_valid=True, dmg_verified=True,
                  notarized=False, physical_second_mac_test=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', default='t-j-fryer/iProteinStudio')
    parser.add_argument('--version', default='0.2.27')
    parser.add_argument('--build', type=int, default=73)
    args = parser.parse_args()
    verify(args.output, args.repository, args.version, args.build)
