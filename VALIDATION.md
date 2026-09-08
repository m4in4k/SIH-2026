# Sentinel Tool validation

## Offline GeoIP enrichment update

- Backend regression suite: all 24 tests passed with the isolated MongoDB mock, including SIH CSV conversion, Country/ASN enrichment, dataset fallback, graph nodes and edges, investigation timeline evidence, and report propagation.
- Real MMDB compatibility check: passed with the repository's Country and ASN databases through the installed MaxMind DB reader, including distinct source/destination results.
- React production build: passed with TypeScript and Vite (1,589 modules transformed).
- GeoIP processing remains fully offline at runtime. Operators supply locally licensed/downloaded MMDB files; no lookup API is called and no network observation leaves the machine.

## Vercel readiness update

- Vercel Services configuration matches the current service schema: Vite and FastAPI build from separate roots, API rewrites precede the frontend catch-all, and the backend entry point is app.main:app.
- Backend regression suite: all 19 tests passed under Python 3.14 with the locked dependencies and isolated MongoDB mock. Coverage verifies self-service analyst signup, password hashing, signup and login throttling, case isolation, request-scoped Vercel analysis, exact-origin trust, secure cookies, the 4 MB Vercel upload limit, and one-time administrator creation.
- React production build: passed with TypeScript and Vite (1,584 modules transformed).
- JSON parsing, Python syntax parsing, Git whitespace checks, and Vercel source exclusions passed.
- MongoDB Atlas credentials and a Vercel account are intentionally not stored in the repository. A live cloud deployment still requires the dashboard steps in DEPLOYMENT.md; no claim of live Atlas/Vercel integration testing is made.

## Deployment readiness update

- Saved-project integrity: matched the validated source copy before deployment changes; required lockfiles, samples, and configuration files are present and non-empty.
- React production build: passed again from the saved Sentinel Tool workspace (1,584 modules transformed).
- Backend regression suite: all 15 tests passed from the saved Sentinel Tool workspace using the isolated test database.
- Production browser smoke test: passed from the compiled `frontend/dist` build at `127.0.0.1:5173`; overview metrics, transaction table, advanced filters, and investigation timeline rendered and navigated without recent console errors.
- Python import compilation, shell syntax, MongoDB initialization-script syntax, and Git whitespace checks: passed.
- Application container build: passed with Podman from the saved directory, including frozen frontend installation, TypeScript/Vite production build, pinned Python dependencies, and the non-root runtime stage.
- `SHA256SUMS`: generated and verified successfully for all deployment source and configuration files. Generated dependencies, build output, caches, Git metadata, and PDF working files are intentionally excluded.
- Deployment hardening: the API now uses a dedicated MongoDB application account, MongoDB is pinned to 8.0.29, container health checks are defined, and a repeatable preflight/deployment guide is included.
- Container runtime limitation on this workstation: Linux `7.1.10-200.fc44.x86_64` is rejected by the currently stable MongoDB startup guard. MongoDB documents the affected kernel range and tracks recognition of fixed kernels under `SERVER-125742`. The project remains ready for a supported LTS deployment host or MongoDB Atlas; an end-to-end local Compose start could not be completed on this kernel.

- React production build: passed (TypeScript + Vite).
- Fifteen backend regression tests: passed against real MongoDB Community 8.0.28. Each test used an isolated database, removed afterward.
- Live HTTP integration through the React development proxy: passed for sign-in, combined transaction filters, confirmation/script metadata, resolved input evidence, stage-filtered alerts, processing timeline, evidence export, oversized numeric-filter rejection, and logout.
- Existing cases and review history were preserved. A separate synthetic case, `Detection trace · training`, was added to demonstrate the new recorded stages.

Coverage includes the original import → analysis → graph → review → report workflow, case isolation, viewer restrictions, session expiry, CSRF checks, login throttling, duplicate lineage, XML entity rejection, uniform-data scoring, combined filters, pagination, unknown values, timezone validation, rich transaction details, rule/model threshold evidence, dual detections, stage ordering, actual detection timestamps, skipped model stages, failed validation events, and legacy records without fabricated history.

No cloud/LAN deployment, large-scale load testing, or real-world model-accuracy validation was performed. One upstream test-client deprecation warning remains; there were no test failures in the final suite.

The current browser preview serves the compiled, read-only synthetic demo. Authenticated case work requires MongoDB on a supported host or Atlas. Preview credentials remain outside this saved project. Follow README.md and DEPLOYMENT.md for durable installation and deployment hardening.
