/* Personalized Environment-Aware Biomedical Monitoring - dashboard client */

(function () {
  "use strict";

  const CONTINUOUS = [
    { key: "hr",           label: "Heart rate",          unit: "bpm", dp: 0 },
    { key: "spo2",         label: "SpO\u2082",           unit: "%",   dp: 1 },
    { key: "body_temp",    label: "Body temperature",    unit: "\u00b0C", dp: 2 },
    { key: "ambient_temp", label: "Ambient temperature", unit: "\u00b0C", dp: 1 },
    { key: "humidity",     label: "Humidity",            unit: "%",   dp: 0 },
    { key: "pressure",     label: "Pressure",            unit: "hPa", dp: 1 }
  ];

  const ADDON = [
    { key: "ecg",   label: "ECG amplitude", unit: "mV", dp: 3 },
    { key: "pm25",  label: "PM2.5",         unit: "\u00b5g/m\u00b3", dp: 0 },
    { key: "accel", label: "Motion",        unit: "g",  dp: 2 }
  ];

  const $ = (id) => document.getElementById(id);
  const state = {
    connected: false, testMode: false, latest: null, status: null,
    series: { t: [], hr: [], spo2: [], risk: [] }, socket: null, retry: 0
  };

  /* ---------------------------------------------------------------- tiles */
  function buildTiles(container, defs) {
    container.innerHTML = defs.map((d) => `
      <article class="tile idle" id="tile-${d.key}">
        <h3>${d.label}</h3>
        <p class="value" id="val-${d.key}">&mdash;<span class="unit">${d.unit}</span></p>
        <div class="zbar" id="zbar-${d.key}"><i></i></div>
        <p class="foot"><span id="base-${d.key}">baseline &mdash;</span><span id="z-${d.key}"></span></p>
      </article>`).join("");
  }

  function fmt(v, dp) {
    if (v === null || v === undefined || Number.isNaN(v)) return "\u2014";
    return Number(v).toFixed(dp);
  }

  function renderTile(def, readings, zScores, baseline) {
    const tile = $("tile-" + def.key);
    const valEl = $("val-" + def.key);
    if (!tile || !valEl) return;
    const v = readings ? readings[def.key] : undefined;
    const has = v !== undefined && v !== null;

    valEl.innerHTML = (has ? fmt(v, def.dp) : "\u2014") +
      `<span class="unit">${def.unit}</span>`;
    tile.classList.toggle("idle", !has);

    const z = zScores ? zScores[def.key] : null;
    const zEl = $("z-" + def.key);
    const zbar = $("zbar-" + def.key);
    if (zEl) zEl.textContent = (z === null || z === undefined) ? "" : "z " + (z > 0 ? "+" : "") + z.toFixed(2);
    if (zbar) {
      const i = zbar.firstElementChild;
      const mag = Math.min(Math.abs(z || 0) / 4, 1);
      i.style.width = (mag * 50) + "%";
      i.style.left = (z || 0) >= 0 ? "50%" : (50 - mag * 50) + "%";
      zbar.classList.toggle("hot", (z || 0) > 0);
      zbar.classList.toggle("cold", (z || 0) < 0);
    }

    const bEl = $("base-" + def.key);
    const b = baseline && baseline.signals ? baseline.signals[def.key] : null;
    if (bEl) {
      bEl.textContent = b ? `baseline ${fmt(b.mean, def.dp)} \u00b1 ${fmt(b.std, def.dp)}`
                          : "baseline \u2014";
    }

    tile.classList.remove("warn", "alarm");
    if (has && z !== null && z !== undefined) {
      if (Math.abs(z) >= 3) tile.classList.add("alarm");
      else if (Math.abs(z) >= 2) tile.classList.add("warn");
    }
  }

  /* -------------------------------------------------------------- verdict */
  function renderVerdict(latest) {
    const verdict = $("verdict");
    if (!latest) {
      verdict.dataset.level = "NORMAL";
      $("risk-level").textContent = "\u2014";
      $("risk-reason").textContent = state.connected
        ? "Waiting for the first packet."
        : "Connect a device or start test mode to begin monitoring.";
      $("risk-score").textContent = "\u2014";
      $("confidence").textContent = "\u2014";
      $("emergency-mode").textContent = "OFF";
      $("risk-bar").style.width = "0%";
      $("conf-bar").style.width = "0%";
      return;
    }
    verdict.dataset.level = latest.risk_level;
    $("risk-level").textContent = latest.risk_level;
    $("risk-reason").textContent = latest.reason || "\u2014";
    $("risk-score").textContent = Number(latest.risk_score).toFixed(0);
    $("confidence").textContent = Math.round(latest.confidence * 100) + "%";
    $("emergency-mode").textContent = latest.emergency_mode ? "ACTIVE" : "OFF";
    $("risk-bar").style.width = Math.min(100, latest.risk_score) + "%";
    $("conf-bar").style.width = Math.round(latest.confidence * 100) + "%";
    $("baseline-maturity").textContent =
      "Baseline " + Math.round((latest.baseline_maturity || 0) * 100) + "% learned";
  }

  /* --------------------------------------------------------------- status */
  function renderStatus(status) {
    if (!status) return;
    state.status = status;
    state.connected = !!status.connected;
    state.testMode = !!status.test_mode;

    const pill = $("state-pill");
    if (!status.connected) {
      pill.dataset.state = "off";
      pill.textContent = "DEVICE NOT CONNECTED";
    } else if (status.stale) {
      pill.dataset.state = "stale";
      pill.textContent = "No data \u2014 link stale";
    } else if (status.test_mode) {
      pill.dataset.state = "test";
      pill.textContent = "TEST MODE \u00b7 " + (status.virtual ? status.virtual.scenario_label : "");
    } else {
      pill.dataset.state = "live";
      pill.textContent = "LIVE \u00b7 " + (status.port || "");
    }

    $("test-banner").hidden = !status.test_mode;
    $("connect-btn").disabled = status.connected;
    $("disconnect-btn").disabled = !status.connected;
    $("scenario-select").hidden = !status.test_mode;

    const sc = $("scenario-select");
    if (sc.options.length === 0 && status.scenarios) {
      sc.innerHTML = status.scenarios
        .map((s) => `<option value="${s.id}">${s.label}</option>`).join("");
    }
    if (status.test_mode && status.virtual) sc.value = status.virtual.scenario;

    const cmd = status.last_command;
    $("command-text").textContent = cmd
      ? `Last command: ${JSON.stringify(cmd.command)} \u2014 ${cmd.sent ? "sent" : "not sent"}`
      : "No activation command sent yet.";

    const p = status.parser || {};
    $("footer-stats").textContent =
      `packets ${p.accepted || 0} accepted \u00b7 ${p.rejected || 0} rejected \u00b7 ` +
      `commands ${status.commands_sent || 0} \u00b7 stored ${status.db ? status.db.readings : 0}`;
    $("history-note").textContent = status.test_mode
      ? "Test-mode records only \u2014 kept separate from hardware history."
      : "Hardware records only.";
  }

  /* ------------------------------------------------------------- baseline */
  function renderBaseline(baseline, z) {
    const body = $("baseline-table").querySelector("tbody");
    if (!baseline || !baseline.signals) { body.innerHTML = ""; return; }
    body.innerHTML = CONTINUOUS.map((d) => {
      const b = baseline.signals[d.key] || {};
      const zv = z ? z[d.key] : null;
      return `<tr><td>${d.label}</td><td>${fmt(b.mean, d.dp)}</td>` +
             `<td>&plusmn;${fmt(b.std, d.dp)}</td><td>${b.samples || 0}</td>` +
             `<td>${zv === null || zv === undefined ? "\u2014" : (zv > 0 ? "+" : "") + zv.toFixed(2)}</td></tr>`;
    }).join("");
  }

  /* --------------------------------------------------------------- alerts */
  function renderAlerts(alerts) {
    const list = $("alert-list");
    if (!alerts || !alerts.length) {
      list.innerHTML = '<li class="empty">No alerts yet.</li>';
      return;
    }
    list.innerHTML = alerts.slice(0, 20).map((a) => {
      const when = new Date((a.ts || 0) * 1000).toLocaleTimeString();
      return `<li data-kind="${a.kind}"><strong>${a.kind}</strong> &middot; ${a.risk_level}
        <span class="when">${when}</span><br>${a.detail || ""} &mdash; ${a.reason || ""}</li>`;
    }).join("");
  }

  function renderRejects(rejects) {
    const list = $("reject-list");
    if (!rejects || !rejects.length) {
      list.innerHTML = '<li class="empty">None. Every packet so far parsed cleanly.</li>';
      return;
    }
    list.innerHTML = rejects.slice(0, 12).map((r) => {
      const when = new Date((r.ts || 0) * 1000).toLocaleTimeString();
      return `<li>${when} \u2014 ${escapeHtml(r.error || "")} :: ${escapeHtml((r.raw || "").slice(0, 70))}</li>`;
    }).join("");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* -------------------------------------------------------------- history */
  function renderHistory(items) {
    const body = $("history-table").querySelector("tbody");
    if (!items || !items.length) { body.innerHTML = ""; return; }
    body.innerHTML = items.slice().reverse().slice(0, 40).map((r) => `
      <tr><td>${(r.iso || "").split(" ")[1] || r.iso || ""}</td>
      <td>${fmt(r.hr, 0)}</td><td>${fmt(r.spo2, 1)}</td><td>${fmt(r.body_temp, 2)}</td>
      <td>${fmt(r.ambient_temp, 1)}</td><td>${fmt(r.humidity, 0)}</td><td>${fmt(r.pressure, 1)}</td>
      <td>${r.risk_level || ""}</td><td>${fmt(r.risk_score, 0)}</td>
      <td>${r.confidence === null || r.confidence === undefined ? "" : Math.round(r.confidence * 100) + "%"}</td></tr>`).join("");
  }

  /* --------------------------------------------------------------- charts */
  function pushSeries(latest) {
    const s = state.series;
    s.t.push(latest.timestamp);
    s.hr.push(latest.readings.hr ?? null);
    s.spo2.push(latest.readings.spo2 ?? null);
    s.risk.push(latest.risk_score);
    const max = 120;
    ["t", "hr", "spo2", "risk"].forEach((k) => {
      while (s[k].length > max) s[k].shift();
    });
  }

  function drawChart(canvas, series, opts) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 400;
    const h = parseInt(canvas.getAttribute("height"), 10) || 200;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr; canvas.height = h * dpr;
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const pad = { l: 38, r: 10, t: 10, b: 18 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;

    ctx.strokeStyle = "#23393f"; ctx.lineWidth = 1;
    ctx.fillStyle = "#8aa3a8"; ctx.font = "10px system-ui, sans-serif";
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (ih * i) / 4;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      const val = opts.max - ((opts.max - opts.min) * i) / 4;
      ctx.fillText(val.toFixed(0), 4, y + 3);
    }

    const n = Math.max(series[0].values.length, 2);
    series.forEach((s) => {
      ctx.strokeStyle = s.color; ctx.lineWidth = 1.8;
      ctx.beginPath();
      let started = false;
      s.values.forEach((v, i) => {
        if (v === null || v === undefined || Number.isNaN(v)) { started = false; return; }
        const x = pad.l + (iw * i) / (n - 1);
        const clamped = Math.max(opts.min, Math.min(opts.max, v));
        const y = pad.t + ih - (ih * (clamped - opts.min)) / (opts.max - opts.min);
        if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
      });
      ctx.stroke();
    });

    let lx = pad.l;
    series.forEach((s) => {
      ctx.fillStyle = s.color;
      ctx.fillRect(lx, h - 9, 10, 2);
      ctx.fillStyle = "#8aa3a8";
      ctx.fillText(s.name, lx + 14, h - 5);
      lx += 14 + ctx.measureText(s.name).width + 16;
    });
  }

  function redrawCharts() {
    const s = state.series;
    drawChart($("chart-vitals"), [
      { name: "HR (bpm)", values: s.hr, color: "#45d4c0" },
      { name: "SpO\u2082 (%)", values: s.spo2, color: "#9a8cf5" }
    ], { min: 40, max: 180 });
    drawChart($("chart-risk"), [
      { name: "Risk score", values: s.risk, color: "#ef8a48" }
    ], { min: 0, max: 100 });
  }

  /* ------------------------------------------------------------- add-ons */
  function renderAddons(latest) {
    const block = $("addon-block");
    const active = latest && latest.addon_active;
    block.dataset.active = active ? "true" : "false";
    $("addon-note").textContent = active
      ? "Active \u2014 " + (latest.addon_sensors || []).join(", ")
      : "Standby \u2014 activated by the decision engine";
    ADDON.forEach((d) => renderTile(d, latest ? latest.readings : null,
                                    latest ? latest.z_scores : null, null));
  }

  /* ----------------------------------------------------------- data flow */
  function applyLatest(latest) {
    if (!latest) { renderVerdict(null); return; }
    state.latest = latest;
    renderVerdict(latest);
    CONTINUOUS.forEach((d) => renderTile(d, latest.readings, latest.z_scores,
                                         state.baseline));
    renderAddons(latest);
    renderBaseline(state.baseline, latest.z_scores);
    pushSeries(latest);
    redrawCharts();
  }

  function applySnapshot(msg) {
    if (msg.status) renderStatus(msg.status);
    if (msg.baseline) state.baseline = msg.baseline;
    if (msg.alerts) renderAlerts(msg.alerts);
    if (msg.rejects) renderRejects(msg.rejects);
    if (msg.latest) applyLatest(msg.latest);
    else renderVerdict(null);
  }

  /* ------------------------------------------------------------ websocket */
  function connectSocket() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + location.host + "/ws");
    state.socket = ws;

    ws.onopen = () => { state.retry = 0; };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      switch (msg.type) {
        case "snapshot":
          applySnapshot(msg);
          loadHistory();
          break;
        case "reading":
          if (msg.status) renderStatus(msg.status);
          if (msg.baseline) state.baseline = msg.baseline;
          if (msg.alerts) renderAlerts(msg.alerts);
          if (msg.rejects) renderRejects(msg.rejects);
          applyLatest(msg.latest);
          if ((msg.new_alerts || []).length) loadHistory();
          break;
        case "reject":
          if (msg.reject) {
            state.rejects = [msg.reject].concat(state.rejects || []).slice(0, 12);
            renderRejects(state.rejects);
          }
          break;
        case "link":
        case "status":
          renderStatus(msg.status);
          if (msg.status && !msg.status.connected) { applyLatest(null); loadHistory(); }
          break;
        case "command":
          if (msg.command) {
            $("command-text").textContent =
              `Last command: ${JSON.stringify(msg.command.command)} \u2014 ` +
              (msg.command.sent ? "sent" : "not sent");
          }
          break;
        default:
          break;
      }
    };
    ws.onclose = () => {
      state.retry = Math.min(state.retry + 1, 10);
      setTimeout(connectSocket, 800 * state.retry);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* ignore */ } };
  }

  /* ------------------------------------------------------------ REST bits */
  async function api(path, options) {
    const res = await fetch(path, Object.assign({
      headers: { "Content-Type": "application/json" }
    }, options || {}));
    let body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    return { ok: res.ok, body: body };
  }

  async function loadPorts() {
    const { body } = await api("/api/ports");
    const sel = $("port-select");
    const previous = sel.value;
    const ports = (body && body.ports) || [];
    sel.innerHTML = ports.map((p) =>
      `<option value="${p.device}">${p.device} \u2014 ${p.description}</option>`).join("");
    if (previous) sel.value = previous;
  }

  async function loadHistory() {
    const { body } = await api("/api/history?limit=200");
    if (body) renderHistory(body.items || []);
  }

  async function bootstrap() {
    await loadPorts();
    const { body } = await api("/api/latest");
    if (body) {
      if (body.status) renderStatus(body.status);
      if (body.baseline) state.baseline = body.baseline;
      if (body.alerts) renderAlerts(body.alerts);
      if (body.latest) applyLatest(body.latest); else renderVerdict(null);
    }
    await loadHistory();
    connectSocket();
  }

  /* --------------------------------------------------------------- events */
  $("refresh-ports").addEventListener("click", loadPorts);

  $("connect-btn").addEventListener("click", async () => {
    const payload = {
      port: $("port-select").value,
      baudrate: parseInt($("baud-input").value, 10) || 115200,
      scenario: $("scenario-select").value || "normal"
    };
    const { ok, body } = await api("/api/connect",
      { method: "POST", body: JSON.stringify(payload) });
    if (!ok) alert((body && body.error) || "Could not connect to that port.");
    else {
      state.series = { t: [], hr: [], spo2: [], risk: [] };
      if (body.status) renderStatus(body.status);
      loadHistory();
    }
  });

  $("disconnect-btn").addEventListener("click", async () => {
    const { body } = await api("/api/disconnect", { method: "POST" });
    if (body && body.status) renderStatus(body.status);
    applyLatest(null);
  });

  $("scenario-select").addEventListener("change", async (e) => {
    await api("/api/scenario",
      { method: "POST", body: JSON.stringify({ scenario: e.target.value }) });
  });

  $("force-addon").addEventListener("click", async () => {
    const { ok, body } = await api("/api/command",
      { method: "POST", body: JSON.stringify({ enable: true }) });
    if (!ok) alert((body && body.error) || "Device is not connected.");
  });

  $("stop-addon").addEventListener("click", async () => {
    await api("/api/command",
      { method: "POST", body: JSON.stringify({ enable: false, sensors: [] }) });
  });

  window.addEventListener("resize", redrawCharts);

  buildTiles($("continuous-tiles"), CONTINUOUS);
  buildTiles($("addon-tiles"), ADDON);
  renderVerdict(null);
  bootstrap();
})();
