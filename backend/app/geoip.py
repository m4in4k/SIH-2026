"""Offline country and ASN enrichment for network observations."""
import os
from functools import lru_cache
from pathlib import Path

import maxminddb


COUNTRY_ENV = 'GEOIP_COUNTRY_DB'
ASN_ENV = 'GEOIP_ASN_DB'
LEGACY_COUNTRY_ENV = 'SENTINEL_GEOIP_COUNTRY_DB'
LEGACY_ASN_ENV = 'SENTINEL_GEOIP_ASN_DB'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / 'geoip_data'
VPN_ASNS = {
    'AS9009', 'AS60068', 'AS20473', 'AS396507', 'AS30083', 'AS211252',
    'AS213361', 'AS209854', 'AS34788', 'AS51167', 'AS59253',
}


@lru_cache(maxsize=1)
def _tor_exits():
    path = DATA_DIR / 'tor_exits.txt'
    if not path.is_file():
        return set()
    return {
        line.strip() for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.startswith('#')
    }


def _path(kind):
    env_names = (COUNTRY_ENV, LEGACY_COUNTRY_ENV) if kind == 'country' else (ASN_ENV, LEGACY_ASN_ENV)
    for name in env_names:
        value = os.getenv(name, '').strip()
        if value:
            return value
    names = ('GeoLite2-Country.mmdb', 'country.mmdb') if kind == 'country' else ('GeoLite2-ASN.mmdb', 'asn.mmdb')
    for root in (PROJECT_ROOT / 'geoip', Path.cwd() / 'geoip', Path('/opt/sentinel/geoip')):
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
    return ''


def configured_paths():
    return {kind: _path(kind) for kind in ('country', 'asn')}


def configuration_status():
    return {
        kind: {
            'configured': bool(path),
            'available': bool(path and Path(path).is_file()),
            'filename': Path(path).name if path else None,
        }
        for kind, path in configured_paths().items()
    }


def _country(record):
    if not record:
        return {}
    value = record.get('country') or record.get('registered_country') or {}
    names = value.get('names') or {}
    result = {'country_code': value.get('iso_code'), 'country': names.get('en') or value.get('name')}
    continent = record.get('continent') or {}
    if continent.get('code'):
        result['continent_code'] = continent['code']
    return {key: value for key, value in result.items() if value is not None}


def _asn(record):
    if not record:
        return {}
    result = {
        'asn': record.get('autonomous_system_number'),
        'as_org': record.get('autonomous_system_organization'),
    }
    return {key: value for key, value in result.items() if value is not None}


def _reader_country(reader, ip):
    if hasattr(reader, 'get'):
        return _country(reader.get(ip))
    response = reader.country(ip)
    country = response.country
    continent = getattr(response, 'continent', None)
    return {
        key: value for key, value in {
            'country_code': getattr(country, 'iso_code', None),
            'country': getattr(country, 'name', None),
            'continent_code': getattr(continent, 'code', None),
        }.items() if value is not None
    }


def _reader_asn(reader, ip):
    if hasattr(reader, 'get'):
        return _asn(reader.get(ip))
    response = reader.asn(ip)
    return {
        key: value for key, value in {
            'asn': response.autonomous_system_number,
            'as_org': response.autonomous_system_organization,
        }.items() if value is not None
    }


def _readers():
    """Open configured readers. Kept as a seam for isolated tests."""
    mmap_mode = maxminddb.MODE_MMAP if hasattr(maxminddb, 'MODE_MMAP') else maxminddb.Mode.MMAP
    return tuple(
        maxminddb.open_database(path, mode=mmap_mode) if path and Path(path).is_file() else None
        for path in configured_paths().values()
    )


def clear_reader_cache():
    """Compatibility hook; readers are intentionally scoped to each import."""


class GeoIPEnricher:
    def __init__(self, country_reader=None, asn_reader=None, filenames=None, errors=None):
        self.country_reader = country_reader
        self.asn_reader = asn_reader
        self.filenames = filenames or {}
        self.errors = errors or []
        self._cache = {}

    @classmethod
    def from_environment(cls):
        paths = configured_paths()
        filenames = {kind: Path(path).name for kind, path in paths.items() if path}
        errors = []
        readers = [None, None]
        try:
            readers = list(_readers())
        except Exception as exc:
            errors.append(f'GeoIP database could not be opened: {type(exc).__name__}.')
        for kind, path in paths.items():
            if path and not Path(path).is_file():
                errors.append(f'{kind.title()} GeoIP database was not found at the configured local path.')
        return cls(readers[0], readers[1], filenames, errors)

    @property
    def available(self):
        return self.country_reader is not None or self.asn_reader is not None

    def close(self):
        for reader in (self.country_reader, self.asn_reader):
            if reader is not None and hasattr(reader, 'close'):
                reader.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def lookup(self, ip):
        if not ip:
            return {}
        if ip in self._cache:
            return dict(self._cache[ip])
        result = {}
        if self.country_reader is not None:
            try:
                result.update(_reader_country(self.country_reader, ip))
            except Exception:
                pass
        if self.asn_reader is not None:
            try:
                result.update(_reader_asn(self.asn_reader, ip))
            except Exception:
                pass
        is_tor = ip in _tor_exits()
        if result:
            result['source'] = 'offline_mmdb'
            asn = result.get('asn')
            asn_label = str(asn).upper() if str(asn).upper().startswith('AS') else f'AS{asn}'
            result['is_vpn'] = asn is not None and asn_label in VPN_ASNS
            result['is_tor'] = is_tor
        elif is_tor:
            result = {'is_tor': True, 'is_vpn': False, 'source': 'offline_list'}
        self._cache[ip] = dict(result)
        return result

    @staticmethod
    def _dataset_geo(observation, side):
        if side == 'src':
            country = observation.get('src_country') or observation.get('country') or observation.get('geo_country')
            asn = observation.get('src_asn') or observation.get('asn') or observation.get('ASN')
            organization = observation.get('src_asn_org') or observation.get('asn_org')
        else:
            country = observation.get('dst_country')
            asn = observation.get('dst_asn')
            organization = observation.get('dst_asn_org')
        return {key: value for key, value in {'country': country, 'asn': asn, 'as_org': organization}.items() if value is not None}

    def enrich(self, observations):
        enriched = []
        unique_ips = set()
        matched_ips = set()
        country_matches = set()
        asn_matches = set()
        for original in observations:
            observation = dict(original)
            for side in ('src', 'dst'):
                ip = observation.get(f'{side}_ip')
                if not ip:
                    continue
                unique_ips.add(ip)
                geo = self.lookup(ip)
                supplied = self._dataset_geo(observation, side)
                supplied_used = False
                for key, value in supplied.items():
                    if geo.get(key) is None:
                        geo[key] = value
                        supplied_used = True
                if geo:
                    observation['is_tor'] = bool(observation.get('is_tor') or geo.pop('is_tor', False))
                    observation['is_vpn'] = bool(observation.get('is_vpn') or geo.pop('is_vpn', False))
                    if not geo.get('source'):
                        geo['source'] = 'dataset'
                    elif supplied_used:
                        geo['source'] = 'offline_mmdb+dataset'
                    observation[f'{side}_geo'] = geo
                    observation[f'{side}_country'] = geo.get('country_code') or geo.get('country')
                    asn = geo.get('asn')
                    observation[f'{side}_asn'] = (
                        asn if asn is None or str(asn).upper().startswith('AS') else f'AS{asn}'
                    )
                    observation[f'{side}_asn_org'] = geo.get('as_org')
                    matched_ips.add(ip)
                    if geo.get('country') or geo.get('country_code'):
                        country_matches.add(ip)
                    if geo.get('asn') is not None:
                        asn_matches.add(ip)
            observation['country'] = observation.get('country') or observation.get('src_country') or observation.get('dst_country')
            observation['asn'] = observation.get('asn') or observation.get('src_asn') or observation.get('dst_asn')
            observation['asn_org'] = observation.get('asn_org') or observation.get('src_asn_org') or observation.get('dst_asn_org')
            enriched.append(observation)
        return enriched, {
            'mode': 'offline_mmdb' if self.available else 'dataset_only',
            'databases': self.filenames,
            'observations': len(observations),
            'unique_ips': len(unique_ips),
            'matched_ips': len(matched_ips),
            'country_matches': len(country_matches),
            'asn_matches': len(asn_matches),
            'errors': list(self.errors),
        }


def lookup(ip):
    with GeoIPEnricher.from_environment() as enricher:
        result = enricher.lookup(ip)
    return {**result, 'available': bool(result)}


def enrich_observation(observation):
    with GeoIPEnricher.from_environment() as enricher:
        rows, _ = enricher.enrich([observation])
    return rows[0]
