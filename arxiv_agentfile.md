# Agent File: LLM-curated arXiv Monitor

## Goal
Build a GitHub-hosted website that updates automatically, fetches recent arXiv papers, uses an LLM to decide which papers are relevant for the user, stores structured results, and publishes a static site.

This file is written for Codex or another coding agent to implement directly.

---

## Feasibility check

All required pieces are possible with current public tooling:

1. **Fetch candidate papers from arXiv** — possible via the arXiv API, which supports custom queries, Atom responses, paging with `start` and `max_results`, and sorting options. arXiv explicitly notes that you can generate your own custom feed from API queries. It also recommends a 3 second delay between repeated calls and advises refining queries larger than 1,000 results. citeturn673505view0turn585569view4
2. **Host a static website on GitHub** — possible with GitHub Pages. GitHub supports publishing from a branch or from a custom GitHub Actions workflow. citeturn673505view1turn673505view4
3. **Run scheduled updates automatically** — possible with GitHub Actions using scheduled workflows. GitHub workflow syntax explicitly supports time-based schedules. citeturn673505view3turn532089search9
4. **Use an LLM to decide relevance** — possible with the OpenAI Responses API. OpenAI supports Structured Outputs so responses can be forced into a JSON Schema, which is well suited to paper classification. citeturn673505view2turn275373search0turn275373search1
5. **Keep the implementation agentic if desired** — possible. The Responses API supports tools and function calling, but for this project the LLM should mainly act as a classifier/ranker over already-fetched paper metadata rather than free-form browsing. citeturn275373search0turn275373search1turn275373search6

### Important implementation constraint
Do **not** rely on “Pages from branch” if the papers JSON is updated by a GitHub Actions workflow using `GITHUB_TOKEN`. GitHub documents that commits pushed by a workflow using `GITHUB_TOKEN` do not trigger a GitHub Pages build. Use a **custom GitHub Actions Pages deployment workflow** instead. citeturn673505view4

### Practical conclusion
The whole system is feasible. The recommended architecture is:

- arXiv API for candidate retrieval
- local rule-based prefilter for cheap narrowing
- OpenAI LLM classification with Structured Outputs
- static site generation into a `dist/` folder
- GitHub Pages deployment via GitHub Actions

---

## Product definition

The system should:

- query arXiv for papers from selected categories and/or keywords
- consider only recent papers, default 2 to 3 days back
- prefilter candidates cheaply before sending anything to the LLM
- ask the LLM whether each paper is relevant for the user
- store the result as structured JSON
- publish a static website listing:
  - recommended papers
  - maybe papers
  - ignored papers hidden by default or stored separately
  - score, confidence, tags, and short reason
- update automatically once or twice per day

The system should **not**:

- expose API keys in the frontend
- call the LLM from browser JavaScript
- require a persistent backend server
- require a database for version 1

---

## Recommended repository structure

```text
arxiv-llm-monitor/
├─ README.md
├─ .gitignore
├─ requirements.txt
├─ config/
│  ├─ profile.yaml
│  ├─ sources.yaml
│  └─ schema.json
├─ src/
│  ├─ fetch_arxiv.py
│  ├─ prefilter.py
│  ├─ classify_papers.py
│  ├─ build_site.py
│  ├─ models.py
│  └─ utils.py
├─ data/
│  ├─ raw/
│  │  └─ latest_arxiv.xml
│  ├─ intermediate/
│  │  └─ candidates.json
│  └─ output/
│     ├─ papers.json
│     ├─ recommended.json
│     ├─ maybe.json
│     └─ ignored.json
├─ web/
│  ├─ index.html
│  ├─ app.js
│  ├─ styles.css
│  └─ assets/
├─ dist/
│  ├─ index.html
│  ├─ app.js
│  ├─ styles.css
│  └─ data/
│     ├─ papers.json
│     ├─ recommended.json
│     ├─ maybe.json
│     └─ ignored.json
└─ .github/
   └─ workflows/
      ├─ update-and-deploy.yml
      └─ validate.yml
```

### Why this structure

- `config/` keeps the user’s research taste and contracts separate from code.
- `src/` keeps the pipeline modular.
- `data/` keeps raw, intermediate, and final artifacts inspectable.
- `web/` contains the static site source.
- `dist/` is the deployable output uploaded to GitHub Pages.
- a single workflow can fetch, classify, build, and deploy in one run.

---

## Required configuration files

### 1. `config/profile.yaml`
This is the main “agent file” describing the user’s interests and decision policy.

```yaml
name: andi_arxiv_selector
owner: Andreas Kruckenhauser

model_policy:
  model: gpt-5.4-mini
  reasoning_effort: medium
  temperature: 0.2

paper_window:
  days_back: 3
  max_candidates_per_run: 120
  max_llm_candidates_per_run: 40

arxiv_sources:
  categories:
    - quant-ph
    - cond-mat.str-el
    - cond-mat.mes-hall
  keyword_queries:
    - 'all:"many-body"'
    - 'all:"variational dynamics"'
    - 'all:"quantum simulation"'
    - 'all:"error mitigation"'

prefilter:
  require_any:
    - many-body
    - dynamics
    - variational
    - Hamiltonian
    - simulation
    - quantum
  exclude_if_any:
    - review
    - survey
    - editorial
  boost_if_any:
    - trotter
    - pVQD
    - tensor network
    - resource estimate
    - fault tolerant

research_profile: |
  You are filtering arXiv papers for a researcher in quantum computing.

  Prioritize:
  - quantum algorithms
  - many-body simulation
  - variational quantum dynamics
  - simulation methods with rigorous or practically meaningful resource estimates
  - useful error mitigation when it materially improves an algorithm or simulation workflow
  - papers with concrete methods, bounds, experiments, or implementation detail

  Deprioritize:
  - generic surveys or reviews
  - hardware-only engineering papers without algorithmic insight
  - incremental benchmark papers with weak conceptual novelty
  - classical-only methods unless directly tied to quantum algorithms or quantum simulation

  Favor papers that are likely to be useful for research direction, implementation, or journal-club style triage.

classification_policy: |
  Judge relevance using only the provided metadata.
  Do not infer experimental results or claims not stated in the abstract.
  Be conservative about novelty claims.
  Prefer precise reasons over broad praise.

labels:
  buckets:
    - recommended
    - maybe
    - ignore
  tags:
    - variational dynamics
    - many-body simulation
    - quantum algorithms
    - error mitigation
    - resource estimates
    - Hamiltonian simulation
    - tensor networks
    - benchmarking
    - hardware-oriented

thresholds:
  recommended_min_score: 75
  maybe_min_score: 50
```

### 2. `config/schema.json`
Use Structured Outputs with a strict JSON schema.

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "paper_id": { "type": "string" },
    "title": { "type": "string" },
    "bucket": {
      "type": "string",
      "enum": ["recommended", "maybe", "ignore"]
    },
    "score": { "type": "integer", "minimum": 0, "maximum": 100 },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "short_reason": { "type": "string" },
    "matched_topics": {
      "type": "array",
      "items": { "type": "string" }
    },
    "concerns": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": [
    "paper_id",
    "title",
    "bucket",
    "score",
    "confidence",
    "short_reason",
    "matched_topics",
    "concerns"
  ]
}
```

### 3. `config/sources.yaml`
This separates query logic from preference logic.

```yaml
sort_by: submittedDate
sort_order: descending
page_size: 100
max_pages: 2
request_delay_seconds: 3

queries:
  - '(cat:quant-ph OR cat:cond-mat.str-el) AND (all:"many-body" OR all:"variational" OR all:"simulation")'
  - 'cat:quant-ph AND all:"error mitigation"'
  - 'cat:quant-ph AND all:"Hamiltonian simulation"'
```

---

## Data contracts

### Raw candidate paper shape

```json
{
  "paper_id": "2504.01234",
  "title": "...",
  "abstract": "...",
  "authors": ["..."],
  "categories": ["quant-ph"],
  "published": "2026-04-22T12:34:56Z",
  "updated": "2026-04-22T12:34:56Z",
  "link_abs": "https://arxiv.org/abs/2504.01234",
  "link_pdf": "https://arxiv.org/pdf/2504.01234",
  "comment": "optional"
}
```

### Final paper shape used by frontend

```json
{
  "paper_id": "2504.01234",
  "title": "...",
  "abstract": "...",
  "authors": ["..."],
  "categories": ["quant-ph"],
  "published": "2026-04-22T12:34:56Z",
  "link_abs": "https://arxiv.org/abs/2504.01234",
  "link_pdf": "https://arxiv.org/pdf/2504.01234",
  "bucket": "recommended",
  "score": 86,
  "confidence": 0.88,
  "short_reason": "Relevant because it proposes a variational method for many-body dynamics with implementation detail and resource discussion.",
  "matched_topics": ["variational dynamics", "many-body simulation"],
  "concerns": ["limited novelty evidence in abstract"]
}
```

---

## Implementation instructions for Codex

### Step 1: Candidate retrieval from arXiv
Implement `src/fetch_arxiv.py`.

Requirements:
- Query the arXiv API endpoint.
- Support multiple queries from `config/sources.yaml`.
- Respect paging using `start` and `max_results`.
- Sleep `request_delay_seconds` between repeated calls.
- Parse Atom XML into normalized JSON.
- Deduplicate by `paper_id`.
- Keep only papers within `days_back` from `config/profile.yaml`.
- Save:
  - raw XML to `data/raw/latest_arxiv.xml` only for the first query or latest merged source snapshot
  - normalized candidates to `data/intermediate/candidates.json`

Implementation notes:
- Use `submittedDate` and `descending` for retrieval unless overridden.
- Use small slices; do not request giant result sets.
- Refine queries instead of brute-force harvesting.

### Step 2: Cheap prefilter
Implement `src/prefilter.py`.

Requirements:
- Lowercase and normalize title + abstract + categories.
- Keep papers that match at least one `require_any` term.
- Drop papers matching `exclude_if_any` unless there is a strong positive score override.
- Add a lightweight heuristic score using `boost_if_any`.
- Cap the outgoing LLM set to `max_llm_candidates_per_run`.
- Save prefiltered output back to `data/intermediate/candidates.json` or `prefiltered.json`.

Purpose:
- reduce cost
- reduce latency
- avoid sending obvious junk to the model

### Step 3: LLM classification
Implement `src/classify_papers.py`.

Requirements:
- Load `config/profile.yaml` and `config/schema.json`.
- Call the OpenAI Responses API.
- Use Structured Outputs so the model returns strict JSON matching `schema.json`.
- Send one paper at a time for simplicity and easy retries.
- Include in prompt:
  - research profile
  - classification policy
  - thresholds context
  - the paper metadata
- Merge model outputs with original paper metadata.
- Save merged results to:
  - `data/output/papers.json`
  - `data/output/recommended.json`
  - `data/output/maybe.json`
  - `data/output/ignored.json`

Prompting requirements:
- The model may only use supplied metadata.
- The model must not invent claims or read the PDF.
- The model must give a short reason grounded in the abstract.
- The model should be calibrated conservatively.

Operational requirements:
- Read API key from `OPENAI_API_KEY` environment variable.
- Never write secrets to output files.
- On failed calls, retry a small number of times with backoff.
- If one paper fails classification, continue with the rest and mark that record with an error field in a separate log.

### Step 4: Static site build
Implement `src/build_site.py`.

Requirements:
- Copy `web/` into `dist/`.
- Copy `data/output/*.json` into `dist/data/`.
- Optionally render a generated `dist/index.html` from a simple template, but plain static assets are sufficient.

Frontend requirements:
- The site must not depend on any server-side runtime.
- It should load JSON from `dist/data/`.
- It should provide:
  - bucket filters
  - text search
  - sort by score and date
  - show/hide abstract
  - show reason, confidence, tags, and categories
  - links to arXiv abstract and PDF

### Step 5: Deploy with GitHub Pages via Actions
Implement `.github/workflows/update-and-deploy.yml`.

Requirements:
- Trigger on schedule and on manual dispatch.
- Checkout repository.
- Set up Python.
- Install dependencies.
- Run fetch, prefilter, classify, and build steps.
- Upload `dist/` as GitHub Pages artifact.
- Deploy Pages from artifact.

Use a custom Pages Actions workflow rather than branch-based publishing.

Suggested shape:

```yaml
name: Update and deploy arXiv monitor

on:
  schedule:
    - cron: '15 5 * * *'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python src/fetch_arxiv.py
      - run: python src/prefilter.py
      - run: python src/classify_papers.py
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      - run: python src/build_site.py
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

### Step 6: Validation workflow
Implement `.github/workflows/validate.yml`.

Requirements:
- run on pull requests and pushes
- validate Python formatting/linting if configured
- validate JSON files against schema where relevant
- ensure build completes without secrets

---

## Security requirements

- Store `OPENAI_API_KEY` in GitHub repository secrets.
- Never expose the API key in client-side code.
- Never call the OpenAI API from the browser.
- Assume the GitHub Pages site is public.
- Do not put private notes or private ranking rationales into the public frontend unless intended.

GitHub explicitly warns that Pages sites are publicly available on the internet, even when the repository is private under supported plans. citeturn673505view4

---

## Recommended dependencies

`requirements.txt` should start small:

```text
openai>=1.0.0
PyYAML>=6.0
requests>=2.31.0
feedparser>=6.0.0
jsonschema>=4.0.0
python-dateutil>=2.8.2
```

Notes:
- `feedparser` is optional if using XML parsing manually.
- `requests` is enough for arXiv HTTP calls.
- `jsonschema` is useful for local validation of model outputs.

---

## Prompt contract for the classifier

Use this as the basis of the system instruction for each paper classification call:

```text
You are classifying arXiv papers for a specific researcher.

Use only the provided metadata:
- title
- abstract
- categories
- authors
- comments if present

Do not invent claims not present in the abstract.
Do not assume a paper is novel just because it sounds ambitious.
Do not use outside knowledge.
Be conservative when confidence is low.

Return JSON matching the provided schema exactly.
Bucket definitions:
- recommended: likely worth active attention soon
- maybe: plausibly relevant but not clearly strong
- ignore: not worth attention for this profile
```

Then append the user’s `research_profile` and `classification_policy`, followed by the paper metadata.

---

## Acceptance criteria

The implementation is complete when all of the following are true:

1. Running the pipeline locally produces valid JSON outputs.
2. The model output conforms to `config/schema.json`.
3. The site builds into `dist/` with no backend required.
4. A scheduled GitHub Actions run fetches papers, classifies them, and deploys the updated site.
5. No secrets are present in the published site.
6. The site displays score, confidence, tags, and a grounded short reason for each surfaced paper.
7. If the OpenAI step fails for some papers, the pipeline still publishes the rest.

---

## Suggested first implementation scope

Version 1 should intentionally stay narrow:

- only title + abstract based selection
- no PDF ingestion
- no embeddings
- no user accounts
- no database
- no email notifications

That is enough to prove the full loop.

### Version 2 options

After V1 works, optional upgrades include:
- embeddings-based reranking
- duplicate tracking across days
- email or Telegram digest
- “why shown” filters by tag
- per-query analytics
- PDF-aware second-pass analysis on only top candidates
- archive/history pages

---

## Final recommendation to Codex

Implement the system as a **deterministic pipeline with one LLM decision step**, not as a free-form autonomous agent.

Specifically:
- arXiv produces candidates
- local code applies cheap filters
- the model classifies each remaining paper into a strict schema
- static files are generated
- GitHub Actions deploys the site to Pages

This design is simpler, cheaper, easier to debug, and fully supported by the current arXiv, GitHub, and OpenAI capabilities cited above. citeturn585569view4turn673505view4turn673505view2turn275373search0
