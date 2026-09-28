const NIX_REPO = 'nix_unstable';

// Figure out which repo's data branch to read. Works unmodified on a
// GitHub Pages project site (https://<owner>.github.io/<repo>/); override
// with ?owner=...&repo=... when testing locally or on a custom domain.
function detectRepo() {
  const params = new URLSearchParams(location.search);
  if (params.get('owner') && params.get('repo')) {
    return { owner: params.get('owner'), repo: params.get('repo') };
  }
  const host = location.hostname;
  const owner = host.endsWith('.github.io') ? host.split('.')[0] : null;
  const seg = location.pathname.split('/').filter(Boolean)[0] || null;
  if (owner && seg) return { owner, repo: seg };
  return null;
}

function rawUrl(owner, repo, path) {
  return `https://raw.githubusercontent.com/${owner}/${repo}/data/${path}`;
}

let repoInfo = detectRepo();
const detailCache = new Map(); // name -> parsed per-package Repology JSON
let packages = [];
let checkedAt = null;
let activeFilter = 'all'; // 'all' | 'warn' | 'failed' | 'vuln'
let sortAZ = false; // default order puts what needs attention first
let platformFilter = null; // null | 'linux' | 'darwin', combined with activeFilter

// "any platform" (no restriction in nixpkgs) counts as both.
const PLATFORMS = {
  linux:  { label: 'Linux', param: 'linux' },
  darwin: { label: 'macOS', param: 'macos' },
};
function onPlatform(pkg, key) {
  return pkg.platforms === null || Boolean(pkg.platforms && pkg.platforms[key]);
}
function inPlatform(pkg) {
  return !platformFilter || onPlatform(pkg, platformFilter);
}
// The sync runs daily; older than this means runs are failing or GitHub has
// paused the schedule (it does after 60 days without commits).
const STALE_AFTER_HOURS = 48;

// `param` is how each filter appears in the page address (?filter=outdated).
const FILTERS = {
  all:     { label: 'tracked',         test: () => true },
  warn:    { label: 'outdated',        param: 'outdated',       color: 'var(--warn)',   test: p => computeStatus(p) === 'warn' },
  failed:  { label: 'failed',          param: 'failed',         color: 'var(--danger)', test: p => hasFailure(p) },
  vuln:    { label: 'flagged vulnerable', param: 'vulnerable',  color: 'var(--danger)', test: p => p.nixVulnerable },
};

// Everything shown in red: not found in nixpkgs, or a build or update
// failure reported.
function hasFailure(pkg) {
  return computeStatus(pkg) === 'missing' || Boolean(pkg.buildFailure || pkg.updateFailure);
}

// Default order: failed, then outdated (longest outdated first), then the
// rest; otherwise alphabetical (the index arrives sorted by name and
// Array.sort is stable).
function attentionRank(pkg) {
  if (hasFailure(pkg)) return 0;
  if (computeStatus(pkg) === 'warn') return 1;
  return 2;
}

// Filter, search and sort live in the page address, so a view survives a
// reload and can be bookmarked or shared. Other parameters (owner, repo) are
// left alone.
function readViewFromUrl() {
  const params = new URLSearchParams(location.search);
  activeFilter = Object.keys(FILTERS).find(k => FILTERS[k].param && FILTERS[k].param === params.get('filter')) || 'all';
  document.getElementById('search').value = params.get('q') || '';
  sortAZ = params.get('sort') === 'az';
  platformFilter = Object.keys(PLATFORMS).find(k => PLATFORMS[k].param === params.get('platform')) || null;
  document.getElementById('sortBtn').setAttribute('aria-pressed', sortAZ);
}

function writeViewToUrl() {
  const params = new URLSearchParams(location.search);
  const q = document.getElementById('search').value.trim();
  const set = (k, v) => v ? params.set(k, v) : params.delete(k);
  set('filter', FILTERS[activeFilter].param);
  set('q', q);
  set('sort', sortAZ ? 'az' : '');
  set('platform', platformFilter && PLATFORMS[platformFilter].param);
  const query = params.toString();
  // replaceState, not pushState: typing a search shouldn't fill the history.
  history.replaceState(null, '', location.pathname + (query ? '?' + query : '') + location.hash);
}

async function loadIndex() {
  const content = document.getElementById('content');
  if (!repoInfo) {
    content.innerHTML = `<div class="error">
      Couldn't tell which GitHub repo to read from this URL.<br>
      Add <code>?owner=you&repo=your-repo</code> to the address, or open this from your GitHub Pages project site.
    </div>`;
    return;
  }
  try {
    const res = await fetch(rawUrl(repoInfo.owner, repoInfo.repo, 'data/index.json'), { cache: 'no-store' });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    packages = data.packages || [];
    checkedAt = data.checkedAt || null;
    document.getElementById('search').disabled = false;
    render(currentFiltered());
  } catch (err) {
    content.innerHTML = `<div class="error">
      Couldn't load <code>data/index.json</code> from the <code>data</code> branch of
      <code>${escapeHtml(repoInfo.owner)}/${escapeHtml(repoInfo.repo)}</code>.<br>
      Check that the repo is public and the sync workflow has run at least once.
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
  if (pkg.nixStatus === 'newest' || pkg.nixStatus === 'unique' || pkg.nixStatus === 'devel') return 'ok';
  return 'neutral';
}

// How long a package has been outdated, one letter per unit: <1 d, 3 d, 2 w,
// 5 m (months), 2 y.
function shortAge(iso) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400e3);
  if (days < 1) return '<1 d';
  if (days < 7) return days + ' d';
  if (days < 30) return Math.floor(days / 7) + ' w';
  if (days < 365) return Math.min(11, Math.floor(days / 30)) + ' m'; // 360-364 days: not "12 m" before "1 y"
  return Math.floor(days / 365) + ' y';
}

function daysText(iso) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400e3);
  return days < 1 ? 'today' : days === 1 ? '1 day' : days + ' days';
}

function longDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

function timeAgo(iso) {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}

function renderStats() {
  // Counts follow the platform filter, so "outdated" means outdated on macOS
  // while macOS is selected.
  const base = packages.filter(inPlatform);
  const buttons = Object.entries(FILTERS).map(([key, f]) => {
    const count = base.filter(f.test).length;
    // "vulnerable" only shows up when something is actually flagged.
    if (key === 'vuln' && !count && activeFilter !== 'vuln') return '';
    const pressed = activeFilter === key;
    return `<button class="stat-btn" data-filter="${key}" aria-pressed="${pressed}"
      ${!count && key !== 'all' && !pressed ? 'disabled' : ''}>
      <b${f.color ? ` style="color:${f.color}"` : ''}>${count}</b> ${f.label}</button>`;
  }).join('');
  const stale = !checkedAt || Date.now() - new Date(checkedAt).getTime() > STALE_AFTER_HOURS * 3600e3;
  const platformChip = platformFilter
    ? `<button class="plat-filter" title="Show all platforms">${PLATFORMS[platformFilter].label} only ✕</button>` : '';
  document.getElementById('stats').innerHTML = `${buttons}${platformChip}<span class="checked${stale ? ' stale' : ''}"
    ${stale ? 'title="The daily sync hasn\'t updated the data in over 2 days. Check the workflow in the Actions tab."' : ''}>
    checked ${timeAgo(checkedAt)}${stale ? ' — sync may be failing' : ''}</span>`;
}

function escapeHtml(s) { return (s || '').toString().replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

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
  list.forEach(pkg => {
    const st = computeStatus(pkg);
    const verCell = st === 'missing' ? `<span class="badge missing">not packaged</span>`
      : `${escapeHtml(pkg.nixVersion)}${st === 'warn' ? ` <span class="ref mono">→ ${escapeHtml(pkg.refVersion || '?')}</span>` : ''}${st === 'warn' && pkg.outdatedSince ? ` <span class="age" title="Outdated since ${escapeHtml(longDate(pkg.outdatedSince))}">· ${shortAge(pkg.outdatedSince)}</span>` : ''}${st === 'neutral' ? ` <span class="badge neutral">${escapeHtml(pkg.nixStatus)}</span>` : ''}${pkg.devel ? ` <span class="badge devel ${st}">devel</span>` : ''}${pkg.nixVulnerable ? ' <span class="badge vuln">vulnerable</span>' : ''}${pkg.staleSince ? ` <span class="badge neutral" title="Repology lookup failed on the last run; this is data from ${escapeHtml(new Date(pkg.staleSince).toLocaleString())}">not refreshed</span>` : ''}`;

    const tr = document.createElement('tr');
    tr.className = 'row'; tr.tabIndex = 0;
    tr.innerHTML = `
      <td><div class="pkg-name"><span class="status-dot ${st}"></span><span class="n">${escapeHtml(pkg.name)}</span>${platformTags(pkg)}</div></td>
      <td class="ver mono">${verCell}</td>
      <td>${githubLinks(pkg)}</td>
      <td>${failureCell('build', pkg.buildFailure)}</td>
      <td>${failureCell('update', pkg.updateFailure)}</td>
      <td><span class="chev">▸</span></td>
    `;

    const detail = document.createElement('tr');
    detail.className = 'detail';
    detail.innerHTML = `<td colspan="6"><div class="detail-inner">
      <div class="nix-line">Loading detail…</div>
    </div></td>`;

    tr.querySelectorAll('.failure-btn').forEach(btn => btn.addEventListener('click', e => {
      e.stopPropagation(); // don't expand the row
      const url = FAILURE_URLS[btn.dataset.kind](pkg);
      if (url) window.open(url, '_blank', 'noopener');
    }));

    tr.querySelectorAll('.gh-btn').forEach(a => a.addEventListener('click', e => e.stopPropagation()));
    tr.querySelectorAll('button.plat').forEach(btn => btn.addEventListener('click', e => {
      e.stopPropagation(); // don't expand the row
      // Clicking the active platform again shows all platforms.
      platformFilter = platformFilter === btn.dataset.platform ? null : btn.dataset.platform;
      render(currentFiltered());
    }));

    tr.addEventListener('click', async () => {
      const isOpen = tr.classList.toggle('open');
      detail.classList.toggle('open', isOpen);
      if (isOpen) await fillDetail(pkg, detail.querySelector('.detail-inner'));
    });
    tr.addEventListener('keydown', e => { if (e.target === tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); } });

    rowsEl.appendChild(tr);
    rowsEl.appendChild(detail);
  });
}

// Placeholders until failure data exists: the fetch script doesn't produce
// `buildFailure` / `updateFailure` yet, so every package reads as passing.
function failureCell(kind, failing) {
  return `<button class="failure-btn${failing ? ' failing' : ''}" type="button" data-kind="${kind}">
    <span class="status-dot ${failing ? 'missing' : 'ok'}"></span>${failing ? 'failure reported' : 'none reported'}</button>`;
}

// TODO: link each kind to its log once we have one (build: e.g. Hydra).
const FAILURE_URLS = {
  build: pkg => null,
  update: pkg => null,
};

// From nixpkgs meta.platforms; null means nixpkgs doesn't restrict it.
function platformTags(pkg) {
  const pl = pkg.platforms;
  if (pl === undefined) return '';
  if (pl === null) return `<span class="plat any" title="nixpkgs doesn't restrict its platforms">any platform</span>`;
  return Object.entries(PLATFORMS).filter(([key]) => pl[key]).map(([key, p]) =>
    `<button class="plat" type="button" data-platform="${key}" aria-pressed="${platformFilter === key}"
      title="${platformFilter === key ? 'Show all platforms' : `Show only packages available on ${p.label}`}">${p.label}</button>`).join('');
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

async function fillDetail(pkg, el) {
  // Raw Repology data is stored per project, under a file-name-safe version
  // of its name (python:requests -> python_requests.json).
  const file = pkg.dataFile || `${pkg.project || pkg.name}.json`;
  let entries = detailCache.get(file);
  if (!entries) {
    try {
      const res = await fetch(rawUrl(repoInfo.owner, repoInfo.repo, `data/${encodeURIComponent(file)}`), { cache: 'no-store' });
      entries = res.ok ? await res.json() : [];
      detailCache.set(file, entries);
    } catch (e) { entries = []; }
  }

  const others = entries.filter(e => e.repo !== NIX_REPO);
  const homepage = pkg.homepage;

  const st = computeStatus(pkg);
  const nixLine = st === 'missing'
    ? `Not found in <span class="mono">nix_unstable</span> — nixpkgs doesn't currently package this.`
    : `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>${st === 'warn' ? `, the newest seen elsewhere is <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(pkg.refVersion || '?')}</span>${pkg.outdatedSince ? ` — outdated since ${escapeHtml(longDate(pkg.outdatedSince))} (${daysText(pkg.outdatedSince)})` : ''}`
      : st === 'neutral' ? ` — Repology classifies this version as <span class="mono">${escapeHtml(pkg.nixStatus)}</span>.`
      : ` — matches the newest ${pkg.devel ? 'devel ' : ''}version seen vs. ${pkg.repoCount} other ${pkg.repoCount === 1 ? 'repo' : 'repos'}.`}`;

  el.innerHTML = `
    <div class="nix-line">${nixLine}</div>
    ${others.length ? `<div class="other-label">Compared against</div><div class="repo-chips">
      ${others.map(e => `<span class="repo-chip ${e.status === 'newest' && e.version !== pkg.nixVersion ? 'ahead' : ''}">${escapeHtml(e.repo)} <span class="v mono">${escapeHtml(e.version || '?')}</span></span>`).join('')}
    </div>` : ''}
    <div class="detail-row">
      ${homepage ? `<a class="files-link" href="${escapeHtml(homepage)}" target="_blank" rel="noopener">Homepage →</a>` : ''}
      ${pkg.project ? `<a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/versions" target="_blank" rel="noopener">View on Repology ↗</a>` : ''}
    </div>
  `;
}

function currentFiltered() {
  writeViewToUrl();
  const q = document.getElementById('search').value.trim().toLowerCase();
  const list = packages.filter(p => inPlatform(p) && FILTERS[activeFilter].test(p) && (!q || [p.name, p.project, ...(p.attrs || [])].some(n => n && n.toLowerCase().includes(q))));
  return sortAZ ? list : list.sort((a, b) =>
    attentionRank(a) - attentionRank(b)
    // ISO dates in UTC compare correctly as strings; undated ones go last.
    || (attentionRank(a) === 1 ? (a.outdatedSince || '~').localeCompare(b.outdatedSince || '~') : 0));
}

document.getElementById('stats').addEventListener('click', e => {
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

document.getElementById('search').addEventListener('input', () => render(currentFiltered()));
document.getElementById('sortBtn').addEventListener('click', e => {
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
