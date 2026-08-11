const fmt = new Intl.NumberFormat("en-US");
const pct = (x) => `${Math.round(x * 100)}%`;

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

// ── Shared hover tooltip, used by all three hand-rolled SVG charts ─────────
let tooltipEl = null;

function ensureTooltip() {
  if (!tooltipEl) {
    tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    document.body.appendChild(tooltipEl);
  }
  return tooltipEl;
}

function moveTooltip(evt) {
  const tt = ensureTooltip();
  const pad = 14;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  const rect = tt.getBoundingClientRect();
  if (x + rect.width > window.innerWidth - 8) x = evt.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight - 8) y = evt.clientY - rect.height - pad;
  tt.style.left = `${x}px`;
  tt.style.top = `${y}px`;
}

function showTooltip(evt, html) {
  const tt = ensureTooltip();
  tt.innerHTML = html;
  tt.classList.add("visible");
  moveTooltip(evt);
}

function hideTooltip() {
  if (tooltipEl) tooltipEl.classList.remove("visible");
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
    const bar = svgEl("rect", {
      class: d.is_current ? "bar current" : "bar",
      x, y, width: barW, height: Math.max(h, 1), rx: 2,
    });
    const africaLine = d.africa_any
      ? `<div class="tt-row">${fmt.format(d.africa_any)} (${pct(d.africa_any_share)}) with an author at an African institution</div>`
      : "";
    const tip = `<div class="tt-title">${d.fy}${d.is_current ? " (in progress)" : ""}</div>` +
      `<div class="tt-row">${fmt.format(d.total)} papers</div>` + africaLine;
    bar.addEventListener("mouseenter", (e) => showTooltip(e, tip));
    bar.addEventListener("mousemove", moveTooltip);
    bar.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(bar);
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
  const point = (i, key) => [padL + i * step, padT + plotH * (1 - rows[i][key] / max)];

  [0, 0.25, 0.5, 0.75, 1].forEach((f) => {
    const y = padT + plotH * (1 - f);
    svg.appendChild(svgEl("line", { class: "gridline", x1: padL, x2: W - padR, y1: y, y2: y }));
    const t = svgEl("text", { class: "axis-label", x: 2, y: y + 4 });
    t.textContent = pct(max * f);
    svg.appendChild(t);
  });

  // The current FY is still in progress, so its segment is drawn faded and
  // dashed, matching how the flow chart lightens that FY's bar.
  const lastIdx = rows.length - 1;
  const currentIdx = lastIdx >= 0 && rows[lastIdx].is_current ? lastIdx : -1;
  const solidEnd = currentIdx === -1 ? lastIdx : currentIdx - 1;

  const pathFor = (key, fromI, toI) => {
    if (fromI < 0 || toI < 0 || fromI > toI) return "";
    let d = "";
    for (let i = fromI; i <= toI; i++) {
      const [x, y] = point(i, key);
      d += `${i === fromI ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)} `;
    }
    return d.trim();
  };

  [["africa_any_share", "line-any"], ["africa_first_share", "line-first"]].forEach(([key, cls]) => {
    if (solidEnd >= 0) {
      svg.appendChild(svgEl("path", { class: cls, d: pathFor(key, 0, solidEnd) }));
    }
    if (currentIdx > 0) {
      svg.appendChild(svgEl("path", { class: `${cls} line-current`, d: pathFor(key, currentIdx - 1, currentIdx) }));
    }
  });

  const seriesLabel = {
    africa_any_share: "Any author at an African institution",
    africa_first_share: "First author at an African institution",
  };

  rows.forEach((d, i) => {
    const isCurrent = i === currentIdx;
    let x;
    ["africa_any_share", "africa_first_share"].forEach((key) => {
      const [px, py] = point(i, key);
      x = px;
      const dot = svgEl("circle", {
        class: (key === "africa_any_share" ? "dot-any" : "dot-first") + (isCurrent ? " dot-current" : ""),
        cx: px, cy: py, r: 2.6,
      });
      // an invisible, generously-sized circle on top gives a comfortable hover
      // target without making the visible dot itself distractingly large
      const hit = svgEl("circle", { class: "dot-hit", cx: px, cy: py, r: 9 });
      const tip = `<div class="tt-title">${d.fy}${isCurrent ? " (in progress)" : ""}</div>` +
        `<div class="tt-row">${seriesLabel[key]}: ${pct(d[key])}</div>`;
      hit.addEventListener("mouseenter", (e) => { dot.setAttribute("r", 5); showTooltip(e, tip); });
      hit.addEventListener("mousemove", moveTooltip);
      hit.addEventListener("mouseleave", () => { dot.setAttribute("r", 2.6); hideTooltip(); });
      svg.appendChild(dot);
      svg.appendChild(hit);
    });
    if (i % 3 === 0 || rows.length <= 10 || isCurrent) {
      const xt = svgEl("text", { class: "axis-label", x, y: H - padB + 16, "text-anchor": "middle" });
      xt.textContent = d.fy;
      svg.appendChild(xt);
    }
  });

  container.appendChild(svg);
}

const TIER_COLORS = ["#1F3864", "#2E75B6", "#5B9BD5", "#9DC3E6", "#DEEBF7"];

// Wider than TIER_COLORS since publication_type (OpenAlex's own category,
// unlike our small fixed set of journal tiers) can run to a dozen-plus
// distinct values; ordered so the biggest slice gets the most saturated color.
const PUBTYPE_COLORS = [
  "#1F5C99", "#009FDA", "#0091B4", "#008980", "#4455A0", "#E65100",
  "#004370", "#5B9BD5", "#9DC3E6", "#7A8CC4", "#6FBFB0", "#F2A354",
  "#8FAFC9", "#B7C4D6",
];

function renderTierPie(container, tiers, colors = TIER_COLORS) {
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
    const slice = svgEl("path", { d, fill: colors[i % colors.length], class: "pie-slice" });

    // pull the wedge outward along its own mid-angle on hover, rather than a fixed
    // direction, so every slice - whatever its position on the circle - moves away
    // from the center convincingly instead of just sliding sideways
    const mid = (angle + next) / 2;
    const dx = Math.cos(mid) * 12, dy = Math.sin(mid) * 12;
    const tip = `<div class="tt-title">${t.label}</div>` +
      `<div class="tt-row">${fmt.format(t.count)} papers (${pct(t.count / total)})</div>`;
    slice.addEventListener("mouseenter", (e) => {
      slice.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
      showTooltip(e, tip);
    });
    slice.addEventListener("mousemove", moveTooltip);
    slice.addEventListener("mouseleave", () => {
      slice.style.transform = "";
      hideTooltip();
    });
    svg.appendChild(slice);
    angle = next;
  });

  const legend = document.createElement("div");
  legend.className = "legend";
  legend.style.flexDirection = "column";
  legend.style.gap = "5px";
  legend.style.marginTop = "10px";
  tiers.forEach((t, i) => {
    const row = document.createElement("div");
    row.innerHTML = `<span class="swatch" style="background:${colors[i % colors.length]}"></span>${t.label}: ${fmt.format(t.count)} (${pct(t.count / total)})`;
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
  document.getElementById("stat-total-sub").textContent =
    `Papers confirmed to use data from LSMS-supported longitudinal in-person and phone surveys since 2008 (under LSMS-ISA, LSMS-HFPS, and other on-going initiatives)`;
  document.getElementById("stat-flow").textContent = fmt.format(m.most_recent_completed_fy_count);
  document.getElementById("stat-flow-sub").textContent = `New papers in ${m.most_recent_completed_fy} (World Bank fiscal year)`;
  document.getElementById("stat-share").textContent = pct(m.geography.any_author_africa_recent_fy.share);
  document.getElementById("stat-share-sub").textContent =
    `${fmt.format(m.geography.any_author_africa_recent_fy.count)} of ${fmt.format(m.most_recent_completed_fy_count)} ${m.most_recent_completed_fy} papers had an author affiliated with an African institution`;
}

function renderGates(m) {
  const g1 = document.getElementById("gate1-grid");
  g1.appendChild(gateCard(m.gate1.tier_a.count, pct(m.gate1.tier_a.share), "Exact match: the survey's full name leaves no doubt, for example “Uganda National Panel Survey”"));
  g1.appendChild(gateCard(m.gate1.tier_b.count, pct(m.gate1.tier_b.share), "Generic name plus country: a common survey name confirmed by the country's name appearing nearby"));
  g1.appendChild(gateCard(m.gate1.tier_c.count, pct(m.gate1.tier_c.share), "Short acronym plus country: an acronym such as “LSMS” confirmed by the country's name appearing nearby"));

  const g2 = document.getElementById("gate2-grid");
  g2.appendChild(gateCard(m.gate2.well_backed.count, pct(m.gate2.well_backed.share), "Strong evidence: clear confirmation on both questions above"));
  g2.appendChild(gateCard(m.gate2.borderline.count, pct(m.gate2.borderline.share), "Minimum confirmation: the paper just cleared both questions"));
  g2.appendChild(gateCard(m.gate2.strong_use.count, pct(m.gate2.strong_use.share), "Detailed evidence of data use: the paper describes its methods using the data, or cites the official dataset"));

  const totalsEl = document.getElementById("totals-summary");
  const rows = [
    ["Total confirmed papers", fmt.format(m.total_papers)],
    ["Peer-reviewed journal articles", `${fmt.format(m.peer_reviewed.count)} (${pct(m.peer_reviewed.share)})`],
    ["Open access", `${fmt.format(m.open_access.count)} (${pct(m.open_access.share)})`],
    ["World Bank–affiliated papers", `${fmt.format(m.wb_affiliated.count)} (${pct(m.wb_affiliated.share)})`],
    ["Other multilateral organization–affiliated papers", `${fmt.format(m.multilateral.count)} (${pct(m.multilateral.share)})`],
  ];
  totalsEl.innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}

function renderGeography(m) {
  const grid = document.getElementById("geo-grid");
  const g = m.geography;
  grid.appendChild(gateCard(g.any_author_africa.count, pct(g.any_author_africa.share), "At least one author based at an African institution"));
  grid.appendChild(gateCard(g.first_author_africa.count, pct(g.first_author_africa.share), "Lead author based at an African institution"));
  grid.appendChild(gateCard(g.all_authors_ssa.count, pct(g.all_authors_ssa.share), "Every author based at a Sub-Saharan African institution"));
  grid.appendChild(gateCard(g.unclassified.count, pct(g.unclassified.share), "Author location unknown (no institution data available)"));
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
    const link = p.doi || p.link || p.oa_url || "";
    const titleHtml = link
      ? `<a href="${escapeAttr(link)}" target="_blank" rel="noopener">${escapeHtml(p.title || "Untitled")}</a>`
      : escapeHtml(p.title || "Untitled");
    const africa = [
      p.is_any_author_africa ? '<span class="badge yes">Africa (any)</span>' : "",
      p.is_first_author_africa ? '<span class="badge yes">Africa (1st)</span>' : "",
    ].filter(Boolean).join(" ") || '<span class="badge no">n/a</span>';
    return `<tr>
      <td class="title-cell">
        ${titleHtml}
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
  renderTierPie(document.getElementById("pubtype-pie"), data.metrics.publication_types, PUBTYPE_COLORS);
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
