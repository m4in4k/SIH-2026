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
