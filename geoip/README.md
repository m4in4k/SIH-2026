# Offline GeoIP data

Place compatible, licensed country and ASN MaxMind DB files here as `GeoLite2-Country.mmdb` and `GeoLite2-ASN.mmdb` before building an offline release. Native installs may alternatively use `country.mmdb` and `asn.mmdb` or configure absolute paths through the documented environment variables.

The files are mounted read-only inside the API and worker containers. They must never be downloaded at application runtime. Record the provider, database release date, license, and checksum in the delivered evidence package.

During ingestion Sentinel looks up both `src_ip` and `dst_ip`, stores distinct `src_geo` and `dst_geo` evidence, records database/match statistics in the `geoip_enrichment` pipeline stage, and exposes the results in transaction details, timelines, graphs, and evidence reports. A lookup is attribution metadata only; it does not establish transaction origin, device identity, wallet ownership, or intent.

