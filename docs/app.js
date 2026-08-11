const fmt = new Intl.NumberFormat("en-US");
const pct = (x) => `${Math.round(x * 100)}%`;

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

function renderFlowChart(container, flow) {
  const W = 620, H = 320, padL = 44, padR = 12, padT = 16, padB = 34;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const max = Math.max(...flow.map((d) => d.total)) * 1.15;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });
  const step = plotW / flow.length;
  const barW = step * 0.62;

  [0, 0.25, 0.5, 0.75, 1].forEach((f) => {
    const y = padT + plotH * (1 - f);
    svg.appendChild(svgEl("line", {
      class: "gridline", x1: padL, x2: W - padR, y1: y, y2: y,
    }));
    const t = svgEl("text", { class: "axis-label", x: 4, y: y + 4 });
    t.textContent = fmt.format(Math.round(max * f));
    svg.appendChild(t);
  });

  flow.forEach((d, i) => {
    const x = padL + i * step + (step - barW) / 2;
    const h = (d.total / max) * plotH;
    const y = padT + plotH - h;
    svg.appendChild(svgEl("rect", {
      class: d.is_current ? "bar current" : "bar",
      x, y, width: barW, height: Math.max(h, 1), rx: 2,
    }));
    const lbl = svgEl("text", {
      class: "bar-label", x: x + barW / 2, y: y - 5, "text-anchor": "middle",
    });
    lbl.textContent = fmt.format(d.total);
    svg.appendChild(lbl);
    if (i % 2 === 0 || flow.length <= 12) {
      const xt = svgEl("text", {
        class: "axis-label", x: x + barW / 2, y: H - padB + 16, "text-anchor": "middle",
      });
      xt.textContent = d.fy;
      svg.appendChild(xt);
    }
  });

  container.appendChild(svg);
}

function renderShareChart(container, flow) {
  const W = 460, H = 320, padL = 40, padR = 12, padT = 16, padB = 34;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const rows = flow.filter((d) => d.total >= 5);
  const max = Math.max(0.5, Math.max(...rows.map((d) => Math.max(d.africa_any_share, d.africa_first_share))) * 1.2);

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });
  const step = plotW / (rows.length - 1 || 1);

  [0, 0.25, 0.5, 0.75, 1].forEach((f) => {
    const y = padT + plotH * (1 - f);
    svg.appendChild(svgEl("line", { class: "gridline", x1: padL, x2: W - padR, y1: y, y2: y }));
    const t = svgEl("text", { class: "axis-label", x: 2, y: y + 4 });
    t.textContent = pct(max * f);
    svg.appendChild(t);
  });

  const pathFor = (key) => rows.map((d, i) => {
    const x = padL + i * step;
    const y = padT + plotH * (1 - d[key] / max);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  svg.appendChild(svgEl("path", { class: "line-any", d: pathFor("africa_any_share") }));
  svg.appendChild(svgEl("path", { class: "line-first", d: pathFor("africa_first_share") }));

  rows.forEach((d, i) => {
    const x = padL + i * step;
    ["africa_any_share", "africa_first_share"].forEach((key) => {
      const y = padT + plotH * (1 - d[key] / max);
      svg.appendChild(svgEl("circle", {
        class: key === "africa_any_share" ? "dot-any" : "dot-first",
        cx: x, cy: y, r: 2.6,
      }));
    });
    if (i % 3 === 0 || rows.length <= 10) {
      const xt = svgEl("text", { class: "axis-label", x, y: H - padB + 16, "text-anchor": "middle" });
      xt.textContent = d.fy;
      svg.appendChild(xt);
    }
  });

  container.appendChild(svg);
}

function renderTierPie(container, tiers) {
  const colors = ["#1F3864", "#2E75B6", "#5B9BD5", "#9DC3E6", "#DEEBF7"];
  const total = tiers.reduce((s, t) => s + t.count, 0) || 1;
  const cx = 130, cy = 130, r = 110;
  const svg = svgEl("svg", { viewBox: "0 0 260 260" });

  let angle = -Math.PI / 2;
  tiers.forEach((t, i) => {
    const frac = t.count / total;
    const next = angle + frac * 2 * Math.PI;
    const x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle);
    const x2 = cx + r * Math.cos(next), y2 = cy + r * Math.sin(next);
    const large = frac > 0.5 ? 1 : 0;
    const d = frac >= 0.9995
      ? `M ${cx - r},${cy} A ${r},${r} 0 1 1 ${cx + r},${cy} A ${r},${r} 0 1 1 ${cx - r},${cy} Z`
      : `M ${cx},${cy} L ${x1.toFixed(1)},${y1.toFixed(1)} A ${r},${r} 0 ${large} 1 ${x2.toFixed(1)},${y2.toFixed(1)} Z`;
    svg.appendChild(svgEl("path", { d, fill: colors[i % colors.length] }));
    angle = next;
  });

  const legend = document.createElement("div");
  legend.className = "legend";
  legend.style.flexDirection = "column";
  legend.style.gap = "5px";
  legend.style.marginTop = "10px";
  tiers.forEach((t, i) => {
    const row = document.createElement("div");
    row.innerHTML = `<span class="swatch" style="background:${colors[i % colors.length]}"></span>${t.label} — ${fmt.format(t.count)} (${pct(t.count / total)})`;
    legend.appendChild(row);
  });

  container.appendChild(svg);
  container.appendChild(legend);
}

function gateCard(n, sharePct, desc) {
  const div = document.createElement("div");
  div.className = "gate-card";
  div.innerHTML = `<span class="n">${fmt.format(n)}</span>${sharePct !== null ? `<span class="pct">${sharePct}</span>` : ""}<div class="desc">${desc}</div>`;
  return div;
}

function renderHero(m) {
  document.getElementById("stat-total").textContent = fmt.format(m.total_papers);
  document.getElementById("stat-flow").textContent = fmt.format(m.most_recent_completed_fy_count);
  document.getElementById("stat-flow-sub").textContent = `New papers in ${m.most_recent_completed_fy} (WBG fiscal year)`;
  document.getElementById("stat-share").textContent = pct(m.geography.any_author_africa_recent_fy.share);
  document.getElementById("stat-share-sub").textContent =
    `${fmt.format(m.geography.any_author_africa_recent_fy.count)} of ${fmt.format(m.most_recent_completed_fy_count)} ${m.most_recent_completed_fy} papers had an African-affiliated author`;
}

function renderGates(m) {
  const g1 = document.getElementById("gate1-grid");
  g1.appendChild(gateCard(m.gate1.tier_a.count, pct(m.gate1.tier_a.share), "Tier A — unambiguous survey name (e.g. “Uganda National Panel Survey”)"));
  g1.appendChild(gateCard(m.gate1.tier_b.count, pct(m.gate1.tier_b.share), "Tier B — generic survey name + country context"));
  g1.appendChild(gateCard(m.gate1.tier_c.count, pct(m.gate1.tier_c.share), "Tier C — short acronym + country context + case check"));

  const g2 = document.getElementById("gate2-grid");
  g2.appendChild(gateCard(m.gate2.well_backed.count, pct(m.gate2.well_backed.share), "Well-backed — identity and use evidence beyond the minimum"));
  g2.appendChild(gateCard(m.gate2.borderline.count, pct(m.gate2.borderline.share), "Borderline — both axes exactly at the minimum threshold"));
  g2.appendChild(gateCard(m.gate2.strong_use.count, pct(m.gate2.strong_use.share), "Strong data-use evidence — methods language or microdata citation"));

  const totalsEl = document.getElementById("totals-summary");
  const rows = [
    ["Total papers retained", fmt.format(m.total_papers)],
    ["Peer-reviewed journal articles", `${fmt.format(m.peer_reviewed.count)} (${pct(m.peer_reviewed.share)})`],
    ["World Bank–affiliated papers", `${fmt.format(m.wb_affiliated.count)} (${pct(m.wb_affiliated.share)})`],
    ["Multilateral org–affiliated", `${fmt.format(m.multilateral.count)} (${pct(m.multilateral.share)})`],
  ];
  if (m.total_retrieved !== null) {
    rows.push(["Total retrieved before exclusion", fmt.format(m.total_retrieved)]);
    rows.push(["Excluded — mentions survey, no evidence of use", fmt.format(m.excluded_no_use)]);
    rows.push(["Excluded — not confidently our survey", fmt.format(m.excluded_no_identity)]);
    rows.push(["Excluded — publication type can't be empirical use", fmt.format(m.excluded_vetoed)]);
  }
  totalsEl.innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}

function renderGeography(m) {
  const grid = document.getElementById("geo-grid");
  const g = m.geography;
  grid.appendChild(gateCard(g.any_author_africa.count, pct(g.any_author_africa.share), "Any author at an African institution"));
  grid.appendChild(gateCard(g.first_author_africa.count, pct(g.first_author_africa.share), "First author at an African institution"));
  grid.appendChild(gateCard(g.all_authors_ssa.count, pct(g.all_authors_ssa.share), "All authors at a Sub-Saharan African institution"));
  grid.appendChild(gateCard(g.unclassified.count, pct(g.unclassified.share), "Geography unclassified (no OpenAlex institution data)"));
}

// ── Papers table ──────────────────────────────────────────────────────

let PAPERS = [];
let filtered = [];
let page = 0;
const PAGE_SIZE = 50;

function populateFilterOptions() {
  const fySel = document.getElementById("filter-fy");
  const fys = [...new Set(PAPERS.map((p) => p.fy).filter(Boolean))]
    .sort((a, b) => b.localeCompare(a));
  fys.forEach((fy) => {
    const opt = document.createElement("option");
    opt.value = fy;
    opt.textContent = fy;
    fySel.appendChild(opt);
  });
}

function applyFilters() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const fy = document.getElementById("filter-fy").value;
  const geo = document.getElementById("filter-geo").value;
  const peer = document.getElementById("filter-peer").value;

  filtered = PAPERS.filter((p) => {
    if (fy && p.fy !== fy) return false;
    if (geo === "any" && !p.is_any_author_africa) return false;
    if (geo === "first" && !p.is_first_author_africa) return false;
    if (peer === "yes" && p.peer_reviewed_auto !== "Yes") return false;
    if (q) {
      const hay = `${p.title || ""} ${p.authors || ""} ${p.venue || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  page = 0;
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById("papers-body");
  const start = page * PAGE_SIZE;
  const rows = filtered.slice(start, start + PAGE_SIZE);
  tbody.innerHTML = rows.map((p) => {
    const link = p.link || p.doi || "#";
    const africa = [
      p.is_any_author_africa ? '<span class="badge yes">Africa (any)</span>' : "",
      p.is_first_author_africa ? '<span class="badge yes">Africa (1st)</span>' : "",
    ].filter(Boolean).join(" ") || '<span class="badge no">—</span>';
    return `<tr>
      <td class="title-cell">
        <a href="${escapeAttr(link)}" target="_blank" rel="noopener">${escapeHtml(p.title || "Untitled")}</a>
        <span class="venue">${escapeHtml(p.venue || "")}</span>
      </td>
      <td>${escapeHtml(truncateAuthors(p.authors))}</td>
      <td>${p.fy || ""}</td>
      <td>${escapeHtml(p.journal_tier || "")}</td>
      <td>${p.peer_reviewed_auto === "Yes" ? '<span class="badge yes">Yes</span>' : '<span class="badge no">No</span>'}</td>
      <td>${escapeHtml(p.geography_clean || "")}</td>
      <td>${africa}</td>
    </tr>`;
  }).join("");

  document.getElementById("table-count").textContent =
    `${fmt.format(filtered.length)} paper${filtered.length === 1 ? "" : "s"} matched`;

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  document.getElementById("page-info").textContent = `Page ${page + 1} of ${totalPages}`;
  document.getElementById("prev-page").disabled = page === 0;
  document.getElementById("next-page").disabled = page >= totalPages - 1;
}

function truncateAuthors(a) {
  if (!a) return "";
  return a.length > 60 ? a.slice(0, 57) + "..." : a;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

async function main() {
  const [data, papers] = await Promise.all([
    fetch("data.json").then((r) => r.json()),
    fetch("papers.json").then((r) => r.json()),
  ]);

  document.getElementById("generated-at").textContent =
    new Date(data.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  document.getElementById("source-file").textContent = data.source_file;

  renderHero(data.metrics);
  renderFlowChart(document.getElementById("flow-chart"), data.flow);
  renderShareChart(document.getElementById("share-chart"), data.flow);
  renderTierPie(document.getElementById("tier-pie"), data.metrics.journal_tiers);
  renderGates(data.metrics);
  renderGeography(data.metrics);

  PAPERS = papers;
  filtered = papers;
  populateFilterOptions();
  renderTable();

  document.getElementById("search").addEventListener("input", applyFilters);
  document.getElementById("filter-fy").addEventListener("change", applyFilters);
  document.getElementById("filter-geo").addEventListener("change", applyFilters);
  document.getElementById("filter-peer").addEventListener("change", applyFilters);
  document.getElementById("prev-page").addEventListener("click", () => { if (page > 0) { page--; renderTable(); } });
  document.getElementById("next-page").addEventListener("click", () => {
    if ((page + 1) * PAGE_SIZE < filtered.length) { page++; renderTable(); }
  });
}

main().catch((err) => {
  document.getElementById("load-error").style.display = "block";
  document.getElementById("load-error").textContent =
    "Couldn't load the dashboard data (data.json / papers.json). " + err;
  console.error(err);
});
