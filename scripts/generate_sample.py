#!/usr/bin/env python3
"""
generate_sample.py — SIH-2026 Bitcoin Intelligence Dataset Generator

Generates a synthetic dataset containing all required fields from the SIH-2026
problem statement, including IP/port metadata and GeoIP observations.

Usage:
    python scripts/generate_sample.py --count 500 --format json --output samples/dataset.json
    python scripts/generate_sample.py --count 100 --format csv  --output samples/dataset.csv
    python scripts/generate_sample.py --count 50  --format xml  --output samples/dataset.xml
"""
import argparse
import csv
import json
import random
import sys
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

# Add backend to path so we can import training_data
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

def generate_dataset(count: int = 500) -> dict:
    """Generate the full dataset using the backend training_data logic."""
    try:
        from app.analysis import training_data
        raw = json.loads(training_data().decode())
        # Trim or extend to requested count
        txs = raw['transactions'][:count]
        obs = raw.get('observations', [])
        return {'transactions': txs, 'observations': obs, 'synthetic': True}
    except ImportError:
        print("Backend not available, using standalone generator...")
        return _standalone_generate(count)


def _standalone_generate(count: int) -> dict:
    """Fallback standalone generator (no backend imports needed)."""
    rng = random.Random(42)
    base = datetime(2026, 1, 15, tzinfo=timezone.utc)
    rows = []
    observations = []

    ip_pools = {
        'US': ['13.52.1.1', '52.86.4.2', '18.144.3.3', '34.212.4.4'],
        'RU': ['46.148.1.10', '77.88.2.20', '81.19.3.30', '176.9.4.40'],
        'CN': ['1.179.1.100', '27.155.2.200', '114.114.3.3', '221.12.4.4'],
        'DE': ['78.46.1.1', '88.198.2.2', '85.10.3.3', '213.239.4.4'],
        'NL': ['185.220.101.1', '89.163.2.2', '91.218.3.3', '84.200.4.4'],
    }

    available = []

    for i in range(count):
        txid = sha256(f'standalone-v1-{i}'.encode()).hexdigest()
        ts = base + timedelta(hours=rng.randint(0, 720))

        if available:
            prev = available.pop(0)
            ins = [{'prev_txid': prev['txid'], 'prev_vout': prev['index']}]
            budget = prev['value_sats']
        else:
            ins = []
            budget = rng.randint(5_000_000_000, 50_000_000_000)

        fee = max(200, budget // 500)
        n_out = rng.choice([1, 2, 2, 3])

        # Insert anomalies
        if i % 25 == 0:
            n_out = rng.randint(12, 18)  # fan-out

        each = (budget - fee) // n_out
        outputs = [
            {
                'index': j,
                'value_sats': each + (budget - fee - each * n_out if j == 0 else 0),
                'address': f'bc1q{sha256(f"{i}-{j}".encode()).hexdigest()[:26]}',
                'script_type': rng.choice(['p2wpkh', 'p2sh', 'p2pkh', 'p2wsh']),
            }
            for j in range(n_out)
        ]

        for o in outputs:
            if o['value_sats'] > 10_000:
                available.append({'txid': txid, **o})

        confirmed = i < int(count * 0.9)
        rows.append({
            'txid': txid,
            'observed_at': ts.isoformat(),
            'inputs': ins,
            'outputs': outputs,
            'fee_sats': fee if rng.random() > 0.1 else None,
            'vsize': 141 + len(ins) * 41 + n_out * 32,
            'size_bytes': 190 + len(ins) * 41 + n_out * 32,
            'weight': (141 + len(ins) * 41 + n_out * 32) * 4,
            'version': 2,
            'locktime': 0,
            'confirmed': confirmed,
            'confirmations': rng.randint(1, 500) if confirmed else 0,
            'block_height': 880_000 + i // 10 if confirmed else None,
            'block_time': (ts + timedelta(minutes=10)).isoformat() if confirmed else None,
        })

        # Network observations for 30% of transactions
        if rng.random() < 0.3:
            country = rng.choice(list(ip_pools.keys()))
            ip = rng.choice(ip_pools[country])
            asns = {'US': 'AS16509', 'DE': 'AS3320', 'NL': 'AS9009', 'RU': 'AS12389', 'CN': 'AS4134'}
            observations.append({
                'txid': txid,
                'observed_at': ts.isoformat(),
                'src_ip': ip,
                'dst_ip': rng.choice(ip_pools['US']),
                'src_port': rng.randint(10000, 65535),
                'dst_port': 8333,
                'country': country,
                'asn': asns[country],
                'is_tor': False,
                'is_vpn': country == 'NL',
                'sensor': 'synthetic-sensor-standalone',
            })

    return {'transactions': rows, 'observations': observations, 'synthetic': True}


def write_json(data: dict, path: Path):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f"Wrote {len(data['transactions'])} transactions + {len(data.get('observations', []))} observations → {path}")


def write_csv(data: dict, path: Path):
    rows = data['transactions']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['txid', 'observed_at', 'block_time', 'confirmed', 'confirmations',
                      'block_height', 'fee_sats', 'vsize', 'size_bytes', 'weight',
                      'version', 'locktime', 'inputs', 'outputs']
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            row = dict(r)
            row['inputs'] = json.dumps(r.get('inputs', []))
            row['outputs'] = json.dumps(r.get('outputs', []))
            w.writerow(row)
    print(f"Wrote {len(rows)} transactions → {path} (observations not in CSV; export as JSON for full data)")


def write_xml(data: dict, path: Path):
    root = Element('dataset')
    root.set('synthetic', 'true')
    txs_el = SubElement(root, 'transactions')
    for r in data['transactions']:
        tx = SubElement(txs_el, 'transaction')
        for key, val in r.items():
            if key in ('inputs', 'outputs'):
                continue
            el = SubElement(tx, key)
            el.text = '' if val is None else str(val)
        ins_el = SubElement(tx, 'inputs')
        for inp in r.get('inputs', []):
            i_el = SubElement(ins_el, 'input')
            for k, v in inp.items():
                i_el.set(k, str(v))
        outs_el = SubElement(tx, 'outputs')
        for out in r.get('outputs', []):
            o_el = SubElement(outs_el, 'output')
            for k, v in out.items():
                o_el.set(k, '' if v is None else str(v))
    obs_el = SubElement(root, 'observations')
    for obs in data.get('observations', []):
        o = SubElement(obs_el, 'observation')
        for k, v in obs.items():
            o.set(k, '' if v is None else str(v))
    indent(root)
    ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    print(f"Wrote {len(data['transactions'])} transactions + {len(data.get('observations', []))} observations → {path}")


def main():
    parser = argparse.ArgumentParser(description='SIH-2026 Bitcoin dataset generator')
    parser.add_argument('--count', type=int, default=500, help='Number of transactions to generate')
    parser.add_argument('--format', choices=['json', 'csv', 'xml'], default='json')
    parser.add_argument('--output', default=None, help='Output file path')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    args = parser.parse_args()

    output = Path(args.output) if args.output else Path(f'samples/generated-{args.count}.{args.format}')
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.count} synthetic transactions (seed={args.seed})…")
    data = generate_dataset(args.count)

    {'json': write_json, 'csv': write_csv, 'xml': write_xml}[args.format](data, output)
    print("Done.")


if __name__ == '__main__':
    main()
