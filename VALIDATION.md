# Validation — investigation enhancements, 2026-09-01

- React production build: passed (TypeScript + Vite).
- Fifteen backend regression tests: passed against real MongoDB Community 8.0.28. Each test used an isolated database, removed afterward.
- Live HTTP integration through the React development proxy: passed for sign-in, combined transaction filters, confirmation/script metadata, resolved input evidence, stage-filtered alerts, processing timeline, schema 1.1 evidence export, oversized numeric-filter rejection, and logout.
- Existing cases and review history were preserved. A separate synthetic case, `Detection trace · training`, was added to demonstrate the new recorded stages.

Coverage includes the original import → analysis → graph → review → report workflow, case isolation, viewer restrictions, session expiry, CSRF checks, login throttling, duplicate lineage, XML entity rejection, uniform-data scoring, combined filters, pagination, unknown values, timezone validation, rich transaction details, rule/model threshold evidence, dual detections, stage ordering, actual detection timestamps, skipped model stages, failed validation events, and legacy records without fabricated history.

No browser screenshot/interaction QA, container image build, cloud/LAN deployment, large-scale load testing, or real-world model-accuracy validation was performed. One upstream test-client deprecation warning remains; there were no test failures in the final suite.

The running preview uses local MongoDB with synthetic data. Credentials remain only in `.local/preview-access.txt` and are excluded from the project archive. Follow README.md for durable installation and deployment hardening.
