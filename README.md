# LSMS Publications Impact Pipeline

Automatically discovers research papers that use an LSMS-produced dataset,
computes exact World Bank fiscal-year attribution, identifies African-affiliated
authorship, classifies journal type/tier, and writes it all into a formatted
Excel workbook. No manual coding required. Built to replace a manually-maintained
tracker while improving accuracy, not just automating the old process.

This README has two parts:

1. **Quick start** — how to get it running today.
2. **How the code works** — a walkthrough of every file and every section inside
   `discover.py`, written so that someone who has never seen this project can
   open the code and know what each part does and why.

---

# PART 1 — QUICK START

## Setup

```bash
pip install -r requirements.txt
```

Get a free OpenAlex API key (30 seconds, no cost): https://openalex.org/settings/api

## Run it

**Easiest way** — double-click `Run LSMS Finder.bat` (Windows) or
`Run LSMS Finder.command` (Mac), paste your key into the window that opens, and
press Run. See `LSMS_Finder_Instructions.docx` for a fuller step-by-step
walkthrough.

**Command line:**

```bash
python discover.py --api-key YOUR_KEY
```

Runtime is roughly 5–10 minutes for a full scan. Cost is well under $1 in
OpenAlex API usage (OpenAlex gives every account $1.00 of free daily budget).
Output is written to `LSMS_papers_YYYYMMDD_HHMMSS.xlsx` — timestamped, so
re-running never overwrites a previous result.

## Options

```bash
python discover.py --api-key KEY                            # full scan
python discover.py --api-key KEY --test                      # 2 families, ~30s smoke test
python discover.py --api-key KEY --since-fy FY25             # only FY25 onward (faster incremental run)
python discover.py --api-key KEY --merge-existing prior.xlsx # dedup against a previous run's output
python discover.py --api-key KEY --min-relevance 3            # stricter: only survey-in-title papers (score 3)
python discover.py --api-key KEY --min-year 1990              # change the earliest publication year accepted (default 1980)
python discover.py --api-key KEY --output custom_name.xlsx    # choose the output filename
python discover.py --api-key KEY --crossref                   # also query Crossref titles (slower, off by default)
python discover.py --api-key KEY --fuzzy-threshold 0.9        # stricter fuzzy title match vs --merge-existing (default 0.88)
python discover.py --api-key KEY -q                            # quiet mode, no progress printing
```

---

# PART 2 — HOW THE CODE WORKS

## Files in this folder

| File | What it is |
|---|---|
| `discover.py` | The pipeline itself. Everything described below lives here. |
| `keywords.py` | The list of survey search terms, organised by survey family, each with a fixed match tier (A/B/C/AND). This is the only file you need to touch to add a new survey or keyword. |
| `scholar_supplement.py` | Optional, off by default. Searches Google Scholar for the same terms as a supplementary source (grey literature OpenAlex might miss). Not wired into the default run — call it directly if needed. |
| `run_lsms.py` | A small Tkinter GUI: paste your API key, click Run, watch progress, get a "done" popup. This is what the `.bat`/`.command` launchers open. |
| `Run LSMS Finder.bat` / `Run LSMS Finder.command` | Double-click launchers for Windows / Mac that just call `python run_lsms.py`. |
| `LSMS_Finder_Instructions.docx` | A 1–2 page instructions document for non-technical staff: how to get an API key, how to run the tool, cost and timing expectations. |
| `requirements.txt` | Python package dependencies (`pip install -r requirements.txt`). |

---

## `discover.py` section by section

The file is organised top-to-bottom in the order things happen: constants,
fiscal year math, geography classification, the OpenAlex fetcher (the part
that actually talks to the internet), deduplication, relevance scoring,
auto-detected metadata columns, journal classification, the Excel writer, and
finally the command-line entry point. Below is what each section does.

### 1. Imports and constants (top of file)

Standard library (`re`, `time`, `difflib` for fuzzy string matching,
`hashlib`, `unicodedata` for accent-stripping) plus `requests` (HTTP calls),
`pandas` (building the output tables), and `openpyxl` (writing styled Excel
files with charts). `tqdm` is optional — if it's not installed, a no-op
fallback is used so the pipeline still runs, just without progress bars in
places that use it.

`OPENALEX_BASE` / `CROSSREF_BASE`: API root URLs.
`PAGE_SIZE` (200): OpenAlex's maximum results per page.
`MAX_PAGES` (25): caps any single search term at 5,000 results, so an
accidentally very broad term can't run away and eat the whole time/cost budget.
`RATE_DELAY`: pause between requests to stay within OpenAlex's polite-use rate.

### 2. Fiscal year math

The World Bank's fiscal year runs 1 July – 30 June, so a paper published in
January 2026 is FY26, but one published in August 2026 is FY27.

- `fiscal_year(year, month)` — converts a calendar year+month into an `"FYxx"` label.
- `fy_start_date(fy_label)` — the reverse: given `"FY25"`, returns the calendar
  date its fiscal year started (1 Jul 2024). Used by `--since-fy` to build the
  OpenAlex date filter.
- `current_and_prior_fy()` — returns the fiscal year that's currently in
  progress, plus the 5 most recently *completed* fiscal years. Used throughout
  the Analysis sheet and charts (the in-progress FY is always excluded from
  charts since its count is necessarily incomplete).
- `_fy_to_year(fy)` — converts `"FY27"` → 2027, `"FY99"` → 1999, `"FY00"` → 2000.
  This exists because two-digit fiscal year labels don't sort correctly as
  plain numbers: without this function, "FY00" would sort as if it came before
  "FY99" even though FY00 (2000) is actually more recent than FY99 (1999). This
  function is what makes the Papers sheet and both charts read in true
  chronological order.

### 3. Title/DOI normalisation

`norm_title()` and `norm_doi()` — strip accents, punctuation, and the
`https://doi.org/` prefix so two records of the same paper (one from OpenAlex,
one from a prior manually-maintained tracker) can be compared as equal even if
they're formatted slightly differently. Used by deduplication.

### 4. Geography classification

`classify_geography(country_codes, first_author_codes)` — given the list of
every author's institution country codes on a paper, returns four things:

- `geography_clean`: `"Sub-Saharan Africa"` (all institutions in SSA),
  `"Mixed"` (some African, some not), `"Other"` (no African institutions), or
  `"Unclassified"` (no institution data at all).
- `is_first_author_africa`: is the *first* author at an African institution.
- `is_any_author_africa`: is *any* author at an African institution. This is
  the closest automated analogue to the original tracker's manually-coded
  "Sub-Saharan Africa + Mixed" categories (~52% in the original data).
- `is_africa_institution_strict`: are *all* authors at Sub-Saharan African
  institutions (the narrowest, most conservative flag).

Important limitation, documented directly in the function's docstring: this
method under-counts African researchers, because (a) African scholars working
at the World Bank or at US/European universities show up as non-African, and
(b) OpenAlex's institution metadata is incomplete for many African
universities. The Analysis sheet reports this gap explicitly (an
"Unclassified" count) rather than hiding it.

### 5. `OpenAlexFetcher` class — the primary data source

This is the class that actually queries OpenAlex. Key methods:

- `_get(params)` — makes one HTTP GET request with retry/backoff on rate
  limits, and appends the API key if one was supplied.
- `search_family(family, ...)` — the main search loop. For each survey family
  (e.g. "Malawi IHS / IHPS"), it loops through every `(term, tier)` pair in
  that family and:
  1. Builds the OpenAlex search query for that term (see `_build_search_query`
     in the filtering section below — plain phrase search, or a boolean AND
     query for compound terms).
  2. Pages through results (OpenAlex returns 200 per page, up to 25 pages =
     5,000 results per term).
  3. For every candidate paper, runs `_passes_filters()` (the tiered
     precision/recall gate — see below) before doing the expensive work of
     parsing the full record. Rejected candidates are counted and dropped
     immediately.
  4. Deduplicates by OpenAlex ID *within this one family's search* (the same
     paper can turn up under many different search terms in the same family;
     cross-family duplicates are handled later, in `deduplicate()`).
  5. If a paper passed an unambiguous ("Tier A") match but OpenAlex has no
     abstract on file for it, the relevance scorer would have nothing to check
     and would otherwise default to a weak score — this is corrected here by
     treating a missing abstract as a data-availability gap, not evidence of
     irrelevance, and bumping the relevance score to 2.
  6. Prints live progress (family name, term being searched, result counts) so
     a long-running console session never looks frozen.
- `_parse(work, ...)` — converts one raw OpenAlex "work" record into the flat
  dictionary structure used everywhere else in the pipeline: extracts title,
  DOI, publication date → fiscal year, authorships → geography flags, abstract
  (OpenAlex stores abstracts as an "inverted index" of word positions, which
  this function reconstructs into plain text), citation count, and so on. This
  is also where `_detect_wb`, `_detect_multilat`, `_auto_topics`,
  `_dataset_countries`, `_detect_pub_type`, and `_detect_journal_tier` (all
  described further down) get called to fill in the auto-detected columns.

### 6. `CrossrefFetcher` class — optional supplement

Only used when `--crossref` is passed. Searches Crossref's title index (not
full text) as a supplementary source for older or grey-literature papers that
OpenAlex might not index. Off by default because OpenAlex already covers the
large majority of relevant papers and Crossref's generic query parameter tends
to return a lot of noise.

### 7. Deduplication — `deduplicate()`

Runs in two stages:

**Stage 1 — within this run.** The same paper is very often discovered
multiple times: once under each survey-family term that happens to match it.
Papers are matched (in order of preference) by OpenAlex ID, then by DOI, then
by normalised title. When a duplicate is found, its `survey_family`,
`survey_terms_matched`, and `dataset_country` fields are *merged* into the
first-seen copy rather than being discarded, so a paper that legitimately uses
data from two different countries keeps both.

Immediately after this merge step, a **multi-family relevance boost** runs: if
a paper ended up matched by 2 or more genuinely distinct survey families
(e.g. it names both the Malawi and the Tanzania survey), that's very strong
independent evidence the paper actually uses LSMS microdata — even if its
relevance score was otherwise weak — so its score is bumped to at least 2. This
step has to happen *after* merging and *before* the relevance cutoff is
applied in `run_discovery()`, otherwise the individual low-scoring duplicates
would each get excluded on their own before ever being merged together.

**Stage 2 — against a prior run.** If `--merge-existing` was given, new papers
are checked against the old file's DOIs and titles (exact match, then fuzzy
string similarity via `difflib`). Exact matches are silently dropped as
already-known. Fuzzy matches above the similarity threshold (default 0.88) are
set aside in a "Dedup Review" sheet for a human to glance at, rather than
either silently merging or silently duplicating.

### 8. The three-tier search filter

This is the core precision/recall mechanism, and it exists because the ~124
search keywords vary enormously in how specific they are. `"Uganda National
Panel Survey"` cannot plausibly appear in an unrelated paper. `"IHS"` (three
letters) appears constantly in completely unrelated contexts. One matching
rule applied to both either loses real papers or lets garbage through.

Every keyword in `keywords.py` therefore carries an explicit tier, reviewed
and assigned by the LSMS team directly (not guessed by an algorithm):

| Tier | Rule |
|---|---|
| **A** — unambiguous | Full-text match accepted. No requirement that the term appear in the title or abstract specifically, and no subject-matter filter. Most discovered papers come from this tier: a paper often names its data source in the Methods section, not the abstract, and OpenAlex's search indexes the full text. |
| **B** — medium | The term must appear in the title or abstract (case-insensitive, whole-word match). |
| **C** — short/ambiguous | Strictest tier. Requires (a) a **case-sensitive** whole-word match — this is what stops `IHPS` (a survey acronym) from matching `IHPs`, the plural of the unrelated medical term "Individual Health Plan" — **and** (b) a country/context word from the survey family nearby (e.g. `"IHPS"` needs `"malawi"` present somewhere in the text) **and** (c) the paper isn't in an academic field where a household survey obviously couldn't be the data source. |
| **AND** | The keyword is actually two concepts joined by "and" (e.g. `"HFPS and Burkina Faso"`). Split into a boolean query; both halves must independently match. |

Key functions:
- `_build_search_query(term, tier)` — builds the actual string sent to
  OpenAlex's `search=` parameter. AND-tier terms become
  `"part1" AND "part2"`; everything else becomes a plain quoted phrase.
- `_word_present(word, text, case_sensitive)` — whole-word regex match, so
  `"niger"` never accidentally matches inside `"Nigeria"`.
- `_is_relevant_topic(primary_topic)` — the discipline filter used only at
  Tier C. Deliberately narrow: it excludes fields where a household survey
  obviously isn't the data source (astronomy, particle physics, linguistics,
  philosophy, cell biology, cultural studies) while leaving in every field
  where LSMS data is actually used a lot (health, nutrition, agriculture,
  education, and all social sciences).
- `_passes_filters(title, abstract, term, tier, context_hints, primary_topic)`
  — the master gate that combines all of the above and returns whether the
  paper passes, plus the tier and a human-readable reason (both get written
  to the output as `match_tier` / `match_reason`, so every inclusion decision
  is auditable after the fact).

### 9. Relevance scoring — `_relevance_score()`

Separate from the search-filter tier above. Once a paper has passed the search
filter, this function scores how *likely* it is that the paper actually **uses**
the survey's data (as opposed to merely mentioning the survey in passing, or
being a literature review that cites many papers that used it). Score is 0–3:

- **3** — the survey name appears in the paper's title. Near-certain.
- **2** — any of: the survey name appears in the abstract; explicit data-use
  language is present ("we use", "drawing on data from", "nationally
  representative", etc. — see `_USE_PATTERNS`); the LSMS programme or World
  Bank is named anywhere; three or more empirical-paper signal words appear
  (regression, household, poverty, consumption, etc. — see
  `_EMPIRICAL_SIGNALS`); or a fuzzy/grammatical-variant match of the survey
  name is found close to data-use vocabulary in the abstract (see the
  proximity check below).
- **1** — some weak evidence, or none of the above fired.
- **0** — the abstract matches a genuine literature-review/meta-analysis
  pattern (see `_REVIEW_PATTERNS` — deliberately narrow, so a paper that merely
  "provides an overview of" its own survey isn't penalised; only true
  systematic reviews and meta-analyses are caught here).

**The proximity/fuzzy match** (`_fuzzy_survey_pattern`,
`_proximity_data_use_match`) exists to catch a specific failure mode: a paper's
abstract sometimes uses a grammatical variant of the exact keyword string that
matched it — for example the keyword `"Ethiopia Rural Socioeconomic Survey"`
matched a paper whose own abstract says `"the Ethiopian Rural Socioeconomic
Survey"` (adjective form, one letter different), which a literal substring
check misses entirely even though a human reader sees an obvious data-use
statement. The fix: build a regex that matches each word of the survey term as
a *prefix* rather than requiring an exact match (so "Ethiopia" also matches
"Ethiopian", "Uganda" also matches "Ugandan", and so on for all eight ISA
countries), locate that fuzzy match in the abstract, and check the ~175
characters on either side for common data-use vocabulary.

Only papers scoring 2 or higher enter the main "Papers" sheet. Scores 0 and 1
are written to the "Not Relevant (Backup)" sheet instead — kept, not deleted,
but excluded from every headline metric, both charts, and the total paper
count on the Analysis sheet.

### 10. Auto-detected metadata columns

None of these require any manual coding — every one is computed directly from
what OpenAlex returns.

- `_detect_wb(authorships)` — checks each author's institution name against a
  small list of World Bank Group name variants (World Bank, IFC, IBRD, IDA).
- `_detect_multilat(authorships)` — same idea for other multilateral
  organisations: IFPRI, FAO, IFAD, CGIAR (and its constituent centres like
  CIMMYT/ILRI/CIFOR), WFP, UNICEF, WHO, UNDP, IMF, AfDB.
- `_auto_topics(title, abstract)` — keyword-based topic tagging across the 12
  original tracker topic categories (Agricultural Production, Health,
  Nutrition & Food Security, Gender, Poverty/Income/Welfare, etc.). Written to
  a single `research_topics` column as a comma-separated list rather than 12
  separate Yes/No columns.
- `_dataset_countries(survey_family, survey_terms_matched)` — works out which
  of the 8 ISA countries' data a paper uses, based on which survey family
  matched it (and, for HFPS phone-survey papers, which country name appeared
  in the specific compound-AND term that matched). Written to a single
  `dataset_country` column (e.g. `"Malawi; Tanzania"` for a cross-country
  paper) rather than 8 separate Yes/No columns.

### 11. Journal type and tier classification

- `_detect_pub_type(oa_type, venue)` — classifies what kind of output this
  actually is, since OpenAlex's own `type` field alone isn't reliable enough:
  it recognises institutional repositories (by name — Deep Blue, AgEcon
  Search, DSpace-based repositories, thesis archives, etc.), eBook publishers
  (Elsevier, Springer, Oxford/Cambridge University Press, World Bank eBooks),
  and working-paper series (NBER, RePEc, SSRN, MPRA, Econstor) as distinct
  from genuine peer-reviewed journal articles.
- `_JOURNAL_TIERS` — a curated lookup of ~90 named journals to a tier label
  (Tier 1 = top-5 general economics, Tier 2 = top field journals, Tier 3 =
  quality field journals, Tier 4 = other recognised peer-reviewed journals).
  Based on standard development-economics field rankings; intended to be
  replaced or extended with a WBG-approved list once the research group
  provides one — just edit this dictionary directly, nothing else needs to
  change.
- `_detect_journal_tier(venue, pub_type)` — applies the lookup, and critically,
  **never leaves a peer-reviewed article's tier blank**: anything classified
  as a working paper/repository/thesis/eBook gets tier `"WP"`, and any journal
  article not found in the curated list still gets `"4 — Other Peer-Reviewed"`
  rather than an empty cell. This closes what was previously a large
  "no marker" gap in the original tracker.

### 12. The Analysis sheet writer — `write_analysis_sheet()`

Writes the Analysis sheet cell-by-cell (rather than through pandas) so its
exact visual styling can be controlled: navy section headers spanning all four
columns, light-blue highlighted metric cells with bold text and a black
border, and specific column widths (75/48/23/23) matching a reference layout
the LSMS team supplied. Sections written, top to bottom: totals (including how
many papers were excluded and why), FLOW (papers per fiscal year), a breakdown
of how each paper was matched (tier A/B/C/AND counts), the relevance-score
composition of the analysed set, and the SHARE section (African authorship,
with the current-fiscal-year figure computed relative to that fiscal year's
own total, not the full corpus).

Below the metrics, a small data table is written (fiscal year, paper count,
Africa share for any/first author) restricted to *completed* fiscal years only
— the currently in-progress year is deliberately excluded since its count is
partial. Three charts are then built directly from that table:

1. **Bar chart** — papers per fiscal year, data labels on every bar.
2. **Line chart with markers** — share of papers with African-affiliated
   authors by fiscal year, two series (any author / first author).
3. **Pie chart** — journal tier distribution across the analysed set.

All three charts are anchored at column E so they sit beside the metrics
table rather than being buried below it, and their source data is written as
a *visible* table on the sheet (Excel renders a chart blank if its source
columns are hidden).

### 13. Excel export — `export_excel()`

Assembles every sheet and writes the final `.xlsx` file. Sheet order:

1. **Papers** — every analysed paper (relevance score ≥ 2), sorted by fiscal
   year descending, then alphabetically by title within each year.
2. **Analysis** — see above.
3. **FY Trend** — the full per-fiscal-year numeric table backing the charts
   (all fiscal years back to 2009, not just the completed ones shown in the
   Analysis-sheet chart data).
4. **Keywords** — every search term used, its family, its tier, the matching
   rule applied, the exact query string sent to OpenAlex, and any required
   context words.
5. **Search Log** — one row per survey family per source (OpenAlex, and
   Crossref if enabled), recording how many raw results came back.
6. **Dedup Review** — only present if `--merge-existing` produced any
   borderline fuzzy title matches needing a human glance.
7. **Not Relevant (Backup)** — always last. Every paper that was matched by a
   keyword but scored below the relevance cutoff (0 or 1). Kept for audit
   purposes, excluded from every metric elsewhere in the workbook.

`_clean_cell()` sanitises every cell value before writing: strips characters
Excel's XML format can't represent, decodes stray HTML entities, and prefixes
a leading `=`/`+`/`-`/`@` with a space (Excel would otherwise try to interpret
the cell as a formula).

### 14. Loading a prior run — `load_existing()`

Reads a previous output file (or a plain CSV) so `--merge-existing` can
compare against it. Tries several likely column names for the title field
(`title`, or `Document Info` from the original manually-maintained tracker's
format) so it works against either this pipeline's own prior output or the
original spreadsheet.

### 15. Orchestration — `run_discovery()`

The function that ties everything together, in order:

1. Resolve the output filename (timestamped if not given explicitly) and the
   `--since-fy` date filter, if any.
2. Load the existing file for merge-dedup, if `--merge-existing` was passed.
3. For each survey family, call `OpenAlexFetcher.search_family()` (and
   `CrossrefFetcher.search_term()` if `--crossref` is set), collecting every
   raw match plus a log entry per family/source.
4. Drop anything published before `--min-year` (default 1980, when the LSMS
   programme began) or after the current year (allowing one year of headroom
   for legitimately forthcoming articles) — this second check exists because
   OpenAlex occasionally carries a placeholder or erroneous future publication
   date, which would otherwise show up as, say, a paper from 2028.
5. Deduplicate (see section 7 above) — this must happen *before* the relevance
   cutoff, so the multi-family boost can rescue papers whose individual raw
   matches were each too weak on their own.
6. Apply the relevance cutoff: only papers scoring 2 or higher continue;
   everything else is set aside as `excluded_low_relevance` for the backup
   sheet. The cutoff has a hard floor of 2 regardless of `--min-relevance`
   (`RELEVANCE_CUTOFF = max(2, min_relevance_score)`) — passing
   `--min-relevance 3` raises the bar to only the strongest signal (survey
   name in the title), but passing 0, 1, or 2 all behave identically.
7. Print a results summary (paper counts, FY breakdown, Africa share) if
   `verbose` is on.
8. Call `export_excel()` to write the workbook.

### 16. `main()` — command-line entry point

Defines every `--flag` (see the Options table in Part 1) and calls
`run_discovery()` with the parsed arguments.

---

## `keywords.py`

Structured as a list of survey-family dictionaries, each with a `label`, a
`region`, a list of `context_hints` (the country/survey words required
alongside a Tier C acronym from that family), and a `terms` list. Each entry
in `terms` is a `(search_string, tier)` tuple — the tier is fixed data, set
directly by the LSMS team's own review of every keyword, not inferred by any
heuristic in `discover.py`. To add a new survey wave or keyword: add a tuple to
the appropriate family's `terms` list with its tier already decided.

`all_terms()` returns every unique search string across all families (used to
build the Keywords sheet and by `scholar_supplement.py`). `term_tier(term)`
looks up a single term's assigned tier.

The bottom of the file also defines the country-code sets (`AFRICA_COUNTRY_CODES`,
`SSA_COUNTRY_CODES`) and country-name sets used by `classify_geography()` in
`discover.py`.

Current keyword count: **124 terms across 10 survey families** — LSMS Core
Program, Burkina Faso (EMC/EHCVM), Ethiopia (ESS/ESPS), Malawi (IHS/IHPS), Mali
(EACI), Niger (ECVMA), Nigeria (GHS-Panel), Tanzania (NPS), Uganda (UNPS), and
High-Frequency Phone Surveys (HFPS).

---

## `scholar_supplement.py`

A standalone, optional module — not called by the default pipeline run. Uses
the `scholarly` package to query Google Scholar for the same survey-family
terms, as a way of catching grey literature (theses, working papers, non-
indexed reports) that OpenAlex might miss. Because Google Scholar has no
official API and aggressively rate-limits/blocks automated access, this is
slow and best-effort rather than something to run routinely — it supports an
optional ScrapeOps proxy configuration for that reason. Call
`search_scholar_batch()` directly if you want to use it; results are shaped to
merge into the same pipeline (same field names as `discover.py`'s output).

---

## `run_lsms.py` and the launcher scripts

`run_lsms.py` opens a small Tkinter window: an API-key field (pre-filled from
`openalex_key.txt` if you've run it before — that file is created next to the
script the first time you enter a key, so you never have to retype it), a
"quick test run" checkbox, a Run button, and a scrolling log panel that streams
`discover.py`'s console output live. On completion it pops up a confirmation
and offers to open the results folder. If Tkinter isn't available in the
Python environment, it falls back to a plain console prompt with the same
key-saving behaviour.

`Run LSMS Finder.bat` (Windows) and `Run LSMS Finder.command` (Mac) are
one-line double-click shortcuts that just `cd` into this folder and run
`python run_lsms.py` (trying `py` first on Windows, since that launcher is
more reliably on `PATH` than `python` on some systems).

---

## note on the Africa share limitations

1. African researchers based at the World Bank, or at US/European
   universities, are invisible to an institution-based method.
2. OpenAlex's institution metadata is sparse for many African universities;
   those papers land in `geography_clean = "Unclassified"` rather than being
   miscounted as non-African.

---

## Scheduling Possibility

Cron example:

```
0 8 1 1,4,7,10 * cd /path/to/pipeline && python discover.py \
    --api-key $OPENALEX_KEY --merge-existing master.xlsx
```
