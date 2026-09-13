#!/usr/bin/env python3
"""One-time, user-authorized Release cleanup AFTER v4.4.4 and metadata publish.

Delete Release objects/assets only. Never delete tags, branches, source history,
4.0.0, future releases, drafts, or older stable releases outside the six entries.
Dry-run is the default. REST reference: https://docs.github.com/en/rest/releases/releases
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPOSITORY = 'xgl34222220-ops/LuoShu'
TARGET = 'v4.4.4'
CUTOFF = '2026-09-13T02:32:33Z'
# Frozen request-time window; reruns must NOT slide the six-entry window back.
PREVIOUS_SIX = frozenset({
    'v4.3.2-Beta1', 'v4.3.1-Beta1', 'v4.3.0', 'v4.2.0', 'v4.1.0', 'v4.0.0',
})
PROTECTED = frozenset({TARGET, 'v4.0.0'})


def before_request(release: dict) -> bool:
    value = release.get('published_at')
    if release.get('draft') or not value:
        return False
    return datetime.fromisoformat(value.replace('Z', '+00:00')) <= datetime.fromisoformat(CUTOFF.replace('Z', '+00:00'))


def selected(releases: list[dict]) -> list[dict]:
    return sorted((r for r in releases
                   if r.get('tag_name') not in PROTECTED and before_request(r)
                   and (r.get('tag_name') in PREVIOUS_SIX or r.get('prerelease') is True)),
                  key=lambda r: (r['published_at'], r['id']), reverse=True)


class Client:
    def __init__(self):
        token = os.environ.get('GH_TOKEN', '')
        if not token:
            raise RuntimeError('GH_TOKEN is required')
        if os.environ.get('GITHUB_REPOSITORY', REPOSITORY) != REPOSITORY:
            raise RuntimeError('unexpected repository')
        self.headers = {'Authorization': f'Bearer {token}',
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28',
                        'User-Agent': 'LuoShu-authorized-v444-cleanup'}

    def request(self, path: str, method: str = 'GET'):
        request = Request(f'https://api.github.com/repos/{REPOSITORY}/{path}',
                          headers=self.headers, method=method)
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    def releases(self) -> list[dict]:
        found = []
        for page in range(1, 101):
            rows = self.request(f'releases?per_page=100&page={page}')
            if not isinstance(rows, list):
                raise RuntimeError('invalid release list')
            found.extend(rows)
            if len(rows) < 100:
                return found
        raise RuntimeError('release pagination limit reached; nothing deleted')


def assets(release: dict) -> dict:
    return {item['name']: item for item in release.get('assets', [])}


def verify_published(client: Client) -> dict:
    release = client.request(f'releases/tags/{TARGET}')
    if release.get('tag_name') != TARGET or release.get('prerelease') is not False or release.get('draft') is not False:
        raise RuntimeError('v4.4.4 stable release is not published')
    if not release.get('published_at'):
        raise RuntimeError('release has no publish timestamp')
    files = assets(release)
    for name in (f'LuoShu-{TARGET}.zip', f'LuoShu-App-{TARGET}.apk'):
        for required in (name, name + '.sha256'):
            entry = files.get(required, {})
            if entry.get('state') != 'uploaded' or entry.get('size', 0) <= 0:
                raise RuntimeError(f'missing completed release asset: {required}')
        digest = files[name].get('digest', '')
        if not digest.startswith('sha256:') or len(digest) != 71:
            raise RuntimeError(f'release asset has no SHA-256: {name}')
    expected_zip = files[f'LuoShu-{TARGET}.zip']['browser_download_url']
    for name in ('update.json', 'update-prerelease.json'):
        data = client.request(f'contents/{name}?ref=main')
        metadata = json.loads(base64.b64decode(data['content']))
        if metadata.get('version') != TARGET or metadata.get('versionCode') != 40404 or metadata.get('zipUrl') != expected_zip:
            raise RuntimeError(f'{name} not synchronized; nothing deleted')
    return release


def summarize(release: dict) -> dict:
    return {key: release.get(key) for key in ('id', 'tag_name', 'prerelease', 'published_at')}


def cleanup(client: Client, apply: bool, report: Path) -> dict:
    verified = verify_published(client)
    anchor = client.request('releases/tags/v4.0.0')
    initial = client.releases()
    plan = selected(initial)
    result = {'target': TARGET, 'cutoff': CUTOFF, 'apply': apply,
              'protected': sorted(PROTECTED), 'tagsDeleted': False,
              'planned': [summarize(r) for r in plan], 'deleted': []}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for item in plan:
        if not apply:
            continue
        # Re-read identity/status immediately before each destructive action.
        current = client.request(f"releases/{item['id']}")
        if current.get('tag_name') != item['tag_name'] or current.get('id') != item['id'] or not selected([current]):
            raise RuntimeError('release changed after planning; deletion stopped')
        client.request(f"releases/{item['id']}", method='DELETE')
        result['deleted'].append(summarize(item))
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    final = client.releases()
    if apply and selected(final):
        raise RuntimeError('authorized cleanup incomplete')
    for old in (verified, anchor):
        current = client.request(f"releases/tags/{quote(old['tag_name'], safe='')}")
        # Download counters may change; compare durable asset identities only.
        identity = lambda r: sorted((a['id'], a['name'], a['size'], a.get('digest')) for a in r.get('assets', []))
        if current['id'] != old['id'] or identity(current) != identity(old):
            raise RuntimeError(f"protected release changed: {old['tag_name']}")
    result['remaining'] = [summarize(r) for r in final]
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--report', type=Path, default=Path('dist/release-cleanup-v4.4.4.json'))
    args = parser.parse_args()
    try:
        result = cleanup(Client(), args.apply, args.report)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, HTTPError, ValueError, KeyError, RuntimeError) as error:
        print(f'Release cleanup stopped: {error}', file=os.sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
