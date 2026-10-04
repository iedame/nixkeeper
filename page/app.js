import {
  buildsWith as buildsOn,
  communityCheck,
  comparedRepos,
  compareVersions,
  computeStatus,
  daysText,
  escapeHtml,
  hasFailure as failureOn,
  faviconKey,
  fromMaster,
  href,
  midway,
  onMaster,
  onPlatform,
  attentionRank as rankOn,
  githubRepo as repoFrom,
  safeUrl,
  shortAge,
  targetVersion,
  themeFor,
  timeAgo,
  updateTitle,
  versionDiff,
  waitingForChannel,
  withSlash,
} from './logic.js';

const NIX_REPO = 'nix_unstable';

const githubRepo = (params) => repoFrom(params, location);

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
// The rules that follow the platform filter (logic.js), on the selected one.
const hasFailure = (pkg) => failureOn(pkg, platformFilter);
const buildsWith = (pkg, status) => buildsOn(pkg, status, platformFilter);
const failedBuilds = (pkg) => buildsWith(pkg, 'failed');
const attentionRank = (pkg) => rankOn(pkg, platformFilter);
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
    ? ` <a class="badge ${cls}" href="${href(pr.url)}" target="_blank" rel="noopener" title="${escapeHtml(title)}">${text}</a>`
    : ` <span class="badge ${cls}" title="${escapeHtml(title)}">${text}</span>`;

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
  if (st === 'missing') return `<span class="badge missing">not packaged</span>`;
  const now = escapeHtml(pkg.nixVersion);
  const failing = notRefreshed(pkg, 'upstream')
    ? `<span class="badge neutral" title="${escapeHtml(staleText(notRefreshed(pkg, 'upstream'), "nixkeeper's update check failing"))}. ${communityCheck(pkg) ? "It's a community rule: report it to nixkeeper, or give the package a rule of your own." : 'Fix it in package-lists/update-checks.nix.'}">check failing</span>`
    : '';
  const about = `${st === 'neutral' ? `<span class="badge neutral">${escapeHtml(pkg.nixStatus)}</span>` : ''}${pkg.devel ? `<span class="badge devel ${st}">devel</span>` : ''}${pkg.nixVulnerable ? '<span class="badge vuln">vulnerable</span>' : ''}${pkg.staleSince ? `<span class="badge neutral" title="Repology lookup failed on the last run; this is data from ${escapeHtml(new Date(pkg.staleSince).toLocaleString())}">not refreshed</span>` : ''}`;
  if (st !== 'warn')
    return `<div class="vcell"><span class="v-now"><span class="v">${now}</span></span><span class="v-tags top">${about}${failing}</span></div>`;
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
      return `<span class="${cls}" aria-hidden="true"><span class="arrow">→</span><span class="unknown">newer version unknown</span></span>`;
    return `<span class="${cls}" aria-hidden="true" title="${escapeHtml(to)}"><span class="arrow">→</span><span class="same">${escapeHtml(d.same)}</span><span class="ref${colour}">${escapeHtml(d.to)}</span></span>`;
  };
  // Master partway there: its own line, with its badge, between the two.
  const mid = midway(pkg);
  const steps = mid
    ? `${step('v-mid', pkg.nixVersion, mid, ' merged')}${step('v-next', mid, target, '')}`
    : step('v-next', pkg.nixVersion, target, merged ? ' merged' : '');
  const said = mid
    ? `${now}, on master ${escapeHtml(mid)}, newest ${escapeHtml(target || 'unknown')}`
    : `${now}, newest ${escapeHtml(target || 'unknown')}`;
  return `<div class="vcell${mid ? ' three' : ''}">
    <button type="button" class="vcopy" data-copy="${escapeHtml(title || '')}" title="Copy “${escapeHtml(title || '')}”">
    <span class="v-now"><span class="v" aria-hidden="true">${now}</span><span class="sr-only">${said}</span></span>
    ${steps}
    </button>
    <span class="v-tags top">${about}</span>${mid ? `<span class="v-tags mid">${masterBadge(pkg)}</span>` : ''}
    <span class="v-tags bottom">${mid ? openPrBadge(pkg) : prBadge(pkg)}${failing}</span>
  </div>`;
}

// How long an outdated package has been outdated, after its name: orange,
// or violet when the update is merged and waiting for the channel.
function ageTag(pkg, st) {
  if (st !== 'warn' || !pkg.outdatedSince) return '';
  return `<span class="age${waitingForChannel(pkg) ? ' merged' : ''}" title="Outdated since ${escapeHtml(longDate(pkg.outdatedSince))}">${shortAge(pkg.outdatedSince)}</span>`;
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
    ? `⚠ ${problems.length === 1 ? 'A problem' : `${problems.length} problems`} in the package lists, found by the last sync:
      <ul>${problems.map((p) => `<li>${escapeHtml(p)}</li>`).join('')}</ul>`
    : '';
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
    // The nixkeeper that made the data, in the footer (older data has none).
    document.getElementById('version').textContent =
      data.version && data.version !== 'unknown' ? ` ${data.version}` : '';
    showListProblems(data.listProblems || []);
    setSitePalette(data.page?.theme || null);
    document.getElementById('search').disabled = false;
    render(currentFiltered());
  } catch {
    content.innerHTML = `<div class="error">
      Couldn't load <code>${escapeHtml(dataUrl('index.json'))}</code>.<br>
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
  const base = packages.filter((p) => inPlatform(p) && inList(p));
  setFavicon(base);
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
  document.getElementById('stats').innerHTML = `${buttons}${platformChip}`;
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

function render(list) {
  renderStats();
  const content = document.getElementById('content');
  if (!list.length) {
    content.innerHTML = `<div class="empty">No packages match${activeFilter !== 'all' && !document.getElementById('search').value.trim() ? ` the “${FILTERS[activeFilter].label}” filter` : ''}.</div>`;
    return;
  }
  content.innerHTML = `<div class="wrap"><table>
    <thead><tr>
      <th style="padding-left:10px">Package</th><th>nixpkgs unstable</th><th>Open on GitHub</th><th>Build failures</th><th>Update failures</th><th aria-hidden="true"></th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table></div>`;

  const rowsEl = document.getElementById('rows');
  list.forEach((pkg) => {
    const st = computeStatus(pkg);
    const verCell = versionCell(pkg, st);

    const tr = document.createElement('tr');
    tr.className = 'row';
    tr.tabIndex = 0;
    tr.innerHTML = `
      <td class="c-name"><div class="pkg-name"><span class="who"><span class="status-dot ${waitingForChannel(pkg) ? 'merged' : st}" title="${waitingForChannel(pkg) ? DOT_TITLE.merged : DOT_TITLE[st]}"></span><span class="n">${escapeHtml(pkg.name)}</span>${ageTag(pkg, st)}</span>${platformTags(pkg)}</div></td>
      <td class="c-ver ver mono">${verCell}</td>
      <td class="c-gh${pkg.openPRs || pkg.openIssues ? '' : ' quiet'}">${githubLinks(pkg)}</td>
      <td class="c-build">${buildCell(pkg)}</td>
      <td class="c-update">${updateCell(pkg)}</td>
      <td class="c-chev"><span class="chev" aria-hidden="true"><svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg></span></td>
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
    tr.querySelector('.vcopy')?.addEventListener('click', (e) => {
      e.stopPropagation(); // copy, don't expand the row
      copyTitle(e.currentTarget);
    });
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

// quiet: nothing that needs attention, so it's drawn muted, without a dot
// ("none reported" as a dash), and the phone layout leaves it out. Only
// what needs a look keeps its colour.
function failureButton(kind, dot, text, extra = '', stale = null, quiet = false) {
  const calm = quiet && !stale;
  const shown = calm && text === 'none reported' ? '<span aria-hidden="true">—</span>' : text;
  return `<button class="failure-btn${dot === 'missing' ? ' failing' : ''}${calm ? ' calm' : ''}" type="button" data-kind="${kind}"${calm ? ` data-quiet aria-label="${kind}: ${text}"` : ''} ${extra}>
    <span class="status-dot ${dot}"></span><span class="cell-label">${kind}:</span>${shown}${
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
  if (buildsWith(pkg, 'broken').length) return button('caution', 'marked broken');
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
  if (pkg.update?.outcome === 'superseded') return button('neutral', 'superseded', true);
  // A newer version the bot has no way to update to: not a failure, but it
  // needs a manual update (or an updateScript).
  if (pkg.update?.outcome === 'cantUpdate') return button('caution', "can't update");
  if (pkg.update === null) return button('neutral', 'not attempted', true);
  return button('ok', 'none reported', true);
}

const prLink = (n, text) =>
  `<a class="files-link" href="https://github.com/NixOS/nixpkgs/pull/${n}" target="_blank" rel="noopener">${text}</a>`;
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
        ? `failed trying <span class="mono">${escapeHtml(version)}</span>, a version ignored by ${u.community ? 'a community rule' : 'a manual rule'}: ${escapeHtml(u.reason)}`
        : u.supersededOn === 'master'
          ? `${what}, but master already has <span class="mono">${escapeHtml(onMaster(pkg))}</span> (merged, waiting for nixos-unstable)`
          : `${what}, but nixpkgs has moved on to <span class="mono">${escapeHtml(pkg.nixVersion)}</span> since`;
    },
  },
  // Every way the bot has of updating a package declined (the excerpt says
  // why): the update needs doing by hand, or an updateScript.
  cantUpdate: {
    dot: 'caution',
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
    return `<span class="plats"><span class="plat any" title="nixpkgs doesn't restrict its platforms">any platform</span></span>`;
  const tags = Object.entries(PLATFORMS)
    .filter(([key]) => pl[key])
    .map(
      ([key, p]) =>
        `<button class="plat" type="button" data-platform="${key}" aria-pressed="${platformFilter === key}"
      title="${platformFilter === key ? 'Show all platforms' : `Show only packages available on ${p.label}`}">${p.label}</button>`,
    )
    .join('');
  // Together, so they wrap as one.
  return tags && `<span class="plats">${tags}</span>`;
}

// Open nixpkgs PRs / issues with the package's attribute name in the title. Counts come from
// the fetch script's GitHub search; without them the buttons are plain links.
function githubLinks(pkg) {
  const term = pkg.searchTerm || pkg.name;
  const link = (kind, path, label, count) => {
    const q = encodeURIComponent(`is:${kind} state:open in:title ${term}`);
    return `<a class="gh-btn" href="https://github.com/NixOS/nixpkgs/${path}?q=${q}" target="_blank" rel="noopener"
      title="Open nixpkgs ${label} with ${escapeHtml(term)} in the title"${count === 0 ? ' data-zero' : ''}>${label}${count != null ? ` <b>${count}</b>` : ''}</a>`;
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

  const others = comparedRepos(entries.filter((e) => e.repo !== NIX_REPO));
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
  // A package updated together with another (follows): which, and that its
  // newest version and update PRs are that package's.
  const follows = up?.follows
    ? `updated together with <b>${escapeHtml(up.follows)}</b> (${communityCheck(pkg) ? 'a community rule' : 'your update checks'}): its newest version and update PRs count for this package too`
    : '';
  // When the update check is what makes it outdated, say where the newer
  // version came from, and how it compares with Repology.
  const upstreamLine = () =>
    follows
      ? `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>, behind <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(up.version)}</span>: it's ${follows}${since}.`
      : `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>; ${communityCheck(pkg) ? 'a community update check' : "nixkeeper's update check"} found <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(up.version)}</span> ${upLink}${
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
      } ${
        communityCheck(pkg)
          ? `It's a community rule (<span class="mono">community/update-checks.nix</span> in nixkeeper): report it there, or give this package a rule of your own in your update checks.`
          : 'Fix it in <span class="mono">package-lists/update-checks.nix</span>.'
      }</div>`
    : '';
  // An up-to-date rule: Repology gets this version wrong, so it counts as
  // up to date. What Repology said, and why the rule says otherwise.
  const rule = pkg.upToDate;
  const ruleText = rule
    ? ` — up to date by ${rule.community ? 'a community rule' : 'a manual rule'}: ${escapeHtml(rule.reason || '')} (Repology calls it <span class="mono">${escapeHtml(rule.status || '?')}</span>${
        rule.newest
          ? `, with <span class="mono">${escapeHtml(rule.newest)}</span> as the newest elsewhere`
          : ''
      }).`
    : '';
  const nixLine =
    up?.newer && !fromMaster(pkg)
      ? upstreamLine()
      : st === 'missing'
        ? `Not found in <span class="mono">nix_unstable</span> — nixpkgs doesn't currently package this.`
        : `nixpkgs unstable has <span class="mono" style="font-weight:600">${escapeHtml(pkg.nixVersion)}</span>${
            rule
              ? ruleText
              : st === 'warn' && fromMaster(pkg)
                ? ` — the newest Repology and the update checks know of, but master already has a newer one${since.replace(' — ', '; ')}:`
                : st === 'warn'
                  ? `, the newest seen elsewhere is <span class="mono" style="font-weight:600;color:var(--warn)">${escapeHtml(pkg.refVersion || '?')}</span>${since}`
                  : st === 'neutral'
                    ? ` — Repology classifies this version as <span class="mono">${escapeHtml(pkg.nixStatus)}</span>.`
                    : ` — the newest ${pkg.devel ? 'devel ' : ''}version, compared with ${others.length} other ${others.length === 1 ? 'repository' : 'repositories'}.`
          }${
            up && !up.newer && !failing
              ? follows
                ? ` It's ${follows}.`
                : up.behind
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
      ${others.map((e, i) => `<span class="repo-chip ${e.status === 'newest' && e.version !== pkg.nixVersion ? 'ahead' : ''}"${i >= COMPARED_SHOWN ? ' hidden' : ''}>${escapeHtml(e.repo)} <span class="v mono">${escapeHtml(e.version || '?')}</span></span>`).join('')}${
        others.length > COMPARED_SHOWN
          ? `<button type="button" class="more-btn" aria-expanded="false">Show all ${others.length}</button>`
          : ''
      }
    </div>`
        : ''
    }
    <div class="detail-row">
      ${homepage ? `<a class="files-link" href="${href(homepage)}" target="_blank" rel="noopener">Homepage ↗</a>` : ''}
      ${safeUrl(pkg.source) ? `<a class="files-link" href="${href(pkg.source)}" target="_blank" rel="noopener" title="Where nixpkgs defines this package">${escapeHtml(sourceFileName(pkg.source))} ↗</a>` : ''}
      ${pkg.project ? `<a class="files-link" href="https://repology.org/project/${encodeURIComponent(pkg.project)}/versions" target="_blank" rel="noopener">View on Repology ↗</a>` : ''}
    </div>
  `;
  el.querySelector('.more-btn')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const open = btn.getAttribute('aria-expanded') !== 'true';
    el.querySelectorAll('.repo-chip').forEach((chip, i) => {
      chip.hidden = !open && i >= COMPARED_SHOWN;
    });
    btn.setAttribute('aria-expanded', open);
    btn.textContent = open ? 'Show fewer' : `Show all ${others.length}`;
  });
}

// How many repositories a panel shows before "Show all".
const COMPARED_SHOWN = 8;

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
// "/" jumps to the filter, as on GitHub; Escape in it clears it.
document.addEventListener('keydown', (e) => {
  const search = document.getElementById('search');
  if (e.key === '/' && !e.target.closest('input, textarea') && !search.disabled) {
    e.preventDefault();
    search.focus();
  } else if (e.key === 'Escape' && e.target === search && search.value) {
    search.value = '';
    render(currentFiltered());
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
