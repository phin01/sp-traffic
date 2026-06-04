# Transformation (dbt)

dbt project that turns the staging tables loaded by the Python ingestion into
analytics-ready models for SP-Traffic.

## Layout

```
transformation/
├── dbt_project.yml
├── profiles.yml              # credentials hardcoded here (see AGENTS.md)
├── models/
│   ├── sources/              # external table declarations
│   ├── staging/              # 1:1 unnested views of source JSON blobs
│   ├── intermediate/         # business-logic enrichments
│   │   ├── int_previsao_calculated.sql        # ETA computation
│   │   └── line_stops/
│   │       └── int_line_stops.sql             # canonical stop order per line
│   └── marts/                # WIP — final consumer-facing models
└── macros/                   # time arithmetic helpers
```

## Running

From this folder:

```
dbt deps
dbt run
dbt test
```

To rebuild a single model and its tests:

```
dbt run --select int_line_stops
dbt test --select int_line_stops
```

## Models at a glance

| Model | Layer | Materialization | Purpose |
|---|---|---|---|
| `stg_previsao_raw` | staging | incremental table | Unnested rows from Olho Vivo `previsao` JSON blobs. Incremental on `loaded_at`. |
| `stg_weather_raw` | staging | incremental table | Unnested rows from Open-Meteo JSON blobs. |
| `int_previsao_calculated` | intermediate | table | Adds `minutes_until_arrival` per snapshot, handling overnight ETAs and delayed snapshots. See ADRs 0002, 0003, 0004. |
| `int_line_stops` | intermediate | table | Canonical stop order per directional line. See ADR-0001. |

### Schema layout

Models are materialized into per-layer Postgres schemas:

- staging → `stg.`
- intermediate → `int.`
- (marts will land in `mart.` when introduced)

The mapping lives in `dbt_project.yml` (`+schema:` per layer) and is enacted
by `macros/generate_schema_name.sql`.

### Materialization rule

Default per layer (in `dbt_project.yml`): staging = `table`, intermediate =
`view`. Override to `table` in a model's own `config()` block when the
model is **compute-intensive enough that re-running it on every downstream
read costs more than the storage of materialising it**. Currently
`int_previsao_calculated` (the ETA enrichment, scanned heavily by
`int_line_stops` and any future marts) and `int_line_stops` (pairwise-voting
self-join) both qualify.

When in doubt, keep it a view and promote to a table later if profiling
shows it is hot.

## Validating `int_line_stops` against SPTrans

The pairwise-voting stop ordering is empirically validated against the public
SPTrans Olho Vivo line page. Pearson rank correlation on the two lines tested
so far is ≥ 0.999 — see the ADR for details.

To validate a new line:

1. Open `https://olhovivo.sptrans.com.br/#busca/linha/<line_id>` and pick a
   vehicle that is near the start of its route (so most stops show ETAs).
2. Save the page as `webscrape_<vehicle_id>.htm` at the project root.
3. Run the sandbox helpers (no extra deps; uses only `psycopg2` and
   `dotenv` from `requirements.txt`):

   ```
   python sandbox/parse_webscrape.py webscrape_<vehicle_id>.htm <vehicle_id>
   python sandbox/compare_line.py <line_id> <vehicle_id>
   ```

4. Expect:
   - Every stop the website reports for the vehicle is present in the model.
   - The model order matches the website order up to a constant offset
     (representing stops the vehicle has already passed).
   - Pearson r > 0.99.

A drop below 0.99 is a signal — either the data drifted or the model
regressed.

### Encoding gotcha

SPTrans line pages can be served as either UTF-8 or Latin-1 depending on the
endpoint / browser. `sandbox/parse_webscrape.py` auto-detects: it tries UTF-8
first and falls back to Latin-1. If you write your own parser, do the same —
mis-decoding silently swallows the `às` separator between the vehicle id and
its ETA, producing zero matches.

## Conventions

- Use the macros under `macros/` for time arithmetic — do not reinvent the
  UTC / overnight handling inline.
- Intermediate models go under `models/intermediate/`; if a model needs more
  than one file (e.g. a chain), give it its own subfolder.
- Document new models in their `.yml` sibling. Tests live there too.
- Significant design choices (anything beyond a straightforward SQL pattern)
  get an ADR under `docs/adr/`.
