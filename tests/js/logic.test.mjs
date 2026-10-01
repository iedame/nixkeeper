// The page's rules (docs/logic.js). Run: node --test tests/js/
// (part of `nix flake check`, as checks.page).

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  attentionRank,
  buildsWith,
  compareVersions,
  computeStatus,
  daysText,
  escapeHtml,
  faviconKey,
  githubRepo,
  hasFailure,
  href,
  onMaster,
  onPlatform,
  safeUrl,
  shortAge,
  timeAgo,
  versionChange,
  waitingForChannel,
  withSlash,
} from '../../docs/logic.js';

const NOW = Date.parse('2026-10-01T12:00:00Z');
const daysAgo = (n) => new Date(NOW - n * 86400e3).toISOString();

// A package as index.json has it, up to date unless overridden.
const pkg = (fields = {}) => ({ name: 'p', nixStatus: 'newest', ...fields });
const outdated = (fields = {}) =>
  pkg({ nixStatus: 'outdated', nixVersion: '1.0', refVersion: '1.1', ...fields });

describe('computeStatus', () => {
  test("follows Repology's statuses", () => {
    assert.equal(computeStatus(pkg()), 'ok');
    assert.equal(computeStatus(pkg({ nixStatus: 'unique' })), 'ok');
    assert.equal(computeStatus(pkg({ nixStatus: 'devel' })), 'ok');
    assert.equal(computeStatus(pkg({ nixStatus: 'outdated' })), 'warn');
    assert.equal(computeStatus(pkg({ nixStatus: 'missing' })), 'missing');
    assert.equal(computeStatus(pkg({ nixStatus: 'rolling' })), 'neutral');
  });
  test('legacy counts as outdated', () => {
    assert.equal(computeStatus(pkg({ nixStatus: 'legacy' })), 'warn');
  });
  test("an update check's newer release makes it outdated", () => {
    assert.equal(computeStatus(pkg({ upstream: { newer: true } })), 'warn');
    assert.equal(computeStatus(pkg({ nixStatus: 'rolling', upstream: { newer: true } })), 'warn');
  });
  test('missing wins over an update check', () => {
    assert.equal(
      computeStatus(pkg({ nixStatus: 'missing', upstream: { newer: true } })),
      'missing',
    );
  });
});

describe('compareVersions', () => {
  test('numbers as numbers', () => {
    assert.equal(compareVersions('1.10', '1.9'), 1);
    assert.equal(compareVersions('1.9', '1.10'), -1);
    assert.equal(compareVersions('2.4.3', '2.4.3'), 0);
  });
  test('a letter part sorts before a number', () => {
    assert.equal(compareVersions('1.0rc1', '1.0.1'), -1);
    assert.equal(compareVersions('1.0.1', '1.0rc1'), 1);
  });
  test('a longer version is newer', () => {
    assert.equal(compareVersions('1.0', '1.0.1'), -1);
    assert.equal(compareVersions('1.0.1', '1.0'), 1);
  });
  test('unstable dates compare by date', () => {
    assert.equal(compareVersions('0-unstable-2026-08-22', '0-unstable-2026-09-01'), -1);
  });
});

describe('onMaster and waitingForChannel', () => {
  test("master's version: the higher of Hydra's and a merged PR's", () => {
    assert.equal(onMaster(pkg()), null);
    assert.equal(onMaster(pkg({ master: '1.1' })), '1.1');
    assert.equal(onMaster(pkg({ master: '1.1', masterPR: { to: '1.2' } })), '1.2');
    assert.equal(onMaster(pkg({ master: '1.3', masterPR: { to: '1.2' } })), '1.3');
  });
  test('waiting once master has the newest version or newer', () => {
    assert.equal(waitingForChannel(outdated({ master: '1.1' })), true);
    assert.equal(waitingForChannel(outdated({ masterPR: { to: '1.2' } })), true);
  });
  test('not waiting when master is still behind', () => {
    assert.equal(waitingForChannel(outdated({ master: '1.0.5' })), false);
    assert.equal(waitingForChannel(outdated()), false);
  });
  test('only outdated packages wait', () => {
    assert.equal(waitingForChannel(pkg({ master: '9.9' })), false);
  });
});

describe('versionChange', () => {
  test('an unstable version with the same base: just the new date', () => {
    assert.equal(
      versionChange('5.1.0-b2-unstable-2022-11-14', '5.1.0-b2-unstable-2026-08-22'),
      '2026-08-22',
    );
  });
  test('anything else in full', () => {
    assert.equal(versionChange('1.3.7', '1.3.8'), '1.3.8');
    assert.equal(
      versionChange('1.0-unstable-2022-11-14', '2.0-unstable-2026-08-22'),
      '2.0-unstable-2026-08-22',
    );
    assert.equal(versionChange('1.0', '1.0-unstable-2026-08-22'), '1.0-unstable-2026-08-22');
  });
  test('a missing target stays missing', () => {
    assert.equal(versionChange('1.0', undefined), undefined);
    assert.equal(versionChange(null, '1.1'), '1.1');
  });
});

describe('failures and platforms', () => {
  const builds = [
    { system: 'x86_64-linux', status: 'failed' },
    { system: 'aarch64-darwin', status: 'succeeded' },
    { system: 'aarch64-linux', status: 'broken' },
  ];
  test('builds with a status, on the selected platform', () => {
    assert.equal(buildsWith(pkg({ builds }), 'failed').length, 1);
    assert.equal(buildsWith(pkg({ builds }), 'failed', 'linux').length, 1);
    assert.equal(buildsWith(pkg({ builds }), 'failed', 'darwin').length, 0);
    assert.equal(buildsWith(pkg({ builds }), 'broken', 'linux').length, 1);
    assert.deepEqual(buildsWith(pkg(), 'failed'), []);
  });
  test('a failed build counts only on its platform', () => {
    assert.equal(hasFailure(pkg({ builds })), true);
    assert.equal(hasFailure(pkg({ builds }), 'linux'), true);
    assert.equal(hasFailure(pkg({ builds }), 'darwin'), false);
  });
  test('marked broken is not a failure', () => {
    assert.equal(hasFailure(pkg({ builds: [builds[2]] })), false);
  });
  test('an update failure or missing from nixpkgs is a failure', () => {
    assert.equal(hasFailure(pkg({ updateFailure: { version: '1.1' } })), true);
    assert.equal(hasFailure(pkg({ updateFailure: { version: '1.1' } }), 'darwin'), true);
    assert.equal(hasFailure(pkg({ nixStatus: 'missing' })), true);
    assert.equal(hasFailure(pkg()), false);
  });
  test('"any platform" counts as both', () => {
    assert.equal(onPlatform(pkg({ platforms: null }), 'linux'), true);
    assert.equal(onPlatform(pkg({ platforms: null }), 'darwin'), true);
    assert.equal(onPlatform(pkg({ platforms: { linux: true } }), 'darwin'), false);
    assert.equal(onPlatform(pkg({ platforms: { linux: true } }), 'linux'), true);
  });
});

describe('attentionRank', () => {
  test('failed, outdated, waiting for the channel, then the rest', () => {
    const order = [
      pkg({ name: 'fine' }),
      outdated({ name: 'waiting', master: '1.1' }),
      outdated({ name: 'outdated' }),
      pkg({ name: 'failed', updateFailure: {} }),
    ].sort((a, b) => attentionRank(a) - attentionRank(b));
    assert.deepEqual(
      order.map((p) => p.name),
      ['failed', 'outdated', 'waiting', 'fine'],
    );
  });
  test('a failure elsewhere ranks with the rest while a platform is selected', () => {
    const failsOnLinux = pkg({ builds: [{ system: 'x86_64-linux', status: 'failed' }] });
    assert.equal(attentionRank(failsOnLinux), 0);
    assert.equal(attentionRank(failsOnLinux, 'darwin'), 2);
  });
});

describe('faviconKey', () => {
  test('all good', () => {
    assert.equal(faviconKey([]), 'ok');
    assert.equal(faviconKey([pkg(), pkg({ nixStatus: 'rolling' })]), 'ok');
  });
  test('each signal lights its own chevron, in r, f, v order', () => {
    assert.equal(faviconKey([outdated()]), 'r');
    assert.equal(faviconKey([pkg({ updateFailure: {} })]), 'f');
    assert.equal(faviconKey([pkg({ nixVulnerable: true })]), 'v');
    assert.equal(
      faviconKey([pkg({ nixVulnerable: true }), pkg({ updateFailure: {} }), outdated()]),
      'rfv',
    );
    assert.equal(faviconKey([outdated({ nixVulnerable: true })]), 'rv');
  });
  test("an update already on master isn't a new release to act on", () => {
    assert.equal(faviconKey([outdated({ master: '1.1' })]), 'ok');
  });
  test('failures follow the platform filter', () => {
    const failsOnLinux = pkg({ builds: [{ system: 'x86_64-linux', status: 'failed' }] });
    assert.equal(faviconKey([failsOnLinux]), 'f');
    assert.equal(faviconKey([failsOnLinux], 'darwin'), 'ok');
  });
});

describe('ages', () => {
  test('shortAge: one unit, rounded down', () => {
    assert.equal(shortAge(daysAgo(0.5), NOW), '<1 d');
    assert.equal(shortAge(daysAgo(1), NOW), '1 d');
    assert.equal(shortAge(daysAgo(6), NOW), '6 d');
    assert.equal(shortAge(daysAgo(7), NOW), '1 w');
    assert.equal(shortAge(daysAgo(29), NOW), '4 w');
    assert.equal(shortAge(daysAgo(30), NOW), '1 m');
    assert.equal(shortAge(daysAgo(364), NOW), '11 m');
    assert.equal(shortAge(daysAgo(365), NOW), '1 y');
    assert.equal(shortAge(daysAgo(800), NOW), '2 y');
  });
  test('daysText', () => {
    assert.equal(daysText(daysAgo(0.2), NOW), 'today');
    assert.equal(daysText(daysAgo(1), NOW), '1 day');
    assert.equal(daysText(daysAgo(12), NOW), '12 days');
  });
  test('timeAgo', () => {
    assert.equal(timeAgo(null, NOW), 'never');
    assert.equal(timeAgo(new Date(NOW - 30e3).toISOString(), NOW), 'just now');
    assert.equal(timeAgo(new Date(NOW - 5 * 60e3).toISOString(), NOW), '5m ago');
    assert.equal(timeAgo(new Date(NOW - 4 * 3600e3).toISOString(), NOW), '4h ago');
    assert.equal(timeAgo(daysAgo(3), NOW), '3d ago');
  });
});

describe('links and markup from data', () => {
  test('escapeHtml', () => {
    assert.equal(
      escapeHtml(`<a href="x">'&'</a>`),
      '&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;',
    );
    assert.equal(escapeHtml(null), '');
    assert.equal(escapeHtml(42), '42');
  });
  test('only web addresses are links', () => {
    assert.equal(
      safeUrl('https://github.com/NixOS/nixpkgs/pull/1'),
      'https://github.com/NixOS/nixpkgs/pull/1',
    );
    assert.equal(safeUrl('http://example.org/'), 'http://example.org/');
    assert.equal(safeUrl('javascript:alert(1)'), '');
    assert.equal(safeUrl('JavaScript:alert(1)'), '');
    assert.equal(safeUrl('data:text/html,<script>'), '');
    assert.equal(safeUrl('not a url'), '');
    assert.equal(safeUrl(undefined), '');
  });
  test('href escapes what it keeps', () => {
    assert.equal(
      href('https://example.org/?a="b"&c'),
      'https://example.org/?a=&quot;b&quot;&amp;c',
    );
    assert.equal(href('javascript:alert(1)'), '');
  });
});

describe('where the data is', () => {
  const at = (url) => {
    const u = new URL(url);
    return [u.searchParams, u];
  };
  test('a GitHub Pages project site names its repository', () => {
    assert.equal(githubRepo(...at('https://iedame.github.io/nixkeeper/')), 'iedame/nixkeeper');
    assert.equal(
      githubRepo(...at('https://iedame.github.io/nixkeeper/index.html')),
      'iedame/nixkeeper',
    );
  });
  test('?owner=&repo= names another one', () => {
    assert.equal(
      githubRepo(...at('https://iedame.github.io/nixkeeper/?owner=someone&repo=their-keeper')),
      'someone/their-keeper',
    );
  });
  test('anywhere else, no repository', () => {
    assert.equal(githubRepo(...at('http://127.0.0.1:8765/')), null);
    assert.equal(githubRepo(...at('https://iedame.github.io/')), null);
    assert.equal(githubRepo(...at('https://example.org/nixkeeper/')), null);
  });
  test('withSlash', () => {
    assert.equal(withSlash('https://x/data'), 'https://x/data/');
    assert.equal(withSlash('https://x/data/'), 'https://x/data/');
  });
});
