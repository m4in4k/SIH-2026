<<<<<<< HEAD
"""Offline GeoIP enrichment — no external runtime calls.

Uses a bundled IP-range CSV (ip_ranges.csv, generated from public domain sources)
and a bundled Tor-exit list. Falls back gracefully to 'Unknown' if the files
are absent so the rest of the pipeline always completes.
"""
import ipaddress
import csv
import os
from functools import lru_cache
from pathlib import Path

# Known VPN / anonymiser ASNs (public list, non-exhaustive)
_VPN_ASNS = {
    'AS9009','AS60068','AS16509','AS14618','AS15169',  # Major cloud (false-pos prone but relevant)
    'AS20473','AS7922','AS4134','AS4837',               # Common VPN providers
    'AS396507','AS30083','AS211252','AS213361',         # NordVPN, ExpressVPN, etc.
    'AS209854','AS34788','AS51167','AS59253',
}

_DATA_DIR = Path(__file__).parent / 'geoip_data'


@lru_cache(maxsize=1)
def _load_ranges():
    """Return sorted list of (start_int, end_int, country, asn) tuples."""
    path = _DATA_DIR / 'ip_ranges.csv'
    if not path.exists():
        return []
    ranges = []
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) < 4 or row[0].startswith('#'):
                continue
            try:
                ranges.append((int(row[0]), int(row[1]), row[2], row[3]))
            except (ValueError, IndexError):
                continue
    ranges.sort(key=lambda r: r[0])
    return ranges


@lru_cache(maxsize=1)
def _load_tor_exits():
    """Return set of Tor exit IP strings."""
    path = _DATA_DIR / 'tor_exits.txt'
    if not path.exists():
        return set()
    exits = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                exits.add(line)
    return exits


def _ip_to_int(ip: str) -> int | None:
    try:
        return int(ipaddress.ip_address(ip))
    except ValueError:
        return None


def lookup(ip: str) -> dict:
    """Return {'country': str, 'asn': str, 'is_tor': bool, 'is_vpn': bool}."""
    ip_int = _ip_to_int(ip)
    country = 'Unknown'
    asn = ''
    if ip_int is not None:
        ranges = _load_ranges()
        # Binary search for the range containing ip_int
        lo, hi = 0, len(ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end, c, a = ranges[mid]
            if ip_int < start:
                hi = mid - 1
            elif ip_int > end:
                lo = mid + 1
            else:
                country, asn = c, a
                break
    is_tor = ip in _load_tor_exits()
    is_vpn = asn in _VPN_ASNS
    return {'country': country, 'asn': asn or 'Unknown', 'is_tor': is_tor, 'is_vpn': is_vpn}


def enrich_observations(observations: list[dict]) -> list[dict]:
    """Add geo fields to a list of observation dicts in-place. Returns the list."""
    for obs in observations:
        for field in ('src_ip', 'dst_ip', 'peer_ip'):
            ip = obs.get(field)
            if ip and not obs.get('country'):
                geo = lookup(ip)
                obs.setdefault('country', geo['country'])
                obs.setdefault('asn', geo['asn'])
                obs['is_tor'] = obs.get('is_tor') or geo['is_tor']
                obs['is_vpn'] = obs.get('is_vpn') or geo['is_vpn']
                break
    return observations
=======
"""Offline GeoIP and ASN enrichment using local MaxMind databases."""
import ipaddress
import os
from functools import lru_cache

try:
    from geoip2.database import Reader
except ImportError:  # Keeps validation and analysis usable before dependencies are installed.
    Reader = None

COUNTRY_DB_ENV = 'SENTINEL_GEOIP_COUNTRY_DB'
ASN_DB_ENV = 'SENTINEL_GEOIP_ASN_DB'
DEFAULT_COUNTRY_DB = 'geoip/GeoLite2-Country.mmdb'
DEFAULT_ASN_DB = 'geoip/GeoLite2-ASN.mmdb'


def _path(name, default):
    return os.getenv(name, default).strip() or default


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
    return enriched
>>>>>>> 8bd8a2169d83afd7ad90d8125606ba357648d268
