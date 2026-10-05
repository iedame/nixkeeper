import {
  buildsWith as buildsOn,
  communityCheck,
  comparedRepos,
  compareVersions,
  computeStatus,
  daysText,
  hasFailure as failureOn,
  faviconKey,
  fromMaster,
  html,
  matchesSearch,
  midway,
  NAME_DOTS,
  nameMatches,
  nixkeeperEntry,
  onMaster,
  onPlatform,
  pageLinks,
  attentionRank as rankOn,
  raw,
  githubRepo as repoFrom,
  safeUrl,
  shardOf,
  shortAge,
  targetVersion,
  themeFor,
  timeAgo,
  updateTitle,
  versionDiff,
  viewPath,
  waitingForChannel,
  withRunStamps,
  withSlash,
} from './logic.js';

const NIX_REPO = 'nix_unstable';

const githubRepo = (params) => repoFrom(params, location);

// Where the data (index.json, summary.json, the shards) lives, as a URL
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
const detailCache = new Map(); // file -> a Repology project's entries (format 1)
// The data's format (docs/data.md). 2: the list from summary.json (a short
// entry per package), each package's full row from its shard
// (rows/<n>.json), loaded when a panel opens. 1 (0.11.0 and before):
// index.json has every row in full, and each Repology project its own file.
let format = 1;
let shardCount = 1;
// With every package (a community instance: index.json's allPackages), the
// page shows one view of the data at a time (viewPath): `packages` is that
// view's, `manifest` index.json, with the counts of all of nixpkgs.
let community = false;
let manifest = null;
let shownView = null; // the path of the view in `packages`
let wantedView = null; // the one being loaded (the newest asked for wins)
let names = null; // the name index (names.json), once loaded: [[name, status, set?]]
let namesLoading = null;
// ?pkg=: one package alone (with every package); ?set=: a generated set.
let pkgParam = null;
let setFilter = null;
const inSet = (pkg) => !setFilter || pkg.set === setFilter;
const shardCache = new Map(); // n -> Promise of Map(name -> full row)
let packages = [];
let checkedAt = null;
let activeFilter = 'all'; // 'all' | 'warn' | 'failed' | 'vuln'
let sortAZ = false; // default order puts what needs attention first
// The table shows PAGE_SIZE rows at a time: drawing stays fast whatever the
// data's size, and the page keeps working with Ctrl+F and screen readers
// (no virtual scrolling). ?page= in the address, past the first.
const PAGE_SIZE = 200;
let pageNum = 1;
let platformFilter = null; // null | 'linux' | 'darwin', combined with activeFilter
// The rules that follow the platform filter (logic.js), on the selected one.
const hasFailure = (pkg) => failureOn(pkg, platformFilter);
const buildsWith = (pkg, status) => buildsOn(pkg, status, platformFilter);
const failedBuilds = (pkg) => buildsWith(pkg, 'failed');
const attentionRank = (pkg) => rankOn(pkg, platformFilter);
// null, or a list from package-lists/ ("maintained", "gaming-team", ...):
// ?list=gaming-team is a page of just that list's packages, to share.
let listFilter = null;
const inList = (pkg) => !listFilter || (pkg.lists || []).includes(listFilter);
// null, or a nixpkgs team (meta.teams, by its short name; any case):
// ?team=gaming is a page of the team's packages here.
let teamFilter = null;
const isTeam = (name) => name.toLowerCase() === teamFilter.toLowerCase();
const inTeam = (pkg) => !teamFilter || (pkg.teams || []).some(isTeam);
// The team's name as nixpkgs writes it ("Qt-KDE"), or as the address has it.
const teamName = () => packages.flatMap((p) => p.teams || []).find(isTeam) || teamFilter;
// Every list some package is on: "maintained" first, as the sync sorts them.
function allLists() {
  // With every package, the view has only some: the manifest has them all.
  if (community) return Object.keys(manifest.views?.lists || {});
  const seen = [];
  for (const p of packages) for (const l of p.lists || []) if (!seen.includes(l)) seen.push(l);
  return seen.sort((a, b) =>
    a === 'maintained' ? -1 : b === 'maintained' ? 1 : a.localeCompare(b),
  );
}

// The platform filter's choices ("any platform" counts as both: onPlatform).
const PLATFORMS = {
  linux: { label: 'Linux', param: 'linux' },
  darwin: { label: 'macOS', param: 'macos' },
};
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

// Where the package's update stands on GitHub, in GitHub's own colors:
// "on master" (merged, purple) while waiting for the channel, else an open
// update PR (green; grey while a draft). A link to the PR when it's known.
const badge = (cls, text, title, pr) =>
  pr
    ? html` <a class="badge ${cls}" href="${safeUrl(pr.url)}" target="_blank" rel="noopener" title="${title}">${text}</a>`
    : html` <span class="badge ${cls}" title="${title}">${text}</span>`;

// The update's badge: on master when that's all it waits for, else its PR.
function prBadge(pkg) {
  return waitingForChannel(pkg) ? masterBadge(pkg) : openPrBadge(pkg);
}

function masterBadge(pkg) {
  const pr = pkg.masterPR;
  return badge(
    'onmaster',
    'on master',
    `master already has ${onMaster(pkg)}: merged${pr ? ` in #${pr.number} (${pr.title})` : ''}, waiting for nixos-unstable to catch up (usually a few days)`,
    pr,
  );
}

function openPrBadge(pkg) {
  const pr = pkg.openPR;
  if (!pr) return '';
  const behind =
    targetVersion(pkg) && compareVersions(pr.to, targetVersion(pkg)) < 0
      ? ` (the newest is ${targetVersion(pkg)})`
      : '';
  return badge(
    pr.draft ? 'prdraft' : 'propen',
    `PR #${pr.number}`,
    `${pr.draft ? 'Draft update PR' : 'Update PR waiting for review'}: ${pr.title}${behind}`,
    pr,
  );
}

// The version column: the versions on the left, badges on the right (so
// they line up from row to row). Up to date: nixpkgs' version, and what's
// said about it (devel, vulnerable, ...) at the right. Outdated, two lines:
// nixpkgs' version, and under it the newest, in full, with the start they
// share faded so the part that changes stands out ("→" hangs to its left).
// At the right, each line's badges: what's said about nixpkgs' version
// (devel, vulnerable, ...) beside it; the update's (its PR, on master, a
// failing check) beside the newest. Screen readers get the two versions in a
// sentence instead. Both versions are one button: it copies the update's
// title as nixpkgs writes it ("unciv: 4.22.1 -> 4.22.6").
function versionCell(pkg, st) {
  if (st === 'missing') return html`<span class="badge missing">not packaged</span>`;
  const now = pkg.nixVersion;
  const stale = notRefreshed(pkg, 'upstream');
  const failing = stale
    ? html`<span class="badge neutral" title="${staleText(stale, "nixkeeper's update check failing")}. ${communityCheck(pkg) ? "It's a community rule: report it to nixkeeper, or give the package a rule of your own." : 'Fix it in package-lists/update-checks.nix.'}">check failing</span>`
    : '';
  const about = html`${pkg.pending ? html`<span class="badge neutral" title="${PENDING_TITLE} (${pkg.set})">pending</span>` : ''}${st === 'neutral' ? html`<span class="badge neutral">${statusLabel(pkg.nixStatus)}</span>` : ''}${pkg.devel ? html`<span class="badge devel ${st}">devel</span>` : ''}${pkg.nixVulnerable ? html`<span class="badge vuln">vulnerable</span>` : ''}${pkg.staleSince ? html`<span class="badge neutral" title="Repology lookup failed on the last run; this is data from ${new Date(pkg.staleSince).toLocaleString()}">not refreshed</span>` : ''}`;
  if (st !== 'warn')
    return html`<div class="vcell"><span class="v-now"><span class="v">${now}</span></span><span class="v-tags top">${about}${failing}</span></div>`;
  const target = targetVersion(pkg);
  const merged = waitingForChannel(pkg);
  const title = updateTitle(pkg);
  // A newer version under the one before it: the start they share faded,
  // the rest in colour, "→" hanging to its left.
  const step = (cls, from, to, colour) => {
    const d = versionDiff(from, to);
    // Outdated, but no newer version known (Repology says outdated without
    // one): say so, rather than a bare "?".
    if (!to)
      return html`<span class="${cls}" aria-hidden="true"><span class="arrow">→</span><span class="unknown">newer version unknown</span></span>`;
    return html`<span class="${cls}" aria-hidden="true" title="${to}"><span class="arrow">→</span><span class="same">${d.same}</span><span class="ref${colour}">${d.to}</span></span>`;
  };
  // Master partway there: its own line, with its badge, between the two.
  const mid = midway(pkg);
  const steps = mid
    ? html`${step('v-mid', pkg.nixVersion, mid, ' merged')}${step('v-next', mid, target, '')}`
    : step('v-next', pkg.nixVersion, target, merged ? ' merged' : '');
  const said = mid
    ? `${now}, on master ${mid}, newest ${target || 'unknown'}`
    : `${now}, newest ${target || 'unknown'}`;
  return html`<div class="vcell${mid ? ' three' : ''}">
    <button type="button" class="vcopy" data-copy="${title || ''}" title="Copy “${title || ''}”">
    <span class="v-now"><span class="v" aria-hidden="true">${now}</span><span class="sr-only">${said}</span></span>
    ${steps}
    </button>
    <span class="v-tags top">${about}</span>${mid ? html`<span class="v-tags mid">${masterBadge(pkg)}</span>` : ''}
    <span class="v-tags bottom">${mid ? openPrBadge(pkg) : prBadge(pkg)}${failing}</span>
  </div>`;
}

// How long an outdated package has been outdated, after its name: orange,
// or violet when the update is merged and waiting for the channel.
function ageTag(pkg, st) {
  if (st !== 'warn' || !pkg.outdatedSince) return '';
  return html`<span class="age${waitingForChannel(pkg) ? ' merged' : ''}" title="Outdated since ${longDate(pkg.outdatedSince)}">${shortAge(pkg.outdatedSince)}</span>`;
}

// Copies an update's title, and says so on the button for a moment. The
// clipboard API needs a secure page (https, or localhost); elsewhere (a
// self-hosted page over plain http) the older way.
async function copyTitle(btn) {
  const text = btn.dataset.copy;
  if (!text) return;
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch {
    const area = Object.assign(document.createElement('textarea'), { value: text });
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    ok = document.execCommand('copy');
    area.remove();
  }
  btn.dataset.copied = ok ? 'Copied' : "Couldn't copy";
  document.getElementById('announce').textContent = ok ? `Copied ${text}` : "Couldn't copy";
  clearTimeout(btn.copiedTimer);
  btn.copiedTimer = setTimeout(() => delete btn.dataset.copied, 1500);
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
  teamFilter = params.get('team') || null;
  setFilter = params.get('set') || null;
  pkgParam = params.get('pkg') || null;
  pageNum = Math.max(1, Number.parseInt(params.get('page'), 10) || 1);
  document.getElementById('sortBtn').setAttribute('aria-pressed', sortAZ);
}

// The address for the current view, on page `page`.
function viewQuery(page = pageNum) {
  const params = new URLSearchParams(location.search);
  const q = document.getElementById('search').value.trim();
  const set = (k, v) => (v ? params.set(k, v) : params.delete(k));
  set('filter', FILTERS[activeFilter].param);
  set('q', q);
  set('sort', sortAZ ? 'az' : '');
  set('platform', platformFilter && PLATFORMS[platformFilter].param);
  set('list', listFilter);
  set('team', teamFilter);
  set('set', setFilter);
  set('pkg', pkgParam);
  set('page', page > 1 ? page : '');
  // "@" is fine in a query: ?q=@handle reads better in a shared link.
  const query = params.toString().replaceAll('%40', '@');
  return location.pathname + (query ? `?${query}` : '');
}
function writeViewToUrl() {
  // replaceState, not pushState: typing a search shouldn't fill the history.
  history.replaceState(null, '', viewQuery() + location.hash);
}

// The Theme menu. theme.js applied the saved choice before the page drew;
// this keeps it, and the page's default from the data, in the browser
// (localStorage: nothing is sent anywhere) and applies changes.
const SITE_PALETTE = `nixkeeper-site-palette:${location.pathname}`;
const stored = (key) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // storage blocked: nothing is remembered
  }
};
const store = (key, value) => {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    // storage blocked: it lasts until the page is left
  }
};

function applyTheme() {
  const { palette, mode } = themeFor(
    { palette: stored('nixkeeper-palette'), mode: stored('nixkeeper-mode') },
    stored(SITE_PALETTE),
  );
  const root = document.documentElement;
  root.dataset.palette = palette;
  if (mode === 'auto') delete root.dataset.mode;
  else root.dataset.mode = mode;
  for (const input of document.querySelectorAll('#themePanel input')) {
    input.checked = input.value === (input.name === 'palette' ? palette : mode);
  }
}

// The default the page's owner set (page.theme in the package lists), kept
// so the next visit starts with it before the data loads.
function setSitePalette(palette) {
  if (palette === stored(SITE_PALETTE)) return;
  store(SITE_PALETTE, palette);
  applyTheme();
}

// The row's dot, on hover (the legend popover lists them all).
// Repology's statuses as the page says them, where the code isn't clear
// ("unlisted": with every package, one Repology doesn't know).
const STATUS_LABEL = { unlisted: 'not on Repology' };
const statusLabel = (status) => STATUS_LABEL[status] || status;
const PENDING_TITLE =
  "A generated package set: only Repology's versions and Hydra's builds for now";

const DOT_TITLE = {
  ok: 'Up to date: nixpkgs has the newest version',
  warn: 'Outdated: a newer release is out',
  merged: 'On master: the update is merged, waiting for nixos-unstable',
  missing: 'Not packaged: not in nixpkgs unstable',
  neutral: "Can't compare: a rolling or unusual version scheme",
};

function showLegend(open) {
  document.getElementById('legendPanel').hidden = !open;
  document.getElementById('legendBtn').setAttribute('aria-expanded', open);
}

function showThemePanel(open) {
  document.getElementById('themePanel').hidden = !open;
  document.getElementById('themeBtn').setAttribute('aria-expanded', open);
}

// Mistakes the sync found in the package lists (nixkeeper/listcheck.py): a
// maintainer handle no package lists tracks nothing, so it's said up front.
function showListProblems(problems) {
  const el = document.getElementById('listProblems');
  if (!el) return;
  el.hidden = problems.length === 0;
  el.innerHTML = problems.length
    ? html`⚠ ${problems.length === 1 ? 'A problem' : `${problems.length} problems`} in the package lists, found by the last sync:
      <ul>${problems.map((p) => html`<li>${p}</li>`)}</ul>`
    : '';
}

// Format 2's summary entries, or null to use index.json's rows (format 1,
// or a summary that couldn't be loaded while index.json still has them).
async function summaryOf(data) {
  if (!(data.format >= 2 && data.shardCount)) return null;
  try {
    const res = await fetch(dataUrl('summary.json'), { cache: 'no-store' });
    if (!res.ok) throw new Error(res.status);
    const summary = await res.json();
    format = 2;
    shardCount = data.shardCount;
    return summary.packages || [];
  } catch (e) {
    if (data.packages) return null;
    throw e;
  }
}

// A package's full row (what its panels show): its shard's in format 2,
// loaded once (a failed load isn't kept, so opening it again tries again);
// in format 1, the row itself. null if it couldn't be loaded.
async function fullRow(pkg) {
  if (format < 2) return pkg;
  const n = shardOf(pkg.name, shardCount);
  if (!shardCache.has(n)) {
    shardCache.set(
      n,
      fetch(dataUrl(`rows/${n}.json`), { cache: 'no-store' })
        .then((res) => {
          if (!res.ok) throw new Error(res.status);
          return res.json();
        })
        .then(
          (shard) =>
            new Map(shard.packages.map((row) => [row.name, withRunStamps(row, checkedAt)])),
        ),
    );
  }
  try {
    return (await shardCache.get(n)).get(pkg.name) || null;
  } catch {
    shardCache.delete(n);
    return null;
  }
}

// A row's Repology entries (the repositories it's compared against): in its
// shard's row (format 2), else its project's file. null when they couldn't
// be loaded (the network, say): the panel says so, rather than "compared
// with 0 other repositories", and isn't kept, so opening it again tries again.
async function repologyEntries(row) {
  if (format >= 2) return row.repology || [];
  // Stored per project, under a file-name-safe version of its name
  // (python:requests -> python_requests.json).
  const file = row.dataFile || `${row.project || row.name}.json`;
  if (detailCache.has(file)) return detailCache.get(file);
  try {
    const res = await fetch(dataUrl(encodeURIComponent(file)), { cache: 'no-store' });
    if (!res.ok) return null;
    const entries = await res.json();
    detailCache.set(file, entries);
    return entries;
  } catch {
    return null;
  }
}

// With every package: load the view the address asks for (viewPath) into
// `packages`, unless it's there already. A maintainer, team or list with no
// file has no packages here. Throws if a view can't be loaded.
async function ensureView() {
  const path = viewPath({
    pkg: pkgParam,
    query: document.getElementById('search').value,
    team: teamFilter,
    list: listFilter,
    set: setFilter,
  });
  if (path === shownView) return;
  wantedView = path;
  let found;
  if (path.startsWith('pkg:')) {
    const row = await fullRow({ name: path.slice(4) });
    found = row ? [row] : [];
  } else {
    const res = await fetch(dataUrl(path), { cache: 'no-store' });
    if (!res.ok && res.status !== 404) throw new Error(res.status);
    found = res.ok ? (await res.json()).packages : [];
  }
  if (wantedView !== path) return; // another view was asked for meanwhile
  packages = found.map((p) => withRunStamps(p, checkedAt));
  shownView = path;
}

// The name index, for searches beyond the view shown: loaded once, when a
// search first needs it, then the list is drawn again.
function loadNames() {
  if (namesLoading) return;
  namesLoading = fetch(dataUrl('names.json'), { cache: 'no-store' })
    .then((res) => (res.ok ? res.json() : { names: [] }))
    .then((data) => {
      names = data.names || [];
      update({ keepPage: true });
    })
    .catch(() => {
      namesLoading = null; // tried again with the next search
    });
}

// Draw the list again after the view's state changed (a filter, the search,
// the address): with every package, its view loaded first. keepPage: as
// render's.
async function update({ keepPage = false } = {}) {
  if (community) {
    try {
      await ensureView();
    } catch {
      document.getElementById('content').innerHTML = html`<div class="error">
        Couldn't load these packages' data. Reload the page to try again.</div>`;
      return;
    }
  }
  render(currentFiltered(), { keepPage });
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
    checkedAt = data.checkedAt || null;
    if (data.allPackages) {
      community = true;
      manifest = data;
      format = 2;
      shardCount = data.shardCount;
    } else {
      packages = ((await summaryOf(data)) || data.packages || []).map((p) =>
        withRunStamps(p, checkedAt),
      );
    }
    // The nixkeeper that made the data, in the footer (older data has none).
    document.getElementById('version').textContent =
      data.version && data.version !== 'unknown' ? ` ${data.version}` : '';
    showListProblems(data.listProblems || []);
    setSitePalette(data.page?.theme || null);
    document.getElementById('search').disabled = false;
    await update({ keepPage: true });
  } catch {
    content.innerHTML = html`<div class="error">
      Couldn't load <code>${dataUrl('index.json')}</code>.<br>
      Check that the sync has run at least once (and, on GitHub, that the repo is public).
    </div>`;
  }
}

function longDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

// The tab's icon shows what needs attention among packages (faviconKey).
function setFavicon(base) {
  const key = faviconKey(base, platformFilter);
  const link = document.getElementById('favicon');
  if (link && !link.href.endsWith(`favicon-${key}.svg`)) link.href = `favicon-${key}.svg`;
}

function renderStats() {
  // Counts follow the platform and list filters, so "outdated" means
  // outdated on macOS, or on the gaming-team list, while that's selected.
  const base = packages.filter((p) => inPlatform(p) && inList(p) && inTeam(p));
  setFavicon(base);
  renderLists();
  const buttons = Object.entries(FILTERS).map(([key, f]) => {
    const count = base.filter(f.test).length;
    // "vulnerable" only shows up when something is actually flagged.
    if (key === 'vuln' && !count && activeFilter !== 'vuln') return '';
    const pressed = activeFilter === key;
    return html`<button class="stat-btn" data-filter="${key}" aria-pressed="${pressed}"
      ${!count && key !== 'all' && !pressed ? raw('disabled') : ''}>
      <b${f.color ? html` style="color:${f.color}"` : ''}>${count}</b> ${key === 'all' && community ? 'here' : f.label}</button>`;
  });
  const stale =
    !checkedAt || Date.now() - new Date(checkedAt).getTime() > STALE_AFTER_HOURS * 3600e3;
  const platformChip = platformFilter
    ? html`<button class="plat-filter" data-clear="platform" title="Show all platforms">${PLATFORMS[platformFilter].label} only ✕</button>`
    : '';
  const teamChip = teamFilter
    ? html`<button class="plat-filter" data-clear="team" title="Show every team's packages">team: ${teamName()} ✕</button>`
    : '';
  document.getElementById('stats').innerHTML = html`${buttons}${platformChip}${teamChip}`;
  const checked = document.getElementById('checked');
  checked.classList.toggle('stale', stale);
  // The exact time on hover: "checked 4h ago" is friendly, but vague.
  const exact = checkedAt
    ? `Last full sync: ${new Date(checkedAt).toLocaleString(undefined, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short',
      })}.`
    : 'No full sync yet.';
  checked.title = stale
    ? `${exact} The daily sync hasn't updated the data in over 2 days. Check where it runs (on GitHub: the Actions tab).`
    : exact;
  checked.textContent = `checked ${timeAgo(checkedAt)}${stale ? ' — sync may be failing' : ''}`;
}

// The lists from package-lists/, as more filters after the counts (a
// divider between). Hidden when there's only one (or data from before lists
// existed).
function renderLists() {
  const el = document.getElementById('lists');
  const names = allLists();
  if (listFilter && !names.includes(listFilter)) names.push(listFilter); // e.g. a renamed list
  if (names.length < 2) {
    el.innerHTML = '';
    return;
  }
  const base = packages.filter((p) => inPlatform(p) && inTeam(p));
  const listCount = (name) =>
    community
      ? manifest.views.lists[name] || 0
      : base.filter((p) => (p.lists || []).includes(name)).length;
  el.innerHTML = html`<span class="lists-label">lists</span>${names.map((name) => {
    const pressed = listFilter === name;
    const count = listCount(name);
    return html`<button class="stat-btn" type="button" data-list="${name}" aria-pressed="${pressed}"
        title="${pressed ? 'Show every list' : `Show only the ${name} list (shareable: it's in the address)`}">
        <b>${count}</b> ${name}</button>`;
  })}`;
}

// The packages the table shows, in order: a row's data-i is its place here.
let shown = [];

const CHEVRON = raw(
  '<svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>',
);

function rowHtml(pkg, i) {
  const st = computeStatus(pkg);
  return html`<tr class="row" tabindex="0" data-i="${i}">
      <td class="c-name"><div class="pkg-name"><span class="who"><span class="status-dot ${waitingForChannel(pkg) ? 'merged' : st}" title="${waitingForChannel(pkg) ? DOT_TITLE.merged : DOT_TITLE[st]}"></span><span class="n">${pkg.name}</span>${ageTag(pkg, st)}</span>${platformTags(pkg)}</div></td>
      <td class="c-ver ver mono">${versionCell(pkg, st)}</td>
      <td class="c-gh${pkg.openPRs || pkg.openIssues ? '' : ' quiet'}">${githubLinks(pkg)}</td>
      <td class="c-build">${buildCell(pkg)}</td>
      <td class="c-update">${updateCell(pkg)}</td>
      <td class="c-chev"><span class="chev" aria-hidden="true">${CHEVRON}</span></td>
    </tr>`;
}

// The pages of the list, when there's more than one: "1–200 of 241" and
// links to the others (real links, so one can open in a new tab).
function pagerHtml(total, pages) {
  if (pages < 2) return '';
  const first = (pageNum - 1) * PAGE_SIZE + 1;
  const last = Math.min(pageNum * PAGE_SIZE, total);
  const link = (p, text, label) =>
    p === pageNum
      ? html`<span class="page-btn" aria-current="page">${text}</span>`
      : html`<a class="page-btn" href="${viewQuery(p)}" data-page="${p}"${label ? html` aria-label="${label}"` : ''}>${text}</a>`;
  return html`<nav class="pager" aria-label="Pages">
    <span class="page-count">${first.toLocaleString()}–${last.toLocaleString()} of ${total.toLocaleString()}</span>
    ${pageNum > 1 ? link(pageNum - 1, '‹', 'Previous page') : ''}
    ${pageLinks(pageNum, pages).map((p) => (p === null ? html`<span class="page-gap" aria-hidden="true">…</span>` : link(p, String(p), `Page ${p}`)))}
    ${pageNum < pages ? link(pageNum + 1, '›', 'Next page') : ''}
  </nav>`;
}

// One page of the table at once, as one piece of markup: many rows draw
// far faster that way than one by one. Each row's panel is only made when
// it's first opened (toggle), and the table's clicks are handled once, for
// every row (below). The list changed (a filter, the search, the order):
// back to the first page, unless keepPage (loading a shared address,
// following a page link).
function render(list, { keepPage = false } = {}) {
  renderStats();
  renderScope();
  const content = document.getElementById('content');
  const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  pageNum = keepPage ? Math.min(pageNum, pages) : 1;
  writeViewToUrl();
  shown = list.slice((pageNum - 1) * PAGE_SIZE, pageNum * PAGE_SIZE);
  if (!list.length) {
    content.innerHTML = html`<div class="empty">No packages match${activeFilter !== 'all' && !document.getElementById('search').value.trim() ? ` the “${FILTERS[activeFilter].label}” filter` : ''}${community ? ' here' : ''}.</div>${moreMatchesHtml()}`;
    return;
  }
  content.innerHTML = html`<div class="wrap"><table>
    <thead><tr>
      <th style="padding-left:10px">Package</th><th>nixpkgs unstable</th><th>Open on GitHub</th><th>Build failures</th><th>Update failures</th><th aria-hidden="true"></th>
    </tr></thead>
    <tbody id="rows">${shown.map(rowHtml)}</tbody>
  </table></div>${pagerHtml(list.length, pages)}${moreMatchesHtml()}`;
}

// With every package: what the page shows, out of all of nixpkgs. The
// counts of it all (the manifest's), the generated sets (pending), the view
// shown and the way back to what needs attention, and a team picker.
function renderScope() {
  const el = document.getElementById('scope');
  if (!el) return;
  el.hidden = !community;
  if (!community) return;
  const c = manifest.counts || {};
  const n = (x) => (x || 0).toLocaleString();
  const views = manifest.views || {};
  const handle = document.getElementById('search').value.trim().replace(/^@/, '');
  const path = shownView || '';
  const what = path.startsWith('pkg:')
    ? html`<b class="mono">${path.slice(4)}</b>`
    : path.startsWith('views/maintainer/')
      ? handle === 'none'
        ? html`packages <b>with no maintainer</b>`
        : html`<b>@${handle}</b>'s packages`
      : path.startsWith('views/team/')
        ? html`the <b>${teamName()}</b> team's packages`
        : path.startsWith('views/list/')
          ? html`the <b>${listFilter}</b> list`
          : path.startsWith('views/set/')
            ? html`<b>${setFilter}</b>, a generated set (pending: only Repology's versions and Hydra's builds for now)`
            : html`what <b>needs attention</b> (${n(views.attention)}: failing or outdated)`;
  const teams = Object.entries(views.teams || {});
  el.innerHTML = html`<div class="scope-all">Every nixpkgs package: <b>${n(c.tracked)}</b>, of which
      <b>${n(c.outdated)}</b> outdated, <b>${n(c.failed)}</b> failed${c.vulnerable ? html`, <b>${n(c.vulnerable)}</b> flagged vulnerable` : ''};
      and <b>${n(c.pending)}</b> in generated sets, pending:
      ${Object.entries(views.sets || {}).map(([s, count], i) => html`${i ? ', ' : ''}<a class="files-link" href="${scopeHref({ set: s })}" data-scope-set="${s}">${s}</a> (${n(count)})`)}.</div>
    <div class="scope-view"><span>Showing ${what}.</span>${
      path === 'views/attention.json'
        ? ''
        : html` <a class="files-link" href="${scopeHref({})}" data-scope-home>Back to what needs attention</a>`
    }
      ${
        teams.length
          ? html`<label class="team-pick">Team <select id="teamPick"><option value="">—</option>${teams.map(([t, count]) => html`<option value="${t}"${teamFilter && t.toLowerCase() === teamFilter.toLowerCase() ? raw(' selected') : ''}>${t} (${n(count)})</option>`)}</select></label>`
          : ''
      }</div>`;
}

// The address of a view (scopeHref({ set }), { pkg }, {} for what needs
// attention): the others' parameters cleared, the data's own kept.
function scopeHref({ set = null, pkg = null }) {
  const params = new URLSearchParams(location.search);
  for (const k of ['filter', 'q', 'sort', 'platform', 'list', 'team', 'set', 'pkg', 'page'])
    params.delete(k);
  if (set) params.set('set', set);
  if (pkg) params.set('pkg', pkg);
  const query = params.toString();
  return location.pathname + (query ? `?${query}` : '');
}

// Show a view: set (a generated set), pkg (one package), neither: what needs
// attention. The search, filters and page start over.
function showView({ set = null, pkg = null }) {
  setFilter = set;
  pkgParam = pkg;
  teamFilter = null;
  listFilter = null;
  activeFilter = 'all';
  document.getElementById('search').value = '';
  update();
  document.getElementById('scope')?.scrollIntoView({ block: 'nearest' });
}

// With every package, under a plain search: the packages beyond the view
// shown whose names match, from the name index (loaded on first use), each
// opening on its own (?pkg=).
function moreMatchesHtml() {
  const query = document.getElementById('search').value;
  if (!community || pkgParam || query.trim().length < 2 || query.trim().startsWith('@')) return '';
  if (!names) {
    loadNames();
    return html`<div class="more-matches"><div class="other-label">Searching all of nixpkgs…</div></div>`;
  }
  const { found, total } = nameMatches(names, query, new Set(packages.map((p) => p.name)));
  if (!total) return '';
  return html`<div class="more-matches">
    <div class="other-label">${total.toLocaleString()} more ${total === 1 ? 'package matches' : 'packages match'} in all of nixpkgs${total > found.length ? html`, the first ${found.length}` : ''}</div>
    <ul>${found.map(
      ([name, letter, set]) =>
        html`<li><span class="status-dot ${NAME_DOTS[letter[0]] || 'neutral'}"></span><a class="files-link mono" href="${scopeHref({ pkg: name })}" data-scope-pkg="${name}">${name}</a>${set ? html` <span class="badge neutral" title="A generated set: only Repology's versions and Hydra's builds for now">pending</span>` : ''}${letter.endsWith('v') ? html` <span class="badge vuln">vulnerable</span>` : ''}</li>`,
    )}</ul>
  </div>`;
}

// One panel under the row, showing the package details (clicking the row),
// its builds or its latest update attempt (clicking those cells). Clicking
// what's shown closes it; clicking something else switches.
async function toggle(tr, mode) {
  const pkg = shown[tr.dataset.i];
  let detail = tr.nextElementSibling;
  if (!detail?.classList.contains('detail')) {
    detail = document.createElement('tr');
    detail.className = 'detail';
    detail.innerHTML = `<td colspan="6"><div class="detail-inner">
      <div class="nix-line">Loading detail…</div>
    </div></td>`;
    tr.after(detail);
  }
  const inner = detail.querySelector('.detail-inner');
  const closing = tr.classList.contains('open') && detail.dataset.mode === mode;
  tr.classList.toggle('open', !closing);
  detail.classList.toggle('open', !closing);
  detail.dataset.mode = closing ? '' : mode;
  for (const btn of tr.querySelectorAll('.failure-btn')) {
    btn.setAttribute('aria-expanded', !closing && btn.dataset.kind === mode);
  }
  if (closing) return;
  // The panel needs the full row (the list has the summary's entry).
  const row = await fullRow(pkg);
  const entries = row && mode === 'info' ? await repologyEntries(row) : null;
  if (detail.dataset.mode !== mode) return; // switched or closed meanwhile
  if (!row) {
    inner.innerHTML = html`<div class="nix-line">Couldn't load this package's details. Open it again to retry.</div>`;
  } else if (mode === 'build') fillBuilds(row, inner);
  else if (mode === 'update') fillUpdate(row, inner);
  else fillDetail(row, inner, entries);
}

// The table's clicks, for every row: a link opens (and nothing else), the
// versions copy the update's title, a platform filters by it, the build and
// update cells open their panel, and anywhere else the details.
document.getElementById('content').addEventListener('click', (e) => {
  // A page link: that page, from its top (a click with a modifier opens it
  // elsewhere, as links do).
  const pageLink = e.target.closest('a.page-btn');
  if (pageLink && !(e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button)) {
    e.preventDefault();
    pageNum = Number(pageLink.dataset.page);
    update({ keepPage: true });
    // Back to the table's top, the keyboard on its first row.
    const content = document.getElementById('content');
    if (content.getBoundingClientRect().top < 0) content.scrollIntoView();
    content.querySelector('tr.row')?.focus({ preventScroll: true });
    return;
  }
  const tr = e.target.closest('tr.row');
  if (!tr || e.target.closest('a')) return;
  const copy = e.target.closest('.vcopy');
  if (copy) {
    copyTitle(copy);
    return;
  }
  const plat = e.target.closest('button.plat');
  if (plat) {
    // Clicking the active platform again shows all platforms.
    platformFilter = platformFilter === plat.dataset.platform ? null : plat.dataset.platform;
    update();
    return;
  }
  toggle(tr, e.target.closest('.failure-btn')?.dataset.kind || 'info');
});
document.getElementById('content').addEventListener('keydown', (e) => {
  if (e.target.matches('tr.row') && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    e.target.click();
  }
});

// A source the last sync couldn't refresh ("builds", "update", "upstream"):
// what's shown is from before `since`. null if it refreshed fine.
const notRefreshed = (pkg, source) => pkg.notRefreshed?.[source] || null;
const staleText = (info, what) =>
  `${what} since ${longDate(info.since)} (${daysText(info.since)}): ${info.reason}`;
// The same, as a line at the top of a panel.
const staleNote = (info, what, after) =>
  info ? html`<div class="stale-note">⚠ ${staleText(info, what)}. ${after}</div>` : '';

// quiet: nothing that needs attention, so it's drawn muted, without a dot
// ("none reported" as a dash), and the phone layout leaves it out. Only
// what needs a look keeps its colour.
function failureButton(kind, dot, text, title, stale = null, quiet = false) {
  const calm = quiet && !stale;
  const shown = calm && text === 'none reported' ? html`<span aria-hidden="true">—</span>` : text;
  return html`<button class="failure-btn${dot === 'missing' ? ' failing' : ''}${calm ? ' calm' : ''}" type="button" data-kind="${kind}"${calm ? html` data-quiet aria-label="${kind}: ${text}"` : ''} aria-expanded="false" title="${title}">
    <span class="status-dot ${dot}"></span><span class="cell-label">${kind}:</span>${shown}${
      stale
        ? html` <span class="stale-tag" title="${staleText(stale, 'Not refreshed')}">not refreshed</span>`
        : ''
    }</button>`;
}

// Whether Hydra built this at all: not for unfree packages, nor ones nixpkgs
// keeps off Hydra (hydraPlatforms).
function hydraBuildsIt(pkg) {
  return !pkg.unfree && pkg.builds.some((b) => b.status !== 'notBuilt');
}

function buildCell(pkg) {
  if (!pkg.builds) return html`<span class="failure-na" title="Not in nixpkgs">—</span>`;
  const button = (dot, text, quiet = false) =>
    failureButton('build', dot, text, 'Show Hydra builds', notRefreshed(pkg, 'builds'), quiet);
  if (failedBuilds(pkg).length) return button('missing', 'failure reported');
  // Known failures: shown, but not counted as failed.
  if (buildsWith(pkg, 'broken').length) return button('caution', 'marked broken');
  if (!hydraBuildsIt(pkg)) return button('neutral', 'not built by Hydra', true);
  return button('ok', 'none reported', true);
}

// nixpkgs-update's latest attempt. `update` is null when the bot never tried
// and missing for packages not in nixpkgs.
function updateCell(pkg) {
  if (pkg.pending)
    return html`<span class="failure-na" title="${PENDING_TITLE}: nixpkgs-update's attempts aren't read">—</span>`;
  if (pkg.update === undefined)
    return html`<span class="failure-na" title="Not in nixpkgs">—</span>`;
  const button = (dot, text, quiet = false) =>
    failureButton(
      'update',
      dot,
      text,
      'Show the latest nixpkgs-update attempt',
      notRefreshed(pkg, 'update'),
      quiet,
    );
  if (pkg.updateFailure) return button('missing', 'failure reported');
  // The bot's last attempt failed, but nixpkgs has moved on since: not a
  // failure anymore, though the next attempt may well break the same way.
  if (pkg.update?.outcome === 'superseded') return button('neutral', 'superseded', true);
  // A newer version the bot has no way to update to: not a failure, but it
  // needs a manual update (or an updateScript).
  if (pkg.update?.outcome === 'cantUpdate') return button('caution', "can't update");
  // With every package, only the lists' packages' logs are read (with no
  // attempt read before).
  if (pkg.unread?.includes('update') && !pkg.update) return button('neutral', 'not read', true);
  if (pkg.update === null) return button('neutral', 'not attempted', true);
  return button('ok', 'none reported', true);
}

const prLink = (n, text) =>
  html`<a class="files-link" href="https://github.com/NixOS/nixpkgs/pull/${n}" target="_blank" rel="noopener">${text}</a>`;
const UPDATE_OUTCOME = {
  failed: { dot: 'missing', text: () => 'failed' },
  // nixpkgs has moved on since the attempt (updated another way): in the
  // channel, or merged on master and not in the channel yet. Or a rule
  // ignores the version it tried: your own (package-lists/ignored-updates.nix)
  // or a community one (community/ignored-updates.nix).
  superseded: {
    dot: 'neutral',
    text: (u, pkg) => {
      const what = u.supersededOutcome === 'cantUpdate' ? "couldn't update it" : 'failed';
      const version = u.to === '1' ? pkg.nixVersion : u.to;
      return u.supersededOn === 'ignored'
        ? html`failed trying <span class="mono">${version}</span>, a version ignored by ${u.community ? 'a community rule' : 'a manual rule'}: ${u.reason}`
        : u.supersededOn === 'master'
          ? html`${what}, but master already has <span class="mono">${onMaster(pkg)}</span> (merged, waiting for nixos-unstable)`
          : html`${what}, but nixpkgs has moved on to <span class="mono">${pkg.nixVersion}</span> since`;
    },
  },
  // Every way the bot has of updating a package declined (the excerpt says
  // why): the update needs doing by hand, or an updateScript.
  cantUpdate: {
    dot: 'caution',
    text: () =>
      "couldn't update it: none of the bot's ways of updating a package apply here. Update it by hand, or give the package an updateScript so the bot can next time",
  },
  prOpened: { dot: 'ok', text: (u) => html`opened ${prLink(u.pr, `PR #${u.pr} ↗`)}` },
  prExists: {
    dot: 'ok',
    text: (u) => html`a PR was already open${u.pr ? html` (${prLink(u.pr, `#${u.pr} ↗`)})` : ''}`,
  },
  noChange: { dot: 'ok', text: () => 'nothing to update' },
  other: { dot: 'neutral', text: () => 'finished without a recognisable result' },
};

function fillUpdate(pkg, el) {
  const u = pkg.update;
  const unread = pkg.unread?.includes('update')
    ? html`<div class="stale-note">Not read on the last sync: with every package, nixpkgs-update's attempts come from a digest of them, which hasn't read this package's yet.${u ? ' Showing the last attempt read.' : ''}</div>`
    : '';
  if (unread && !u) {
    el.innerHTML = unread;
    return;
  }
  const stale = html`${unread}${staleNote(
    notRefreshed(pkg, 'update'),
    'Not refreshed',
    'Showing the last known attempt.',
  )}`;
  if (!u) {
    el.innerHTML = html`${stale}<div class="nix-line">nixpkgs-update hasn't tried to update this package (it may have no update source it understands).</div>`;
    return;
  }
  const dir = u.log.slice(0, u.log.lastIndexOf('/') + 1); // every attempt's log
  // A plain day: read as midday UTC, so no time zone moves it to the day before.
  const day = `${u.date}T12:00:00Z`;
  // "0 -> 1" means the package's updateScript picks the version.
  const versions =
    u.from && !(u.from === '0' && u.to === '1')
      ? html` · <span class="mono">${u.from} → ${u.to}</span>`
      : '';
  const o = UPDATE_OUTCOME[u.outcome] || UPDATE_OUTCOME.other;
  el.innerHTML = html`${stale}
    <div class="nix-line">Latest nixpkgs-update attempt${(pkg.attrs || []).length > 1 ? html` at <span class="mono">${u.attr}</span>` : ''} · ${longDate(day)} (${shortAge(day)} ago)${versions}</div>
    <div class="build-list"><div class="build-line">
      <span class="status-dot ${o.dot}"></span><span class="st ${o.dot}">${o.text(u, pkg)}</span>
    </div></div>
    ${u.excerpt?.length ? html`<pre class="log-excerpt mono">${u.excerpt.join('\n')}</pre>` : ''}
    <div class="detail-row">
      <a class="files-link" href="${safeUrl(u.log)}" target="_blank" rel="noopener">log ↗</a>
      <a class="files-link" href="${safeUrl(dir)}" target="_blank" rel="noopener">all attempts ↗</a>
    </div>`;
}

const HYDRA = 'https://hydra.nixos.org';
const BUILD_STATUS = {
  ok: { dot: 'ok', text: 'built OK' },
  failed: { dot: 'missing', text: 'failed' },
  broken: { dot: 'caution', text: 'marked broken in nixpkgs' },
  dependency: { dot: 'caution', text: "didn't build: a dependency failed" },
  unfinished: { dot: 'caution', text: "didn't finish (timed out or aborted)" },
  notBuilt: { dot: 'neutral', text: 'not built by Hydra on this platform' },
  unknown: { dot: 'neutral', text: "couldn't check Hydra on the last run" },
};

function buildLine(pkg, b) {
  const s = BUILD_STATUS[b.status] || BUILD_STATUS.unknown;
  const multi = (pkg.attrs || []).length > 1;
  // The versions only when they differ: the same version means something else
  // broke it (a dependency, the toolchain), not the update.
  const versionsDiffer = b.version && b.lastSuccessVersion && b.version !== b.lastSuccessVersion;
  const at = versionsDiffer && b.status === 'failed' ? ` at ${b.version}` : '';
  let lastGood = '';
  if (versionsDiffer) {
    const v = b.lastSuccessVersion;
    lastGood = b.lastSuccessBuild
      ? html` at <a href="${HYDRA}/build/${b.lastSuccessBuild}" target="_blank" rel="noopener">${v} ↗</a>,`
      : ` at ${v},`;
  }
  const since =
    'lastSuccess' in b
      ? html`<span class="since">${b.lastSuccess ? html`last succeeded${lastGood} ${longDate(b.lastSuccess)} (${shortAge(b.lastSuccess)} ago)` : 'never built successfully'}</span>`
      : '';
  let links = '';
  if (b.status === 'failed') {
    links = html`<a class="files-link" href="${HYDRA}/build/${b.build}/log" target="_blank" rel="noopener">log ↗</a>${since}`;
  } else if (b.status === 'dependency' || b.status === 'unfinished') {
    links = html`<a class="files-link" href="${HYDRA}/build/${b.build}" target="_blank" rel="noopener">build ${b.build} ↗</a>${since}`;
  } else if (b.status === 'broken') {
    // Where to fix it: the package's source, at the line nixpkgs points to.
    links = html`${since}${safeUrl(pkg.source) ? html`<a class="files-link" href="${safeUrl(pkg.source)}" target="_blank" rel="noopener">source ↗</a>` : ''}`;
  } else if (b.build) {
    links = html`<a class="files-link" href="${HYDRA}/build/${b.build}" target="_blank" rel="noopener">build ${b.build} ↗</a>`;
  }
  return html`<div class="build-line">
    <span class="status-dot ${s.dot}"></span>
    <span class="mono sys">${b.system}</span>
    ${multi ? html`<span class="mono attr">${b.attr}</span>` : ''}
    <span class="st ${s.dot}">${s.text}${at}</span>${links}
  </div>`;
}

function fillBuilds(pkg, el) {
  const jobset = html`<span class="mono">nixpkgs/unstable</span>`;
  let body;
  if (pkg.unfree) {
    body = html`<div class="nix-line">Hydra doesn't build unfree packages, so there are no build results for this one.</div>`;
  } else if (!hydraBuildsIt(pkg)) {
    body = html`<div class="nix-line">Hydra doesn't build this package (nixpkgs may exclude it with <span class="mono">hydraPlatforms</span>).</div>`;
  } else {
    const darwin = pkg.platforms === null || pkg.platforms?.darwin;
    // Builds with nothing going on are checked every few days, not daily
    // (nixkeeper/sources/hydra.py): when the oldest was, if it isn't today.
    const checked = pkg.builds
      .map((b) => b.checkedAt)
      .filter(Boolean)
      .sort()[0];
    const age = checked && daysText(checked);
    const when =
      checked && age !== 'today'
        ? html`, <span title="${new Date(checked).toLocaleString()}">checked ${age} ago</span>`
        : '';
    body = html`<div class="nix-line">Hydra builds of nixpkgs master (jobset ${jobset})${when}</div>
      <div class="build-list">${pkg.builds.map((b) => buildLine(pkg, b))}</div>
      ${darwin ? html`<div class="build-note">x86_64-darwin is no longer built by nixpkgs.</div>` : ''}`;
  }
  const jobLinks = (pkg.builds || [])
    .filter((b) => b.status !== 'notBuilt')
    .map(
      (b) =>
        html`<a class="files-link" href="${HYDRA}/job/nixpkgs/unstable/${encodeURIComponent(`${b.attr}.${b.system}`)}" target="_blank" rel="noopener">${pkg.attrs.length > 1 ? `${b.attr}.${b.system}` : b.system} job ↗</a>`,
    );
  const stale = staleNote(
    notRefreshed(pkg, 'builds'),
    'Not refreshed',
    'Showing the last known results.',
  );
  el.innerHTML = html`${stale}${body}${jobLinks.length ? html`<div class="detail-row">${jobLinks}</div>` : ''}`;
}

// From nixpkgs meta.platforms; null means nixpkgs doesn't restrict it.
function platformTags(pkg) {
  const pl = pkg.platforms;
  if (pl === undefined) return '';
  if (pl === null)
    return html`<span class="plats"><span class="plat any" title="nixpkgs doesn't restrict its platforms">any platform</span></span>`;
  const tags = Object.entries(PLATFORMS)
    .filter(([key]) => pl[key])
    .map(
      ([key, p]) =>
        html`<button class="plat" type="button" data-platform="${key}" aria-pressed="${platformFilter === key}"
      title="${platformFilter === key ? 'Show all platforms' : `Show only packages available on ${p.label}`}">${p.label}</button>`,
    );
  // Together, so they wrap as one.
  return tags.length ? html`<span class="plats">${tags}</span>` : '';
}

// Open nixpkgs PRs / issues with the package's attribute name in the title. Counts come from
// the fetch script's GitHub search; without them the buttons are plain links.
function githubLinks(pkg) {
  const term = pkg.searchTerm || pkg.name;
  // Packages with none open are counted every few days, not daily
  // (nixkeeper/sources/github.py): when, if it wasn't today.
  const age = pkg.countedAt && daysText(pkg.countedAt);
  const counted = age && age !== 'today' ? ` (counted ${age} ago)` : '';
  const link = (kind, path, label, count) => {
    const q = encodeURIComponent(`is:${kind} state:open in:title ${term}`);
    return html`<a class="gh-btn" href="https://github.com/NixOS/nixpkgs/${path}?q=${q}" target="_blank" rel="noopener"
      title="Open nixpkgs ${label} with ${term} in the title${counted}"${count === 0 ? raw(' data-zero') : ''}>${label}${count != null ? html` <b>${count}</b>` : ''}</a>`;
  };
  return html`<span class="gh-links">${link('pr', 'pulls', 'PRs', pkg.openPRs)}${link('issue', 'issues', 'issues', pkg.openIssues)}</span>`;
}

// "…/pkgs/by-name/we/wesnoth/package.nix#L147" -> "package.nix"
function sourceFileName(url) {
  return url.split('#')[0].split('/').pop();
}

// entries: the row's Repology entries, or null if they couldn't be loaded
// (repologyEntries).
function fillDetail(pkg, el, entries) {
  const loaded = Array.isArray(entries);

  const others = loaded ? comparedRepos(entries.filter((e) => e.repo !== NIX_REPO)) : [];
  // With every package, a row no list has keeps the newest repositories
  // only (nixkeeper/datastore.py, kept_entries): the rest are on Repology.
  const notKept =
    community && !pkg.lists?.length && pkg.repoCount > others.length
      ? pkg.repoCount - others.length
      : 0;
  const compared = others.length + notKept;
  // Repology is asked every few days for packages with nothing going on
  // (nixkeeper/lookup.py): how old its data is, if it isn't from today.
  const repologyDays = pkg.repologyCheckedAt && daysText(pkg.repologyCheckedAt);
  const repologyAge =
    repologyDays && repologyDays !== 'today'
      ? html` <span class="since" title="${new Date(pkg.repologyCheckedAt).toLocaleString()}">· ${repologyDays} ago</span>`
      : '';
  const homepage = safeUrl(pkg.homepage);

  const st = computeStatus(pkg);
  const up = pkg.upstream;
  // nixkeeper's update check, and whether it was worked out from nixpkgs.
  const ours = up?.inferred
    ? "nixkeeper's update check (worked out from nixpkgs' source)"
    : "nixkeeper's update check";
  // The repositories it's compared against, nixkeeper's update check first.
  const mine = nixkeeperEntry(pkg);
  const checkedDays = up?.checkedAt && daysText(up.checkedAt);
  const chips = [
    ...(mine
      ? [
          {
            ...mine,
            title: `${mine.kind}${mine.where ? `: ${mine.where}` : ''}${checkedDays && checkedDays !== 'today' ? `, checked ${checkedDays} ago` : ''}`,
          },
        ]
      : []),
    ...others.map((e) => ({
      repo: e.repo,
      version: e.version,
      ahead: e.status === 'newest' && e.version !== pkg.nixVersion,
    })),
  ];
  // "in the wesnoth/wesnoth tags" or "on www.barebones.com".
  const upLabel = up ? up.label || `${up.repo} tags` : '';
  const upLink = up
    ? html`${up.repo ? 'in the' : 'on'} ${safeUrl(up.url) ? html`<a class="files-link" href="${safeUrl(up.url)}" target="_blank" rel="noopener">${upLabel} ↗</a>` : upLabel}`
    : '';
  const since = pkg.outdatedSince
    ? ` — outdated since ${longDate(pkg.outdatedSince)} (${daysText(pkg.outdatedSince)})`
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
  // A package updated together with another (follows): which, and that its
  // newest version and update PRs are that package's.
  const follows = up?.follows
    ? html`updated together with <b>${up.follows}</b> (${communityCheck(pkg) ? 'a community rule' : 'your update checks'}): its newest version and update PRs count for this package too`
    : '';
  // When the update check is what makes it outdated, say where the newer
  // version came from, and how it compares with Repology.
  const upstreamLine = () =>
    follows
      ? html`nixpkgs unstable has <span class="mono" style="font-weight:600">${pkg.nixVersion}</span>, behind <span class="mono" style="font-weight:600;color:var(--warn)">${up.version}</span>: it's ${follows}${since}.`
      : html`nixpkgs unstable has <span class="mono" style="font-weight:600">${pkg.nixVersion}</span>; ${communityCheck(pkg) ? 'a community update check' : ours} found <span class="mono" style="font-weight:600;color:var(--warn)">${up.version}</span> ${upLink}${
          pkg.refVersion !== up.version
            ? html`; Repology's newest is <span class="mono">${pkg.refVersion}</span>`
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
    ? html`<div class="stale-note">⚠ ${staleText(failing, "nixkeeper's update check has been failing")}.${
        up
          ? html` Still using its last result: <span class="mono">${up.version}</span>${up.checkedAt ? ` (${longDate(up.checkedAt)})` : ''}.`
          : ' It has no result yet.'
      } ${
        communityCheck(pkg)
          ? html`It's a community rule (<span class="mono">community/update-checks.nix</span> in nixkeeper): report it there, or give this package a rule of your own in your update checks.`
          : html`Fix it in <span class="mono">package-lists/update-checks.nix</span>.`
      }</div>`
    : '';
  // An up-to-date rule: Repology gets this version wrong, so it counts as
  // up to date. What Repology said, and why the rule says otherwise.
  const rule = pkg.upToDate;
  const ruleText = rule
    ? html` — up to date by ${rule.community ? 'a community rule' : 'a manual rule'}: ${rule.reason || ''} (Repology calls it <span class="mono">${rule.status || '?'}</span>${
        rule.newest
          ? html`, with <span class="mono">${rule.newest}</span> as the newest elsewhere`
          : ''
      }).`
    : '';
  const nixLine =
    up?.newer && !fromMaster(pkg)
      ? upstreamLine()
      : st === 'missing'
        ? html`Not found in <span class="mono">nix_unstable</span> — nixpkgs doesn't currently package this.`
        : html`nixpkgs unstable has <span class="mono" style="font-weight:600">${pkg.nixVersion}</span>${
            rule
              ? ruleText
              : st === 'warn' && fromMaster(pkg)
                ? ` — the newest Repology and the update checks know of, but master already has a newer one${since.replace(' — ', '; ')}:`
                : st === 'warn'
                  ? html`, the newest seen elsewhere is <span class="mono" style="font-weight:600;color:var(--warn)">${pkg.refVersion || '?'}</span>${since}`
                  : st === 'neutral'
                    ? pkg.nixStatus === 'unlisted'
                      ? " — Repology doesn't list this package, so there's nothing to compare it with."
                      : html` — Repology classifies this version as <span class="mono">${pkg.nixStatus}</span>.`
                    : loaded
                      ? ` — the newest ${pkg.devel ? 'devel ' : ''}version, compared with ${compared} other ${compared === 1 ? 'repository' : 'repositories'}.`
                      : ` — the newest ${pkg.devel ? 'devel ' : ''}version.`
          }${
            up && !up.newer && !failing
              ? follows
                ? html` It's ${follows}.`
                : up.behind
                  ? html` ${ours}: ${behind} ${upLink} (up to <span class="mono">${up.version}</span>), not counted as outdated until ${limits}.`
                  : html` ${ours} ${st === 'warn' ? 'found nothing newer' : 'agrees'}: the latest version ${upLink} is <span class="mono">${up.version}</span>.`
              : ''
          }`;
  // Where master is: the PR that brought it, and whether Hydra built it.
  const masterSaid = [
    pkg.masterPR &&
      html`merged in <a class="files-link" href="${safeUrl(pkg.masterPR.url)}" target="_blank" rel="noopener">#${pkg.masterPR.number} ↗</a>`,
    pkg.master ? 'built by Hydra' : 'not built by Hydra yet',
  ]
    .filter(Boolean)
    .flatMap((part, i) => (i ? [', ', part] : [part]));

  const unloaded = loaded
    ? ''
    : html`<div class="stale-note">⚠ Couldn't load Repology's details for this package, so the repositories it's compared with aren't shown. Close and reopen it to try again.</div>`;
  const pending = pkg.pending
    ? html`<div class="stale-note">From a generated package set (<span class="mono">${pkg.set}</span>): only Repology's versions and Hydra's builds for now; update checks, nixpkgs-update's attempts and GitHub counts aren't collected for it yet.</div>`
    : '';
  el.innerHTML = html`
    <div class="nix-line">${nixLine}</div>${pending}${unloaded}${
      onMaster(pkg)
        ? html`<div class="master-note">master already has <span class="mono">${onMaster(pkg)}</span> (${masterSaid})${
            waitingForChannel(pkg)
              ? ': the update is merged, and reaches nixos-unstable when the channel next advances, usually within a few days.'
              : ', not in nixos-unstable yet.'
          }</div>`
        : ''
    }${checkNote}${
      pkg.nixVulnerable
        ? html`<div class="vuln-note">⚠ Repology flags nixpkgs' version <span class="mono">${pkg.nixVersion}</span> as vulnerable.${
            pkg.project
              ? html` <a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/cves" target="_blank" rel="noopener">Known CVEs ↗</a>`
              : ''
          }</div>`
        : ''
    }
    ${
      chips.length
        ? html`<div class="other-label">Compared against${repologyAge}</div><div class="repo-chips">
      ${chips.map((e, i) => html`<span class="repo-chip ${e.ahead ? 'ahead' : ''}"${e.title ? html` title="${e.title}"` : ''}${i >= COMPARED_SHOWN ? raw(' hidden') : ''}>${e.repo} <span class="v mono">${e.version || '?'}</span></span>`)}${
        chips.length > COMPARED_SHOWN
          ? html`<button type="button" class="more-btn" aria-expanded="false">Show all ${chips.length}</button>`
          : ''
      }${
        notKept && pkg.project
          ? html` <a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/versions" target="_blank" rel="noopener">${notKept} more on Repology ↗</a>`
          : ''
      }
    </div>`
        : ''
    }
    ${
      Array.isArray(pkg.maintainers)
        ? html`<div class="other-label">Maintainers</div><div class="maintainers">${
            pkg.maintainers.length
              ? pkg.maintainers.map(
                  (m) =>
                    html`<span class="maintainer"><button type="button" class="maint-btn" data-handle="${m}" title="Their packages here">@${m}</button><a class="files-link" href="https://github.com/${encodeURIComponent(m)}" target="_blank" rel="noopener" aria-label="${m} on GitHub" title="${m} on GitHub">↗</a></span>`,
                )
              : html`<span class="none-note">none in nixpkgs (<button type="button" class="maint-btn" data-handle="none" title="Packages with no maintainer">@none</button>)</span>`
          }</div>`
        : ''
    }
    ${
      pkg.teams?.length
        ? html`<div class="other-label">Teams</div><div class="maintainers">${pkg.teams.map(
            (t) =>
              html`<button type="button" class="maint-btn team-btn" data-team="${t}" title="The team's packages here">${t}</button>`,
          )}</div>`
        : ''
    }
    <div class="detail-row">
      ${homepage ? html`<a class="files-link" href="${homepage}" target="_blank" rel="noopener">Homepage ↗</a>` : ''}
      ${safeUrl(pkg.source) ? html`<a class="files-link" href="${safeUrl(pkg.source)}" target="_blank" rel="noopener" title="Where nixpkgs defines this package">${sourceFileName(pkg.source)} ↗</a>` : ''}
      ${pkg.project ? html`<a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/versions" target="_blank" rel="noopener">View on Repology ↗</a>` : ''}
    </div>
  `;
  // A maintainer's packages: searches for them (the search box, so the
  // address can be shared).
  // A team's packages: the team filter (?team=, shareable too).
  for (const btn of el.querySelectorAll('.team-btn')) {
    btn.addEventListener('click', () => {
      teamFilter = btn.dataset.team;
      update();
      document.getElementById('stats').scrollIntoView({ block: 'nearest' });
    });
  }
  for (const btn of el.querySelectorAll('.maint-btn:not(.team-btn)')) {
    btn.addEventListener('click', () => {
      const search = document.getElementById('search');
      search.value = `@${btn.dataset.handle}`;
      search.dispatchEvent(new Event('input'));
      search.scrollIntoView({ block: 'nearest' });
    });
  }
  el.querySelector('.more-btn')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const open = btn.getAttribute('aria-expanded') !== 'true';
    el.querySelectorAll('.repo-chip').forEach((chip, i) => {
      chip.hidden = !open && i >= COMPARED_SHOWN;
    });
    btn.setAttribute('aria-expanded', open);
    btn.textContent = open ? 'Show fewer' : `Show all ${chips.length}`;
  });
}

// How many repositories a panel shows before "Show all".
const COMPARED_SHOWN = 8;

function currentFiltered() {
  const q = document.getElementById('search').value;
  const list = packages.filter(
    (p) =>
      inPlatform(p) &&
      inList(p) &&
      inTeam(p) &&
      inSet(p) &&
      FILTERS[activeFilter].test(p) &&
      matchesSearch(p, q),
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
  const clear = e.target.closest('.plat-filter');
  if (clear) {
    if (clear.dataset.clear === 'team') teamFilter = null;
    else platformFilter = null;
    update();
    return;
  }
  const btn = e.target.closest('.stat-btn');
  if (!btn) return;
  // Clicking the active filter again goes back to showing everything.
  activeFilter = btn.dataset.filter === activeFilter ? 'all' : btn.dataset.filter;
  update();
});

document.getElementById('lists').addEventListener('click', (e) => {
  const btn = e.target.closest('.stat-btn');
  if (!btn) return;
  // Clicking the active list again shows every list.
  listFilter = btn.dataset.list === listFilter ? null : btn.dataset.list;
  update();
});

// Typing redraws the table once it pauses (150 ms), not at every key: with
// thousands of packages, each redraw takes a moment.
let searchTimer;
document.getElementById('search').addEventListener('input', () => {
  pkgParam = null; // a search leaves a package shown alone (?pkg=)
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => update(), 150);
});
document.getElementById('sortBtn').addEventListener('click', (e) => {
  sortAZ = !sortAZ;
  e.currentTarget.setAttribute('aria-pressed', sortAZ);
  if (packages.length || community) update();
  else writeViewToUrl();
});
// With every package: the links between views (a generated set, one
// package, back to what needs attention) and the team picker. A click with
// a modifier opens the link elsewhere, as links do.
document.addEventListener('click', (e) => {
  const a = e.target.closest('a[data-scope-set], a[data-scope-pkg], a[data-scope-home]');
  if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button) return;
  e.preventDefault();
  showView({ set: a.dataset.scopeSet || null, pkg: a.dataset.scopePkg || null });
});
document.addEventListener('change', (e) => {
  if (e.target.id !== 'teamPick') return;
  // A team's packages, from all of nixpkgs (not within a set or a package).
  teamFilter = e.target.value || null;
  setFilter = null;
  pkgParam = null;
  update();
});

// "/" jumps to the filter, as on GitHub; Escape in it clears it.
document.addEventListener('keydown', (e) => {
  const search = document.getElementById('search');
  if (e.key === '/' && !e.target.closest('input, textarea') && !search.disabled) {
    e.preventDefault();
    search.focus();
  } else if (e.key === 'Escape' && e.target === search && search.value) {
    search.value = '';
    clearTimeout(searchTimer);
    update();
  }
});

document
  .getElementById('themeBtn')
  .addEventListener('click', () => showThemePanel(document.getElementById('themePanel').hidden));
document.getElementById('themePanel').addEventListener('change', (e) => {
  const { name, value } = e.target;
  if (name === 'palette') store('nixkeeper-palette', value);
  // Auto is no choice: the system's setting.
  if (name === 'mode') store('nixkeeper-mode', value === 'auto' ? null : value);
  applyTheme();
});
document
  .getElementById('legendBtn')
  .addEventListener('click', () => showLegend(document.getElementById('legendPanel').hidden));
// The Theme menu and the legend close on a click elsewhere, or Escape (back
// to their button).
document.addEventListener('click', (e) => {
  if (!e.target.closest('.theme')) showThemePanel(false);
  if (!e.target.closest('.legend')) showLegend(false);
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  for (const [panel, btn, show] of [
    ['themePanel', 'themeBtn', showThemePanel],
    ['legendPanel', 'legendBtn', showLegend],
  ]) {
    if (document.getElementById(panel).hidden) continue;
    show(false);
    document.getElementById(btn).focus();
  }
});

// The sticky header's height, for the column headings to stick under it.
new ResizeObserver(([entry]) =>
  document.documentElement.style.setProperty(
    '--sticky-h',
    `${Math.round(entry.borderBoxSize[0].blockSize)}px`,
  ),
).observe(document.getElementById('stickyTop'));

// Phones and tablets: once the filters are stuck at the top, "checked ..."
// hides (stuck), and comes back at the top of the page. The bar keeps its
// place in the page (a margin for the hidden line), so the list doesn't jump.
const narrow = matchMedia('(max-width: 1080px)');
new IntersectionObserver(([entry]) => {
  const bar = document.getElementById('filterbar');
  const stuck = narrow.matches && !entry.isIntersecting && entry.boundingClientRect.top < 0;
  if (stuck === bar.classList.contains('stuck')) return;
  const before = bar.offsetHeight;
  bar.classList.toggle('stuck', stuck);
  bar.style.marginBottom = stuck ? `${before - bar.offsetHeight}px` : '';
}).observe(document.getElementById('stickMark'));

applyTheme();
readViewFromUrl();
loadIndex();
