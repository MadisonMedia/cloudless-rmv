/* Cloudless RMV card – unofficial; data: RMV Open Data. */
const CARD_VERSION = "0.1.0";

const T = {
  de: {
    none: "Keine Abfahrten im Zeitfenster", updated: "aktualisiert vor", sec: "s", min: "Min.",
    now: "jetzt", cancelled: "Ausfall", partCancelled: "Teilausfall", platform: "Gl.",
    served: "wird angefahren", notServed: "wird NICHT angefahren", unknown: "unbekannt",
    some: "von", trips: "Fahrten", onward: "Weiter", running: "fährt", noService: "KEINE Fahrt",
    disrupted: "gestört", noData: "keine Daten", messages: "Meldungen", until: "bis",
    budget_hour: "Stundenlimit der Anfragen erreicht – Anzeige evtl. veraltet",
    budget_day: "Tageslimit der Anfragen erreicht – Anzeige evtl. veraltet",
    quota: "RMV-Limit erreicht – Anzeige evtl. veraltet",
    connection: "RMV nicht erreichbar – Anzeige evtl. veraltet",
    other: "Fehler beim Aktualisieren – Anzeige evtl. veraltet",
    tap: "Tippen zum Aktualisieren", entity: "Entität", title: "Titel",
    refresh: "Aktualisierung alle (Sekunden, 0 = aus)", stations: "Haltestellen-Prüfung zeigen",
    connections: "Weiterfahrt zeigen", msgs: "Meldungen zeigen", rowst: "Haltestellen pro Fahrt zeigen",
    err_entity: "Bitte eine Entität „Nächste Abfahrt“ von Cloudless RMV wählen.",
    attribution: "Daten: RMV",
  },
  en: {
    none: "No departures in the time window", updated: "updated", sec: "s ago", min: "min",
    now: "now", cancelled: "Cancelled", partCancelled: "Part cancelled", platform: "Pl.",
    served: "served", notServed: "NOT served", unknown: "unknown",
    some: "of", trips: "trips", onward: "Onward", running: "running", noService: "NO service",
    disrupted: "disrupted", noData: "no data", messages: "Messages", until: "until",
    budget_hour: "Hourly request limit reached – display may be stale",
    budget_day: "Daily request limit reached – display may be stale",
    quota: "RMV limit reached – display may be stale",
    connection: "RMV not reachable – display may be stale",
    other: "Update failed – display may be stale",
    tap: "Tap to refresh", entity: "Entity", title: "Title",
    refresh: "Refresh every (seconds, 0 = off)", stations: "Show stop check",
    connections: "Show onward connection", msgs: "Show messages", rowst: "Show stops per trip",
    err_entity: "Please choose a Cloudless RMV “Next departure” entity.",
    attribution: "Data: RMV",
  },
};

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeColor = (c, d) => (/^#[0-9a-fA-F]{3,8}$/.test(c || "") ? c : d);
const hhmm = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

class CloudlessRmvCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) throw new Error("entity required");
    this._config = {
      refresh_seconds: 120, show_stations: true, show_connections: true,
      show_messages: true, show_row_stations: true, ...config,
    };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._started = false;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 6; }
  static getConfigElement() { return document.createElement("cloudless-rmv-card-editor"); }
  static getStubConfig(hass) {
    const e = Object.keys(hass.states).find((k) => hass.states[k].attributes?.stop && hass.states[k].attributes?.departures);
    return { entity: e || "", title: "" };
  }

  get _t() { return T[(this._hass?.language || "de").startsWith("de") ? "de" : "en"]; }

  connectedCallback() {
    this._visible = document.visibilityState === "visible";
    this._onVis = () => { this._visible = document.visibilityState === "visible"; this._sync(true); };
    document.addEventListener("visibilitychange", this._onVis);
    if ("IntersectionObserver" in window) {
      this._io = new IntersectionObserver((es) => { this._inView = es.some((e) => e.isIntersecting); this._sync(true); });
      this._io.observe(this);
    } else this._inView = true;
    this._tick = setInterval(() => this._updateAge(), 1000);
    this._sync(true);
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVis);
    this._io?.disconnect();
    clearInterval(this._tick);
    clearInterval(this._timer);
    this._timer = null;
  }

  /* Poll only while this card is actually on screen. */
  _sync(immediate) {
    const active = this._visible && this._inView !== false && this.isConnected;
    const secs = Number(this._config?.refresh_seconds ?? 120);
    if (active && secs > 0) {
      if (!this._timer) this._timer = setInterval(() => this._refresh(), secs * 1000);
      if (immediate && this._isStale(secs)) this._refresh();
    } else if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  _isStale(secs) {
    const f = this._state?.attributes?.fetched_at;
    return !f || (Date.now() - new Date(f).getTime()) / 1000 > Math.min(secs, 60);
  }

  _refresh() {
    if (!this._hass || !this._config?.entity) return;
    this._hass.callService("homeassistant", "update_entity", { entity_id: this._config.entity }).catch(() => {});
  }

  _updateAge() {
    const el = this.shadowRoot?.querySelector(".age");
    const f = this._state?.attributes?.fetched_at;
    if (!el || !f) return;
    const s = Math.max(0, Math.round((Date.now() - new Date(f).getTime()) / 1000));
    el.textContent = `${this._t.updated} ${s} ${this._t.sec}`;
    // Rows and countdowns depend on the clock: re-render once per minute.
    const m = Math.floor(Date.now() / 60000);
    if (m !== this._lastMinute) { this._lastMinute = m; this._render(); }
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const t = this._t;
    const st = this._hass?.states?.[this._config.entity];
    this._state = st;
    if (!this._started && this._hass) { this._started = true; this._sync(true); }
    const root = this.shadowRoot;
    if (!st) {
      root.innerHTML = `${this._style()}<ha-card><div class="pad">${esc(this._config.entity)}: ${esc(t.noData)}</div></ha-card>`;
      return;
    }
    const a = st.attributes;
    const now = Date.now();
    const walk = (a.walk_min || 0) * 60000;
    const rows = (a.departures || [])
      .filter((d) => d.eff && new Date(d.eff).getTime() >= now + walk)
      .slice(0, a.max_rows || 6);
    const title = this._config.title || a.stop?.short || a.stop?.name || "RMV";
    const msgById = Object.fromEntries((a.messages || []).map((m) => [m.id, m]));

    let html = `${this._style()}<ha-card><div class="head"><div class="title">${esc(title)}</div>
      <div class="age" title="${esc(t.tap)}"></div></div>`;

    if (a.error) html += `<div class="banner">${esc(t[a.error] || (a.error.startsWith("budget_") ? t[a.error] : t.other) || t.other)}</div>`;

    if (this._config.show_stations && (a.stations || []).length) {
      html += `<div class="chips">` + a.stations.map((s) => {
        const cls = s.state === "ok" ? "ok" : s.state === "none" ? "bad" : "unk";
        const icon = s.state === "ok" ? "✓" : s.state === "none" ? "✗" : "?";
        const sub = s.state === "unknown" ? t.unknown : s.state === "none" ? t.notServed : `${s.served} ${t.some} ${s.total} ${t.trips}`;
        const nxt = s.next?.arr ? ` · ${hhmm(s.next.arr)}${s.next.arr_delay > 0 ? ` (+${s.next.arr_delay})` : ""}` : "";
        return `<div class="chip ${cls}"><b>${icon} ${esc(s.short)}</b><span>${esc(sub)}${esc(nxt)}</span></div>`;
      }).join("") + `</div>`;
    }

    if (this._config.show_connections && (a.connections || []).length) {
      html += `<div class="chips">` + a.connections.map((c) => {
        const cls = c.status === "ok" ? "ok" : c.status === "unknown" ? "unk" : "bad";
        const label = c.status === "ok" ? `${t.running}${c.lines?.length ? " · " + c.lines.join(", ") : ""}`
          : c.status === "disrupted" ? t.disrupted : c.status === "none" ? t.noService : t.unknown;
        return `<div class="chip ${cls}"><b>🚋 ${esc(c.transfer_short)} → ${esc(c.target_short)}</b><span>${esc(label)}${c.cancelled ? ` · ${c.cancelled} ${esc(t.cancelled)}` : ""}</span></div>`;
      }).join("") + `</div>`;
    }

    if (!rows.length) html += `<div class="pad muted">${esc(t.none)}</div>`;
    for (const d of rows) {
      const mins = Math.max(0, Math.round((new Date(d.eff).getTime() - now) / 60000));
      const cls = d.cancelled ? "cx" : d.delay >= 5 ? "late" : d.delay > 0 ? "slight" : "";
      const badge = d.cancelled ? `<span class="b bad">${esc(t.cancelled)}</span>`
        : d.part_cancelled ? `<span class="b warn">${esc(t.partCancelled)}</span>`
        : d.delay > 0 ? `<span class="b ${d.delay >= 5 ? "bad" : "warn"}">+${d.delay}</span>` : "";
      const stops = this._config.show_row_stations && d.stations
        ? Object.entries(d.stations).map(([id, r]) => {
            const s = (a.stations || []).find((x) => x.id === id);
            if (!s) return "";
            const ok = r.state === "served";
            return `<span class="s ${ok ? "ok" : r.state === "unknown" ? "unk" : "bad"}">${ok ? "✓" : r.state === "unknown" ? "?" : "✗"} ${esc(s.short)}</span>`;
          }).join("") : "";
      const hasMsg = (d.messages || []).some((id) => msgById[id]?.kind === "disruption");
      html += `<div class="row ${cls}">
        <span class="line" style="background:${safeColor(d.color, "#666")};color:${safeColor(d.fg, "#fff")}">${esc(d.line)}</span>
        <div class="mid"><div class="dir">${esc(d.direction)}${hasMsg ? " ⚠️" : ""}</div>
          <div class="sub">${d.platform ? `${esc(t.platform)} ${esc(d.platform)}${d.platform_changed ? " ⚠️" : ""}` : ""}<span class="stops">${stops}</span></div></div>
        <div class="time"><div class="t1">${d.delay > 0 && !d.cancelled ? `<s>${hhmm(d.planned)}</s> ` : ""}<b>${hhmm(d.cancelled ? d.planned : d.eff)}</b></div>
          <div class="t2">${badge}${d.cancelled ? "" : ` ${mins === 0 ? esc(t.now) : mins + " " + esc(t.min)}`}</div></div>
      </div>`;
    }

    if (this._config.show_messages && (a.messages || []).length) {
      html += `<details class="msgs"${a.messages.some((m) => m.kind === "disruption") ? " open" : ""}><summary>${esc(t.messages)} (${a.messages.length})</summary>` +
        a.messages.map((m) => `<div class="msg ${esc(m.kind)}"><b>${esc(m.head || m.lead)}</b> <small>${esc((m.lines || []).join(", "))}${m.until_text ? " · " + esc(m.until_text) : ""}</small><div>${esc(m.text || m.lead)}</div></div>`).join("") +
        `</details>`;
    }
    html += `<div class="foot"><img class="logo" src="/cloudless_rmv/rmv-logo.png" alt="RMV" onerror="this.remove()">${esc(t.attribution)}</div></ha-card>`;
    root.innerHTML = html;
    root.querySelector("ha-card").addEventListener("click", (ev) => {
      if (ev.target.closest("details")) return;
      this._refresh();
    });
    this._updateAge();
  }

  _style() {
    return `<style>
      ha-card{cursor:pointer;overflow:hidden}
      .pad{padding:16px}.muted{color:var(--secondary-text-color)}
      .head{display:flex;justify-content:space-between;align-items:baseline;padding:12px 16px 4px}
      .title{font-size:1.2em;font-weight:600}.age{font-size:.8em;color:var(--secondary-text-color)}
      .banner{margin:4px 16px;padding:6px 10px;border-radius:8px;background:var(--warning-color,#f5a623);color:#000;font-size:.85em}
      .chips{display:flex;flex-wrap:wrap;gap:6px;padding:6px 16px}
      .chip{display:flex;flex-direction:column;border-radius:10px;padding:6px 10px;border:1px solid var(--divider-color);font-size:.85em}
      .chip span{color:var(--secondary-text-color);font-size:.9em}
      .chip.ok{border-color:var(--success-color,#2e9e4f)}.chip.bad{border-color:var(--error-color,#d33);background:color-mix(in srgb,var(--error-color,#d33) 14%,transparent)}
      .chip.unk{opacity:.75}
      .row{display:flex;align-items:center;gap:12px;padding:8px 16px;border-top:1px solid var(--divider-color)}
      .line{min-width:2.6em;text-align:center;font-weight:700;border-radius:8px;padding:6px 6px}
      .mid{flex:1;min-width:0}.dir{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .sub{font-size:.8em;color:var(--secondary-text-color);display:flex;gap:8px;flex-wrap:wrap}
      .stops{display:inline-flex;gap:6px}.s.ok{color:var(--success-color,#2e9e4f)}.s.bad{color:var(--error-color,#d33);font-weight:600}.s.unk{opacity:.7}
      .time{text-align:right;white-space:nowrap}.t1{font-size:1.15em}.t2{font-size:.85em;color:var(--secondary-text-color)}
      .b{border-radius:6px;padding:1px 6px;font-weight:700;color:#fff}.b.bad{background:var(--error-color,#d33)}.b.warn{background:#e08a00}
      .row.cx .dir,.row.cx .t1{text-decoration:line-through;opacity:.7}
      .row.late .t1 b{color:var(--error-color,#d33)}.row.slight .t1 b{color:#e08a00}
      .msgs{padding:8px 16px;border-top:1px solid var(--divider-color)}.msgs summary{cursor:pointer;font-weight:600}
      .msg{margin:8px 0;font-size:.85em}.msg.disruption{border-left:3px solid var(--error-color,#d33);padding-left:8px}
      .msg.construction{border-left:3px solid #e08a00;padding-left:8px}
      .logo{height:18px;vertical-align:middle;margin-right:6px}.foot{padding:4px 16px 10px;font-size:.7em;color:var(--secondary-text-color);text-align:right}
    </style>`;
  }
}

class CloudlessRmvCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._draw(); }
  set hass(h) { this._hass = h; if (this._form) this._form.hass = h; else this._draw(); }

  _draw() {
    if (!this._hass || !this._config) return;
    const t = T[(this._hass.language || "de").startsWith("de") ? "de" : "en"];
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        this._config = ev.detail.value;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { refresh_seconds: 120, show_stations: true, show_connections: true, show_messages: true, show_row_stations: true, ...this._config };
    this._form.computeLabel = (s) => t[{ entity: "entity", title: "title", refresh_seconds: "refresh", show_stations: "stations", show_connections: "connections", show_messages: "msgs", show_row_stations: "rowst" }[s.name]] || s.name;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { domain: "sensor", device_class: "timestamp", integration: "cloudless_rmv" } } },
      { name: "title", selector: { text: {} } },
      { name: "refresh_seconds", selector: { number: { min: 0, max: 900, step: 10, mode: "box" } } },
      { name: "show_stations", selector: { boolean: {} } },
      { name: "show_row_stations", selector: { boolean: {} } },
      { name: "show_connections", selector: { boolean: {} } },
      { name: "show_messages", selector: { boolean: {} } },
    ];
  }
}

customElements.define("cloudless-rmv-card", CloudlessRmvCard);
customElements.define("cloudless-rmv-card-editor", CloudlessRmvCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "cloudless-rmv-card",
  name: "Cloudless RMV",
  description: "RMV departures with delays, cancellations, stop checks and onward connections (unofficial).",
  preview: false,
});
console.info(`%c CLOUDLESS-RMV-CARD %c ${CARD_VERSION} `, "background:#1d6fb8;color:#fff", "");
