# AKRxiv

AKRxiv is a GitHub-hosted arXiv monitor for quantum-computing papers. It fetches recent arXiv entries, applies a cheap local prefilter, asks an OpenAI model for structured relevance judgments, and publishes the results as a static GitHub Pages site.

## What it does

- fetches recent papers from arXiv using configurable category and keyword queries
- narrows the pool with a lightweight heuristic prefilter
- classifies remaining papers into `recommended`, `maybe`, or `ignore`
- stores the results as JSON under `data/output/`
- builds a static site into `dist/`
- deploys to GitHub Pages from a GitHub Actions workflow

## Repository layout

```text
config/                 profile, source queries, classifier schema
src/                    fetch, prefilter, classify, build, validate
data/raw/               raw arXiv XML snapshots
data/intermediate/      normalized candidates and prefiltered papers
data/output/            classified outputs consumed by the site
web/                    static site source
dist/                   generated deployable site
.github/workflows/      validation and Pages deployment workflows
```

## Local setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the pipeline from the repository root:

```bash
python src/fetch_arxiv.py
python src/prefilter.py
OPENAI_API_KEY=your_key_here python src/classify_papers.py
python src/build_site.py
```

Open `dist/index.html` in a browser after the build completes.

## Configuration

- Edit `config/profile.yaml` to change the research profile, score thresholds, model policy, and prefilter terms.
- Edit `config/sources.yaml` to change arXiv queries, paging, and request delay.
- `config/schema.json` defines the strict classifier response schema.

## GitHub setup

1. Add `OPENAI_API_KEY` under `Settings -> Secrets and variables -> Actions`.
2. In `Settings -> Pages`, set the source to `GitHub Actions`.
3. Run the `Update and deploy arXiv monitor` workflow manually once to publish the first build.

The deploy workflow uses the GitHub Pages artifact flow rather than branch-based Pages publishing, which avoids the `GITHUB_TOKEN` Pages build limitation for workflow-generated content.

## Validation

The validation workflow does not require secrets. It:

- compiles the Python sources
- validates the classifier schema and published JSON shapes
- builds the static site

## Notes

- The frontend never calls the OpenAI API directly.
- `dist/` is generated and not committed.
- If an OpenAI call fails for one paper, the pipeline logs the error and continues.

