const NIX_REPO = 'nix_unstable';

// Where the data (index.json and the per-project files) lives, as a URL
// ending in "/". First of:
//   1. ?data=<url> in the address: for testing; same site only, so a link
//      can't point someone's page at data from elsewhere
//   2. <meta name="nixkeeper-data" content="<url>"> in index.html: a host
//      that keeps the data somewhere else sets it
//   3. data/ next to the page, when one server serves both (self-hosting)
//   4. on a GitHub Pages project site (https://<owner>.github.io/<repo>/),
//      the repo's data branch; ?owner=...&repo=... names another repo
async function findDataBase() {
  const params = new URLSearchParams(location.search);
  const asked = params.get('data');
  if (asked) {
    const url = new URL(asked, location.href);
    if (url.origin === location.origin) return withSlash(url.href);
  }
  const meta = document.querySelector('meta[name="nixkeeper-data"]')?.content;
  if (meta) return withSlash(new URL(meta, location.href).href);
  try {
    const res = await fetch('data/index.json', { method: 'HEAD', cache: 'no-store' });
    if (res.ok) return new URL('data/', location.href).href;
  } catch {
    // not served here: try GitHub
  }
  const repo = githubRepo(params);
  return repo ? `https://raw.githubusercontent.com/${repo}/data/data/` : null;
}

const withSlash = (url) => (url.endsWith('/') ? url : `${url}/`);

// "owner/repo" from ?owner=&repo=, or from a GitHub Pages project site's
// address.
function githubRepo(params) {
  if (params.get('owner') && params.get('repo'))
    return `${params.get('owner')}/${params.get('repo')}`;
  const host = location.hostname;
  const owner = host.endsWith('.github.io') ? host.split('.')[0] : null;
  const seg = location.pathname.split('/').filter(Boolean)[0] || null;
  return owner && seg ? `${owner}/${seg}` : null;
}

// The footer links to nixkeeper itself; a copy of it on GitHub Pages (its
// own package lists) also links to those lists.
const UPSTREAM = 'iedame/nixkeeper';
function addListsLink() {
  const repo = githubRepo(new URLSearchParams(location.search));
  if (!repo || repo === UPSTREAM) return;
  const a = document.createElement('a');
  a.className = 'files-link';
  a.href = `https://github.com/${repo}/tree/HEAD/package-lists`;
  a.target = '_blank';
  a.rel = 'noopener';
  a.textContent = "this page's package lists ↗";
  document.getElementById('about')?.prepend(a);
}
addListsLink();

let dataBase = null; // set by loadIndex
const dataUrl = (path) => new URL(path, dataBase).href;
const detailCache = new Map(); // name -> parsed per-package Repology JSON
let packages = [];
let checkedAt = null;
let activeFilter = 'all'; // 'all' | 'warn' | 'failed' | 'vuln'
let sortAZ = false; // default order puts what needs attention first
let platformFilter = null; // null | 'linux' | 'darwin', combined with activeFilter
// null, or a list from package-lists/ ("maintained", "gaming-team", ...):
// ?list=gaming-team is a page of just that list's packages, to share.
let listFilter = null;
const inList = (pkg) => !listFilter || (pkg.lists || []).includes(listFilter);
// Every list some package is on: "maintained" first, as the sync sorts them.
function allLists() {
  const seen = [];
  for (const p of packages) for (const l of p.lists || []) if (!seen.includes(l)) seen.push(l);
  return seen.sort((a, b) =>
    a === 'maintained' ? -1 : b === 'maintained' ? 1 : a.localeCompare(b),
  );
}

// "any platform" (no restriction in nixpkgs) counts as both.
const PLATFORMS = {
  linux: { label: 'Linux', param: 'linux' },
  darwin: { label: 'macOS', param: 'macos' },
};
function onPlatform(pkg, key) {
  return pkg.platforms === null || Boolean(pkg.platforms?.[key]);
}
function inPlatform(pkg) {
  return !platformFilter || onPlatform(pkg, platformFilter);
}
// The sync runs daily; older than this means runs are failing or GitHub has
// paused the schedule (it does after 60 days without commits).
const STALE_AFTER_HOURS = 48;

// `param` is how each filter appears in the page address (?filter=outdated).
const FILTERS = {
  all: { label: 'tracked', test: () => true },
  warn: {
    label: 'outdated',
    param: 'outdated',
    color: 'var(--warn)',
    test: (p) => computeStatus(p) === 'warn',
  },
  failed: { label: 'failed', param: 'failed', color: 'var(--danger)', test: (p) => hasFailure(p) },
  vuln: {
    label: 'flagged vulnerable',
    param: 'vulnerable',
    color: 'var(--danger)',
    test: (p) => p.nixVulnerable,
  },
};

// Everything shown in red: not found in nixpkgs, or a build or update
// failure reported.
function hasFailure(pkg) {
  return (
    computeStatus(pkg) === 'missing' || failedBuilds(pkg).length > 0 || Boolean(pkg.updateFailure)
  );
}

// Hydra builds with a status, on the selected platform only while one is.
function buildsWith(pkg, status) {
  return (pkg.builds || []).filter(
    (b) => b.status === status && (!platformFilter || b.system.endsWith(`-${platformFilter}`)),
  );
}
const failedBuilds = (pkg) => buildsWith(pkg, 'failed');

// Version order as the sync compares them (nixkeeper/versions.py): numbers
// as numbers, a letter part before a number (1.0rc1 < 1.0.1).
function compareVersions(a, b) {
  const parts = (v) =>
    (v.match(/\d+|[A-Za-z]+/g) || []).map((p) => (/^\d/.test(p) ? [1, +p, ''] : [0, 0, p]));
  const [pa, pb] = [parts(a), parts(b)];
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if (!pa[i] || !pb[i]) return pa[i] ? 1 : -1;
    for (let j = 0; j < 3; j++) if (pa[i][j] !== pb[i][j]) return pa[i][j] < pb[i][j] ? -1 : 1;
  }
  return 0;
}

// The version master has, when ahead of the channel: Hydra's build there, or
// what an update PR merged into master brings (before Hydra has built it),
// whichever is higher (on_master in nixkeeper/changes.py).
function onMaster(pkg) {
  const versions = [pkg.master, pkg.masterPR?.to].filter(Boolean);
  return versions.sort(compareVersions).pop() || null;
}

// Outdated, but master already has the target version (or newer): the update
// is merged and waits for nixos-unstable, usually a few days (see
// waiting_for_channel in nixkeeper/changes.py).
function waitingForChannel(pkg) {
  return (
    computeStatus(pkg) === 'warn' &&
    Boolean(onMaster(pkg)) &&
    compareVersions(pkg.refVersion || '', onMaster(pkg)) <= 0
  );
}

// Where the package's update stands on GitHub, in GitHub's own colors:
// "on master" (merged, purple) while waiting for the channel, else an open
// update PR (green; grey while a draft). A link to the PR when it's known.
function prBadge(pkg) {
  const badge = (cls, text, title, pr) =>
    pr
      ? ` <a class="badge ${cls}" href="${href(pr.url)}" target="_blank" rel="noopener" title="${escapeHtml(title)}">${text}</a>`
      : ` <span class="badge ${cls}" title="${escapeHtml(title)}">${text}</span>`;
  if (waitingForChannel(pkg)) {
    const pr = pkg.masterPR;
    return badge(
      'onmaster',
      'on master',
      `master already has ${onMaster(pkg)}: merged${pr ? ` in #${pr.number} (${pr.title})` : ''}, waiting for nixos-unstable to catch up (usually a few days)`,
      pr,
    );
  }
  const pr = pkg.openPR;
  if (!pr) return '';
  const behind =
    pkg.refVersion && compareVersions(pr.to, pkg.refVersion) < 0
      ? ` (the newest is ${pkg.refVersion})`
      : '';
  return badge(
    pr.draft ? 'prdraft' : 'propen',
    `PR #${pr.number}`,
    `${pr.draft ? 'Draft update PR' : 'Update PR waiting for review'}: ${pr.title}${behind}`,
    pr,
  );
}

// What an update would change to, as the table shows it: for an unstable
// version with the same base ("5.1.0-b2-unstable-2022-11-14"), just the new
// date, which is all that differs; anything else in full.
function versionChange(from, to) {
  const unstable = /^(.*-unstable-)(\d{4}-\d{2}-\d{2})$/;
  const a = unstable.exec(from || '');
  const b = unstable.exec(to || '');
  return a && b && a[1] === b[1] ? b[2] : to;
}

// Default order: failed, then outdated (longest outdated first), then
// outdated but already fixed on master, then the rest; otherwise
// alphabetical (the index arrives sorted by name and Array.sort is stable).
function attentionRank(pkg) {
  if (hasFailure(pkg)) return 0;
  if (waitingForChannel(pkg)) return 1.5;
  if (computeStatus(pkg) === 'warn') return 1;
  return 2;
}

// Filter, search and sort live in the page address, so a view survives a
// reload and can be bookmarked or shared. Other parameters (owner, repo) are
// left alone.
function readViewFromUrl() {
  const params = new URLSearchParams(location.search);
  activeFilter =
    Object.keys(FILTERS).find(
      (k) => FILTERS[k].param && FILTERS[k].param === params.get('filter'),
    ) || 'all';
  document.getElementById('search').value = params.get('q') || '';
  sortAZ = params.get('sort') === 'az';
  platformFilter =
    Object.keys(PLATFORMS).find((k) => PLATFORMS[k].param === params.get('platform')) || null;
  // Any name: which lists exist is only known once the data has loaded.
  listFilter = params.get('list') || null;
  document.getElementById('sortBtn').setAttribute('aria-pressed', sortAZ);
}

function writeViewToUrl() {
  const params = new URLSearchParams(location.search);
  const q = document.getElementById('search').value.trim();
  const set = (k, v) => (v ? params.set(k, v) : params.delete(k));
  set('filter', FILTERS[activeFilter].param);
  set('q', q);
  set('sort', sortAZ ? 'az' : '');
  set('platform', platformFilter && PLATFORMS[platformFilter].param);
  set('list', listFilter);
  const query = params.toString();
  // replaceState, not pushState: typing a search shouldn't fill the history.
  history.replaceState(null, '', location.pathname + (query ? `?${query}` : '') + location.hash);
}

async function loadIndex() {
  const content = document.getElementById('content');
  dataBase = dataBase || (await findDataBase());
  if (!dataBase) {
    content.innerHTML = `<div class="error">
      Couldn't find the data to show.<br>
      Serve it as <code>data/</code> next to this page, set it with
      <code>&lt;meta name="nixkeeper-data"&gt;</code> in <code>index.html</code>,
      or open this from its GitHub Pages site.
    </div>`;
    return;
  }
  try {
    const res = await fetch(dataUrl('index.json'), { cache: 'no-store' });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    packages = data.packages || [];
    checkedAt = data.checkedAt || null;
    document.getElementById('search').disabled = false;
    render(currentFiltered());
  } catch {
    content.innerHTML = `<div class="error">
      Couldn't load <code>${escapeHtml(dataUrl('index.json'))}</code>.<br>
      Check that the sync has run at least once (and, on GitHub, that the repo is public).
    </div>`;
  }
}

// Follows Repology's statuses. "legacy" means outdated while the same repo
// carries a newer version in another package (e.g. a beta overtaken by the
// stable release), so it counts as outdated. Whether a row is a devel variant
// comes separately from pkg.devel and only shades its "devel" badge.
function computeStatus(pkg) {
  if (pkg.nixStatus === 'missing') return 'missing';
  if (pkg.nixStatus === 'outdated' || pkg.nixStatus === 'legacy') return 'warn';
  // nixkeeper's own update check found a release Repology hasn't seen.
  if (pkg.upstream?.newer) return 'warn';
  if (pkg.nixStatus === 'newest' || pkg.nixStatus === 'unique' || pkg.nixStatus === 'devel')
    return 'ok';
  return 'neutral';
}

// How long a package has been outdated, one letter per unit: <1 d, 3 d, 2 w,
// 5 m (months), 2 y.
function shortAge(iso) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400e3);
  if (days < 1) return '<1 d';
  if (days < 7) return `${days} d`;
  if (days < 30) return `${Math.floor(days / 7)} w`;
  if (days < 365) return `${Math.min(11, Math.floor(days / 30))} m`; // 360-364 days: not "12 m" before "1 y"
  return `${Math.floor(days / 365)} y`;
}

function daysText(iso) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400e3);
  return days < 1 ? 'today' : days === 1 ? '1 day' : `${days} days`;
}

function longDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function timeAgo(iso) {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function renderStats() {
  // Counts follow the platform and list filters, so "outdated" means
  // outdated on macOS, or on the gaming-team list, while that's selected.
  const base = packages.filter((p) => inPlatform(p) && inList(p));
  renderLists();
  const buttons = Object.entries(FILTERS)
    .map(([key, f]) => {
      const count = base.filter(f.test).length;
      // "vulnerable" only shows up when something is actually flagged.
      if (key === 'vuln' && !count && activeFilter !== 'vuln') return '';
      const pressed = activeFilter === key;
      return `<button class="stat-btn" data-filter="${key}" aria-pressed="${pressed}"
      ${!count && key !== 'all' && !pressed ? 'disabled' : ''}>
      <b${f.color ? ` style="color:${f.color}"` : ''}>${count}</b> ${f.label}</button>`;
    })
    .join('');
  const stale =
    !checkedAt || Date.now() - new Date(checkedAt).getTime() > STALE_AFTER_HOURS * 3600e3;
  const platformChip = platformFilter
    ? `<button class="plat-filter" title="Show all platforms">${PLATFORMS[platformFilter].label} only ✕</button>`
    : '';
  document.getElementById('stats').innerHTML =
    `${buttons}${platformChip}<span class="checked${stale ? ' stale' : ''}"
    ${stale ? 'title="The daily sync hasn\'t updated the data in over 2 days. Check where it runs (on GitHub: the Actions tab)."' : ''}>
    checked ${timeAgo(checkedAt)}${stale ? ' — sync may be failing' : ''}</span>`;
}

// The lists from package-lists/, as a second row of filters. Hidden when
// there's only one (or data from before lists existed).
function renderLists() {
  const el = document.getElementById('lists');
  const names = allLists();
  if (listFilter && !names.includes(listFilter)) names.push(listFilter); // e.g. a renamed list
  if (names.length < 2) {
    el.innerHTML = '';
    return;
  }
  const base = packages.filter(inPlatform);
  el.innerHTML = `<span class="lists-label">lists</span>${names
    .map((name) => {
      const pressed = listFilter === name;
      const count = base.filter((p) => (p.lists || []).includes(name)).length;
      return `<button class="stat-btn" type="button" data-list="${escapeHtml(name)}" aria-pressed="${pressed}"
        title="${pressed ? 'Show every list' : `Show only the ${escapeHtml(name)} list (shareable: it's in the address)`}">
        <b>${count}</b> ${escapeHtml(name)}</button>`;
    })
    .join('')}`;
}

// A link from data, only if it's a web address: escaping stops markup, but
// not a javascript: link, which would run when clicked. '' otherwise.
function safeUrl(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === 'https:' || protocol === 'http:' ? url : '';
  } catch {
    return '';
  }
}

// safeUrl, ready for an href.
function href(url) {
  return escapeHtml(safeUrl(url));
}

function escapeHtml(s) {
  return (s || '')
    .toString()
    .replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
}

function render(list) {
  renderStats();
  const content = document.getElementById('content');
  if (!list.length) {
    content.innerHTML = `<div class="empty">No packages match${activeFilter !== 'all' && !document.getElementById('search').value.trim() ? ` the “${FILTERS[activeFilter].label}” filter` : ''}.</div>`;
    return;
  }
  content.innerHTML = `<div class="wrap"><table>
    <thead><tr>
      <th style="padding-left:10px">Package</th><th>nixpkgs unstable</th><th>open on GitHub</th><th>build failures</th><th>update failures</th><th aria-hidden="true"></th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table></div>`;

  const rowsEl = document.getElementById('rows');
  list.forEach((pkg) => {
    const st = computeStatus(pkg);
    const verCell =
      st === 'missing'
        ? `<span class="badge missing">not packaged</span>`
        : `<span class="v">${escapeHtml(pkg.nixVersion)}</span>${st === 'warn' ? ` <span class="ref mono" title="${escapeHtml(pkg.refVersion || '')}">→ ${escapeHtml(versionChange(pkg.nixVersion, pkg.refVersion) || '?')}</span>` : ''}${st === 'warn' && pkg.outdatedSince ? ` <span class="age${waitingForChannel(pkg) ? ' merged' : ''}" title="Outdated since ${escapeHtml(longDate(pkg.outdatedSince))}">· ${shortAge(pkg.outdatedSince)}</span>` : ''}${prBadge(pkg)}${st === 'neutral' ? ` <span class="badge neutral">${escapeHtml(pkg.nixStatus)}</span>` : ''}${pkg.devel ? ` <span class="badge devel ${st}">devel</span>` : ''}${pkg.nixVulnerable ? ' <span class="badge vuln">vulnerable</span>' : ''}${pkg.staleSince ? ` <span class="badge neutral" title="Repology lookup failed on the last run; this is data from ${escapeHtml(new Date(pkg.staleSince).toLocaleString())}">not refreshed</span>` : ''}${notRefreshed(pkg, 'upstream') ? ` <span class="badge neutral" title="${escapeHtml(staleText(notRefreshed(pkg, 'upstream'), "nixkeeper's update check failing"))}. Fix it in package-lists/update-checks.nix.">check failing</span>` : ''}`;

    const tr = document.createElement('tr');
    tr.className = 'row';
    tr.tabIndex = 0;
    tr.innerHTML = `
      <td class="c-name"><div class="pkg-name"><span class="status-dot ${waitingForChannel(pkg) ? 'merged' : st}"${waitingForChannel(pkg) ? ' title="Update merged: on master, waiting for nixos-unstable"' : ''}></span><span class="n">${escapeHtml(pkg.name)}</span>${platformTags(pkg)}</div></td>
      <td class="c-ver ver mono">${verCell}</td>
      <td class="c-gh${pkg.openPRs || pkg.openIssues ? '' : ' quiet'}">${githubLinks(pkg)}</td>
      <td class="c-build">${buildCell(pkg)}</td>
      <td class="c-update">${updateCell(pkg)}</td>
      <td class="c-chev"><span class="chev">▸</span></td>
    `;

    const detail = document.createElement('tr');
    detail.className = 'detail';
    detail.innerHTML = `<td colspan="6"><div class="detail-inner">
      <div class="nix-line">Loading detail…</div>
    </div></td>`;

    // One panel under the row, showing the package details (clicking the
    // row), its builds or its latest update attempt (clicking those cells).
    // Clicking what's shown closes it; clicking something else switches.
    const inner = detail.querySelector('.detail-inner');
    const panelBtns = tr.querySelectorAll('.failure-btn');
    const toggle = async (mode) => {
      const closing = tr.classList.contains('open') && detail.dataset.mode === mode;
      tr.classList.toggle('open', !closing);
      detail.classList.toggle('open', !closing);
      detail.dataset.mode = closing ? '' : mode;
      for (const btn of panelBtns) {
        btn.setAttribute('aria-expanded', !closing && btn.dataset.kind === mode);
      }
      if (closing) return;
      if (mode === 'build') fillBuilds(pkg, inner);
      else if (mode === 'update') fillUpdate(pkg, inner);
      else await fillDetail(pkg, inner);
    };

    for (const btn of panelBtns) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation(); // not the row's own click
        toggle(btn.dataset.kind);
      });
    }

    for (const a of tr.querySelectorAll('.gh-btn, a.badge')) {
      a.addEventListener('click', (e) => e.stopPropagation()); // open the link, not the row
    }
    for (const btn of tr.querySelectorAll('button.plat')) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation(); // don't expand the row
        // Clicking the active platform again shows all platforms.
        platformFilter = platformFilter === btn.dataset.platform ? null : btn.dataset.platform;
        render(currentFiltered());
      });
    }

    tr.addEventListener('click', () => toggle('info'));
    tr.addEventListener('keydown', (e) => {
      if (e.target === tr && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        tr.click();
      }
    });

    rowsEl.appendChild(tr);
    rowsEl.appendChild(detail);
  });
}

// A source the last sync couldn't refresh ("builds", "update", "upstream"):
// what's shown is from before `since`. null if it refreshed fine.
const notRefreshed = (pkg, source) => pkg.notRefreshed?.[source] || null;
const staleText = (info, what) =>
  `${what} since ${longDate(info.since)} (${daysText(info.since)}): ${info.reason}`;
// The same, as a line at the top of a panel.
const staleNote = (info, what, after) =>
  info ? `<div class="stale-note">⚠ ${escapeHtml(staleText(info, what))}. ${after}</div>` : '';

// quiet: nothing that needs attention, so the phone layout leaves it out.
function failureButton(kind, dot, text, extra = '', stale = null, quiet = false) {
  return `<button class="failure-btn${dot === 'missing' ? ' failing' : ''}" type="button" data-kind="${kind}"${quiet && !stale ? ' data-quiet' : ''} ${extra}>
    <span class="status-dot ${dot}"></span><span class="cell-label">${kind}:</span>${text}${
      stale
        ? ` <span class="stale-tag" title="${escapeHtml(staleText(stale, 'Not refreshed'))}">not refreshed</span>`
        : ''
    }</button>`;
}

// Whether Hydra built this at all: not for unfree packages, nor ones nixpkgs
// keeps off Hydra (hydraPlatforms).
function hydraBuildsIt(pkg) {
  return !pkg.unfree && pkg.builds.some((b) => b.status !== 'notBuilt');
}

function buildCell(pkg) {
  if (!pkg.builds) return '<span class="failure-na" title="Not in nixpkgs">—</span>';
  const button = (dot, text, quiet = false) =>
    failureButton(
      'build',
      dot,
      text,
      'aria-expanded="false" title="Show Hydra builds"',
      notRefreshed(pkg, 'builds'),
      quiet,
    );
  if (failedBuilds(pkg).length) return button('missing', 'failure reported');
  // Known failures: shown, but not counted as failed.
  if (buildsWith(pkg, 'broken').length) return button('warn', 'marked broken');
  if (!hydraBuildsIt(pkg)) return button('neutral', 'not built by Hydra', true);
  return button('ok', 'none reported', true);
}

// nixpkgs-update's latest attempt. `update` is null when the bot never tried
// and missing for packages not in nixpkgs.
function updateCell(pkg) {
  if (pkg.update === undefined) return '<span class="failure-na" title="Not in nixpkgs">—</span>';
  const button = (dot, text, quiet = false) =>
    failureButton(
      'update',
      dot,
      text,
      'aria-expanded="false" title="Show the latest nixpkgs-update attempt"',
      notRefreshed(pkg, 'update'),
      quiet,
    );
  if (pkg.updateFailure) return button('missing', 'failure reported');
  // The bot's last attempt failed, but nixpkgs has moved on since: not a
  // failure anymore, though the next attempt may well break the same way.
  if (pkg.update?.outcome === 'superseded') return button('neutral', 'superseded');
  // A newer version the bot has no way to update to: not a failure, but it
  // needs a manual update (or an updateScript).
  if (pkg.update?.outcome === 'cantUpdate') return button('warn', "can't update");
  if (pkg.update === null) return button('neutral', 'not attempted', true);
  return button('ok', 'none reported', true);
}

const prLink = (n, text) =>
  `<a class="files-link" href="https://github.com/NixOS/nixpkgs/pull/${n}" target="_blank" rel="noopener">${text}</a>`;
const UPDATE_OUTCOME = {
  failed: { dot: 'missing', text: () => 'failed' },
  // nixpkgs has moved on since the attempt (updated another way): in the
  // channel, or merged on master and not in the channel yet. Or a manual rule
  // (package-lists/ignored-updates.nix) ignores the version it tried.
  superseded: {
    dot: 'neutral',
    text: (u, pkg) => {
      const what = u.supersededOutcome === 'cantUpdate' ? "couldn't update it" : 'failed';
      return u.supersededOn === 'ignored'
        ? `failed trying <span class="mono">${escapeHtml(u.to)}</span>, a version ignored by a manual rule: ${escapeHtml(u.reason)}`
        : u.supersededOn === 'master'
          ? `${what}, but master already has <span class="mono">${escapeHtml(onMaster(pkg))}</span> (merged, waiting for nixos-unstable)`
          : `${what}, but nixpkgs has moved on to <span class="mono">${escapeHtml(pkg.nixVersion)}</span> since`;
    },
  },
  // Every way the bot has of updating a package declined (the excerpt says
  // why): the update needs doing by hand, or an updateScript.
  cantUpdate: {
    dot: 'warn',
    text: () =>
      "couldn't update it: none of the bot's ways of updating a package apply here. Update it by hand, or give the package an updateScript so the bot can next time",
  },
  prOpened: { dot: 'ok', text: (u) => `opened ${prLink(u.pr, `PR #${u.pr} ↗`)}` },
  prExists: {
    dot: 'ok',
    text: (u) => `a PR was already open${u.pr ? ` (${prLink(u.pr, `#${u.pr} ↗`)})` : ''}`,
  },
  noChange: { dot: 'ok', text: () => 'nothing to update' },
  other: { dot: 'neutral', text: () => 'finished without a recognisable result' },
};

function fillUpdate(pkg, el) {
  const u = pkg.update;
  const stale = staleNote(
    notRefreshed(pkg, 'update'),
    'Not refreshed',
    'Showing the last known attempt.',
  );
  if (!u) {
    el.innerHTML = `${stale}<div class="nix-line">nixpkgs-update hasn't tried to update this package (it may have no update source it understands).</div>`;
    return;
  }
  const dir = u.log.slice(0, u.log.lastIndexOf('/') + 1); // every attempt's log
  // A plain day: read as midday UTC, so no time zone moves it to the day before.
  const day = `${u.date}T12:00:00Z`;
  // "0 -> 1" means the package's updateScript picks the version.
  const versions =
    u.from && !(u.from === '0' && u.to === '1')
      ? ` · <span class="mono">${escapeHtml(u.from)} → ${escapeHtml(u.to)}</span>`
      : '';
  const o = UPDATE_OUTCOME[u.outcome] || UPDATE_OUTCOME.other;
  el.innerHTML = `${stale}
    <div class="nix-line">Latest nixpkgs-update attempt${(pkg.attrs || []).length > 1 ? ` at <span class="mono">${escapeHtml(u.attr)}</span>` : ''} · ${escapeHtml(longDate(day))} (${shortAge(day)} ago)${versions}</div>
    <div class="build-list"><div class="build-line">
      <span class="status-dot ${o.dot}"></span><span class="st ${o.dot}">${o.text(u, pkg)}</span>
    </div></div>
    ${u.excerpt?.length ? `<pre class="log-excerpt mono">${u.excerpt.map(escapeHtml).join('\n')}</pre>` : ''}
    <div class="detail-row">
      <a class="files-link" href="${href(u.log)}" target="_blank" rel="noopener">log ↗</a>
      <a class="files-link" href="${href(dir)}" target="_blank" rel="noopener">all attempts ↗</a>
    </div>`;
}

const HYDRA = 'https://hydra.nixos.org';
const BUILD_STATUS = {
  ok: { dot: 'ok', text: 'built OK' },
  failed: { dot: 'missing', text: 'failed' },
  broken: { dot: 'warn', text: 'marked broken in nixpkgs' },
  dependency: { dot: 'warn', text: "didn't build: a dependency failed" },
  unfinished: { dot: 'warn', text: "didn't finish (timed out or aborted)" },
  notBuilt: { dot: 'neutral', text: 'not built by Hydra on this platform' },
  unknown: { dot: 'neutral', text: "couldn't check Hydra on the last run" },
};

function buildLine(pkg, b) {
  const s = BUILD_STATUS[b.status] || BUILD_STATUS.unknown;
  const multi = (pkg.attrs || []).length > 1;
  // The versions only when they differ: the same version means something else
  // broke it (a dependency, the toolchain), not the update.
  const versionsDiffer = b.version && b.lastSuccessVersion && b.version !== b.lastSuccessVersion;
  const at = versionsDiffer && b.status === 'failed' ? ` at ${escapeHtml(b.version)}` : '';
  let lastGood = '';
  if (versionsDiffer) {
    const v = escapeHtml(b.lastSuccessVersion);
    lastGood = b.lastSuccessBuild
      ? ` at <a href="${HYDRA}/build/${b.lastSuccessBuild}" target="_blank" rel="noopener">${v} ↗</a>,`
      : ` at ${v},`;
  }
  const since =
    'lastSuccess' in b
      ? `<span class="since">${b.lastSuccess ? `last succeeded${lastGood} ${escapeHtml(longDate(b.lastSuccess))} (${shortAge(b.lastSuccess)} ago)` : 'never built successfully'}</span>`
      : '';
  let links = '';
  if (b.status === 'failed') {
    links = `<a class="files-link" href="${HYDRA}/build/${b.build}/log" target="_blank" rel="noopener">log ↗</a>${since}`;
  } else if (b.status === 'dependency' || b.status === 'unfinished') {
    links = `<a class="files-link" href="${HYDRA}/build/${b.build}" target="_blank" rel="noopener">build ${b.build} ↗</a>${since}`;
  } else if (b.status === 'broken') {
    // Where to fix it: the package's source, at the line nixpkgs points to.
    links = `${since}${safeUrl(pkg.source) ? `<a class="files-link" href="${href(pkg.source)}" target="_blank" rel="noopener">source ↗</a>` : ''}`;
  } else if (b.build) {
    links = `<a class="files-link" href="${HYDRA}/build/${b.build}" target="_blank" rel="noopener">build ${b.build} ↗</a>`;
  }
  return `<div class="build-line">
    <span class="status-dot ${s.dot}"></span>
    <span class="mono sys">${escapeHtml(b.system)}</span>
    ${multi ? `<span class="mono attr">${escapeHtml(b.attr)}</span>` : ''}
    <span class="st ${s.dot}">${s.text}${at}</span>${links}
  </div>`;
}

function fillBuilds(pkg, el) {
  const jobset = `<span class="mono">nixpkgs/unstable</span>`;
  let body;
  if (pkg.unfree) {
    body = `<div class="nix-line">Hydra doesn't build unfree packages, so there are no build results for this one.</div>`;
  } else if (!hydraBuildsIt(pkg)) {
    body = `<div class="nix-line">Hydra doesn't build this package (nixpkgs may exclude it with <span class="mono">hydraPlatforms</span>).</div>`;
  } else {
    const darwin = pkg.platforms === null || pkg.platforms?.darwin;
    body = `<div class="nix-line">Hydra builds of nixpkgs master (jobset ${jobset})</div>
      <div class="build-list">${pkg.builds.map((b) => buildLine(pkg, b)).join('')}</div>
      ${darwin ? '<div class="build-note">x86_64-darwin is no longer built by nixpkgs.</div>' : ''}`;
  }
  const jobLinks = (pkg.builds || [])
    .filter((b) => b.status !== 'notBuilt')
    .map(
      (b) =>
        `<a class="files-link" href="${HYDRA}/job/nixpkgs/unstable/${encodeURIComponent(`${b.attr}.${b.system}`)}" target="_blank" rel="noopener">${escapeHtml(pkg.attrs.length > 1 ? `${b.attr}.${b.system}` : b.system)} job ↗</a>`,
    )
    .join('');
  const stale = staleNote(
    notRefreshed(pkg, 'builds'),
    'Not refreshed',
    'Showing the last known results.',
  );
  el.innerHTML = `${stale}${body}${jobLinks ? `<div class="detail-row">${jobLinks}</div>` : ''}`;
}

// From nixpkgs meta.platforms; null means nixpkgs doesn't restrict it.
function platformTags(pkg) {
  const pl = pkg.platforms;
  if (pl === undefined) return '';
  if (pl === null)
    return `<span class="plat any" title="nixpkgs doesn't restrict its platforms">any platform</span>`;
  return Object.entries(PLATFORMS)
    .filter(([key]) => pl[key])
    .map(
      ([key, p]) =>
        `<button class="plat" type="button" data-platform="${key}" aria-pressed="${platformFilter === key}"
      title="${platformFilter === key ? 'Show all platforms' : `Show only packages available on ${p.label}`}">${p.label}</button>`,
    )
    .join('');
}

// Open nixpkgs PRs / issues with the package's attribute name in the title. Counts come from
// the fetch script's GitHub search; without them the buttons are plain links.
function githubLinks(pkg) {
  const term = pkg.searchTerm || pkg.name;
  const link = (kind, path, label, count) => {
    const q = encodeURIComponent(`is:${kind} state:open in:title ${term}`);
    return `<a class="gh-btn" href="https://github.com/NixOS/nixpkgs/${path}?q=${q}" target="_blank" rel="noopener"
      title="Open nixpkgs ${label} with ${escapeHtml(term)} in the title">${label}${count != null ? ` <b>${count}</b>` : ''}</a>`;
  };
  return `<span class="gh-links">${link('pr', 'pulls', 'PRs', pkg.openPRs)}${link('issue', 'issues', 'issues', pkg.openIssues)}</span>`;
}

// "…/pkgs/by-name/we/wesnoth/package.nix#L147" -> "package.nix"
function sourceFileName(url) {
  return url.split('#')[0].split('/').pop();
}

async function fillDetail(pkg, el) {
  // Raw Repology data is stored per project, under a file-name-safe version
  // of its name (python:requests -> python_requests.json).
  const file = pkg.dataFile || `${pkg.project || pkg.name}.json`;
  let entries = detailCache.get(file);
  if (!entries) {
    try {
      const res = await fetch(dataUrl(encodeURIComponent(file)), { cache: 'no-store' });
      entries = res.ok ? await res.json() : [];
      detailCache.set(file, entries);
    } catch {
      entries = [];
    }
  }

  const others = entries.filter((e) => e.repo !== NIX_REPO);
  const homepage = safeUrl(pkg.homepage);

  const st = computeStatus(pkg);
  const up = pkg.upstream;
  // "in the wesnoth/wesnoth tags" or "on www.barebones.com".
  const upLabel = up ? escapeHtml(up.label || `${up.repo} tags`) : '';
  const upLink = up
    ? `${up.repo ? 'in the' : 'on'} ${safeUrl(up.url) ? `<a class="files-link" href="${href(up.url)}" target="_blank" rel="noopener">${upLabel} ↗</a>` : upLabel}`
    : '';
  const since = pkg.outdatedSince
    ? ` — outdated since ${escapeHtml(longDate(pkg.outdatedSince))} (${daysText(pkg.outdatedSince)})`
    : '';
  const repologyOutdated = ['outdated', 'legacy'].includes(pkg.nixStatus);
  // A branch check (unstable versions): how many commits nixpkgs is behind,
  // and what makes that count as outdated ("90 days or 50 commits").
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const behind = up?.behind ? `${plural(up.behind, 'newer commit')}` : '';
  const limits = up?.outdatedAfter
    ? [
        up.outdatedAfter.days != null && `one has waited ${plural(up.outdatedAfter.days, 'day')}`,
        up.outdatedAfter.commits != null && `there are ${up.outdatedAfter.commits}`,
      ]
        .filter(Boolean)
        .join(' or ')
    : '';
  // When the update check is what makes it outdated, say where the newer
  // version came from, and how it compares with Repology.
  const upstreamLine = () =>
    `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>; nixkeeper's update check found <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(up.version)}</span> ${upLink}${
      pkg.refVersion !== up.version
        ? `; Repology's newest is <span class="mono">${escapeHtml(pkg.refVersion)}</span>`
        : repologyOutdated
          ? ''
          : up.commit
            ? ` (${behind || 'newer commits'}; Repology only tracks releases, so it can't tell)`
            : ", which Repology doesn't count as newest yet"
    }${since}`;
  // A check that can't refresh needs fixing in nixkeeper, so the details say
  // so plainly, with the last result it's still using.
  const failing = notRefreshed(pkg, 'upstream');
  const checkNote = failing
    ? `<div class="stale-note">⚠ ${escapeHtml(staleText(failing, "nixkeeper's update check has been failing"))}.${
        up
          ? ` Still using its last result: <span class="mono">${escapeHtml(up.version)}</span>${up.checkedAt ? ` (${escapeHtml(longDate(up.checkedAt))})` : ''}.`
          : ' It has no result yet.'
      } Fix it in <span class="mono">package-lists/update-checks.nix</span>.</div>`
    : '';
  const nixLine = up?.newer
    ? upstreamLine()
    : st === 'missing'
      ? `Not found in <span class="mono">nix_unstable</span> — nixpkgs doesn't currently package this.`
      : `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>${
          st === 'warn'
            ? `, the newest seen elsewhere is <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(pkg.refVersion || '?')}</span>${since}`
            : st === 'neutral'
              ? ` — Repology classifies this version as <span class="mono">${escapeHtml(pkg.nixStatus)}</span>.`
              : ` — matches the newest ${pkg.devel ? 'devel ' : ''}version seen vs. ${pkg.repoCount} other ${pkg.repoCount === 1 ? 'repo' : 'repos'}.`
        }${
          up && !up.newer && !failing
            ? up.behind
              ? ` nixkeeper's update check: ${behind} ${upLink} (up to <span class="mono">${escapeHtml(up.version)}</span>), not counted as outdated until ${limits}.`
              : ` nixkeeper's update check ${st === 'warn' ? 'found nothing newer' : 'agrees'}: the latest version ${upLink} is <span class="mono">${escapeHtml(up.version)}</span>.`
            : ''
        }`;

  el.innerHTML = `
    <div class="nix-line">${nixLine}</div>${
      onMaster(pkg)
        ? `<div class="master-note">master already has <span class="mono">${escapeHtml(onMaster(pkg))}</span> (${[
            pkg.masterPR &&
              `merged in <a class="files-link" href="${href(pkg.masterPR.url)}" target="_blank" rel="noopener">#${pkg.masterPR.number} ↗</a>`,
            pkg.master ? 'built by Hydra' : 'not built by Hydra yet',
          ]
            .filter(Boolean)
            .join(', ')})${
            waitingForChannel(pkg)
              ? ': the update is merged, and reaches nixos-unstable when the channel next advances, usually within a few days.'
              : ', not in nixos-unstable yet.'
          }</div>`
        : ''
    }${checkNote}${
      pkg.nixVulnerable
        ? `<div class="vuln-note">⚠ Repology flags nixpkgs' version <span class="mono">${escapeHtml(pkg.nixVersion)}</span> as vulnerable.${
            pkg.project
              ? ` <a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/cves" target="_blank" rel="noopener">Known CVEs ↗</a>`
              : ''
          }</div>`
        : ''
    }
    ${
      others.length
        ? `<div class="other-label">Compared against</div><div class="repo-chips">
      ${others.map((e) => `<span class="repo-chip ${e.status === 'newest' && e.version !== pkg.nixVersion ? 'ahead' : ''}">${escapeHtml(e.repo)} <span class="v mono">${escapeHtml(e.version || '?')}</span></span>`).join('')}
    </div>`
        : ''
    }
    <div class="detail-row">
      ${homepage ? `<a class="files-link" href="${href(homepage)}" target="_blank" rel="noopener">Homepage →</a>` : ''}
      ${safeUrl(pkg.source) ? `<a class="files-link" href="${href(pkg.source)}" target="_blank" rel="noopener" title="Where nixpkgs defines this package">${escapeHtml(sourceFileName(pkg.source))} ↗</a>` : ''}
      ${pkg.project ? `<a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/versions" target="_blank" rel="noopener">View on Repology ↗</a>` : ''}
    </div>
  `;
}

function currentFiltered() {
  writeViewToUrl();
  const q = document.getElementById('search').value.trim().toLowerCase();
  const list = packages.filter(
    (p) =>
      inPlatform(p) &&
      inList(p) &&
      FILTERS[activeFilter].test(p) &&
      (!q || [p.name, p.project, ...(p.attrs || [])].some((n) => n?.toLowerCase().includes(q))),
  );
  return sortAZ
    ? list
    : list.sort(
        (a, b) =>
          attentionRank(a) - attentionRank(b) ||
          // ISO dates in UTC compare correctly as strings; undated ones go last.
          (attentionRank(a) === 1
            ? (a.outdatedSince || '~').localeCompare(b.outdatedSince || '~')
            : 0),
      );
}

document.getElementById('stats').addEventListener('click', (e) => {
  if (e.target.closest('.plat-filter')) {
    platformFilter = null;
    render(currentFiltered());
    return;
  }
  const btn = e.target.closest('.stat-btn');
  if (!btn) return;
  // Clicking the active filter again goes back to showing everything.
  activeFilter = btn.dataset.filter === activeFilter ? 'all' : btn.dataset.filter;
  render(currentFiltered());
});

document.getElementById('lists').addEventListener('click', (e) => {
  const btn = e.target.closest('.stat-btn');
  if (!btn) return;
  // Clicking the active list again shows every list.
  listFilter = btn.dataset.list === listFilter ? null : btn.dataset.list;
  render(currentFiltered());
});

document.getElementById('search').addEventListener('input', () => render(currentFiltered()));
document.getElementById('sortBtn').addEventListener('click', (e) => {
  sortAZ = !sortAZ;
  e.currentTarget.setAttribute('aria-pressed', sortAZ);
  if (packages.length) render(currentFiltered());
  else writeViewToUrl();
});
document.getElementById('refreshBtn').addEventListener('click', () => {
  detailCache.clear();
  document.getElementById('content').innerHTML = `<div class="loading">Loading package data…</div>`;
  loadIndex();
});

readViewFromUrl();
loadIndex();
