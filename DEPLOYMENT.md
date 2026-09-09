# Deployment guide

## Vercel + MongoDB Atlas

This repository is ready to deploy as one Vercel project. The root vercel.json defines two services: the React/Vite frontend and the Python/FastAPI backend. All /api/* traffic stays on the same public origin, so session cookies and authorization continue to work. MongoDB Atlas supplies the persistent database.

### 1. Create the database

Create a MongoDB Atlas project and cluster. The Atlas free cluster is enough for a Sentinel Tool demonstration, subject to its storage and usage limits.

Create a database user with a long, unique password and readWrite access only to the bitcoin_sentinel database. Vercel Functions use changing outbound addresses, so an Atlas free-tier deployment normally needs network access from 0.0.0.0/0. Keep the database credentials strong and narrowly scoped because that network rule permits connection attempts from anywhere.

Copy the Atlas application connection string. It should begin with mongodb+srv:// and include the database user's encoded username and password.

### 2. Import the GitHub repository into Vercel

1. In Vercel, choose **Add New -> Project** and import this repository.
2. Leave **Root Directory** at the repository root.
3. Select the **Services** framework preset. Vercel reads the frontend and backend definitions from vercel.json.
4. Do not replace the build or output settings for either service. The backend installs the checked-in locked Python dependency set, and the frontend uses its frozen pnpm lockfile.

### 3. Add environment variables

In **Project Settings -> Environment Variables**, add these values to Production and Preview:

| Name | Value |
| --- | --- |
| MONGO_URI or MONGODB_URI | The MongoDB Atlas connection string. The Vercel integration supplies MONGODB_URI automatically. |
| MONGO_DB | bitcoin_sentinel |
| BOOTSTRAP_ADMIN_EMAIL | The email address for the first administrator |
| BOOTSTRAP_ADMIN_NAME | The display name for the first administrator |
| BOOTSTRAP_ADMIN_PASSWORD | A unique password of at least 4 characters |

Vercel sets VERCEL=1, VERCEL_URL, and VERCEL_PROJECT_PRODUCTION_URL automatically. The backend uses those exact URLs for request-origin validation and automatically uses secure cookies. You do not need to set COOKIE_SECURE or SENTINEL_SERVERLESS.

If you attach a custom domain, set ALLOWED_ORIGINS to its exact HTTPS origin, for example https://sentinel.example.org. Separate multiple origins with commas and omit trailing slashes.

### 4. Deploy and initialize

Choose **Deploy**. When the deployment completes:

1. Open https://your-project.vercel.app/api/health. A healthy response is {"status":"ok","database":"mongodb"}.
2. Open the main site and sign in with the three bootstrap administrator values.
3. Create a case and load the synthetic training dataset. On Vercel the response waits for validation and analysis to finish, then the dashboard shows the completed dataset.
4. Remove the three BOOTSTRAP_ADMIN_* variables from Vercel and redeploy. The account remains in MongoDB; removing the bootstrap password reduces secret exposure.

The bootstrap routine only creates an account while the users collection is empty. It never changes an existing account or creates a second administrator.

New users can create analyst accounts from the public landing page. Each analyst initially sees no shared cases and can create a private investigation case. Viewer accounts and workspace-wide administrator access remain administrator-managed. Signup is rate-limited and never accepts a requested elevated role.

### 5. Vercel operating limits

Vercel Functions reject request and response bodies above 4.5 MB. This project therefore caps Vercel file uploads at 4 MB, including CSV, JSON, and XML. Self-hosted deployments retain the 10 MB application limit.

Analysis runs inside the upload request because a Vercel Function cannot provide the always-running polling worker used by Docker Compose. This is suitable for the bounded 10,000-record Sentinel Tool installation. If processing later exceeds the function duration, move upload content to object storage and analysis to a durable queue/worker service.

Free Vercel and MongoDB Atlas plans can remain reachable without a computer running at home, but they have quotas, cold starts, and no paid uptime guarantee. Monitor the Vercel Functions logs and Atlas metrics, and keep a database backup before demonstrations.

### 6. Verify a deployment

Check these routes from the deployed origin:

    curl --fail https://your-project.vercel.app/api/health
    curl --fail https://your-project.vercel.app/

Then verify sign-in, case creation, synthetic dataset analysis, transaction filters, the graph, alert review, timeline events, and report export in the browser. Every push to main triggers a new production deployment when Vercel Git integration is enabled.

## Docker Compose alternative

Docker Compose runs the React production build and FastAPI API in one container, a separate analysis worker, and MongoDB on a private container network.

MongoDB must run on an operating system and kernel supported by the pinned server release. MongoDB currently documents a TCMalloc incompatibility for Linux kernels 6.19 through 7.0.13. Its stable server builds can also reject newer, already-fixed kernels until the corresponding MongoDB startup-check patch is released. If `mongod` reports this guard, deploy on a supported LTS kernel, use MongoDB Atlas, or upgrade to a stable MongoDB patch that explicitly includes `SERVER-125742`; do not bypass the safety check.

For a disconnected workstation and desktop-style launch experience, use `scripts/package-offline.sh`, `compose.offline.yaml`, and the installed **Sentinel Tool** desktop entry instead of rebuilding with this development Compose file. The offline Compose network is internal, image pulls are forbidden, credentials are generated locally on first launch, and only the application port is exposed on loopback. See [OFFLINE.md](OFFLINE.md).

## 1. Prepare secrets

Copy `.env.example` to `.env`. Generate two different secrets:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Set the first as `MONGO_ROOT_PASSWORD` and the second as `MONGO_APP_PASSWORD`. Keep both values hexadecimal so they are safe inside the MongoDB connection URI. Never commit `.env`.

For a localhost or private-network demonstration, keep `COOKIE_SECURE=false` and list the exact HTTP browser origin in `ALLOWED_ORIGINS`.

For an internet deployment:

- terminate TLS at a trusted reverse proxy or platform ingress;
- set `COOKIE_SECURE=true`;
- set `ALLOWED_ORIGINS` to the exact public HTTPS origin, with no trailing slash;
- keep MongoDB and the worker off public ports;
- persist and back up the `mongo_data` volume;
- configure ingress request-size and rate limits.

## 2. Validate

Install the native development prerequisites described in `README.md`, then run:

```bash
./scripts/preflight.sh
```

The script checks backend imports, runs the regression suite, performs a locked frontend install and production build, and validates the Compose file when Docker is installed.

For a saved release copy, verify the checked-in project files against the supplied manifest:

```bash
sha256sum --check SHA256SUMS
```

## 3. Start

```bash
docker compose up --build -d
docker compose ps
docker compose exec api python -m app.manage create-admin \
  --email admin@your-team.org --name 'Team administrator'
```

Open the origin configured in `.env`. The default is `http://127.0.0.1:8080`.

The API connects as `sentinel_app`, which has read/write access only to the `bitcoin_sentinel` database. The MongoDB root credential is used only for database administration. The application user is created when the database volume is initialized for the first time.

## 4. Operate and verify

```bash
curl --fail http://127.0.0.1:8080/api/health
docker compose logs --tail=100 api worker mongo
```

A healthy response is:

```json
{"status":"ok","database":"mongodb"}
```

Use `docker compose restart` for ordinary restarts. Do not run `docker compose down -v` unless you intentionally want to delete the database volume.

When changing `MONGO_APP_PASSWORD` after initial deployment, update the MongoDB user password inside the database as well; initialization scripts do not rerun on an existing volume.
