"""Offline GeoIP and ASN enrichment using local MaxMind databases."""
import ipaddress
import os
from functools import lru_cache

try:
    from geoip2.database import Reader
except ImportError:  # Keeps validation and analysis usable before dependencies are installed.
    Reader = None

COUNTRY_DB_ENV = 'GEOIP_COUNTRY_DB'
ASN_DB_ENV = 'GEOIP_ASN_DB'
DEFAULT_COUNTRY_DB = 'geoip/GeoLite2-Country.mmdb'
DEFAULT_ASN_DB = 'geoip/GeoLite2-ASN.mmdb'


def _path(name, default):
    legacy = {'GEOIP_COUNTRY_DB': 'SENTINEL_GEOIP_COUNTRY_DB', 'GEOIP_ASN_DB': 'SENTINEL_GEOIP_ASN_DB'}[name]
    return os.getenv(name, os.getenv(legacy, default)).strip() or default


@lru_cache(maxsize=1)
def _readers():
    if Reader is None:
        return None, None
    country_path = _path(COUNTRY_DB_ENV, DEFAULT_COUNTRY_DB)
    asn_path = _path(ASN_DB_ENV, DEFAULT_ASN_DB)
    country = Reader(country_path) if os.path.isfile(country_path) else None
    asn = Reader(asn_path) if os.path.isfile(asn_path) else None
    return country, asn


def clear_reader_cache():
    """Reset cached readers for tests or configuration changes."""
    _readers.cache_clear()


def lookup(ip):
    """Return best-effort offline enrichment; never raises for lookup failures."""
    if not ip:
        return {}
    try:
        address = ipaddress.ip_address(ip)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            return {'available': False, 'reason': 'private-or-reserved-ip'}
    except ValueError:
        return {'available': False, 'reason': 'invalid-ip'}
    try:
        country_reader, asn_reader = _readers()
    except Exception:
        return {'available': False, 'reason': 'database-unavailable'}
    result = {}
    if country_reader:
        try:
            country = country_reader.country(ip)
            result['country'] = country.country.iso_code or country.country.name
        except Exception:
            pass
    if asn_reader:
        try:
            asn = asn_reader.asn(ip)
            if asn.autonomous_system_number:
                result['asn'] = f'AS{asn.autonomous_system_number}'
            if asn.autonomous_system_organization:
                result['asn_org'] = asn.autonomous_system_organization
        except Exception:
            pass
    if not result:
        result['available'] = False
        result['reason'] = 'unknown-ip-or-database-unavailable'
    else:
        result['available'] = True
    return result


def enrich_observation(observation):
    """Enrich source and destination independently while preserving supplied values."""
    enriched = dict(observation)
    if enriched.get('geo_country') and not enriched.get('country'):
        enriched['country'] = enriched['geo_country']
    if enriched.get('ASN') and not enriched.get('asn'):
        enriched['asn'] = enriched['ASN']
    sources = [('src_ip', 'src_country', 'src_asn', 'src_asn_org'), ('dst_ip', 'dst_country', 'dst_asn', 'dst_asn_org')]
    for ip_field, country_field, asn_field, org_field in sources:
        values = lookup(enriched.get(ip_field))
        if values.get('country') and not enriched.get(country_field):
            enriched[country_field] = values['country']
        if values.get('asn') and not enriched.get(asn_field):
            enriched[asn_field] = values['asn']
        if values.get('asn_org') and not enriched.get(org_field):
            enriched[org_field] = values['asn_org']
    if not enriched.get('country'):
        enriched['country'] = enriched.get('src_country') or enriched.get('dst_country')
    if not enriched.get('asn'):
        enriched['asn'] = enriched.get('src_asn') or enriched.get('dst_asn')
    if not enriched.get('asn_org'):
        enriched['asn_org'] = enriched.get('src_asn_org') or enriched.get('dst_asn_org')
    if enriched.get('country') and not enriched.get('src_country'):
        enriched['src_country'] = enriched['country']
    if enriched.get('asn') and not enriched.get('src_asn'):
        enriched['src_asn'] = enriched['asn']
    if enriched.get('asn_org') and not enriched.get('src_asn_org'):
        enriched['src_asn_org'] = enriched['asn_org']
    return enriched
