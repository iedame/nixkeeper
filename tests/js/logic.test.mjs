// The page's rules (page/logic.js). Run: node --test tests/js/
// (part of `nix flake check`, as checks.page).

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
  aheadOnMaster,
  attentionRank,
  buildsWith,
  communityCheck,
  comparedRepos,
  compareVersions,
  computeStatus,
  crc32,
  daysText,
  escapeHtml,
  faviconKey,
  fromMaster,
  githubRepo,
  hasFailure,
  html,
  matchesSearch,
  midway,
  nameMatches,
  nixkeeperEntry,
  onMaster,
  onPlatform,
  pageLinks,
  raw,
  safeUrl,
  shardOf,
  shortAge,
  targetVersion,
  themeFor,
  timeAgo,
  updateTitle,
  versionDiff,
  viewPath,
  viewSlug,
  waitingForChannel,
  withRunStamps,
  withSlash,
} from '../../page/logic.js';

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

describe('master ahead of the channel', () => {
  // wesnoth-devel: Repology knows 1.19.24 (the channel's), master has 1.19.28.
  const wesnoth = (fields = {}) =>
    pkg({
      nixStatus: 'devel',
      nixVersion: '1.19.24',
      refVersion: '1.19.24',
      master: '1.19.28',
      ...fields,
    });

  test('counts as outdated, and waits for the channel', () => {
    assert.equal(aheadOnMaster(wesnoth()), true);
    assert.equal(computeStatus(wesnoth()), 'warn');
    assert.equal(waitingForChannel(wesnoth()), true);
  });
  test("master's version is the one to update to", () => {
    // As the sync now writes it, and as older data has it.
    const synced = wesnoth({ refVersion: '1.19.28', refFromMaster: true });
    for (const p of [synced, wesnoth()]) {
      assert.equal(fromMaster(p), true);
      assert.equal(targetVersion(p), '1.19.28');
    }
  });
  test('a newer known release stays the target, still to do', () => {
    // unciv: master has 4.22.5, but 4.22.6 is out.
    const unciv = outdated({ nixVersion: '4.22.1', refVersion: '4.22.6', master: '4.22.5' });
    assert.equal(fromMaster(unciv), false);
    assert.equal(targetVersion(unciv), '4.22.6');
    assert.equal(waitingForChannel(unciv), false);
  });
  test('not when master matches the channel, or there is no master', () => {
    assert.equal(aheadOnMaster(wesnoth({ master: '1.19.24' })), false);
    assert.equal(computeStatus(wesnoth({ master: '1.19.24' })), 'ok');
    assert.equal(aheadOnMaster(pkg({ nixVersion: '1.0' })), false);
  });
  test("isn't a new release to act on in the tab icon", () => {
    assert.equal(faviconKey([wesnoth()]), 'ok');
  });
});

describe('communityCheck', () => {
  test("a community rule's result, or its failure", () => {
    assert.equal(communityCheck(pkg({ upstream: { version: '2', community: true } })), true);
    const failing = {
      upstream: { since: 'x', reason: 'community rule refused: url must be https://' },
    };
    assert.equal(communityCheck(pkg({ notRefreshed: failing })), true);
  });
  test('your own rule', () => {
    assert.equal(communityCheck(pkg({ upstream: { version: '2' } })), false);
    const failing = { upstream: { since: 'x', reason: 'nothing matches' } };
    assert.equal(communityCheck(pkg({ notRefreshed: failing })), false);
    assert.equal(communityCheck(pkg()), false);
  });
});

describe('matchesSearch', () => {
  const heroic = pkg({
    name: 'heroic',
    attrs: ['heroic', 'heroic-unwrapped'],
    maintainers: ['TomaSajt', 'iedame'],
  });
  test('names, projects and attributes contain the text', () => {
    assert.equal(matchesSearch(heroic, ' Unwrapped '), true);
    assert.equal(matchesSearch(heroic, ''), true);
    assert.equal(matchesSearch(heroic, 'tomas'), false); // handles only with @
  });
  test('@handle: the whole handle, in any case', () => {
    assert.equal(matchesSearch(heroic, '@tomasajt'), true);
    assert.equal(matchesSearch(heroic, '@TomaS'), false);
    assert.equal(matchesSearch(heroic, '@'), true); // still typing
    assert.equal(matchesSearch(pkg(), '@iedame'), false); // not synced yet
  });
  test('@none: no maintainer, not unknown', () => {
    assert.equal(matchesSearch(pkg({ maintainers: [] }), '@none'), true);
    assert.equal(matchesSearch(heroic, '@none'), false);
    assert.equal(matchesSearch(pkg(), '@none'), false);
  });
});

describe('nixkeeperEntry', () => {
  test("its update check's version, ahead when newer", () => {
    const up = { version: '0.48.0', newer: true, inferred: true, repo: 'o/r' };
    assert.deepEqual(nixkeeperEntry(pkg({ upstream: up })), {
      repo: 'nixkeeper',
      version: '0.48.0',
      ahead: true,
      kind: "Worked out from nixpkgs' source",
      where: 'o/r tags',
    });
    const page = { version: '16.0', newer: false, community: true, label: 'www.barebones.com' };
    const entry = nixkeeperEntry(pkg({ upstream: page }));
    assert.equal(entry.ahead, false);
    assert.equal(entry.kind, 'A community update check');
    assert.equal(entry.where, 'www.barebones.com');
    assert.equal(nixkeeperEntry(pkg({ upstream: { version: '2' } })).kind, 'Your update check');
  });
  test('none without a result', () => {
    assert.equal(nixkeeperEntry(pkg()), null);
  });
});

describe('versionDiff', () => {
  test('by whole parts', () => {
    assert.deepEqual(versionDiff('1.19.24', '1.19.28'), { same: '1.19.', from: '24', to: '28' });
    assert.deepEqual(versionDiff('1.9', '1.10'), { same: '1.', from: '9', to: '10' });
    assert.deepEqual(versionDiff('154.0.8037.57', '154.0.8037.92'), {
      same: '154.0.8037.',
      from: '57',
      to: '92',
    });
  });
  test('an unstable version: the date', () => {
    assert.deepEqual(versionDiff('5.1.0-b2-unstable-2022-11-14', '5.1.0-b2-unstable-2026-08-22'), {
      same: '5.1.0-b2-unstable-',
      from: '2022-11-14',
      to: '2026-08-22',
    });
  });
  test('nothing shared, or only something added', () => {
    assert.deepEqual(versionDiff('2.8', '3.0'), { same: '', from: '2.8', to: '3.0' });
    assert.deepEqual(versionDiff('1.2', '1.2.1'), { same: '1.2', from: '', to: '.1' });
  });
  test('a missing version', () => {
    assert.deepEqual(versionDiff('1.0', undefined), { same: '', from: '1.0', to: '' });
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
  test('html escapes everything put in it', () => {
    const title = `<img src=x onerror="alert(1)">'&'`;
    assert.equal(
      String(html`<b title="${title}">${title}</b>`),
      '<b title="&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&#39;&amp;&#39;">' +
        '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&#39;&amp;&#39;</b>',
    );
    // Links: safeUrl, then escaped like the rest.
    assert.equal(
      String(html`<a href="${safeUrl('https://example.org/?a="b"&c')}">`),
      '<a href="https://example.org/?a=&quot;b&quot;&amp;c">',
    );
  });
  test('html keeps markup made with html or raw', () => {
    const name = '<i>x</i>';
    const inner = html`<i>${name}</i>`;
    assert.equal(String(html`<b>${inner}</b>`), '<b><i>&lt;i&gt;x&lt;/i&gt;</i></b>');
    assert.equal(String(html`${raw('<br>')}`), '<br>');
  });
  test('html joins arrays, and leaves out null and undefined only', () => {
    assert.equal(String(html`${['<a>', html`<b>`]}`), '&lt;a&gt;<b>');
    assert.equal(String(html`${null}${undefined}|${0}|${false}`), '|0|false');
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
  test('only names GitHub allows', () => {
    for (const [owner, repo] of [
      ['a"b', 'x'],
      ['someone', '../../evil'],
      ['someone', '..'],
      ['-someone', 'x'],
      ['some/one', 'x'],
      ['someone', 'a b'],
      ['someone', '<script>'],
    ]) {
      const q = new URLSearchParams({ owner, repo });
      assert.equal(
        githubRepo(...at(`https://iedame.github.io/nixkeeper/?${q}`)),
        null,
        `${owner}/${repo}`,
      );
    }
    assert.equal(githubRepo(...at('https://iedame.github.io/%3Cscript%3E/')), null);
    assert.equal(
      githubRepo(...at('https://iedame.github.io/nixkeeper/?owner=a-b&repo=c.d_e-f')),
      'a-b/c.d_e-f',
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

describe('themeFor', () => {
  test('nothing chosen: classic, following the system', () => {
    assert.deepEqual(themeFor(), { palette: 'classic', mode: 'auto' });
    assert.deepEqual(themeFor({ palette: null, mode: null }, null), {
      palette: 'classic',
      mode: 'auto',
    });
  });
  test("the page's default, when the visitor hasn't chosen", () => {
    assert.deepEqual(themeFor({}, 'catppuccin'), { palette: 'catppuccin', mode: 'auto' });
  });
  test("the visitor's choice wins over the page's default", () => {
    assert.deepEqual(themeFor({ palette: 'classic', mode: 'dark' }, 'catppuccin'), {
      palette: 'classic',
      mode: 'dark',
    });
  });
  test('unknown values count as not set', () => {
    assert.deepEqual(themeFor({ palette: 'solarized', mode: 'dim' }, 'catppuccin'), {
      palette: 'catppuccin',
      mode: 'auto',
    });
    assert.deepEqual(themeFor({}, 'nord'), { palette: 'classic', mode: 'auto' });
  });
});

describe('comparedRepos', () => {
  const e = (repo, version, status = 'outdated') => ({ repo, version, status });
  test('newest version first, ties by repository', () => {
    const sorted = comparedRepos([
      e('debian', '1.3.5'),
      e('homebrew', '1.3.8', 'newest'),
      e('aur', '1.3.8', 'newest'),
      e('fedora', '1.3.10'),
    ]);
    assert.deepEqual(
      sorted.map((x) => x.repo),
      ['fedora', 'aur', 'homebrew', 'debian'],
    );
  });
  test('one entry per repository, its newest', () => {
    const sorted = comparedRepos([
      e('alpine_edge', '1.3.7'),
      e('alpine_edge', '1.3.8', 'newest'),
      e('debian', '1.3.5'),
    ]);
    assert.deepEqual(
      sorted.map((x) => `${x.repo} ${x.version}`),
      ['alpine_edge 1.3.8', 'debian 1.3.5'],
    );
  });
  test("versions that don't compare go last", () => {
    const sorted = comparedRepos([e('gentoo', '9999', 'rolling'), e('aur', '1.0', 'newest')]);
    assert.deepEqual(
      sorted.map((x) => x.repo),
      ['aur', 'gentoo'],
    );
  });
  test("doesn't change its input", () => {
    const entries = [e('a', '1'), e('b', '2')];
    comparedRepos(entries);
    assert.equal(entries[0].repo, 'a');
  });
});

describe('updateTitle', () => {
  test("an outdated package: nixpkgs' title for the update", () => {
    assert.equal(
      updateTitle(outdated({ name: 'unciv', nixVersion: '4.22.1', refVersion: '4.22.6' })),
      'unciv: 4.22.1 -> 4.22.6',
    );
  });
  test('none when up to date, or without a newest version', () => {
    assert.equal(updateTitle(pkg({ nixVersion: '1.0' })), null);
    assert.equal(updateTitle(outdated({ refVersion: undefined })), null);
  });
});

describe('midway', () => {
  test("master between the channel and the newest: master's version", () => {
    const pkg = outdated({ nixVersion: '1.0', refVersion: '1.2', masterPR: { to: '1.1' } });
    assert.equal(midway(pkg), '1.1');
    assert.equal(updateTitle({ ...pkg, name: 'p' }), 'p: 1.1 -> 1.2');
  });
  test('none when master already has the newest, or has nothing new', () => {
    assert.equal(
      midway(outdated({ nixVersion: '1.0', refVersion: '1.1', masterPR: { to: '1.1' } })),
      null,
    );
    assert.equal(midway(outdated({ nixVersion: '1.0', refVersion: '1.1' })), null);
    assert.equal(midway(pkg({ nixVersion: '1.1', masterPR: { to: '1.1' } })), null);
  });
});

describe('shards', () => {
  // The same as Python's zlib.crc32 (nixkeeper/datastore.py), or a panel
  // would look for a package in the wrong shard.
  test('crc32 matches zlib', () => {
    assert.equal(crc32(''), 0);
    assert.equal(crc32('wesnoth'), 3265293464);
    assert.equal(crc32('python3.13-ï'), 2328554205); // UTF-8 bytes
  });
  test('shardOf', () => {
    assert.equal(shardOf('pkg0', 4), 1);
    assert.equal(shardOf('wesnoth', 1), 0);
  });
});

describe('pageLinks', () => {
  test('few pages: all of them', () => {
    assert.deepEqual(pageLinks(1, 1), [1]);
    assert.deepEqual(pageLinks(2, 2), [1, 2]);
    assert.deepEqual(pageLinks(1, 6), [1, 2, 3, 4, 5, 6]);
  });
  test('gaps around the current page', () => {
    assert.deepEqual(pageLinks(1, 20), [1, 2, 3, null, 20]);
    assert.deepEqual(pageLinks(10, 20), [1, null, 8, 9, 10, 11, 12, null, 20]);
    assert.deepEqual(pageLinks(20, 20), [1, null, 18, 19, 20]);
  });
  test('a gap of one page shows the page', () => {
    assert.deepEqual(pageLinks(5, 20), [1, 2, 3, 4, 5, 6, 7, null, 20]);
  });
});

describe('withRunStamps', () => {
  const RUN = '2026-10-05T06:00:00+00:00';
  test('puts back the dates left out', () => {
    const row = withRunStamps(
      {
        builds: [{ status: 'ok' }, { status: 'ok', checkedAt: '2026-10-03' }],
        upstream: { version: '2' },
        openPRs: 0,
      },
      RUN,
    );
    assert.deepEqual(
      row.builds.map((b) => b.checkedAt),
      [RUN, '2026-10-03'],
    );
    assert.equal(row.upstream.checkedAt, RUN);
    assert.equal(row.countedAt, RUN);
  });
  test('adds nothing where nothing was', () => {
    assert.deepEqual(withRunStamps({ name: 'a' }, RUN), { name: 'a' });
    assert.deepEqual(withRunStamps({ name: 'a' }, null), { name: 'a' });
  });
});

describe('views (every package)', () => {
  test('viewSlug as datastore.slug', () => {
    assert.equal(viewSlug('Security review'), 'security-review');
    assert.equal(viewSlug('Qt-KDE'), 'qt-kde');
    assert.equal(viewSlug('gaming-team'), 'gaming-team');
  });
  test('viewPath: the narrowest the address asks for', () => {
    assert.equal(viewPath(), 'views/attention.json');
    assert.equal(viewPath({ query: 'firefox' }), 'views/attention.json');
    assert.equal(viewPath({ query: '@Iedame', team: 'Gaming' }), 'views/maintainer/iedame.json');
    assert.equal(viewPath({ query: '@none' }), 'views/maintainer/none.json');
    assert.equal(viewPath({ query: '@' }), 'views/attention.json');
    assert.equal(
      viewPath({ team: 'Security review', list: 'x' }),
      'views/team/security-review.json',
    );
    assert.equal(viewPath({ list: 'gaming-team' }), 'views/list/gaming-team.json');
    assert.equal(viewPath({ set: 'rPackages' }), 'views/set/rPackages.json');
    assert.equal(viewPath({ pkg: 'zlib', query: '@x' }), 'pkg:zlib');
  });
  test('nameMatches leaves out the view shown', () => {
    const names = [
      ['firefox', 'u'],
      ['firefox-esr', 'o'],
      ['thunderbird', 'u'],
    ];
    assert.deepEqual(nameMatches(names, 'FIRE', new Set(['firefox'])), {
      found: [['firefox-esr', 'o']],
      total: 1,
    });
    assert.deepEqual(nameMatches(names, '@fire', new Set()), { found: [], total: 0 });
    assert.equal(nameMatches(names, 'f', new Set(), 1).found.length, 1);
  });
  test('nameMatches: the closest first', () => {
    const names = [
      ['emacsPackages.helm-firefox', 'u'],
      ['firefox-esr', 'u'],
      ['librewolf-firefox', 'u'],
      ['firefox', 'u'],
      ['python3Packages.firefox', 'u'],
    ];
    assert.deepEqual(
      nameMatches(names, 'firefox', new Set()).found.map(([n]) => n),
      [
        'firefox',
        'firefox-esr',
        'librewolf-firefox',
        'emacsPackages.helm-firefox',
        'python3Packages.firefox',
      ],
    );
  });
});
