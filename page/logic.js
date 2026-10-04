// The page's rules, without the page: statuses, versions, ages, links and the
// tab icon's signals, from a package's data alone. app.js draws the page with
// them; tests/js/ tests them (node --test, in the flake checks).
//
// Where a rule depends on the selected platform, it takes it as an argument
// (null for all platforms, or 'linux', 'darwin'); times take `now` so tests
// can fix it.

const DAY = 86400e3;

export const withSlash = (url) => (url.endsWith('/') ? url : `${url}/`);

// "any platform" (no restriction in nixpkgs) counts as both.
export function onPlatform(pkg, key) {
  return pkg.platforms === null || Boolean(pkg.platforms?.[key]);
}

// Follows Repology's statuses. "legacy" means outdated while the same repo
// carries a newer version in another package (e.g. a beta overtaken by the
// stable release), so it counts as outdated. Whether a row is a devel variant
// comes separately from pkg.devel and only shades its "devel" badge.
export function computeStatus(pkg) {
  if (pkg.nixStatus === 'missing') return 'missing';
  if (pkg.nixStatus === 'outdated' || pkg.nixStatus === 'legacy') return 'warn';
  // nixkeeper's own update check found a release Repology hasn't seen.
  if (pkg.upstream?.newer) return 'warn';
  // Or master already has a newer version than the channel.
  if (aheadOnMaster(pkg)) return 'warn';
  if (pkg.nixStatus === 'newest' || pkg.nixStatus === 'unique' || pkg.nixStatus === 'devel')
    return 'ok';
  return 'neutral';
}

// Hydra builds with a status, on the selected platform only while one is.
export function buildsWith(pkg, status, platform = null) {
  return (pkg.builds || []).filter(
    (b) => b.status === status && (!platform || b.system.endsWith(`-${platform}`)),
  );
}

// Everything shown in red: not found in nixpkgs, or a build or update
// failure reported.
export function hasFailure(pkg, platform = null) {
  return (
    computeStatus(pkg) === 'missing' ||
    buildsWith(pkg, 'failed', platform).length > 0 ||
    Boolean(pkg.updateFailure)
  );
}

// Version order as the sync compares them (nixkeeper/versions.py): numbers
// as numbers, a letter part before a number (1.0rc1 < 1.0.1).
export function compareVersions(a, b) {
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
export function onMaster(pkg) {
  const versions = [pkg.master, pkg.masterPR?.to].filter(Boolean);
  return versions.sort(compareVersions).pop() || null;
}

// Outdated, but master already has the target version (or newer): the update
// is merged and waits for nixos-unstable, usually a few days (see
// waiting_for_channel in nixkeeper/changes.py).
export function waitingForChannel(pkg) {
  return (
    computeStatus(pkg) === 'warn' &&
    Boolean(onMaster(pkg)) &&
    compareVersions(targetVersion(pkg) || '', onMaster(pkg)) <= 0
  );
}

// Hydra's build of master is newer than the channel's version: there's a
// newer release, whatever Repology and the update checks know
// (ahead_on_master in nixkeeper/changes.py).
export function aheadOnMaster(pkg) {
  return Boolean(pkg.master && pkg.nixVersion) && compareVersions(pkg.master, pkg.nixVersion) > 0;
}

// Whether the version to update to is master's, newer than anything
// Repology or an update check knows (count_master in nixkeeper/changes.py;
// data from before that rule only has master, not refFromMaster).
export function fromMaster(pkg) {
  return (
    aheadOnMaster(pkg) &&
    (Boolean(pkg.refFromMaster) ||
      !pkg.refVersion ||
      compareVersions(pkg.master, pkg.refVersion) > 0)
  );
}

// Whether the package's update check is a community rule
// (community/update-checks.nix): its result says so, or its failure does.
export function communityCheck(pkg) {
  return Boolean(
    pkg.upstream?.community || pkg.notRefreshed?.upstream?.reason?.startsWith('community rule'),
  );
}

// The version an update would bring.
export function targetVersion(pkg) {
  return fromMaster(pkg) ? pkg.master : pkg.refVersion;
}

// What changed between two versions, compared by whole parts (split at
// . - _ + ~, so 1.19.24 -> 1.19.28 changes "24", not just the "4"): the
// start they share, the rest of each. The page shows the newest version
// under nixpkgs', the shared start faded and the rest in colour.
//   versionDiff('1.19.24', '1.19.28') -> { same: '1.19.', from: '24', to: '28' }
export function versionDiff(from, to) {
  const parts = (v) => (v || '').match(/[^.\-_+~]+|[.\-_+~]/g) || [];
  const [a, b] = [parts(from), parts(to)];
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return { same: a.slice(0, i).join(''), from: a.slice(i).join(''), to: b.slice(i).join('') };
}

// Default order: failed, then outdated (longest outdated first), then
// outdated but already fixed on master, then the rest; otherwise
// alphabetical (the index arrives sorted by name and Array.sort is stable).
export function attentionRank(pkg, platform = null) {
  if (hasFailure(pkg, platform)) return 0;
  if (waitingForChannel(pkg)) return 1.5;
  if (computeStatus(pkg) === 'warn') return 1;
  return 2;
}

// The tab's icon among packages: each signal turns its own chevron of the
// mark (assets/brand/BRAND.md, "Status icon"): r, a new release nothing has
// been done about yet (not already on master); f, a failure; v, a
// vulnerability. "rfv" order, or "ok" with none: favicon-<key>.svg.
export function faviconKey(packages, platform = null) {
  const signals = {
    r: packages.some((p) => computeStatus(p) === 'warn' && !waitingForChannel(p)),
    f: packages.some((p) => hasFailure(p, platform)),
    v: packages.some((p) => p.nixVulnerable),
  };
  return ['r', 'f', 'v'].filter((s) => signals[s]).join('') || 'ok';
}

// How long a package has been outdated, one letter per unit: <1 d, 3 d, 2 w,
// 5 m (months), 2 y.
export function shortAge(iso, now = Date.now()) {
  const days = Math.floor((now - new Date(iso).getTime()) / DAY);
  if (days < 1) return '<1 d';
  if (days < 7) return `${days} d`;
  if (days < 30) return `${Math.floor(days / 7)} w`;
  if (days < 365) return `${Math.min(11, Math.floor(days / 30))} m`; // 360-364 days: not "12 m" before "1 y"
  return `${Math.floor(days / 365)} y`;
}

export function daysText(iso, now = Date.now()) {
  const days = Math.floor((now - new Date(iso).getTime()) / DAY);
  return days < 1 ? 'today' : days === 1 ? '1 day' : `${days} days`;
}

export function timeAgo(iso, now = Date.now()) {
  if (!iso) return 'never';
  const diff = now - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function escapeHtml(s) {
  return (s || '')
    .toString()
    .replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
}

// A link from data, only if it's a web address: escaping stops markup, but
// not a javascript: link, which would run when clicked. '' otherwise.
export function safeUrl(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === 'https:' || protocol === 'http:' ? url : '';
  } catch {
    return '';
  }
}

// Markup, built with the html`...` tag: every ${...} in it is escaped,
// unless it's markup itself (another html`...`, or raw() for markup the page
// writes itself), so text from the data can't add markup, even where an
// escape would have been forgotten. Arrays are joined; null and undefined
// give nothing (and the rest prints as in a template string: false as
// "false", for aria-pressed). The result goes into innerHTML as is.
class Markup {
  constructor(text) {
    this.text = text;
  }
  toString() {
    return this.text;
  }
}
const piece = (v) =>
  v instanceof Markup
    ? v.text
    : Array.isArray(v)
      ? v.map(piece).join('')
      : v == null
        ? ''
        : escapeHtml(String(v));
export function html(strings, ...values) {
  return new Markup(strings.reduce((out, s, i) => out + piece(values[i - 1]) + s));
}
// Markup the page writes itself, as is. Never for text from the data.
export const raw = (text) => new Markup(String(text));

// "owner/repo" from ?owner=&repo=, or from a GitHub Pages project site's
// address (a location: its hostname and pathname). Only names GitHub allows
// (null otherwise): the page loads that repository's data, so a link can't
// make it build a URL out of anything else.
const GITHUB_OWNER = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;
const GITHUB_NAME = /^(?!\.\.?$)[A-Za-z0-9._-]{1,100}$/;
export function githubRepo(params, { hostname, pathname }) {
  const asked = params.get('owner') && params.get('repo');
  const owner = asked
    ? params.get('owner')
    : hostname.endsWith('.github.io')
      ? hostname.split('.')[0]
      : null;
  const name = asked ? params.get('repo') : pathname.split('/').filter(Boolean)[0];
  return GITHUB_OWNER.test(owner || '') && GITHUB_NAME.test(name || '') ? `${owner}/${name}` : null;
}

// The page's look: a palette and light or dark. The visitor's choice (the
// Theme menu, kept in their browser) wins, then the page's default (the
// lists' page.theme, from the data), then classic; light or dark follows the
// system ('auto') unless chosen. Unknown values count as not set.
export const PALETTES = ['classic', 'catppuccin'];
export const MODES = ['auto', 'light', 'dark'];

export function themeFor(chosen = {}, siteDefault = null) {
  const palette = [chosen.palette, siteDefault].find((p) => PALETTES.includes(p)) || 'classic';
  const mode = MODES.includes(chosen.mode) ? chosen.mode : 'auto';
  return { palette, mode };
}

// The repositories a package's panel compares nixpkgs with: one entry per
// repository (Repology lists one per subpackage: alpine has xournalpp,
// xournalpp-doc, ...), its newest version, then newest version first (ties
// by name). Repology's statuses for versions that don't compare (rolling,
// ignored, incorrect, noscheme, untrusted) go last, so a "9999" doesn't top
// the list.
const UNCOMPARABLE = new Set(['rolling', 'ignored', 'incorrect', 'noscheme', 'untrusted']);
const newer = (a, b) =>
  UNCOMPARABLE.has(a.status) - UNCOMPARABLE.has(b.status) ||
  compareVersions(b.version || '', a.version || '');
export function comparedRepos(entries) {
  const best = new Map();
  for (const e of entries) {
    const kept = best.get(e.repo);
    if (!kept || newer(e, kept) < 0) best.set(e.repo, e);
  }
  return [...best.values()].sort(
    (a, b) => newer(a, b) || (a.repo || '').localeCompare(b.repo || ''),
  );
}

// An update's title as nixpkgs writes it, for commits and PRs:
// "unciv: 4.22.1 -> 4.22.6". Only for an outdated package with a known
// newest version; null otherwise.
// Starting from master's version when master is partway there (the next
// update goes on from it): "google-chrome: 154.0.8037.92 -> 154.0.8037.97".
export function updateTitle(pkg) {
  const target = targetVersion(pkg);
  const from = midway(pkg) || pkg.nixVersion;
  return computeStatus(pkg) === 'warn' && from && target
    ? `${pkg.name}: ${from} -> ${target}`
    : null;
}

// Master's version when it's partway between the channel and the newest: an
// update merged (waiting for the channel), and a newer one after it. Null
// otherwise (nothing on master, or master already has the newest).
export function midway(pkg) {
  const master = onMaster(pkg);
  const target = targetVersion(pkg);
  return computeStatus(pkg) === 'warn' &&
    master &&
    target &&
    pkg.nixVersion &&
    compareVersions(master, pkg.nixVersion) > 0 &&
    compareVersions(master, target) < 0
    ? master
    : null;
}
