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

// What an update would change to, as the table shows it: for an unstable
// version with the same base ("5.1.0-b2-unstable-2022-11-14"), just the new
// date, which is all that differs; anything else in full.
export function versionChange(from, to) {
  const unstable = /^(.*-unstable-)(\d{4}-\d{2}-\d{2})$/;
  const a = unstable.exec(from || '');
  const b = unstable.exec(to || '');
  return a && b && a[1] === b[1] ? b[2] : to;
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

// safeUrl, ready for an href.
export function href(url) {
  return escapeHtml(safeUrl(url));
}

// "owner/repo" from ?owner=&repo=, or from a GitHub Pages project site's
// address (a location: its hostname and pathname).
export function githubRepo(params, { hostname, pathname }) {
  if (params.get('owner') && params.get('repo'))
    return `${params.get('owner')}/${params.get('repo')}`;
  const owner = hostname.endsWith('.github.io') ? hostname.split('.')[0] : null;
  const seg = pathname.split('/').filter(Boolean)[0] || null;
  return owner && seg ? `${owner}/${seg}` : null;
}
