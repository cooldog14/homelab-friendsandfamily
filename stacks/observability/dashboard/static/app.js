'use strict';
/* Homelab admin dashboard. Vanilla DOM, one JSON snapshot every 5 s.
 * All server strings enter the page through textContent: no innerHTML. */

(function () {
  const POLL_MS = 5000;
  const STALE_MS = 15000;
  const REQUEST_TIMEOUT_MS = 8000;
  const LEVEL_RANK = { info: 0, warn: 1, error: 2 };

  const state = {
    snapshot: null,
    lastOk: 0,
    lastAttempt: 0,
    error: null,
    filters: { text: '', level: 'all', service: 'all', problems: false },
    selection: -1,
    ping: {},
    alertSince: new Map(),
  };
  const scrolls = new Map();
  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------- DOM --

  function append(node, kids) {
    for (const kid of kids) {
      if (kid === null || kid === undefined || kid === false) continue;
      if (Array.isArray(kid)) { append(node, kid); continue; }
      node.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
  }

  function h(tag, props, ...kids) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = String(value);
      else if (key === 'value') node.value = value;
      else if (key === 'on') { for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn); }
      else if (key === 'attrs') { for (const [a, v] of Object.entries(value)) { if (v !== null && v !== undefined) node.setAttribute(a, String(v)); } }
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key === 'hidden' || key === 'checked' || key === 'disabled') node[key] = Boolean(value);
      else node.setAttribute(key, String(value));
    }
    append(node, kids);
    return node;
  }

  const SVG_NS = 'http://www.w3.org/2000/svg';
  function s(tag, attrs, ...kids) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value !== null && value !== undefined) node.setAttribute(key, String(value));
    }
    append(node, kids);
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  /* A filter that hides everything must say so, not render a blank panel. */
  function emptyNote(container, id, text, show) {
    let node = container.querySelector('#' + id);
    if (!show) {
      if (node) node.remove();
      return;
    }
    if (!node) {
      container.appendChild(h('div', { class: 'empty', attrs: { id: id }, text: text }));
    }
  }

  function rememberScroll(root) {
    for (const el of root.querySelectorAll('[data-scroll]')) scrolls.set(el.dataset.scroll, el.scrollTop);
  }
  function restoreScroll(root) {
    for (const el of root.querySelectorAll('[data-scroll]')) {
      const top = scrolls.get(el.dataset.scroll);
      if (top) el.scrollTop = top;
    }
  }

  // ----------------------------------------------------------- formatting --

  function num(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function fmtBytes(value, suffix) {
    if (!num(value)) return '—';
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
    let n = Math.abs(value);
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
    const digits = i === 0 ? 0 : n < 10 ? 2 : n < 100 ? 1 : 0;
    const sign = value < 0 ? '-' : '';
    return sign + n.toFixed(digits) + ' ' + units[i] + (suffix || '');
  }

  function fmtPct(value, digits) {
    if (!num(value)) return '—';
    return value.toFixed(digits === undefined ? 0 : digits);
  }

  function fmtDuration(seconds) {
    if (!num(seconds) || seconds < 0) return '—';
    const total = Math.floor(seconds);
    if (total < 60) return total + 's';
    const minutes = Math.floor(total / 60);
    if (minutes < 60) return minutes + 'm';
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return hours + 'h ' + (minutes % 60) + 'm';
    const days = Math.floor(hours / 24);
    return days + 'd ' + (hours % 24) + 'h';
  }

  function fmtAge(seconds) {
    if (!num(seconds)) return '—';
    return fmtDuration(seconds) + ' ago';
  }

  function fmtIn(seconds) {
    if (!num(seconds)) return '—';
    if (seconds < 0) return 'overdue ' + fmtDuration(-seconds);
    return 'in ' + fmtDuration(seconds);
  }

  const pad2 = (n) => String(n).padStart(2, '0');
  function fmtDate(value) {
    if (value === null || value === undefined || value === '') return '—';
    const d = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
      ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  function fmtClock(d) {
    return pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  function isSafeUrl(url) {
    if (typeof url !== 'string') return false;
    const trimmed = url.trim();
    if (!/^https?:\/\//i.test(trimmed)) return false;
    return !/[\s\u0000-\u001f]/.test(trimmed);
  }

  // --------------------------------------------------------------- status --

  function stateClass(item) {
    if (!item) return 'state-unknown';
    if (item.internal) return 'state-unknown';
    if (BAD_STATES.has(item.state)) return 'state-alert';
    if (item.state === 'paused') return 'state-warn';
    if (item.health === 'unhealthy') return 'state-alert';
    const probe = item.probe || {};
    if (probe.status === 'fail') return 'state-alert';
    if (probe.status === 'ok') return 'state-ok';
    return 'state-unknown';
  }

  const BAD_STATES = new Set(['exited', 'dead', 'restarting', 'created']);

  function isProblem(item) {
    if (!item) return false;
    if (BAD_STATES.has(item.state)) return true;
    if (item.health === 'unhealthy') return true;
    return (item.probe || {}).status === 'fail';
  }

  function isWarning(item) {
    if (!item) return false;
    return item.state === 'paused' || item.state === 'absent';
  }

  /* Not serving: a hard failure or a deliberate stop. "Unverified" is excluded:
     a running container with no probe is a coverage gap, not an outage. */
  function notNominal(item) {
    return isProblem(item) || isWarning(item);
  }

  function severityRank(item) {
    if (isProblem(item)) return 0;
    if (isWarning(item)) return 1;
    return (item || {}).probe && item.probe.status === 'unverified' ? 2 : 3;
  }

  function stateWord(item) {
    if (!item) return 'unknown';
    if (item.state === 'paused') return 'paused';
    if (BAD_STATES.has(item.state)) return item.state;
    if (item.state === 'absent') return 'absent';
    if (item.health === 'unhealthy') return 'unhealthy';
    const status = (item.probe || {}).status;
    if (status === 'ok') return 'up';
    if (status === 'fail') return 'down';
    if (status === 'unverified') return 'unverified';
    if (status === 'internal') return 'internal';
    return 'unknown';
  }

  /* Why it is down, when Docker can tell us: exit code, OOM, restart count. */
  function detailText(item) {
    const detail = (item || {}).detail || {};
    const bits = [];
    if (num(detail.exit_code) && item.state !== 'running') bits.push('exit ' + detail.exit_code);
    if (detail.oom_killed) bits.push('oom');
    if (num(detail.restart_count) && detail.restart_count > 0) bits.push(detail.restart_count + ' restarts');
    if (detail.error) bits.push(String(detail.error).slice(0, 56));
    return bits.join(' · ');
  }

  function usageText(item) {
    const usage = (item || {}).usage || {};
    const bits = [];
    if (num(usage.cpu_pct)) bits.push(usage.cpu_pct.toFixed(1) + '%');
    if (num(usage.mem_bytes)) bits.push(fmtBytes(usage.mem_bytes));
    return bits.join(' · ');
  }

  function probeRest(item) {
    const probe = (item || {}).probe || {};
    const parts = [];
    if (probe.status === 'ok' && num(probe.latency_ms)) parts.push(Math.round(probe.latency_ms) + ' ms');
    if (probe.status === 'fail' && num(probe.code)) parts.push(String(probe.code));
    const detail = detailText(item);
    if (detail) parts.push(detail);
    if (probe.status === 'fail' && probe.error) parts.push(String(probe.error).slice(0, 56));
    const usage = (item || {}).usage || {};
    if (num(usage.oom_24h) && usage.oom_24h > 0) parts.push(usage.oom_24h + ' oom/24h');
    return parts.join(' · ');
  }

  function probeText(item) {
    const rest = probeRest(item);
    return stateWord(item) + (rest ? ' · ' + rest : '');
  }

  function linkNode(url, label) {
    if (!isSafeUrl(url)) return null;
    return h('a', { href: url, target: '_blank', rel: 'noopener noreferrer', text: label });
  }

  // -------------------------------------------------------------- alerts --

  function renderStatusChip(data) {
    const chip = $('status-chip');
    const summary = data.summary || { alert: 0, warn: 0, total: 0 };
    if (!summary.total) {
      chip.textContent = 'nominal';
      chip.className = 'status-chip state-ok';
    } else {
      const parts = [];
      if (summary.alert) parts.push(summary.alert + (summary.alert === 1 ? ' alert' : ' alerts'));
      if (summary.warn) parts.push(summary.warn + ' warn');
      chip.textContent = parts.join(' · ');
      chip.className = 'status-chip ' + (summary.alert ? 'state-alert' : 'state-warn');
    }
    chip.setAttribute('aria-label', 'open the problem list: ' + (summary.total || 0) + ' open');
  }

  /* First moment this client saw the alert: the strip has no history behind it. */
  function alertSince(alert) {
    if (alert.since) return new Date(alert.since).getTime();
    const now = Date.now();
    if (!state.alertSince.has(alert.id)) state.alertSince.set(alert.id, now);
    return state.alertSince.get(alert.id);
  }

  function alertCard(alert) {
    const since = alertSince(alert);
    const elapsed = num(since) ? fmtDuration(Math.max(0, (Date.now() - since) / 1000)) : null;
    /* Derived alerts have no server-side start time: say what we know
       (how long this page has seen it) instead of implying a birth moment. */
    const meta = alert.source === 'prometheus'
      ? ['prometheus', alert.state || 'firing', elapsed ? 'active ' + elapsed : null]
      : ['dashboard check', elapsed ? 'seen ' + elapsed : null];
    const metaText = meta.filter(Boolean).join(' · ');
    const href = '#' + String(alert.href || 'alerts').replace(/^#/, '');
    return h('div', { class: 'alert alert-' + (alert.severity === 'alert' ? 'alert' : 'warn') },
      h('div', { class: 'title', text: alert.title || 'alert' }),
      h('div', { class: 'detail', text: alert.detail || '' }),
      h('div', { class: 'alert-meta' },
        h('span', { text: metaText }),
        h('a', { href: href, text: 'jump to section' }))
    );
  }

  function renderAlerts(data) {
    const strip = $('alert-strip');
    clear(strip);
    const derived = data.alerts || [];
    const prometheus = data.prometheus_alerts || [];
    renderStatusChip(data);

    const seen = new Set();
    for (const alert of derived) seen.add(alert.id);
    for (const alert of prometheus) seen.add(alert.id);
    for (const key of [...state.alertSince.keys()]) {
      if (!seen.has(key)) state.alertSince.delete(key);
    }

    $('alerts-meta').textContent = 'dashboard ' + derived.length +
      ' · prometheus ' + prometheus.length;

    if (!derived.length && !prometheus.length) {
      strip.appendChild(h('div', { class: 'nominal', text: 'all monitored checks nominal' }));
      return;
    }
    strip.appendChild(h('div', { class: 'alert-block' },
      h('h3', { text: 'Dashboard checks' }),
      derived.length
        ? derived.map(alertCard)
        : h('div', { class: 'empty', text: 'every dashboard check passes' })));
    if (prometheus.length) {
      strip.appendChild(h('div', { class: 'alert-block' },
        h('h3', { text: 'Prometheus alerts' }),
        prometheus.map(alertCard)));
    }
  }

  // ----------------------------------------------------------- telemetry --

  function metricCard(label, value, unit, sub) {
    return h('div', { class: 'metric' },
      h('div', { class: 'label', text: label }),
      h('div', { class: 'value' }, value, unit ? h('span', { class: 'unit', text: unit }) : null),
      sub ? h('div', { class: 'sub', text: sub }) : null
    );
  }

  function hostTable(nodes) {
    if (!nodes.length) return h('div', { class: 'empty', text: 'no host metrics yet' });
    return h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {},
        h('th', { text: 'host' }), h('th', { text: 'state' }),
        h('th', { class: 'right', text: 'cpu' }), h('th', { class: 'right', text: 'mem' }))),
      h('tbody', {}, nodes.map((node) => h('tr', {},
        h('td', { class: 'mono', text: node.name || '—' }),
        h('td', {
          class: stateClass({
            state: node.up ? 'running' : 'exited',
            probe: { status: node.up ? 'ok' : 'fail' },
          }),
        }, h('span', { class: 'dot' }), node.up ? 'up' : 'down'),
        h('td', { class: 'right mono', text: fmtPct(node.cpu_pct, 1) + '%' }),
        h('td', { class: 'right mono', text: fmtPct(node.mem_pct, 1) + '%' })
      )))));
  }

  function consumerTable(rows, kind) {
    if (!rows || !rows.length) return h('div', { class: 'empty', text: 'no container metrics yet' });
    const max = Math.max(...rows.map((row) => (kind === 'cpu' ? row.cpu_pct : row.mem_bytes) || 0), 1);
    return h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {},
        h('th', { text: 'container' }),
        h('th', { class: 'right', text: kind === 'cpu' ? 'cpu' : 'memory' }),
        h('th', { text: '' }))),
      h('tbody', {}, rows.map((row) => {
        const value = kind === 'cpu' ? row.cpu_pct : row.mem_bytes;
        return h('tr', {},
          h('td', {},
            h('div', { text: row.label || row.name }),
            h('div', { class: 'faint mono', text: row.service || row.name })),
          h('td', { class: 'right mono', text: kind === 'cpu' ? fmtPct(value, 1) + '%' : fmtBytes(value) }),
          h('td', {}, h('progress', {
            value: num(value) ? value : 0,
            max: max,
            attrs: { 'aria-label': 'share of the busiest container' },
          })));
      }))));
  }

  function renderTelemetry(data) {
    const body = $('telemetry-body');
    clear(body);
    const telemetry = data.telemetry || {};
    const nodes = telemetry.nodes || [];
    const chill = nodes.find((n) => n.name === 'chill-01') || {};
    $('telemetry-meta').textContent = telemetry.updated_at
      ? 'updated ' + fmtAge((Date.now() - new Date(telemetry.updated_at).getTime()) / 1000)
      : 'waiting for prometheus';
    if (telemetry.error) {
      body.appendChild(h('div', { class: 'panel-note state-alert', text: 'prometheus: ' + telemetry.error }));
    }

    body.appendChild(h('div', { class: 'grid grid-4' },
      metricCard('CPU', fmtPct(chill.cpu_pct, 1), '%', chill.up ? 'chill-01' : 'chill-01 down'),
      metricCard('Memory', fmtPct(chill.mem_pct, 1), '%', chill.up ? 'chill-01' : 'chill-01 down'),
      metricCard('Network in', fmtBytes(chill.net_rx, '/s'), '', 'eth0'),
      metricCard('Network out', fmtBytes(chill.net_tx, '/s'), '', 'eth0')
    ));

    const diskRows = (telemetry.disks || []).map((disk) => {
      const cls = disk.used_pct > 90 ? 'alert' : disk.used_pct >= 85 ? 'warn' : '';
      return h('tr', {},
        h('td', {},
          h('div', { class: 'mono', text: disk.mountpoint }),
          (disk.aliases || []).length
            ? h('div', { class: 'faint mono', text: '+ ' + disk.aliases.join(' ') })
            : null),
        h('td', { class: 'right mono ' + (cls ? 'state-' + cls : '') }, fmtPct(disk.used_pct, 1) + '%'),
        h('td', { class: 'right mono muted', text: fmtBytes(disk.size_bytes) }),
        h('td', { class: 'right mono muted', text: fmtBytes(disk.avail_bytes) }),
        h('td', {}, h('progress', {
          value: num(disk.used_pct) ? Math.min(100, disk.used_pct) : 0,
          max: 100,
          class: cls,
          'aria-label': 'used percent on ' + disk.mountpoint,
        }))
      );
    });

    body.appendChild(h('div', { class: 'grid grid-2' },
      h('div', {},
        h('h3', { text: 'Filesystems' }),
        diskRows.length
          ? h('div', { class: 'table-wrap' }, h('table', {},
            h('thead', {}, h('tr', {},
              h('th', { text: 'mount' }), h('th', { class: 'right', text: 'used' }),
              h('th', { class: 'right', text: 'size' }), h('th', { class: 'right', text: 'free' }),
              h('th', { text: '' }))),
            h('tbody', {}, diskRows)))
          : h('div', { class: 'empty', text: 'no filesystem metrics' })
      ),
      h('div', {},
        h('h3', { text: 'Host' }),
        hostTable(nodes))
    ));

    body.appendChild(h('div', { class: 'grid grid-2' },
      h('div', {}, h('h3', { text: 'Top CPU' }), consumerTable(telemetry.top_cpu, 'cpu')),
      h('div', {}, h('h3', { text: 'Top memory' }), consumerTable(telemetry.top_mem, 'mem'))
    ));
  }

  // ------------------------------------------------------------ services --

  function serviceRow(item, kind) {
    const links = h('div', { class: 'links' });
    const wanted = kind === 'host'
      ? [['private', 'open']]
      : [['private', 'private'], ['public', 'public'], ['local', 'lan']];
    for (const [key, label] of wanted) {
      const url = (item.links || {})[key];
      const node = linkNode(url, label);
      if (node) links.appendChild(node);
    }
    if (!links.childNodes.length) links.appendChild(h('span', { class: 'faint', text: '—' }));

    const search = [
      item.label, item.id, item.stack, item.service, item.image, item.version,
      item.state, item.health, probeText(item),
    ].filter(Boolean).join(' ').toLowerCase();
    const rest = probeRest(item);
    const rowClass = 'svc' + (item.internal ? ' internal' : '') +
      (isProblem(item) ? ' bad' : isWarning(item) ? ' warn-row' : '');

    const image = kind === 'host'
      ? h('div', { class: 'image', text: item.note || 'host' })
      : h('div', { class: 'image' },
        (item.image || 'local build'),
        item.image_id ? h('span', { class: 'faint', text: ' · ' + String(item.image_id).slice(0, 12) }) : null,
        item.note ? h('div', { class: 'faint', text: item.note }) : null);

    return h('div', {
      class: rowClass,
      dataset: { search: search, problem: notNominal(item) ? '1' : '0' },
    },
      h('span', { class: 'dot ' + stateClass(item), attrs: { 'aria-hidden': 'true' } }),
      h('div', {},
        h('div', { class: 'name', text: item.label || item.id }),
        h('div', { class: 'id', text: item.id })),
      image,
      h('div', { class: 'uptime', text: kind === 'host' ? '' : fmtDuration(item.uptime_seconds) }),
      h('div', { class: 'usage', text: kind === 'host' ? '' : (usageText(item) || '—') }),
      links,
      h('div', { class: 'probe ' + stateClass(item) },
        h('span', { class: 'sw', text: stateWord(item) }),
        rest ? h('span', { class: 'rest', text: ' · ' + rest }) : null,
        notNominal(item) && item.service
          ? h('button', {
            class: 'mini',
            type: 'button',
            text: 'logs',
            attrs: { 'aria-label': 'show logs for ' + item.service },
            on: { click: () => openLogs(item.service) },
          })
          : null)
    );
  }

  function renderServices(data) {
    const body = $('services-body');
    rememberScroll(body);
    clear(body);
    const services = data.services || [];
    const hosts = data.hosts || [];
    const byId = new Map(services.map((s) => [s.id, s]));
    const hostsById = new Map(hosts.map((s) => [s.id, s]));
    const groups = data.groups || [];
    const running = services.filter((s) => s.state === 'running').length;
    const problems = services.filter(notNominal).length + hosts.filter(notNominal).length;
    const toggle = $('problems-toggle');
    if (toggle) {
      toggle.textContent = problems ? 'Problems (' + problems + ')' : 'Problems';
      toggle.classList.toggle('state-alert', problems > 0);
    }
    const hostLabel = hosts.length === 1 ? '1 host' : hosts.length + ' hosts';
    $('services-meta').textContent = services.length + ' compose services · ' +
      running + ' running · ' + hostLabel +
      (problems ? ' · ' + problems + ' not serving' : '');

    if (!groups.length) {
      body.appendChild(h('div', { class: 'empty', text: 'no compose inventory yet' }));
      return;
    }
    for (const group of groups) {
      const entries = [];
      for (const id of group.services || []) {
        const item = byId.get(id);
        if (item) entries.push(item);
      }
      for (const id of group.hosts || []) {
        const item = hostsById.get(id);
        if (item) entries.push(item);
      }
      if (!entries.length) continue;
      entries.sort((a, b) => severityRank(a) - severityRank(b) ||
        String(a.label || '').localeCompare(String(b.label || '')));
      const bad = entries.filter(isProblem).length;
      const warn = entries.filter(isWarning).length;
      const worst = bad ? 'state-alert' : warn ? 'state-warn' : 'state-ok';
      body.appendChild(h('div', { class: 'group' + (bad ? ' bad' : ''), dataset: { group: group.id } },
        h('div', { class: 'group-head' },
          h('span', { class: 'dot ' + worst, attrs: { 'aria-hidden': 'true' } }),
          h('h3', { text: group.label || group.id }),
          h('span', { class: 'count', text: String(entries.length) }),
          bad ? h('span', { class: 'rollup state-alert', text: bad + ' failing' }) : null,
          warn ? h('span', { class: 'rollup state-warn', text: warn + ' paused/absent' }) : null),
        entries.map((item) => serviceRow(item, item.stack ? 'service' : 'host'))));
    }
    restoreScroll(body);
  }

  // --------------------------------------------------------------- media --

  function notConfigured(varName) {
    return h('div', { class: 'nominal', text: 'not configured — add ' + varName + ' to observability .env' });
  }

  function streamRow(stream) {
    const position = num(stream.position_s) ? stream.position_s : 0;
    const runtime = num(stream.runtime_s) ? stream.runtime_s : 0;
    const title = stream.series
      ? stream.series + (num(stream.season) && num(stream.episode)
        ? ' · S' + pad2(stream.season) + 'E' + pad2(stream.episode) : '') +
        (stream.title ? ' — ' + stream.title : '')
      : (stream.title || '—');
    return h('tr', {},
      h('td', { class: 'mono', text: stream.user || '—' }),
      h('td', { class: 'mono muted', text: stream.device || '—' }),
      h('td', { class: 'wrap', text: title }),
      h('td', {}, h('span', { class: 'badge ' + (stream.method === 'Transcode' ? 'transcode' : 'direct'), text: stream.method || '—' })),
      h('td', {},
        runtime
          ? h('progress', { value: Math.min(position, runtime), max: runtime, 'aria-label': 'playback position' })
          : h('span', { class: 'faint', text: stream.paused ? 'paused' : '—' }),
        h('div', { class: 'faint mono', text: runtime ? fmtDuration(position) + ' / ' + fmtDuration(runtime) : '' }))
    );
  }

  function requestList(rows, empty) {
    if (!rows || !rows.length) return h('div', { class: 'empty', text: empty });
    return h('ul', { class: 'list' }, rows.map((row) =>
      h('li', {},
        h('div', { text: row.title || '—' }),
        h('div', { class: 'faint mono', text: [row.type, row.requester, fmtDate(row.created)].filter(Boolean).join(' · ') }))));
  }

  function renderMedia(data) {
    const body = $('media-body');
    clear(body);
    const media = data.media || {};
    const jellyfin = media.jellyfin || {};
    const requests = media.requests || {};
    $('media-meta').textContent = jellyfin.configured
      ? (jellyfin.active || 0) + ' active stream(s)'
      : 'jellyfin not configured';

    const left = h('div', {});
    left.appendChild(h('h3', { text: 'Jellyfin' + (jellyfin.version ? ' · ' + jellyfin.version : '') }));
    if (!jellyfin.configured) {
      left.appendChild(notConfigured('DASHBOARD_JELLYFIN_API_KEY'));
    } else {
      if (jellyfin.error) left.appendChild(h('div', { class: 'panel-note state-warn', text: jellyfin.error }));
      left.appendChild(h('div', { class: 'stat-row' },
        h('span', { class: 'stat' }, 'active ', h('b', { text: String(jellyfin.active || 0) })),
        h('span', { class: 'stat' }, 'direct ', h('b', { text: String(jellyfin.direct || 0) })),
        h('span', { class: 'stat' }, 'transcode ', h('b', { text: String(jellyfin.transcode || 0) }))
      ));
      const streams = jellyfin.streams || [];
      left.appendChild(streams.length
        ? h('div', { class: 'table-wrap' }, h('table', {},
          h('thead', {}, h('tr', {},
            h('th', { text: 'user' }), h('th', { text: 'device' }),
            h('th', { text: 'title' }), h('th', { text: 'mode' }), h('th', { text: 'progress' }))),
          h('tbody', {}, streams.map(streamRow))))
        : h('div', { class: 'empty', text: 'nothing streaming' }));
      left.appendChild(h('h3', { text: 'Recently added' }));
      left.appendChild((jellyfin.recent || []).length
        ? h('ul', { class: 'list' }, jellyfin.recent.map((item) =>
          h('li', {},
            h('div', { text: item.series ? item.series + ' — ' + item.title : item.title || '—' }),
            h('div', { class: 'faint mono', text: [item.type, item.year, fmtDate(item.created)].filter(Boolean).join(' · ') }))))
        : h('div', { class: 'empty', text: 'no recent additions' }));
    }

    const right = h('div', {});
    right.appendChild(h('h3', { text: 'Jellyseerr' + (requests.version ? ' · ' + requests.version : '') }));
    if (!requests.configured) {
      right.appendChild(notConfigured('DASHBOARD_JELLYSEERR_API_KEY'));
    } else {
      if (requests.error) right.appendChild(h('div', { class: 'panel-note state-warn', text: requests.error }));
      right.appendChild(h('h3', { text: 'Pending' }));
      right.appendChild(requestList(requests.pending, 'nothing pending'));
      right.appendChild(h('h3', { text: 'Recently available' }));
      right.appendChild(requestList(requests.available, 'nothing available yet'));
    }

    body.appendChild(h('div', { class: 'split' }, left, right));
  }

  // ------------------------------------------------------------ pipeline --

  function healthList(entry, label) {
    const items = [];
    for (const message of entry.errors || []) {
      items.push(h('li', { class: 'state-alert' }, h('span', { class: 'dot' }), message));
    }
    for (const message of entry.warnings || []) {
      items.push(h('li', { class: 'state-warn' }, h('span', { class: 'dot' }), message));
    }
    if (!items.length) items.push(h('li', { class: 'faint', text: label + ' health ok' }));
    return h('ul', { class: 'list' }, items);
  }

  function arrPanel(name, label, entry) {
    const panel = h('div', {});
    panel.appendChild(h('h3', { text: label + (entry && entry.version ? ' · ' + entry.version : '') }));
    if (!entry || !entry.configured) {
      panel.appendChild(notConfigured('DASHBOARD_' + name.toUpperCase() + '_API_KEY'));
      return panel;
    }
    if (entry.error) panel.appendChild(h('div', { class: 'panel-note state-warn', text: entry.error }));
    panel.appendChild(healthList(entry, label));
    if (entry.queue) {
      const stalled = entry.queue.stalled || [];
      panel.appendChild(h('div', { class: 'stat-row' },
        h('span', { class: 'stat' }, 'queue ', h('b', { text: String(entry.queue.total || 0) })),
        h('span', { class: 'stat' }, 'stalled ', h('b', { text: String(stalled.length) }))));
      if (stalled.length) {
        panel.appendChild(h('div', { class: 'table-wrap' }, h('table', {},
          h('thead', {}, h('tr', {},
            h('th', { text: 'title' }), h('th', { text: 'state' }), h('th', { text: 'error' }))),
          h('tbody', {}, stalled.map((row) => h('tr', {},
            h('td', { class: 'wrap', text: row.title || '—' }),
            h('td', { class: 'mono', text: row.tracked_state || row.status || '—' }),
            h('td', { class: 'wrap muted', text: row.error || '—' })))))));
      }
    }
    return panel;
  }

  function renderPipeline(data) {
    const body = $('pipeline-body');
    clear(body);
    const pipeline = data.pipeline || {};
    const arr = ['prowlarr', 'sonarr', 'radarr'];
    const configured = arr.filter((name) => pipeline[name] && pipeline[name].configured).length;
    $('pipeline-meta').textContent = configured + '/' + arr.length + ' integrations configured';
    body.appendChild(h('div', { class: 'grid grid-3' },
      arrPanel('prowlarr', 'Prowlarr', pipeline.prowlarr),
      arrPanel('sonarr', 'Sonarr', pipeline.sonarr),
      arrPanel('radarr', 'Radarr', pipeline.radarr)
    ));
    const seerr = pipeline.jellyseerr || {};
    if (seerr.configured && seerr.error) {
      body.appendChild(h('div', { class: 'panel-note state-warn', text: 'jellyseerr: ' + seerr.error }));
    }
  }

  // ------------------------------------------------------------- backups --

  function renderBackups(data) {
    const body = $('backups-body');
    rememberScroll(body);
    clear(body);
    const backups = data.backups || {};
    const repos = backups.repos || [];
    const jobs = backups.jobs || [];
    const markers = backups.markers || [];
    $('backups-meta').textContent = repos.length + ' repositories · ' + jobs.length + ' guarded jobs';

    if (!repos.length) {
      body.appendChild(h('div', { class: 'panel-note faint', text: 'no repository stats yet — homelab-backup-stats writes them every 6 h' }));
    }
    body.appendChild(h('div', { class: 'grid grid-3' }, repos.map((repo) => {
      const marker = markers.find((m) => m.host === repo.host);
      const state = repo.success === false ? 'state-alert'
        : (num(repo.snapshot_count) && repo.snapshot_count === 0) ? 'state-alert'
        : (num(repo.latest_age) && repo.latest_age > 48 * 3600) ? 'state-alert'
        : repo.success ? 'state-ok' : 'state-unknown';
      return h('div', { class: 'metric' },
        h('div', { class: 'label', text: repo.host + ' · ' + repo.repository }),
        h('div', { class: 'value ' + state, text: num(repo.latest_age) ? fmtDuration(repo.latest_age) : '—' }),
        h('div', { class: 'sub', text: 'latest snapshot · ' + fmtBytes(repo.latest_snapshot_bytes) }),
        h('div', { class: 'sub', text: (num(repo.snapshot_count) ? repo.snapshot_count : '?') + ' snapshots · ' + fmtBytes(repo.size_bytes) + ' repo' }),
        h('div', { class: 'sub', text: 'stats ' + (num(repo.stats_age) ? fmtAge(repo.stats_age) : 'never') }),
        marker ? h('div', { class: 'sub', text: 'last success ' + fmtAge(marker.age) }) : null
      );
    })));

    body.appendChild(h('h3', { text: 'Guarded jobs' }));
    body.appendChild(jobs.length
      ? h('div', { class: 'table-wrap tall', dataset: { scroll: 'jobs' } }, h('table', {},
        h('thead', {}, h('tr', {},
          h('th', { text: 'host' }), h('th', { text: 'task' }), h('th', { text: 'timer' }),
          h('th', { text: 'last run' }), h('th', { text: 'next run' }),
          h('th', { class: 'right', text: 'exit' }), h('th', { text: 'state' }))),
        h('tbody', {}, jobs.map((job) => {
          const bad = job.failed || job.missed || job.timer_active === false;
          return h('tr', {},
            h('td', { class: 'mono', text: job.host || '—' }),
            h('td', { class: 'mono', text: job.task || '—' }),
            h('td', { class: job.timer_active ? 'state-ok' : 'state-alert' },
              h('span', { class: 'dot' }), job.timer_active ? 'active' : 'inactive'),
            h('td', { class: 'mono muted', text: job.last_run ? fmtDate(job.last_run) : '—' }),
            h('td', { class: 'mono muted', text: fmtIn(job.next_run_in) }),
            h('td', { class: 'right mono', text: num(job.exit_code) ? String(job.exit_code) : '—' }),
            h('td', { class: bad ? 'state-alert' : 'state-ok' },
              h('span', { class: 'dot' }),
              job.failed ? 'failed' : job.missed ? 'missed' : job.timer_active === false ? 'inactive' : 'ok')
          );
        }))))
      : h('div', { class: 'empty', text: 'no job metrics yet' }));
    restoreScroll(body);
  }

  // ------------------------------------------------------------- network --

  function pingCell(peer) {
    const cell = h('td', {});
    const out = h('span', { class: 'mono faint', text: '—' });
    const button = h('button', {
      type: 'button',
      text: 'ping',
      attrs: { 'aria-label': 'ping ' + (peer.name || peer.id) },
      on: {
        click: async () => {
          button.disabled = true;
          out.className = 'mono muted';
          out.textContent = 'pinging…';
          try {
            const response = await fetch('/api/tailscale/ping', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
              body: JSON.stringify({ id: peer.id }),
            });
            const payload = await response.json();
            if (payload.error) {
              out.className = 'mono state-warn';
              out.textContent = payload.error;
            } else {
              out.className = 'mono state-ok';
              out.textContent = payload.path + ' · ' + payload.latency_ms + ' ms' +
                (payload.derp ? ' · ' + payload.derp : '') +
                (payload.endpoint ? ' · ' + payload.endpoint : '');
            }
          } catch (err) {
            out.className = 'mono state-alert';
            out.textContent = String(err && err.message ? err.message : err);
          } finally {
            button.disabled = false;
          }
        },
      },
    });
    cell.appendChild(button);
    cell.appendChild(document.createTextNode(' '));
    cell.appendChild(out);
    return cell;
  }

  function renderNetwork(data) {
    const body = $('network-body');
    rememberScroll(body);
    clear(body);
    const network = data.network || {};
    const tailscale = network.tailscale || {};
    const peers = tailscale.peers || [];
    $('network-meta').textContent = tailscale.available
      ? peers.length + ' tailscale peers'
      : 'tailscale unavailable';

    const left = h('div', {});
    left.appendChild(h('h3', { text: 'Tailscale' }));
    if (!tailscale.available) {
      left.appendChild(h('div', { class: 'nominal', text: 'LocalAPI unavailable — the rest of the dashboard is unaffected' }));
    } else {
      left.appendChild(h('div', { class: 'stat-row' },
        h('span', { class: 'stat' }, 'self ', h('b', { text: (tailscale.self || {}).name || '—' })),
        h('span', { class: 'stat' }, 'ip ', h('b', { class: 'ip', text: (tailscale.self || {}).ip || '—' }))
      ));
      left.appendChild(h('div', { class: 'table-wrap', dataset: { scroll: 'peers' } }, h('table', {},
        h('thead', {}, h('tr', {},
          h('th', { text: 'host' }), h('th', { text: 'ip' }), h('th', { text: 'state' }),
          h('th', { text: 'path' }), h('th', { text: 'last seen' }), h('th', { text: 'ping' }))),
        h('tbody', {}, peers.map((peer) => h('tr', {},
          h('td', { class: 'mono', text: peer.name || peer.id }),
          h('td', { class: 'mono', text: peer.ip || '—' }),
          h('td', { class: peer.online ? 'state-ok' : 'state-unknown' },
            h('span', { class: 'dot' }), peer.online ? 'online' : 'offline'),
          h('td', { class: 'mono muted', text: peer.direct ? 'direct' : (peer.relay || 'relay') }),
          h('td', { class: 'mono muted', text: peer.online ? 'now' : fmtAge(peer.last_seen ? (Date.now() / 1000 - peer.last_seen) : null) }),
          pingCell(peer)
        ))))));
    }

    const right = h('div', {});
    right.appendChild(h('h3', { text: 'WireGuard' }));
    const wireguard = network.wireguard || [];
    right.appendChild(wireguard.length
      ? h('div', { class: 'table-wrap' }, h('table', {},
        h('thead', {}, h('tr', {}, h('th', { text: 'peer' }), h('th', { text: 'handshake' }), h('th', { text: 'state' }))),
        h('tbody', {}, wireguard.map((peer) => {
          const stale = num(peer.age) && peer.age > 600;
          return h('tr', {},
            h('td', { class: 'mono', text: String(peer.peer || '').slice(0, 16) }),
            h('td', { class: 'mono muted', text: fmtAge(peer.age) }),
            h('td', { class: stale ? 'state-warn' : 'state-ok' }, h('span', { class: 'dot' }), stale ? 'stale' : 'fresh'));
        }))))
      : h('div', { class: 'empty', text: 'no WireGuard metrics' }));
    body.appendChild(h('div', { class: 'split' }, left, right));

    body.appendChild(h('h3', { text: 'Proxy routes' }));
    const routes = network.routes || [];
    body.appendChild(h('div', { class: 'table-wrap', dataset: { scroll: 'routes' } }, h('table', {},
      h('thead', {}, h('tr', {},
        h('th', { text: 'exposure' }), h('th', { text: 'host' }), h('th', { text: 'upstream' }),
        h('th', { text: 'status' }), h('th', { class: 'right', text: 'latency' }), h('th', { class: 'right', text: 'tls' }))),
      h('tbody', {}, routes.map((route) => {
        const ok = route.status === 'ok';
        const cls = ok ? 'state-ok' : route.status === 'fail' ? 'state-alert' : 'state-unknown';
        return h('tr', {},
          h('td', { class: 'mono muted', text: route.exposure }),
          h('td', { class: 'mono', text: route.host || '—' }),
          h('td', { class: 'mono muted', text: route.upstream || '—' }),
          h('td', { class: cls }, h('span', { class: 'dot' }), route.status || 'unknown'),
          h('td', { class: 'right mono', text: num(route.latency_ms) ? Math.round(route.latency_ms) + ' ms' : '—' }),
          h('td', { class: 'right mono', text: num(route.tls_days) ? route.tls_days.toFixed(0) + ' d' : '—' }));
      })))));
    body.appendChild(h('div', { class: 'panel-note faint', text: 'public routes are judged by the blackbox probe on chill-01 (hairpin), not from the internet' }));

    body.appendChild(h('h3', { text: 'TCP DNAT probes' }));
    const tcp = network.tcp_probes || [];
    body.appendChild(tcp.length
      ? h('div', { class: 'table-wrap' }, h('table', {},
        h('thead', {}, h('tr', {},
          h('th', { text: 'service' }), h('th', { class: 'right', text: 'port' }),
          h('th', { text: 'proto' }), h('th', { text: 'state' }), h('th', { class: 'right', text: 'latency' }))),
        h('tbody', {}, tcp.map((probe) => h('tr', {},
          h('td', { text: probe.label || probe.instance }),
          h('td', { class: 'right mono', text: probe.port ? String(probe.port) : '—' }),
          h('td', { class: 'mono muted', text: probe.proto || 'tcp' }),
          h('td', { class: probe.success ? 'state-ok' : 'state-alert' },
            h('span', { class: 'dot' }), probe.success ? 'ok' : 'fail'),
          h('td', { class: 'right mono', text: num(probe.latency_ms) ? Math.round(probe.latency_ms) + ' ms' : '—' }))))))
      : h('div', { class: 'empty', text: 'no TCP probes' }));
    restoreScroll(body);
  }

  // ---------------------------------------------------------------- logs --

  function renderLogs(data) {
    const body = $('logs-body');
    rememberScroll(body);
    clear(body);
    const logs = data.logs || [];
    const select = $('log-service');
    const services = [...new Set(logs.map((event) => event.service).filter(Boolean))].sort();
    const current = state.filters.service;
    const rest = [...new Set(services.concat(current === 'all' ? [] : [current]))]
      .filter((name) => name && name !== 'all').sort();
    const wanted = ['all'].concat(rest);
    const present = [...select.options].map((option) => option.value);
    if (wanted.length !== present.length || wanted.some((value, i) => present[i] !== value)) {
      clear(select);
      for (const name of wanted) select.appendChild(h('option', { value: name, text: name }));
      select.value = wanted.includes(current) ? current : 'all';
      state.filters.service = select.value;
    }
    $('logs-meta').textContent = logs.length + ' events · newest first';
    if (!logs.length) {
      body.appendChild(h('div', { class: 'empty', text: 'no log events collected yet' }));
      return;
    }
    for (const event of logs) {
      const level = event.level || 'info';
      if (state.filters.level !== 'all' && LEVEL_RANK[level] < LEVEL_RANK[state.filters.level]) continue;
      if (state.filters.service !== 'all' && event.service !== state.filters.service) continue;
      body.appendChild(h('div', {
        class: 'log level-' + level,
        dataset: { search: [event.service, level, event.message].join(' ').toLowerCase() },
      },
        h('span', { class: 'ts', text: event.ts ? fmtDate(event.ts) : '—' }),
        h('span', { class: 'log-svc', text: event.service || '—' }),
        h('span', { class: 'badge ' + (level === 'error' ? 'alert' : level === 'warn' ? 'warn' : ''), text: level.toUpperCase() }),
        h('span', { class: 'msg', text: event.message || '' })
      ));
    }
    restoreScroll(body);
  }

  // -------------------------------------------------------------- config --

  function definitionList(rows) {
    const list = h('dl', { class: 'kv' });
    for (const [key, value] of rows) {
      list.appendChild(h('dt', { text: key }));
      list.appendChild(h('dd', { text: value }));
    }
    return list;
  }

  function renderConfig(data) {
    const body = $('config-body');
    rememberScroll(body);
    clear(body);
    const git = data.git || {};
    const inventory = data.inventory || {};
    $('config-meta').textContent = inventory.stacks + ' stacks · ' +
      (inventory.ports || []).length + ' ports · ' + (inventory.volumes || []).length + ' volumes';

    body.appendChild(h('div', { class: 'grid grid-2' },
      h('div', {},
        h('h3', { text: 'Source tree at deploy' }),
        definitionList([
          ['commit', git.commit || 'unknown'],
          ['branch', git.branch || 'unknown'],
          ['subject', git.subject || 'unknown'],
          ['deployed', git.deployed_at ? fmtDate(git.deployed_at) : 'unknown'],
          ['dirty', git.dirty === null || git.dirty === undefined ? 'unknown' : git.dirty ? 'yes' : 'no'],
        ])),
      h('div', {},
        h('h3', { text: 'Inventory' }),
        definitionList([
          ['stacks', String(inventory.stacks || 0)],
          ['services', String(inventory.services || 0)],
          ['ports', String((inventory.ports || []).length)],
          ['volumes', String((inventory.volumes || []).length)],
        ]))
    ));

    body.appendChild(h('h3', { class: 'alloc-title', text: 'Ports' }));
    const ports = inventory.ports || [];
    body.appendChild(ports.length
      ? h('div', { class: 'table-wrap', dataset: { scroll: 'ports' } }, h('table', { class: 'alloc-table' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'stack / service' }), h('th', { text: 'host ip' }),
          h('th', { class: 'right', text: 'host' }), h('th', { class: 'right', text: 'container' }),
          h('th', { text: 'proto' }), h('th', { text: 'note' }))),
        h('tbody', {}, ports.map((row) => {
          const search = [row.stack, row.service, row.host_ip, row.host_port, row.container_port, row.note]
            .filter((v) => v !== null && v !== undefined).join(' ').toLowerCase();
          return h('tr', { dataset: { search } },
            h('td', { class: 'mono' },
              h('span', { class: 'alloc-id' },
                h('span', { class: 'stack', text: row.stack }),
                h('span', { class: 'sep', text: '/' }),
                h('span', { class: 'service', text: row.service }))),
            h('td', { class: 'mono muted', text: row.host_ip || '—' }),
            h('td', { class: 'right mono', text: row.host_port === null || row.host_port === undefined ? '—' : String(row.host_port) }),
            h('td', { class: 'right mono', text: String(row.container_port) }),
            h('td', { class: 'mono muted', text: row.proto || 'tcp' }),
            h('td', { class: 'muted', text: row.note || '' }));
        }))))
      : h('div', { class: 'empty', text: 'no declared ports' }));

    body.appendChild(h('h3', { class: 'alloc-title', text: 'Volumes' }));
    const volumes = inventory.volumes || [];
    body.appendChild(volumes.length
      ? h('div', { class: 'table-wrap', dataset: { scroll: 'volumes' } }, h('table', { class: 'alloc-table' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'stack / service' }), h('th', { text: 'source' }),
          h('th', { text: 'target' }), h('th', { text: 'mode' }))),
        h('tbody', {}, volumes.map((row) => {
          const search = [row.stack, row.service, row.source, row.target, row.mode]
            .filter((v) => v !== null && v !== undefined).join(' ').toLowerCase();
          return h('tr', { dataset: { search } },
            h('td', { class: 'mono' },
              h('span', { class: 'alloc-id' },
                h('span', { class: 'stack', text: row.stack }),
                h('span', { class: 'sep', text: '/' }),
                h('span', { class: 'service', text: row.service }))),
            h('td', { class: 'mono muted wrap', text: row.source || 'anonymous' }),
            h('td', { class: 'mono wrap', text: row.target || '' }),
            h('td', { class: 'mono muted', text: row.mode || 'rw' }));
        }))))
      : h('div', { class: 'empty', text: 'no declared volumes' }));
    restoreScroll(body);
  }

  // -------------------------------------------------------------- filter --

  function applyFilter() {
    const needle = state.filters.text.trim().toLowerCase();
    const servicesBody = $('services-body');
    let visible = 0;
    for (const row of servicesBody.querySelectorAll('.svc')) {
      const haystack = row.dataset.search || '';
      const matchesText = !needle || haystack.includes(needle);
      const matchesProblem = !state.filters.problems || row.dataset.problem === '1';
      const match = matchesText && matchesProblem;
      row.classList.toggle('hidden', !match);
      if (match) visible += 1;
    }
    for (const group of servicesBody.querySelectorAll('.group')) {
      const rows = group.querySelectorAll('.svc');
      const shown = group.querySelectorAll('.svc:not(.hidden)');
      group.classList.toggle('hidden', rows.length > 0 && shown.length === 0);
    }
    emptyNote(
      servicesBody,
      'services-no-match',
      state.filters.problems && !needle
        ? 'no service is failing; switch Problems off to see the full directory'
        : 'no service matches this filter',
      visible === 0 && (Boolean(needle) || state.filters.problems)
    );
    for (const row of document.querySelectorAll('#config-body tbody tr[data-search]')) {
      row.classList.toggle('hidden', Boolean(needle) && !(row.dataset.search || '').includes(needle));
    }
    for (const row of document.querySelectorAll('#logs-body .log[data-search]')) {
      row.classList.toggle('hidden', Boolean(needle) && !(row.dataset.search || '').includes(needle));
    }
    const logsBody = $('logs-body');
    const shownLogs = logsBody.querySelectorAll('.log:not(.hidden)').length;
    emptyNote(
      logsBody,
      'logs-no-match',
      'no log line matches this filter',
      shownLogs === 0 && logsBody.querySelectorAll('.log').length > 0
    );
    state.selection = -1;
    for (const row of servicesBody.querySelectorAll('.svc.kb')) row.classList.remove('kb');
  }

  function targets() {
    return [...$('services-body').querySelectorAll('.svc:not(.hidden) a')].filter((a) => isSafeUrl(a.href));
  }

  function moveSelection(delta) {
    const links = targets();
    if (!links.length) return;
    state.selection = Math.max(0, Math.min(links.length - 1, state.selection + delta));
    for (const row of $('services-body').querySelectorAll('.svc.kb')) row.classList.remove('kb');
    const link = links[state.selection];
    const row = link.closest('.svc');
    if (row) {
      row.classList.add('kb');
      row.scrollIntoView({ block: 'nearest' });
    }
  }

  function wireFilter() {
    const input = $('quick-filter');
    input.addEventListener('input', () => {
      state.filters.text = input.value;
      applyFilter();
    });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); moveSelection(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); moveSelection(-1); }
      else if (event.key === 'Enter') {
        const link = targets()[state.selection];
        if (link) {
          event.preventDefault();
          window.open(link.href, '_blank', 'noopener');
        }
      } else if (event.key === 'Escape') {
        input.value = '';
        state.filters.text = '';
        applyFilter();
        input.blur();
      }
    });
    document.addEventListener('keydown', (event) => {
      const tag = event.target && event.target.tagName ? event.target.tagName : '';
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(tag);
      if (typing) return;
      if (event.key === '/' || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k')) {
        event.preventDefault();
        input.focus();
        input.select();
      }
    });
  }

  function openLogs(service) {
    state.filters.service = service;
    state.filters.level = 'all';
    for (const button of document.querySelectorAll('#logs .group-btns button')) {
      button.setAttribute('aria-pressed', String(button.dataset.level === 'all'));
    }
    render();
    const select = $('log-service');
    if (select) select.value = service;
    const panel = $('logs');
    if (panel) panel.scrollIntoView({ block: 'start' });
  }

  function wireServicesControls() {
    const toggle = $('problems-toggle');
    toggle.addEventListener('click', () => {
      state.filters.problems = !state.filters.problems;
      toggle.setAttribute('aria-pressed', String(state.filters.problems));
      applyFilter();
    });
    $('status-chip').addEventListener('click', () => {
      const panel = $('alerts');
      if (panel) panel.scrollIntoView({ block: 'start' });
    });
  }

  function wireLogControls() {
    for (const button of document.querySelectorAll('#logs .group-btns button')) {
      button.addEventListener('click', () => {
        state.filters.level = button.dataset.level;
        for (const other of document.querySelectorAll('#logs .group-btns button')) {
          other.setAttribute('aria-pressed', String(other === button));
        }
        render();
      });
    }
    $('log-service').addEventListener('change', (event) => {
      state.filters.service = event.target.value;
      render();
    });
  }

  // ---------------------------------------------------------------- render --

  function render() {
    const data = state.snapshot;
    if (!data) return;
    renderAlerts(data);
    renderTelemetry(data);
    renderServices(data);
    renderMedia(data);
    renderPipeline(data);
    renderBackups(data);
    renderNetwork(data);
    renderLogs(data);
    renderConfig(data);
    applyFilter();
    const git = data.git || {};
    $('commit').textContent = 'commit ' + (git.short || 'unknown') + (git.dirty ? '+' : '');
    const grafana = (data.links || {}).grafana;
    const grafanaLink = $('grafana-link');
    if (grafanaLink) {
      if (isSafeUrl(grafana)) {
        grafanaLink.href = grafana;
        grafanaLink.classList.remove('hidden');
      } else {
        grafanaLink.classList.add('hidden');
      }
    }
  }

  // ------------------------------------------------------------------ poll --

  async function poll() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch('/api/snapshot', {
        signal: controller.signal,
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      state.snapshot = data;
      state.lastOk = Date.now();
      state.error = null;
      render();
    } catch (err) {
      state.error = err && err.name === 'AbortError' ? 'request timed out' : String(err && err.message ? err.message : err);
    } finally {
      clearTimeout(timer);
      state.lastAttempt = Date.now();
      tick();
      setTimeout(poll, POLL_MS);
    }
  }

  /* The banner reports a real outage only: a slow first load is not stale data. */
  function tick() {
    $('clock').textContent = fmtClock(new Date());
    const heartbeat = $('heartbeat');
    const banner = $('stale');
    const kind = $('stale-kind');
    const detail = $('stale-detail');
    let stale = false;
    if (state.lastOk) {
      const age = (Date.now() - state.lastOk) / 1000;
      stale = age * 1000 > STALE_MS;
      if (stale) {
        kind.textContent = 'DATA STALE';
        detail.textContent = '— last update ' + fmtAge(age);
      }
    } else if (state.lastAttempt) {
      stale = true;
      kind.textContent = 'NO DATA';
      detail.textContent = '— first snapshot failed: ' + (state.error || 'unknown error');
    }
    heartbeat.className = 'heartbeat ' + (stale ? 'dead' : state.lastOk ? 'live' : '');
    banner.classList.toggle('hidden', !stale);
    document.body.classList.toggle('stale-on', stale);
  }

  function boot() {
    wireFilter();
    wireServicesControls();
    wireLogControls();
    setInterval(tick, 1000);
    tick();
    poll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
