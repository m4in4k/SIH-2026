# Sentinel Tool — technical approach

## System approach

Sentinel Tool is an offline-first Linux investigation application built with React, FastAPI, MongoDB, and a separate analysis worker. An investigator signs in, creates or selects a case, and uploads CSV, JSON, or XML evidence. The parser validates and normalizes blockchain fields and SIH-style network fields, records the source-file SHA-256 hash and record lineage, and correlates observations to transactions through `txid`.

Network evidence keeps source and destination IP, port, sensor, and observation time separate. Country and ASN data are read from local MaxMind DB files. Sentinel stores distinct source and destination enrichment with provenance; no IP address is submitted to an external lookup service. A relay observation is evidence that a sensor saw a peer relay a transaction, not proof of transaction origin, device identity, or wallet ownership.

The worker persists transactions, observations, feature vectors, alerts, processing-stage events, and entity clusters. The dashboard exposes ranked leads, transaction details, a processing timeline, geographic summaries, entity clusters, and a link graph connecting transactions, wallet/address nodes, IPs, countries, and ASNs. A versioned JSON evidence report contains the source metadata and evidence used for review.

## Detection model

The working ML use case is an Isolation Forest trained locally on each imported dataset when at least 40 valid transactions are available. It uses 14 blockchain and network features: input count, output count, log output value, largest-output share, log fee rate, missing-fee indicator, output-value entropy, round-output fraction, off-hours indicator, unique relay-IP count, cross-border indicator, Tor/VPN relay indicator, transaction size, and fee per output.

Raw model anomaly values are converted into within-dataset mid-rank percentiles. A score at or above the configured 97th percentile creates a model lead. These scores rank unusual records inside the current dataset; they are not calibrated probabilities of criminal activity and should not be compared as if they were probabilities across unrelated datasets.

Interpretable rules run alongside the model for fan-in, fan-out, peel-chain behavior, structuring, repeated round outputs, off-hours large transfers, cross-border relays, and Tor/VPN relay evidence. Rules remain useful on small datasets where an Isolation Forest result would be unreliable. The final 0–100 lead-confidence score combines rule priority with the anomaly percentile and is explicitly labeled as an investigative ranking, not proof of wrongdoing.

## Explainability

Every alert stores the detector, stage, observed value, comparison operator, threshold, timestamp, and a plain-language reason. For model results, Sentinel estimates per-feature contributions by replacing one feature at a time with the dataset median and measuring the change in Isolation Forest score. The UI displays the strongest positive and negative contributions and their underlying values.

This is a local perturbation explanation (SHAP-style), not exact SHAP and not causal attribution. The alert also records plausible benign alternatives such as payment batching, wallet maintenance, or consolidation. Investigators must validate ownership, intent, and external evidence before drawing conclusions.

## Entity clustering

Wallet/address clusters use common-input co-occurrence evidence, while IP clusters use relay co-occurrence. Clusters receive risk scores from the alerts associated with their supporting transactions and are shown with the supporting entities and transactions. These clusters are investigative hypotheses; shared infrastructure, custodial services, and CoinJoin-like activity can invalidate a common-ownership interpretation.

## Offline operation

The transferable Linux package contains the application image and MongoDB image. The desktop launcher generates local credentials, starts the internal Compose network, waits for health checks, and opens the browser. Normal analysis, authentication, storage, GeoIP lookup, ML inference, clustering, graphs, and reporting require no internet connection. GeoIP database updates and release construction happen on a connected preparation machine before the package is transferred to the isolated workstation.

The hosted Vercel instance is a separate online deployment and must not be described as offline. The Linux package is the complete offline execution path.
