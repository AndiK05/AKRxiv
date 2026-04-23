const state = {
  papers: [],
  metadata: null,
  query: "",
  sort: "score",
  activeBuckets: new Set(["recommended", "maybe"]),
  expanded: new Set(),
};

const bucketLabels = {
  recommended: "Recommended",
  maybe: "Maybe",
  ignore: "Ignore",
};

document.addEventListener("DOMContentLoaded", () => {
  wireControls();
  loadData();
});

async function loadData() {
  const resultsEl = document.getElementById("results");
  resultsEl.innerHTML = renderNotice("Loading papers...");

  try {
    const [papers, metadata] = await Promise.all([
      fetchJson("./data/papers.json"),
      fetchJson("./data/metadata.json").catch(() => null),
    ]);
    state.papers = Array.isArray(papers) ? papers : [];
    state.metadata = metadata;
    render();
  } catch (error) {
    resultsEl.innerHTML = renderNotice(
      `The site data could not be loaded. ${escapeHtml(String(error))}`,
    );
  }
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function wireControls() {
  document.getElementById("search-input").addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    render();
  });

  document.getElementById("sort-select").addEventListener("change", (event) => {
    state.sort = event.target.value;
    render();
  });

  document.getElementById("bucket-bar").addEventListener("click", (event) => {
    const button = event.target.closest("[data-bucket]");
    if (!button) {
      return;
    }

    const { bucket } = button.dataset;
    if (state.activeBuckets.has(bucket)) {
      state.activeBuckets.delete(bucket);
    } else {
      state.activeBuckets.add(bucket);
    }
    syncBucketButtons();
    render();
  });

  document.getElementById("results").addEventListener("click", (event) => {
    const button = event.target.closest("[data-toggle-abstract]");
    if (!button) {
      return;
    }

    const paperId = button.dataset.toggleAbstract;
    if (state.expanded.has(paperId)) {
      state.expanded.delete(paperId);
    } else {
      state.expanded.add(paperId);
    }
    render();
  });
}

function syncBucketButtons() {
  document.querySelectorAll("[data-bucket]").forEach((button) => {
    const active = state.activeBuckets.has(button.dataset.bucket);
    button.classList.toggle("is-active", active);
  });
}

function render() {
  renderHero();
  renderFooter();

  const resultsEl = document.getElementById("results");
  const visiblePapers = sortPapers(filterPapers());

  if (!visiblePapers.length) {
    resultsEl.innerHTML = renderNotice(
      "No papers match the current filters yet. Try enabling another bucket or clearing the search.",
    );
    return;
  }

  resultsEl.innerHTML = visiblePapers.map((paper) => renderCard(paper)).join("");
}

function renderHero() {
  const heroStats = document.getElementById("hero-stats");
  const counts = state.metadata?.counts || {};
  const pills = [
    statPill("Papers", state.papers.length),
    statPill("Recommended", counts.recommended ?? countBucket("recommended")),
    statPill("Maybe", counts.maybe ?? countBucket("maybe")),
    statPill("Ignore", counts.ignored ?? countBucket("ignore")),
  ];
  heroStats.innerHTML = pills.join("");
}

function renderFooter() {
  const generatedAtEl = document.getElementById("generated-at");
  const generatedAt = state.metadata?.generated_at;
  generatedAtEl.textContent = generatedAt
    ? `Last build: ${formatDate(generatedAt)}`
    : "Last build time unavailable";
}

function countBucket(bucket) {
  return state.papers.filter((paper) => paper.bucket === bucket).length;
}

function filterPapers() {
  return state.papers.filter((paper) => {
    if (!state.activeBuckets.has(paper.bucket)) {
      return false;
    }
    if (!state.query) {
      return true;
    }

    const haystack = [
      paper.title,
      paper.abstract,
      paper.short_reason,
      ...(paper.authors || []),
      ...(paper.categories || []),
      ...(paper.matched_topics || []),
    ]
      .join(" ")
      .toLowerCase();

    return haystack.includes(state.query);
  });
}

function sortPapers(papers) {
  const items = [...papers];
  switch (state.sort) {
    case "newest":
      return items.sort((a, b) => new Date(b.published) - new Date(a.published));
    case "oldest":
      return items.sort((a, b) => new Date(a.published) - new Date(b.published));
    case "title":
      return items.sort((a, b) => a.title.localeCompare(b.title));
    case "score":
    default:
      return items.sort((a, b) => {
        if (b.score !== a.score) {
          return b.score - a.score;
        }
        return new Date(b.published) - new Date(a.published);
      });
  }
}

function renderCard(paper) {
  const expanded = state.expanded.has(paper.paper_id);
  const tags = renderPills(paper.matched_topics || [], "tag");
  const categories = renderPills(paper.categories || [], "category");
  const concerns =
    paper.concerns && paper.concerns.length
      ? `<p class="concerns"><strong>Concerns:</strong> ${escapeHtml(paper.concerns.join("; "))}</p>`
      : "";

  return `
    <article class="paper-card bucket-${escapeHtml(paper.bucket)}">
      <div class="card-head">
        <div class="card-copy">
          <div class="card-topline">
            <span class="bucket-pill bucket-${escapeHtml(paper.bucket)}">${escapeHtml(bucketLabels[paper.bucket] || paper.bucket)}</span>
            <span class="score-pill">Score ${escapeHtml(String(paper.score))}</span>
            <span class="confidence-pill">Confidence ${escapeHtml(formatPercent(paper.confidence))}</span>
          </div>
          <h2 class="paper-title">${escapeHtml(paper.title)}</h2>
          <p class="paper-meta">${escapeHtml(formatAuthors(paper.authors || []))} • ${escapeHtml(formatDate(paper.published))}</p>
        </div>
        <div class="card-links">
          <a href="${escapeHtml(paper.link_abs)}" target="_blank" rel="noreferrer">Abstract</a>
          <a href="${escapeHtml(paper.link_pdf)}" target="_blank" rel="noreferrer">PDF</a>
        </div>
      </div>

      <p class="reason">${escapeHtml(paper.short_reason)}</p>
      <div class="pill-row">${tags}${categories}</div>
      ${concerns}

      <button class="abstract-toggle" type="button" data-toggle-abstract="${escapeHtml(paper.paper_id)}">
        ${expanded ? "Hide abstract" : "Show abstract"}
      </button>

      <div class="abstract ${expanded ? "is-visible" : ""}">
        <p>${escapeHtml(paper.abstract || "No abstract available.")}</p>
      </div>
    </article>
  `;
}

function renderPills(items, className) {
  if (!items.length) {
    return "";
  }
  return items
    .map((item) => `<span class="mini-pill ${className}">${escapeHtml(item)}</span>`)
    .join("");
}

function renderNotice(message) {
  return `<div class="notice-card"><p>${escapeHtml(message)}</p></div>`;
}

function statPill(label, value) {
  return `<span class="stat-pill"><strong>${escapeHtml(String(value))}</strong> ${escapeHtml(label)}</span>`;
}

function formatAuthors(authors) {
  if (!authors.length) {
    return "Authors unavailable";
  }
  if (authors.length <= 4) {
    return authors.join(", ");
  }
  return `${authors.slice(0, 4).join(", ")}, et al.`;
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown date";
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

