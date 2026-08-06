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

Runtime is roughly 5 minutes for a full run, which costs about $1.60 in
OpenAlex usage. An update run costs cents and is what you want most of the
time. OpenAlex gives every account a free daily budget.
Each run writes four timestamped files, so re-running never overwrites an
earlier result:

| File | What it is |
|---|---|
| `LSMS_papers_<stamp>.xlsx` | The workbook: results, analysis, keyword register, audit trail, and every rejected paper with its reason. |
| `LSMS_papers_<stamp>.csv` | The same rows and columns as the Papers sheet, for re-use elsewhere. The charts are built from this file, so what is plotted is provably what was exported. |
| `LSMS_papers_<stamp>_flow.png` | Papers per fiscal year, with this run's additions stacked on top. |
| `LSMS_papers_<stamp>_africa_share.png` | Share of papers with an African-affiliated author, per fiscal year. |

## Options

```bash
python discover.py --api-key KEY --update                    # update run: only new papers cost anything
python discover.py --api-key KEY                             # full run: rescore everything from scratch
python discover.py --api-key KEY --test                      # 2 families, quick smoke test
python discover.py --api-key KEY --since-fy FY25             # only papers published FY25 onward
python discover.py --api-key KEY --merge-existing prior.xlsx # compare against a specific file
python discover.py --api-key KEY --no-merge                  # don't compare against anything
python discover.py --api-key KEY --min-relevance 4           # extra floor on identity+use combined
python discover.py --api-key KEY --min-year 1990             # earliest publication year (default 1980)
python discover.py --api-key KEY --output custom_name.xlsx   # choose the output filename
python discover.py --api-key KEY --crossref                  # also query Crossref titles (see the caveat below)
python discover.py --api-key KEY -q                          # quiet mode, no progress printing
```

Most people should use the launcher (`LSMS Impact Analysis.bat`) instead,
which exposes the one choice that matters as a tickbox.

### Update runs vs full runs

Every run compares against the most recent `LSMS_papers_*.xlsx` in the folder
unless told otherwise, and marks each paper as new or already known. Rows
added by this run are highlighted in the workbook.

`--update` additionally skips the expensive step for papers a previous run
already scored. It still **searches** everything, so nothing is missed; it just
doesn't pay to re-examine the full text of papers whose verdict is already
known. Gate 1 is roughly 20% of a run's cost and Gate 2b the other 80%, so an
update run costs cents rather than about $1.60.

It is deliberately not a date window. OpenAlex indexes papers long after they
are published, so "only search since last time" would lose late arrivals
permanently, and the `from_created_date` filter that would fix that requires a
paid OpenAlex plan (verified: the free tier returns 429).

Use a full run after changing the matching rules, since `--update` reuses
stored verdicts and would otherwise keep the old ones.

---

# PART 2 — HOW THE CODE WORKS

## Files in this folder

| File | What it is |
|---|---|
| `discover.py` | Ties the pipeline together and exposes the command line. The steps below live in the modules it imports. |
| `matching.py` | Gate 1: builds the OpenAlex queries and decides whether a keyword hit is admitted. |
| `relevance.py` | Gate 2: scores the identity and use axes and decides what counts. |
| `fetchers.py` | Talks to OpenAlex (and Crossref, optionally), including the full-text pass and the spend guard. |
| `dedup.py` | Merges duplicates within a run and marks papers new or already known against the previous run. |
| `excel_export.py` | Writes the workbook and the CSV, and tints the rows this run added. |
| `charts.py` | The two PNG charts, in the World Bank palette. Swap the hexes at the top of the file to restyle everything. |
| `test_logic.py` | Offline sanity checks for the matching and scoring logic. No network: `python test_logic.py`. |
| `keywords.py` | The survey search terms by family, each with a fixed tier (A/B/C) and the country words that gate it. This is the only file you need to touch to add a survey or keyword. |
| `scholar_supplement.py` | Optional, off by default. Searches Google Scholar for the same terms as a supplementary source (grey literature OpenAlex might miss). Not wired into the default run — call it directly if needed. |
| `run_pipeline.py` | The launcher: paste your API key, choose update or full run, click Run. This is what the `.bat` opens. |
| `LSMS Impact Analysis.bat` | Double-click launcher. `Initial Setup.bat` installs the dependencies once, first. |
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

Standard library (`re`, `time`,
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

**Stage 2 — against the previous run.** Every paper found is kept; the prior
file only decides what is *marked* as new. Matching is exact, on OpenAlex id
first, then DOI, then normalised title. A paper carries the same OpenAlex id
between runs, so this is both exact and instant.

This replaced a fuzzy title comparison that ran every new title against every
old one. It was quadratic and never finished on a real corpus: 200 papers
against a 7,600-row export did not complete in five minutes, so runs hung
before writing any output. It also bought nothing that the id doesn't already
settle.

### 8. The three-tier search filter

This is the core precision/recall mechanism, and it exists because the ~124
search keywords vary enormously in how specific they are. `"Uganda National
Panel Survey"` cannot plausibly appear in an unrelated paper. `"IHS"` (three
letters) appears constantly in completely unrelated contexts. One matching
rule applied to both either loses real papers or lets garbage through.

### Stemming: off at Gate 1, on at Gate 2b

This is the single most consequential setting in the whole pipeline, so it's
worth stating plainly. OpenAlex stems and removes stop words by default, which
means a search for `LSMS` also matches `LSM` — and `LSM` is the standard
abbreviation for *land-surface model* and *log-structured merge-tree*. Stemmed,
the bare `"LSMS"` query returned **13,506 hits for a single fiscal year**
(26,592 before the country gate was tightened). Unstemmed, the same query
returns **698**.

Queries therefore go out via OpenAlex's `search.exact` parameter, which
bypasses stemming. (OpenAlex's `.no_stem` filter was added in May 2024 and then
withdrawn as too expensive to operate — it is still listed as a valid field
name but returns `400`, so `search.exact` is the supported route.)

Two caveats worth knowing:

- `search.exact` is still **case-insensitive** — `LSMs` and `LSMS` are the same
  token to the server. That residual collision is what the Tier C case check
  catches locally.
- **Gate 2b deliberately keeps stemming on.** Its queries always carry an
  `ids.openalex:` filter restricting them to an explicit list of already-
  admitted candidates, so a stem collision physically cannot drag in an
  unrelated paper the way it can at Gate 1. What stemming buys there is verb
  variants — `supported by` also matching `supports` — and that matters:
  unstemmed, the provenance probe went from 89 hits to 0 and the flagged-set
  score dropped from 24/32 to 23/32.

Every keyword in `keywords.py` therefore carries an explicit tier, reviewed
and assigned by the LSMS team directly (not guessed by an algorithm):

| Tier | Rule |
|---|---|
| **A** — unambiguous | The name identifies the survey on its own: it contains a country (`"Tanzania National Panel Survey"`) or an acronym that can't plausibly mean anything else (`"LSMS-ISA"`, `"TZNPS"`). A full-text match is accepted as-is — a paper often names its data source in the Methods section, not the abstract, and OpenAlex indexes full text. |
| **B** — generic name | A real survey name, but the words *describe* the survey rather than identify it, and other countries or programmes use the same phrase — `"National Panel Survey"` (Tanzania and Uganda both), `"High-Frequency Phone Survey"` (every agency ran one during COVID), `"Living Standards Survey"` (ordinary prose). Requires a country context word somewhere in the document **and** an allowed field. Case-insensitive: casing carries no information in a phrase. |
| **C** — short acronym | `"IHPS"`, `"LSMS"`, `"UNPS"`. Same country + field gating as B, plus a case check: OpenAlex case-folds and stems server-side (so `"LSMS"` also retrieves `"LSM"`), and casing is the only local defence against a collision. If the acronym appears in the title/abstract with the *wrong* case (`IHPs`, the plural of the unrelated medical term), that's a positive refutation and the paper is dropped; if it doesn't appear there at all we can't tell, and the query's own country+field gating stands. |

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

### 9. Gate 2 — relevance, scored on two axes (`relevance.py`)

Gate 1 above only answers *did we find the name*. Gate 2 answers the two
questions that actually decide whether a paper belongs in the tracker, and it
keeps them deliberately separate:

- **IDENTITY** — is this really one of our surveys, or a name collision / a
  different country's survey that shares a phrase?
- **USE** — did the authors work with the microdata, or do they only *mention*
  it: cite it, credit it, list it as related work?

A strong signal is worth 2 points and a weak one 1. **Identity needs 2+ AND use
needs 2+** — clearing one axis alone is not enough.

Collapsing these into a single number is what lets a paper pass on identity
alone. Name the survey three times in an abstract, add a World Bank co-author,
and a pure literature review outscores a real empirical paper. Keeping the axes
apart makes "mentions but does not use" structurally unable to pass, which is
the entire point of the gate.

**Tied vs untied use evidence.** "We use household survey data" proves the
authors used *some* data — not *ours*. Only evidence tying the use language to
the survey counts fully: full-text proximity (Gate 2b, below, requires the two
within 40 words of each other), or an abstract that both names the survey and
describes using data. Untied evidence (generic empirical vocabulary, data-use
language with no survey named) is capped at 1 point total, so it can corroborate
a real signal but never carry the axis by itself.

**Publication type** is the one absolute veto: the six OpenAlex types that can
never be an empirical use — conference abstract, dataset, paratext, erratum,
letter, software. Editorial is deliberately *not* on that list.

**Reviews** are flagged rather than vetoed. A review that genuinely re-analyses
the microdata still passes; it just has to show a *strong* tied use signal
rather than coasting on weak ones. Reviews are the single largest
"mentions but doesn't use" category, so the bar is raised, not closed.

### 9b. Gate 2b — the full-text pass (`fetchers.fulltext_data_use_probe`)

Runs for every paper whose **use** score is still short — note that's the use
axis, not the total. A paper can sit on a mountain of identity evidence and
still show nothing about whether the data was used; that's exactly the paper
worth spending an API call on.

It asks OpenAlex whether the paper's own matched survey name sits within 40
words of language describing working with the data. Proximity is what ties the
evidence to *our* survey.

The phrase lists were **picked from measurement, not intuition**: every
candidate was run against the 36-DOI flagged review set and scored on how many
intended-include vs intended-exclude papers it hit.

- *Strong* (2 pts use, +1 identity): `using data from` (8 include / 1 exclude),
  `data from the` (8/2), `we use` (3/0), `we used` (3/0), `collected by` (4/1),
  `conducted by` (2/0), `we collected`, `obtained from`.
- *Weak* (1 pt): `using the` (12/7 — best recall, noisiest), `sample of` (5/2),
  `survey data` (7/5), `microdata`, `wave`, `round`.
- *Provenance* (1 pt): `supported by`, `funded by`, `implemented by` — each 2/2
  alone, kept separate so they stack rather than decide.

Three findings from that measurement are worth recording, because all three
contradicted an assumption:

1. Phrases that *sound* like obvious wins — `we draw on`, `our analysis`,
   `our sample`, `we obtained`, `drawn from` — scored **zero hits**. Academic
   prose overwhelmingly prefers `using data from` / `data from the`.
2. `this paper uses` (0/2), `this study uses` (1/3) and `based on the` (2/4) are
   **negative** discriminators — they hit more citations than real uses.
3. Citing the World Bank microdata catalogue measured **2/2 — no separation at
   all**, despite the intuition that you only cite the catalogue when you
   downloaded the files. It is searched (in the paper's *text*, not its hosting
   URL) and written to the workbook as a flag, because it's useful when
   reviewing by hand, but it gets **no points**.

Bare nouns (`data`, `survey data`, `panel survey`, `using the`) were also tried
as a combined group and dropped: a bibliography entry sits within 40 words of
the word "data" in essentially every empirical paper, and they fired on 14
known-good exclusions (17/32 vs 24/32).

Papers failing either axis go to the "Not Relevant (Backup)" sheet — kept, not
deleted, but excluded from every headline metric and both charts.


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
of how each paper was matched (strongest tier per paper), the two-axis
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

1. **Papers** — every paper that cleared both the identity and use axes,
   sorted by fiscal year descending, then alphabetically within each year.
   Rows added by this run are tinted, and the `is_new` column records
   Yes/No.
2. **Analysis** — see above.
3. **FY Trend** — the full per-fiscal-year numeric table backing the charts
   (all fiscal years back to 2009, not just the completed ones shown in the
   Analysis-sheet chart data).
4. **Keywords** — every search term used, its family, its tier, the matching
   rule applied, the exact query string sent to OpenAlex, and any required
   context words.
5. **Search Log** — one row per survey family per source (OpenAlex, and
   Crossref if enabled), recording how many raw results came back.
6. **Dedup Review** — retained for backwards compatibility; empty now that
   matching against a previous run is exact.
7. **Not Relevant (Backup)** — always last. Every paper matched by a keyword
   that failed the identity or the use axis. Kept for audit purposes and
   excluded from every metric elsewhere in the workbook. An update run reads
   this sheet too, so papers already rejected are not re-checked.

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
   `CrossrefFetcher.search_term()` if `--crossref` is set) — note Crossref gives no full text and no OpenAlex id, so Gate 2b
   cannot run on those records and their use axis must come from an abstract
   that is often missing; measured, 0 of 9 could clear Gate 2, so treat
   `--crossref` as an audit trail rather than a source of new papers, collecting every
   raw match plus a log entry per family/source.
4. Drop anything published before `--min-year` (default 1980, when the LSMS
   programme began) or after the current year (allowing one year of headroom
   for legitimately forthcoming articles) — this second check exists because
   OpenAlex occasionally carries a placeholder or erroneous future publication
   date, which would otherwise show up as, say, a paper from 2028.
5. Deduplicate (see section 7 above) — this must happen *before* scoring, so a
   paper's separate matches (several terms, several families) merge into one
   record first; multi-term and multi-family are identity signals and need that
   merge to exist.
6. Score Gate 2a for every deduped paper, then run the Gate 2b full-text pass
   over everything whose use axis is still short. Papers clearing **both** axes
   continue; everything else is set aside as `excluded_low_relevance` for the
   backup sheet. `--min-relevance` can only tighten this further — it never
   lets through a paper that failed an axis.
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
alongside a Tier B or C term from that family — countries only, never a word
that appears in the family's own terms, which would make the gate
self-satisfying), and a `terms` list. Each entry
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

Current keyword count: **109 terms across 10 survey families** — LSMS Core
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

## `run_pipeline.py` and the launcher

`run_pipeline.py` opens a small Tkinter window: an API-key field (remembered
in `pipeline_config.json` so you never retype it), a tickbox choosing between
an update run and a full run, and a Run button. It streams `discover.py`'s
progress and offers to open the result when it finishes.

The tickbox is the only decision most people need to make:

| Ticked (default) | Unticked |
|---|---|
| Adds newly found papers to your latest results and highlights them. Costs cents. | Rebuilds and rescores everything. About 5 minutes, roughly $1.60. |

Untick it after changing the matching rules, since an update run reuses stored
verdicts and would otherwise keep the old ones.

`LSMS Impact Analysis.bat` is the double-click shortcut. `Initial Setup.bat`
installs the dependencies and only needs running once.

`pipeline_config.json` holds the API key and is deliberately not tracked by
git. The launcher recreates it the first time you enter a key.

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
