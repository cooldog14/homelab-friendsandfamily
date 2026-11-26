// External WAN prober. Healthchecks.io can only receive a heartbeat; it cannot
// tell "the VPS is up and pinging" from "the VPS reaches nothing". This Worker
// runs outside the homelab, requests every public vhost from the real internet,
// and pings the heartbeat only when all of them answer.
//
// HEARTBEAT_URL is a Worker secret (wrangler secret put). Never inline it here.

// KEEP IN SYNC with the git-owned public vhosts in vps/sites/*.caddy.
// host/check-probe-targets.py fails `make check` when this list drifts.
const DEFAULT_TARGETS = [
  "https://photos.malice.biz",
  "https://files.malice.biz",
  "https://paperless.malice.biz",
  "https://kavita.malice.biz",
  "https://neko.malice.biz",
  "https://screego.malice.biz",
  "https://jellyfin.malice.biz",
  "https://requests.malice.biz",
  "https://player.malice.biz",
  "https://fiesta.malice.biz",
  "https://upload.malice.biz",
  "https://nvdr.malice.biz",
  "https://mg.malice.biz",
  // Status bit for the local alert pipeline (vps/sites/health.caddy). It is
  // not an application: see the special case in probe() below.
  "https://health.malice.biz",
];

const TIMEOUT_MS = 15000;
const HEALTH_HOST = "health.malice.biz";

function targets(env) {
  const override = env.PROBE_TARGETS;
  if (!override) return DEFAULT_TARGETS;
  return override
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

// Redirects are not followed: a public vhost that answers with a redirect is
// healthy, and following one would probe a host outside the declared set.
async function probe(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      redirect: "manual",
      signal: controller.signal,
    });
    if (response.status < 200 || response.status >= 400) {
      if (response.body) await response.body.cancel();
      return { ok: false, url, detail: `status ${response.status}` };
    }
    // health.malice.biz always answers 200 with {"ok": ...} so public-check
    // and blackbox-http never page on a deliberate "pipeline down" signal.
    // The Worker is the only reader of that body, and the only pinger that
    // can combine the internet view with the local pipeline view.
    if (new URL(url).hostname === HEALTH_HOST) {
      const state = await response.json();
      return { ok: state && state.ok === true, url, detail: "alert pipeline unhealthy" };
    }
    // Only the status matters for a real vhost; release the connection instead
    // of buffering a page body we will never read.
    if (response.body) await response.body.cancel();
    return { ok: true, url };
  } catch (err) {
    return { ok: false, url, detail: err.name === "AbortError" ? "timeout" : String(err) };
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async scheduled(_event, env, _ctx) {
    if (!env.HEARTBEAT_URL) {
      console.error("HEARTBEAT_URL is not configured; no heartbeat sent");
      return;
    }
    const results = await Promise.allSettled(targets(env).map(probe));
    // probe() never rejects, but allSettled keeps an unexpected throw from
    // silently passing as success.
    const failures = results.map((result) =>
      result.status === "fulfilled"
        ? result.value
        : { ok: false, url: "unknown", detail: String(result.reason) },
    ).filter((result) => !result.ok);

    if (failures.length > 0) {
      for (const failure of failures) {
        console.log(`FAIL ${failure.url}: ${failure.detail}`);
      }
    } else {
      console.log(`all ${results.length} public targets healthy`);
    }

    const base = env.HEARTBEAT_URL.replace(/\/+$/, "");
    const url = failures.length > 0 ? `${base}/fail` : base;
    try {
      const response = await fetch(url, { method: "GET" });
      if (response.body) await response.body.cancel();
      if (!response.ok) {
        console.error(`heartbeat delivery failed: HTTP ${response.status}`);
      } else {
        console.log(`heartbeat ${response.status} ${failures.length > 0 ? "fail" : "ok"}`);
      }
    } catch {
      // fetch exceptions can contain the complete secret ping URL.
      console.error("heartbeat request failed");
    }
  },

  // No public route (workers_dev = false); this only makes `wrangler dev`
  // inspectable and confirms the trigger wiring without leaking the secret.
  async fetch() {
    return new Response(
      `homelab-wan-heartbeat: ${targets({}).length} targets, every 5 minutes\n`,
      { headers: { "content-type": "text/plain" } },
    );
  },
};
