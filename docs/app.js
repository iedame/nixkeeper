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

const repoInfo = detectRepo();
const detailCache = new Map(); // name -> parsed per-package Repology JSON
let packages = [];
let checkedAt = null;
let activeFilter = 'all'; // 'all' | 'warn' | 'failed' | 'vuln'
let sortAZ = false; // default order puts what needs attention first
let platformFilter = null; // null | 'linux' | 'darwin', combined with activeFilter

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
  activeFilter =
    Object.keys(FILTERS).find(
      (k) => FILTERS[k].param && FILTERS[k].param === params.get('filter'),
    ) || 'all';
  document.getElementById('search').value = params.get('q') || '';
  sortAZ = params.get('sort') === 'az';
  platformFilter =
    Object.keys(PLATFORMS).find((k) => PLATFORMS[k].param === params.get('platform')) || null;
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
  const query = params.toString();
  // replaceState, not pushState: typing a search shouldn't fill the history.
  history.replaceState(null, '', location.pathname + (query ? `?${query}` : '') + location.hash);
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
    const res = await fetch(rawUrl(repoInfo.owner, repoInfo.repo, 'data/index.json'), {
      cache: 'no-store',
    });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    packages = data.packages || [];
    checkedAt = data.checkedAt || null;
    document.getElementById('search').disabled = false;
    render(currentFiltered());
  } catch {
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
  // Counts follow the platform filter, so "outdated" means outdated on macOS
  // while macOS is selected.
  const base = packages.filter(inPlatform);
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
    ${stale ? 'title="The daily sync hasn\'t updated the data in over 2 days. Check the workflow in the Actions tab."' : ''}>
    checked ${timeAgo(checkedAt)}${stale ? ' — sync may be failing' : ''}</span>`;
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
        : `${escapeHtml(pkg.nixVersion)}${st === 'warn' ? ` <span class="ref mono">→ ${escapeHtml(pkg.refVersion || '?')}</span>` : ''}${st === 'warn' && pkg.outdatedSince ? ` <span class="age" title="Outdated since ${escapeHtml(longDate(pkg.outdatedSince))}">· ${shortAge(pkg.outdatedSince)}</span>` : ''}${st === 'neutral' ? ` <span class="badge neutral">${escapeHtml(pkg.nixStatus)}</span>` : ''}${pkg.devel ? ` <span class="badge devel ${st}">devel</span>` : ''}${pkg.nixVulnerable ? ' <span class="badge vuln">vulnerable</span>' : ''}${pkg.staleSince ? ` <span class="badge neutral" title="Repology lookup failed on the last run; this is data from ${escapeHtml(new Date(pkg.staleSince).toLocaleString())}">not refreshed</span>` : ''}`;

    const tr = document.createElement('tr');
    tr.className = 'row';
    tr.tabIndex = 0;
    tr.innerHTML = `
      <td><div class="pkg-name"><span class="status-dot ${st}"></span><span class="n">${escapeHtml(pkg.name)}</span>${platformTags(pkg)}</div></td>
      <td class="ver mono">${verCell}</td>
      <td>${githubLinks(pkg)}</td>
      <td>${buildCell(pkg)}</td>
      <td>${updateCell(pkg)}</td>
      <td><span class="chev">▸</span></td>
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

    for (const a of tr.querySelectorAll('.gh-btn')) {
      a.addEventListener('click', (e) => e.stopPropagation());
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

function failureButton(kind, dot, text, extra = '') {
  return `<button class="failure-btn${dot === 'missing' ? ' failing' : ''}" type="button" data-kind="${kind}" ${extra}>
    <span class="status-dot ${dot}"></span>${text}</button>`;
}

// Whether Hydra built this at all: not for unfree packages, nor ones nixpkgs
// keeps off Hydra (hydraPlatforms).
function hydraBuildsIt(pkg) {
  return !pkg.unfree && pkg.builds.some((b) => b.status !== 'notBuilt');
}

function buildCell(pkg) {
  if (!pkg.builds) return '<span class="failure-na" title="Not in nixpkgs">—</span>';
  const extra = 'aria-expanded="false" title="Show Hydra builds"';
  if (failedBuilds(pkg).length) return failureButton('build', 'missing', 'failure reported', extra);
  // Known failures: shown, but not counted as failed.
  if (buildsWith(pkg, 'broken').length)
    return failureButton('build', 'warn', 'marked broken', extra);
  if (!hydraBuildsIt(pkg)) return failureButton('build', 'neutral', 'not built by Hydra', extra);
  return failureButton('build', 'ok', 'none reported', extra);
}

// nixpkgs-update's latest attempt. `update` is null when the bot never tried
// and missing for packages not in nixpkgs.
function updateCell(pkg) {
  if (pkg.update === undefined) return '<span class="failure-na" title="Not in nixpkgs">—</span>';
  const extra = 'aria-expanded="false" title="Show the latest nixpkgs-update attempt"';
  if (pkg.updateFailure) return failureButton('update', 'missing', 'failure reported', extra);
  if (pkg.update === null) return failureButton('update', 'neutral', 'not attempted', extra);
  return failureButton('update', 'ok', 'none reported', extra);
}

const prLink = (n, text) =>
  `<a class="files-link" href="https://github.com/NixOS/nixpkgs/pull/${n}" target="_blank" rel="noopener">${text}</a>`;
const UPDATE_OUTCOME = {
  failed: { dot: 'missing', text: () => 'failed' },
  superseded: {
    dot: 'neutral',
    text: (u) => `failed, but nixpkgs has <span class="mono">${escapeHtml(u.to)}</span> by now`,
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
  if (!u) {
    el.innerHTML = `<div class="nix-line">nixpkgs-update hasn't tried to update this package (it may have no update source it understands).</div>`;
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
  el.innerHTML = `
    <div class="nix-line">Latest nixpkgs-update attempt${(pkg.attrs || []).length > 1 ? ` at <span class="mono">${escapeHtml(u.attr)}</span>` : ''} · ${escapeHtml(longDate(day))} (${shortAge(day)} ago)${versions}</div>
    <div class="build-list"><div class="build-line">
      <span class="status-dot ${o.dot}"></span><span class="st ${o.dot}">${o.text(u)}</span>
    </div></div>
    ${u.excerpt?.length ? `<pre class="log-excerpt mono">${u.excerpt.map(escapeHtml).join('\n')}</pre>` : ''}
    <div class="detail-row">
      <a class="files-link" href="${escapeHtml(u.log)}" target="_blank" rel="noopener">log ↗</a>
      <a class="files-link" href="${escapeHtml(dir)}" target="_blank" rel="noopener">all attempts ↗</a>
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
  const since =
    'lastSuccess' in b
      ? `<span class="since">${b.lastSuccess ? `last succeeded ${escapeHtml(longDate(b.lastSuccess))} (${shortAge(b.lastSuccess)} ago)` : 'never built successfully'}</span>`
      : '';
  let links = '';
  if (b.status === 'failed') {
    links = `<a class="files-link" href="${HYDRA}/build/${b.build}/log" target="_blank" rel="noopener">log ↗</a>${since}`;
  } else if (b.status === 'broken') {
    // Where to fix it: the package's source, at the line nixpkgs points to.
    links = `${since}${pkg.source ? `<a class="files-link" href="${escapeHtml(pkg.source)}" target="_blank" rel="noopener">source ↗</a>` : ''}`;
  } else if (b.build) {
    links = `<a class="files-link" href="${HYDRA}/build/${b.build}" target="_blank" rel="noopener">build ${b.build} ↗</a>`;
  }
  return `<div class="build-line">
    <span class="status-dot ${s.dot}"></span>
    <span class="mono sys">${escapeHtml(b.system)}</span>
    ${multi ? `<span class="mono attr">${escapeHtml(b.attr)}</span>` : ''}
    <span class="st ${s.dot}">${s.text}</span>${links}
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
  el.innerHTML = `${body}${jobLinks ? `<div class="detail-row">${jobLinks}</div>` : ''}`;
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
      const res = await fetch(
        rawUrl(repoInfo.owner, repoInfo.repo, `data/${encodeURIComponent(file)}`),
        { cache: 'no-store' },
      );
      entries = res.ok ? await res.json() : [];
      detailCache.set(file, entries);
    } catch {
      entries = [];
    }
  }

  const others = entries.filter((e) => e.repo !== NIX_REPO);
  const homepage = pkg.homepage;

  const st = computeStatus(pkg);
  const up = pkg.upstream;
  // "in the wesnoth/wesnoth tags" or "on www.barebones.com".
  const upLink = up
    ? `${up.repo ? 'in the' : 'on'} <a class="files-link" href="${escapeHtml(up.url)}" target="_blank" rel="noopener">${escapeHtml(up.label || `${up.repo} tags`)} ↗</a>`
    : '';
  const since = pkg.outdatedSince
    ? ` — outdated since ${escapeHtml(longDate(pkg.outdatedSince))} (${daysText(pkg.outdatedSince)})`
    : '';
  const repologyOutdated = ['outdated', 'legacy'].includes(pkg.nixStatus);
  // When the update check is what makes it outdated, say where the newer
  // version came from, and how it compares with Repology.
  const upstreamLine = () =>
    `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>; nixkeeper's update check found <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(up.version)}</span> ${upLink}${
      pkg.refVersion !== up.version
        ? `; Repology's newest is <span class="mono">${escapeHtml(pkg.refVersion)}</span>`
        : repologyOutdated
          ? ''
          : ", which Repology doesn't count as newest yet"
    }${since}`;
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
          up && !up.newer
            ? ` nixkeeper's update check ${st === 'warn' ? 'found nothing newer' : 'agrees'}: the latest version ${upLink} is <span class="mono">${escapeHtml(up.version)}</span>.`
            : ''
        }`;

  el.innerHTML = `
    <div class="nix-line">${nixLine}</div>
    ${
      others.length
        ? `<div class="other-label">Compared against</div><div class="repo-chips">
      ${others.map((e) => `<span class="repo-chip ${e.status === 'newest' && e.version !== pkg.nixVersion ? 'ahead' : ''}">${escapeHtml(e.repo)} <span class="v mono">${escapeHtml(e.version || '?')}</span></span>`).join('')}
    </div>`
        : ''
    }
    <div class="detail-row">
      ${homepage ? `<a class="files-link" href="${escapeHtml(homepage)}" target="_blank" rel="noopener">Homepage →</a>` : ''}
      ${pkg.source ? `<a class="files-link" href="${escapeHtml(pkg.source)}" target="_blank" rel="noopener" title="Where nixpkgs defines this package">${escapeHtml(sourceFileName(pkg.source))} ↗</a>` : ''}
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
