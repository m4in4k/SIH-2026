# Sentinel Tool

An AI-powered Sentinel Tool platform for offline or private-network Bitcoin investigation, built with **React + FastAPI + MongoDB**. Includes case permissions, dataset ingestion, exploratory anomaly detection, interactive transaction graphs, and JSON evidence reports.

Submission documentation: [technical approach, model, and explainability](TECHNICAL_WRITEUP.md) and [offline Linux workflow](OFFLINE.md).

## Investigation enhancements

- **Transactions → Advanced filters:** combine a dataset, explicit observation/block time range (UTC), output total in satoshis, fee rate, input/output counts, confirmation snapshot, script type, and alert presence. Sort and paginate the filtered results. Missing values do not match numeric or date ranges.
- **Alert queue → Advanced filters:** add priority, review status, minimum model percentile, and detection stage. Stage filters match any triggering stage; the record also identifies the first stage that detected the signal.
- **Rich transaction drawer:** source-supplied chain metadata, confirmation snapshot, both timestamps, sizes, weight, locktime, fees, resolved input references, observed spending links, script information, associated anomalies, network observations, and source/pipeline lineage. Missing spenders do not prove an output is unspent. Confirmation counts are imported snapshots, never silently updated or inferred.
- **Investigation timeline:** transaction observations, reported block times, network observations, pipeline events, anomaly detection events, and analyst actions. Filter by event type, stage, dataset, UTC date range, or text; follow links back to transactions and alerts.
- **Detection evidence:** each triggering rule/model stores its stage, detector, observed value, threshold, comparison operator, applicable baseline, reason, and actual processing timestamp. An alert can record both a rule signal and a model signal. Rule detection precedes model scoring. Validation errors are processing failures, not suspicious-transaction findings.

Model version `sentinel-iforest-v2` records validation, feature engineering, rule detection, model scoring (or skipped for small datasets), and alert generation. Transaction observation time, detection time, and alert creation time are separate fields. Old records remain unchanged: unknown historical stages/times are explicitly labeled, never backfilled with invented events. Import into a new case to obtain a fresh recorded analysis without erasing review history.

Reports use schema version 1.2 and include stored detection evidence, feature contributions, entity clusters, network observations, and dataset stage events. The timeline reads at most 20,000 records per source and displays a source-cap warning when reached; its total then describes the bounded view. Live chain verification and calibrated real-world crime detection remain outside scope.

## What works

- A responsive React investigation dashboard, transaction search and detail panels, alert review, and Cytoscape graph exploration.
- A clearly labeled, read-only synthetic demo available without credentials. Demo review changes exist only in browser memory; demo scores are illustrative.
- Self-service analyst signup plus administrator-provisioned viewer accounts; Argon2 password hashes; signup and login throttling; opaque expiring, server-revocable HttpOnly session cookies. No hardcoded passwords or public administrator-bootstrap endpoint.
- Case owners, analysts, and viewers. Backend authorization on every case operation. Workspace administrators can access all cases and create accounts. Ordinary analysts see only cases they own or are assigned to. Viewers cannot import, create cases, or review alerts.
- CSV, JSON, XML uploads, SHA-256 source hashes, record lineage, input/output schema validation, and duplicate detection. Optional network observations are correlated to transactions and enriched from local country/ASN MMDB databases when configured.
- Mongo-backed queued analysis with a separate worker for Docker/local use, request-scoped analysis for Vercel, visible processing stages, multi-pattern rules, deterministic Isolation Forest scoring for datasets of at least 40 records, feature-contribution explanations, and wallet/IP entity clustering.
- Evidence export containing dataset metadata, alerts, source transactions, feature vectors, model parameters, and audit history.

This is a prototype, not a validated forensic product. No blockchain consensus verification, wallet ownership inference, or calibrated crime prediction is performed.

## Deploy the complete project on Vercel

The repository includes a root vercel.json that deploys the Vite frontend and FastAPI backend as one Vercel Services project. Use MongoDB Atlas for the database. Imports are processed within the API request on Vercel because serverless deployments do not keep the local polling worker alive.

See [DEPLOYMENT.md](DEPLOYMENT.md#vercel--mongodb-atlas) for the exact dashboard settings, environment variables, first administrator setup, validation steps, and free-tier limits.

## Quick start: Docker Compose

Requires Docker Engine with Compose. First installation/build needs internet access; once images and dependencies are present, the application runs without internet.

1. Create your local configuration:

   ```bash
   cp .env.example .env
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   ```

   Paste the two different generated values into `MONGO_ROOT_PASSWORD` and `MONGO_APP_PASSWORD` in `.env`. Use hex values so the MongoDB URI needs no escaping. Do not commit `.env`.

2. Build and start:

   ```bash
   docker compose up --build -d
   ```

3. Create your administrator account (password entered interactively):

   ```bash
   docker compose exec api python -m app.manage create-admin --email admin@your-team.org --name 'Team administrator'
   ```

4. Open **http://localhost:8080**, choose **Sign in**, then **New case**. In **Datasets**, choose **Load training data** or import a sample file.

5. Wait for the dataset status to become `completed`, then inspect alerts, open the graph, mark an alert reviewed, and export a report.

MongoDB is not published to the host network. The API uses a dedicated `sentinel_app` account limited to the application database; it does not use the MongoDB root account. The named volume `mongo_data` preserves data across ordinary restarts. Do not use `docker compose down -v` unless you deliberately intend to delete all project data.

Container definitions are supplied but were not built in the development environment; native FastAPI/React and a real MongoDB instance were tested.

## One-click offline Linux release

For the investigator-facing offline workflow, build a transferable release once on a connected Linux build machine:

```bash
bash ./scripts/package-offline.sh 0.2.0
```

Move the generated `dist-offline/Sentinel-Tool-0.2.0-linux-x86_64` directory to the offline workstation, verify `SHA256SUMS`, and run `bash ./scripts/install-desktop-launcher.sh` once. Normal use then requires only opening **Sentinel Tool**, signing in, and importing a CSV, JSON, or XML dataset. The launcher starts the bundled database, API, and worker without pulling or building images; analysis runs automatically and the dashboard opens the ranked results when processing finishes.

Accounts, cases, evidence, and results persist locally between launches. When a signed-in user without a case imports a file, Sentinel creates the investigation case automatically. See [OFFLINE.md](OFFLINE.md) for packaging, installation, and operational details.

## Native development

Use Python 3.14 (tested), Node.js 24 (tested), pnpm, and a local MongoDB 8.x instance. Python 3.12+ may also work but was not verified.

From the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock.txt
cd frontend
pnpm install --frozen-lockfile --ignore-scripts
pnpm run build
cd ..
```

The frontend dependencies used here do not require dependency lifecycle scripts; `--ignore-scripts` avoids executing third-party installers.

Start your own MongoDB service, then create an account:

```bash
export MONGO_URI='mongodb://127.0.0.1:27017'
export MONGO_DB='bitcoin_sentinel'
PYTHONPATH=backend .venv/bin/python -m app.manage create-admin --email admin@your-team.org
```

Serve the built frontend, API, and worker locally:

```bash
./scripts/start-local.sh
```

Open **http://127.0.0.1:8000**. To develop with hot reload instead, run the API and worker in separate terminals from the project root:

```bash
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
PYTHONPATH=backend .venv/bin/python -m app.worker
```

Then run `pnpm run dev` inside `frontend` and open **http://127.0.0.1:5173**. Vite proxies `/api` to FastAPI; the browser never accesses MongoDB directly. The frontend contains no external fonts, CDN scripts, analytics, or runtime network dependencies. Swagger's optional `/api/docs` interface uses upstream CDN assets; the investigation application itself does not.

## Team workflow

Sign in as the workspace administrator, create a case, open **Team & access**, and create a user. Add that existing user to the case as an analyst or viewer. The account does not receive case access merely by being created.

Administrators and case owners manage case membership. Case owners cannot provision new workspace users unless they are also workspace administrators.

To reset a user's password and revoke their sessions:

```bash
PYTHONPATH=backend .venv/bin/python -m app.manage reset-password --email analyst@your-team.org
```

## Input format

Ready-to-use examples are in `samples/`. All examples are synthetic. Use `samples/sentineltool-test-dataset.json` for comprehensive end-to-end testing; its expected signals are documented in `samples/README.md`. The examples are independent format samples, and importing files that share TXIDs into the same case will skip those duplicates.

JSON accepts a list of transactions or an object with `transactions` and optional `observations` arrays:

```json
{
  "transactions": [{
    "txid": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "observed_at": "2025-08-31T12:00:00Z",
    "block_time": null,
    "inputs": [{
      "prev_txid": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "prev_vout": 0
    }],
    "outputs": [{"index": 0, "value_sats": 120000, "address": "example-address"}],
    "fee_sats": 500,
    "vsize": 140
  }],
  "observations": []
}
```

- Values must be integer satoshis, never floating-point BTC. Optional fees remain unknown when absent. Input values are not guessed.
- TXIDs are lowercase 64-character hexadecimal identifiers. Output indexes are consecutive from zero. An address is optional; it is not an identity. Addresses are stored as supplied, not cryptographically validated.
- Optional transaction metadata: `confirmed` (boolean), `confirmations`, `block_height`, `block_hash`, `size_bytes`, `weight`, `version`, and `locktime`. Outputs may include `script_type` and `script_hex`; inputs may include `sequence`. CSV/XML parsers normalize scalar values before validation.
- A timestamp must carry a timezone; store observation and block times separately. Charts explicitly combine available observation/block timestamps and omit records lacking both. They are not precise creation-time charts.
- CSV uses the same top-level fields with JSON-encoded `inputs` and `outputs` cells. XML examples use output and input attributes; XML entity expansion is disabled.
- An optional network observation has `txid`, `observed_at`, `sensor`, and either legacy `peer_ip`/`peer_port` or SIH-style `src_ip`, `dst_ip`, `src_port`, and `dst_port`. Optional `country` (or `geo_country`) and `asn` values are accepted when supplied by an offline source. When local MMDB files are configured, Sentinel records separate `src_geo` and `dst_geo` evidence containing country code/name, continent, ASN, organization, and provenance. These observations are correlated only to the referenced transaction, preserved in reports, and never treated as evidence of origin or ownership. The graph labels IP, country, ASN, transaction, and wallet/address nodes separately; unmatched network records remain unmatched.
- SIH rows may also use `timestamp`, `txid`, `input_addresses`, `output_addresses`, `input_amounts`, `output_amounts`, `src_ip`, `dst_ip`, `src_port`, `dst_port`, `geo_country`, and `ASN`. Amount arrays are interpreted as BTC and converted to integer satoshis before normal `Transaction` validation. Address-only inputs are retained as unresolved references; no wallet ownership is inferred.
- Limits: 4 MB/file on Vercel (to stay below its 4.5 MB function body limit), 10 MB/file when self-hosted, 10,000 transaction records/file, 500 inputs or outputs/record, and 100,000 records/case for summary scans. These are explicit prototype bounds, not Bitcoin protocol limits.

## Analysis behavior and limits

Rules detect fan-in/fan-out, peel chains, structuring, round outputs, off-hours large transfers, cross-border relays, and Tor/VPN relay evidence. Isolation Forest uses 14 blockchain and network features: input/output counts, value and fee measures, output entropy and roundness, time, transaction size, unique relay IP count, cross-border activity, and Tor/VPN evidence. Parameters: 200 estimators, random seed 42, one training thread.

For at least 40 accepted records, scores are mid-rank percentiles **within the imported dataset**. This is exploratory, in-sample scoring. A 97th-percentile score can create a medium-priority model alert; rule matches create high-priority review leads. Identical feature vectors share a score. Fewer than 40 records use rules only; the UI shows no ML score. Scores from separately imported datasets are not calibrated for direct comparison.

Explanations list actual feature values, triggered thresholds, and per-feature perturbation contributions relative to dataset medians. These contributions are local, SHAP-style approximations rather than exact SHAP values or causal attribution. Legitimate batching and consolidation can trigger the same rules. There is no validated precision/recall claim.

Reports include up to 1,000 alerts and 200 recent audit entries, with explicit limits. Graphs show at most 25 transactions within two hops and selected outputs, retaining connecting outputs where possible. Wallet clusters use common-input co-occurrence evidence; IP clusters use relay co-occurrence and are displayed with risk scores and supporting transactions. These are investigative groupings, not proven common ownership. Missing GeoIP enrichment is recorded as a skipped pipeline stage and never blocks core transaction analysis. Live collection is not implemented.

## Offline GeoIP enrichment

Sentinel performs GeoIP lookup locally; it never sends IP addresses to a web service. Obtain compatible country and ASN databases in MaxMind DB (`.mmdb`) format under terms suitable for your deployment, then place them at:

```text
geoip/country.mmdb
geoip/asn.mmdb
```

The recognized default names are also `geoip/GeoLite2-Country.mmdb` and `geoip/GeoLite2-ASN.mmdb`. The offline Compose configuration mounts the directory read-only. Native deployments may set `GEOIP_COUNTRY_DB` and `GEOIP_ASN_DB` (or the older `SENTINEL_GEOIP_*` names) to absolute local paths. Each import records a `geoip_enrichment` stage with database filenames and match counts. `/api/health` reports whether each configured file is present. Source and destination lookups are stored independently, exposed in transaction detail and timeline responses, included in evidence exports, and represented as IP, country, and ASN nodes in the graph.

Supplied `country`/`geo_country` and `asn` fields remain usable as dataset-sourced fallback evidence. GeoIP location identifies an address allocation record, not a person, device, transaction origin, or wallet owner.

Use one worker for the Docker/local prototype. Queued jobs survive restarts. Vercel processes imports within the request and does not start this worker. Running jobs older than an hour without progress become visible failures; failed payloads are retained for administrator inspection. Automatic retry/reprocessing is not implemented. A fresh case can be used to retry a corrected or unchanged source file. Source import is schema validation, not a guarantee of chain validity, input-value conservation, authenticity, or absence of double spending.

## Tests

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

Tests cover the complete import, queue, analysis, graph, review, and report flow; Vercel request-scoped processing; deployment-origin and secure-cookie behavior; one-time administrator setup; cross-case isolation; viewer restrictions; expired sessions; CSRF checks; login throttling; duplicate lineage; malformed records; XML entity rejection; and uniform-data scoring.

To run the same tests against real MongoDB:

```bash
SENTINEL_TEST_MONGO_URI='mongodb://127.0.0.1:27017' PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

Each test creates a randomly named `sentinel_test_*` database and deletes only that database after the test. Never point tests at a shared production database without reviewing the test configuration.

## Private-network or future public deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the deployment preflight, secrets, startup, health-check, and operating procedure.

The default bind address is localhost. For a trusted LAN demo, explicitly set `BIND_ADDRESS=0.0.0.0` and add the exact browser origin (for example `http://192.168.1.20:8080`) to `ALLOWED_ORIGINS`. Plain HTTP is appropriate only for trusted local demos with non-sensitive data.

Before internet exposure:

- Put the app behind HTTPS, set `COOKIE_SECURE=true`, and allow only the exact HTTPS origin.
- Use a least-privilege MongoDB application account. Compose's root credential is a local setup convenience, not the recommended production account.
- Add ingress rate limiting and body limits, hardened trusted-proxy configuration, malware/file handling review, backup/restore drills, and access-log monitoring.
- Add user disabling/removal, self-service password changes, stronger account recovery, role-change session revocation, and organization policies.
- Evaluate query/index performance, asynchronous Mongo access or dedicated upload services, case quotas, worker leases/retries, model reproducibility artifacts, and tamper-resistant audit storage.
- Replace in-dataset exploratory ranking with evaluated reference-baseline modeling before claiming detection effectiveness.
- Review dependency/security updates and test deployment on the target platform.

## Project layout

```text
frontend/src/       React workspace, graph, demo adapter, CSS
backend/app/        FastAPI routes, access checks, MongoDB, models, worker
backend/tests/      Workflow and security regression tests
samples/           Synthetic JSON, CSV, XML
scripts/           Local launcher
web-host/          Tracked preview-host configuration
vercel.json        Vercel Services routing for React + FastAPI
compose.yaml       Private MongoDB + API + worker deployment
```
