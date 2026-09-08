# Offline GeoIP data

Place the licensed, downloadable country and ASN MMDB files here as `country.mmdb` and `asn.mmdb` before building an offline release.

The files are mounted read-only inside the API and worker containers. They must never be downloaded at application runtime. Record the provider, database release date, license, and checksum in the delivered evidence package.

The current application preserves network observations but does not yet perform MMDB enrichment. These paths reserve the offline deployment contract for that implementation.

