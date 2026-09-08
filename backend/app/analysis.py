"""Exploratory in-dataset anomaly ranking. No attribution or crime probabilities.

AI/ML pipeline:
  Stage 1 — Feature engineering (14 blockchain + network features)
  Stage 2 — Rule detection (fan-out, fan-in, structuring, peel-chain, round-number,
             off-hours burst, Tor/VPN IP, cross-border IP)
  Stage 3 — Isolation Forest model scoring (anomaly percentile)
  Stage 4 — Feature-contribution explainability (manual SHAP-style attribution)
  Stage 5 — Alert generation with ranked, explainable output
"""
import csv
import io
import json
import math
import statistics
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from defusedxml import ElementTree
from pydantic import ValidationError
from sklearn.ensemble import IsolationForest
from .models import Transaction, Observation

MODEL_VERSION = 'sentinel-iforest-shap-v3'
MAX_RECORDS = 10000

FEATURE_NAMES = [
    'input_count',
    'output_count',
    'log_output_total',
    'largest_output_share',
    'log_fee_rate',
    'fee_rate_missing',
    'output_value_entropy',
    'round_output_fraction',
    'is_off_hours',
    'unique_ip_count',
    'cross_border_flag',
    'tor_vpn_ip_flag',
    'tx_size_bytes',
    'fee_per_output',
]

FEATURE_DESCRIPTIONS = {
    'input_count': 'Number of inputs (high = consolidation/mixing)',
    'output_count': 'Number of outputs (high = fan-out/mixing)',
    'log_output_total': 'Log of total output value in satoshis',
    'largest_output_share': 'Fraction of value in the largest output (1.0 = single recipient)',
    'log_fee_rate': 'Log of fee rate sat/vbyte (high = urgency; missing = anomalous)',
    'fee_rate_missing': 'Binary: fee data absent from record',
    'output_value_entropy': 'Shannon entropy of output values (0=uniform, high=varied)',
    'round_output_fraction': 'Fraction of outputs with round BTC values (structuring indicator)',
    'is_off_hours': 'Binary: transaction observed between 00:00–05:00 UTC',
    'unique_ip_count': 'Number of unique IPs that relayed this TX (network anomaly)',
    'cross_border_flag': 'Binary: TX relayed from >1 country',
    'tor_vpn_ip_flag': 'Binary: TX relayed via Tor or known VPN ASN',
    'tx_size_bytes': 'Transaction size in bytes (proxy for complexity)',
    'fee_per_output': 'Log of fee per output (normalised complexity cost)',
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _btc_to_sats(value, field, record):
    try:
        sats = Decimal(str(value)) * Decimal(100_000_000)
    except (InvalidOperation, TypeError):
        raise ValueError(f'Record {record}: {field} must be a numeric BTC amount.')
    if not sats.is_finite() or sats != sats.to_integral_value() or sats < 0:
        raise ValueError(f'Record {record}: {field} must be a non-negative whole satoshi amount.')
    return int(sats)


def _flat_csv_row(row, record):
    required = {'tx_id', 'from_address', 'to_address', 'amount_btc', 'fee_btc', 'input_count', 'output_count'}
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f'Record {record}: missing flat CSV fields: {", ".join(missing)}.')
    try:
        input_count = int(row['input_count'])
        output_count = int(row['output_count'])
    except (TypeError, ValueError):
        raise ValueError(f'Record {record}: input_count and output_count must be integers.')
    if input_count < 0 or output_count < 1:
        raise ValueError(f'Record {record}: input_count must be non-negative and output_count must be positive.')
    txid = row['tx_id'].strip().lower()
    total_sats = _btc_to_sats(row['amount_btc'], 'amount_btc', record)
    base, remainder = divmod(total_sats, output_count)
    outputs = [
        {'index': index, 'value_sats': base + (1 if index < remainder else 0),
         'address': row['to_address'].strip() or None}
        for index in range(output_count)
    ]
    inputs = [
        {'prev_txid': sha256(f'{txid}:flat-input:{index}'.encode()).hexdigest(), 'prev_vout': 0}
        for index in range(input_count)
    ]
    return {
        'txid': txid,
        'observed_at': row.get('timestamp') or row.get('observed_at') or None,
        'inputs': inputs,
        'outputs': outputs,
        'fee_sats': _btc_to_sats(row['fee_btc'], 'fee_btc', record),
        'vsize': 1,
    }


def _sih_row(row, record):
    required = {'txid', 'input_addresses', 'output_addresses', 'input_amounts', 'output_amounts'}
    if not required.issubset(row):
        return None

    def values(field):
        value = row.get(field) or []
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, list):
            raise ValueError(f'Record {record}: {field} must be an array.')
        return value

    input_addresses = values('input_addresses')
    output_addresses = values('output_addresses')
    input_amounts = values('input_amounts')
    output_amounts = values('output_amounts')
    if len(output_addresses) != len(output_amounts) or not output_addresses:
        raise ValueError(f'Record {record}: output_addresses and output_amounts must have the same non-zero length.')
    if len(input_addresses) != len(input_amounts):
        raise ValueError(f'Record {record}: input_addresses and input_amounts must have the same length.')
    txid = str(row['txid']).strip().lower()
    inputs = [
        {'prev_txid': sha256(f'{txid}:input:{address}:{index}'.encode()).hexdigest(), 'prev_vout': 0}
        for index, address in enumerate(input_addresses)
    ]
    outputs = [
        {'index': index, 'value_sats': _btc_to_sats(amount, 'output_amounts', record),
         'address': str(address).strip() or None}
        for index, (address, amount) in enumerate(zip(output_addresses, output_amounts))
    ]
    normalized = {
        'txid': txid,
        'observed_at': row.get('timestamp') or row.get('observed_at'),
        'inputs': inputs,
        'outputs': outputs,
        'fee_sats': None,
        'vsize': 1,
    }
    if row.get('fee_btc') not in (None, ''):
        normalized['fee_sats'] = _btc_to_sats(row['fee_btc'], 'fee_btc', record)
    return normalized


def _network_observation(row):
    if not row.get('txid') or not (row.get('src_ip') or row.get('dst_ip')):
        return None
    observation = {
        key: row[key] for key in (
            'txid', 'src_ip', 'dst_ip', 'src_port', 'dst_port', 'country', 'geo_country',
            'asn', 'ASN', 'asn_org', 'timestamp', 'observed_at', 'sensor'
        ) if row.get(key) not in (None, '')
    }
    if 'geo_country' in observation and 'country' not in observation:
        observation['country'] = observation.pop('geo_country')
    if 'ASN' in observation and 'asn' not in observation:
        observation['asn'] = observation.pop('ASN')
    observation['observed_at'] = observation.get('observed_at') or observation.pop('timestamp', None)
    observation['sensor'] = observation.get('sensor') or 'dataset-import'
    for key in ('src_port', 'dst_port'):
        if key in observation:
            observation[key] = int(observation[key])
    return observation

def parse(content: bytes, filename: str):
    text = content.decode('utf-8-sig')
    observations = []
    if filename.lower().endswith('.json'):
        raw = json.loads(text)
        rows = raw if isinstance(raw, list) else raw.get('transactions', [])
        if isinstance(raw, dict):
            observations = raw.get('observations', [])
    elif filename.lower().endswith('.csv'):
        rows = list(csv.DictReader(io.StringIO(text)))
        flat_fields = {'tx_id', 'from_address', 'to_address', 'amount_btc', 'fee_btc', 'input_count', 'output_count'}
        sih_fields = {'txid', 'input_addresses', 'output_addresses', 'input_amounts', 'output_amounts'}
        if rows and flat_fields.issubset(rows[0]):
            rows = [_flat_csv_row(row, number) for number, row in enumerate(rows, 1)]
        elif rows and sih_fields.issubset(rows[0]):
            observations.extend(filter(None, (_network_observation(row) for row in rows)))
            rows = [_sih_row(row, number) for number, row in enumerate(rows, 1)]
        for row in rows:
            for key in ['inputs', 'outputs']:
                if isinstance(row.get(key), str):
                    row[key] = json.loads(row.get(key) or '[]')
            for key in ['fee_sats', 'vsize', 'confirmations', 'block_height',
                        'size_bytes', 'weight', 'version', 'locktime']:
                row[key] = int(row[key]) if row.get(key) else None
            for key in ['observed_at', 'block_time']:
                row[key] = row.get(key) or None
    elif filename.lower().endswith('.xml'):
        root = ElementTree.fromstring(text)
        rows = []
        for node in root.findall('transaction'):
            row = {child.tag: child.text for child in node if child.tag not in {'inputs', 'outputs'}}
            row['inputs'] = [dict(i.attrib) for i in node.findall('inputs/input')]
            row['outputs'] = [dict(o.attrib) for o in node.findall('outputs/output')]
            for entry in row['inputs']:
                entry['prev_vout'] = int(entry['prev_vout'])
                if entry.get('sequence') is not None:
                    entry['sequence'] = int(entry['sequence'])
            for entry in row['outputs']:
                entry['index'] = int(entry['index'])
                entry['value_sats'] = int(entry['value_sats'])
            for key in ['fee_sats', 'vsize', 'confirmations', 'block_height',
                        'size_bytes', 'weight', 'version', 'locktime']:
                row[key] = int(row[key]) if row.get(key) else None
            rows.append(row)
        observations = [
            {**node.attrib, **{child.tag: child.text for child in node}}
            for node in root.findall('observation')
        ]
        for observation in observations:
            for key in ['peer_port', 'src_port', 'dst_port']:
                if observation.get(key):
                    observation[key] = int(observation[key])
    else:
        raise ValueError('Use .json, .csv, or .xml files.')
    if rows and isinstance(rows[0], dict) and {
        'txid', 'input_addresses', 'output_addresses', 'input_amounts', 'output_amounts'
    }.issubset(rows[0]):
        observations.extend(filter(None, (_network_observation(row) for row in rows)))
        rows = [_sih_row(row, number) for number, row in enumerate(rows, 1)]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_RECORDS:
        raise ValueError(f'Import between 1 and {MAX_RECORDS:,} transactions per file.')
    if not isinstance(observations, list) or len(observations) > MAX_RECORDS:
        raise ValueError('Import at most 10,000 network observations.')
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get('confirmed'), str):
            flag = row['confirmed'].strip().lower()
            if flag not in {'true', 'false', ''}:
                raise ValueError('confirmed must be true, false, or empty.')
            row['confirmed'] = {'true': True, 'false': False, '': None}[flag]
        if isinstance(row, dict) and row.get('block_hash') == '':
            row['block_hash'] = None
    seen = set(); result = []; duplicate = 0
    for n, row in enumerate(rows, 1):
        try:
            tx = Transaction.model_validate(row).model_dump()
        except ValidationError as exc:
            err = exc.errors()[0]
            raise ValueError(f'Record {n}: {".".join(map(str, err["loc"]))}: {err["msg"]}') from exc
        if tx['txid'] in seen:
            duplicate += 1
            continue
        seen.add(tx['txid'])
        tx['source_record'] = n
        result.append(tx)
    try:
        obs = [Observation.model_validate(o).model_dump() for o in observations]
    except ValidationError as exc:
        err = exc.errors()[0]
        raise ValueError(f'Observation: {".".join(map(str, err["loc"]))}: {err["msg"]}') from exc
    warnings = []
    if duplicate:
        warnings.append(f'{duplicate} duplicate TXIDs within this file were skipped.')
    if any(t['fee_sats'] is None for t in result):
        warnings.append('Missing fees are not inferred; the model includes a missing-fee indicator.')
    if any(t['observed_at'] is None for t in result):
        warnings.append('Some observation timestamps are missing. Block time is displayed separately where available.')
    return result, obs, warnings


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _entropy(values: list[int]) -> float:
    if not values:
        return 0.0
    total = sum(values)
    if total == 0:
        return 0.0
    probs = [v / total for v in values if v > 0]
    return -sum(p * math.log2(p) for p in probs)


def _is_round_btc(sats: int) -> bool:
    """True if the output value is a round number of BTC/mBTC/bits."""
    if sats == 0:
        return False
    # Round BTC: divisible by 1_000_000 (0.01 BTC)
    if sats % 1_000_000 == 0:
        return True
    # Round mBTC: divisible by 100_000 (0.001 BTC)
    if sats % 100_000 == 0:
        return True
    return False


def _build_obs_index(observations: list[dict]) -> dict[str, list[dict]]:
    """Index observations by txid for O(1) lookup."""
    index: dict[str, list[dict]] = {}
    for obs in observations:
        txid = obs.get('txid', '')
        index.setdefault(txid, []).append(obs)
    return index


def _extract_features(t: dict, obs_for_tx: list[dict]) -> list[float]:
    vals = [o['value_sats'] for o in t['outputs']]
    total = sum(vals)
    n_out = len(vals)
    n_in = len(t['inputs'])
    rate = t['fee_sats'] / t['vsize'] if t['fee_sats'] is not None and t['vsize'] else None

    # Output entropy
    entropy = _entropy(vals)

    # Round-number fraction
    round_frac = sum(1 for v in vals if _is_round_btc(v)) / max(n_out, 1)

    # Off-hours (midnight to 5am UTC)
    off_hours = 0
    ts = t.get('observed_at') or t.get('block_time')
    if ts:
        try:
            hour = ts.hour if hasattr(ts, 'hour') else datetime.fromisoformat(str(ts).replace('Z', '+00:00')).hour
            off_hours = 1 if hour < 5 else 0
        except Exception:
            off_hours = 0

    # Network-layer features
    unique_ips = len({obs.get('src_ip') or obs.get('dst_ip') or obs.get('peer_ip')
                      for obs in obs_for_tx if obs.get('src_ip') or obs.get('dst_ip') or obs.get('peer_ip')})
    countries = {obs.get('country', 'Unknown') for obs in obs_for_tx if obs.get('country') and obs.get('country') != 'Unknown'}
    cross_border = 1 if len(countries) > 1 else 0
    tor_vpn = 1 if any(obs.get('is_tor') or obs.get('is_vpn') for obs in obs_for_tx) else 0

    # Size and fee per output
    size_b = t.get('size_bytes') or (t.get('vsize') or 0) * 1  # approximate
    fee_per_out = math.log1p((t['fee_sats'] / n_out) if t['fee_sats'] is not None and n_out else 0)

    return [
        float(n_in),
        float(n_out),
        math.log1p(total),
        float(max(vals) / total if total else 0),
        math.log1p(rate or 0),
        float(rate is None),
        float(entropy),
        float(round_frac),
        float(off_hours),
        float(unique_ips),
        float(cross_border),
        float(tor_vpn),
        math.log1p(size_b),
        float(fee_per_out),
    ]


# ---------------------------------------------------------------------------
# SHAP-style feature attribution (manual perturbation-based)
# ---------------------------------------------------------------------------

def _shap_contributions(model: IsolationForest, vector: list[float],
                         baseline_vector: list[float]) -> list[float]:
    """
    Approximate feature contributions using leave-one-out perturbation.
    Replaces each feature with the dataset median and measures score change.
    Returns a list of contribution scores per feature.
    """
    import numpy as np
    v = np.array([vector])
    base_score = float(-model.score_samples(v)[0])
    contributions = []
    for i in range(len(vector)):
        perturbed = vector.copy()
        perturbed[i] = baseline_vector[i]
        ps = float(-model.score_samples(np.array([perturbed]))[0])
        contributions.append(round(base_score - ps, 4))
    return contributions


# ---------------------------------------------------------------------------
# Detection patterns (rule-based)
# ---------------------------------------------------------------------------

def _detect_rules(t: dict, obs_for_tx: list[dict], median_out: float,
                  median_in: float, rule_time: datetime) -> list[dict]:
    signals = []

    n_out = len(t['outputs'])
    n_in = len(t['inputs'])
    vals = [o['value_sats'] for o in t['outputs']]
    total = sum(vals)

    # 1. Fan-out (payment batching / mixing)
    if n_out >= 10:
        signals.append({
            'code': 'fan_out', 'stage': 'rule_detection',
            'detector': 'Count threshold rule',
            'title': 'Unusual output fan-out',
            'feature': 'output_count', 'observed': n_out,
            'operator': '>=', 'threshold': 10, 'baseline': median_out,
            'unit': 'count', 'detected_at': rule_time,
            'reason': f'{n_out} outputs meet the fan-out threshold of 10; dataset median is {median_out:g}.',
        })

    # 2. Fan-in (consolidation / mixing)
    if n_in >= 10:
        signals.append({
            'code': 'fan_in', 'stage': 'rule_detection',
            'detector': 'Count threshold rule',
            'title': 'High input consolidation',
            'feature': 'input_count', 'observed': n_in,
            'operator': '>=', 'threshold': 10, 'baseline': median_in,
            'unit': 'count', 'detected_at': rule_time,
            'reason': f'{n_in} inputs suggest consolidation of funds; dataset median is {median_in:g}.',
        })

    # 3. Peel-chain detection: 1 input, 2 outputs, one large one very small
    if n_in == 1 and n_out == 2 and total > 0:
        ratio = max(vals) / total
        if ratio >= 0.90:
            signals.append({
                'code': 'peel_chain', 'stage': 'rule_detection',
                'detector': 'Peel-chain heuristic',
                'title': 'Possible peel-chain layering',
                'feature': 'largest_output_share', 'observed': round(ratio, 3),
                'operator': '>=', 'threshold': 0.90, 'baseline': None,
                'unit': 'ratio', 'detected_at': rule_time,
                'reason': f'{ratio*100:.1f}% of output value in one output (1-in-2-out pattern). '
                          f'Consistent with peel-chain layering used to obscure fund trails.',
            })

    # 4. Structuring: many outputs with similar values near a round threshold
    if n_out >= 5 and total > 0:
        vals_sorted = sorted(vals, reverse=True)
        # Check if top outputs are suspiciously uniform (std < 5% of mean)
        try:
            mean_top = statistics.mean(vals_sorted[:5])
            std_top = statistics.stdev(vals_sorted[:5])
            if mean_top > 0 and std_top / mean_top < 0.05:
                signals.append({
                    'code': 'structuring', 'stage': 'rule_detection',
                    'detector': 'Structuring heuristic',
                    'title': 'Possible structuring (Smurfing)',
                    'feature': 'output_uniformity', 'observed': round(std_top / mean_top, 4),
                    'operator': '<', 'threshold': 0.05, 'baseline': None,
                    'unit': 'coefficient_of_variation', 'detected_at': rule_time,
                    'reason': f'Top {min(n_out, 5)} outputs have coefficient of variation '
                              f'{std_top/mean_top:.4f} (<0.05). Near-identical output amounts '
                              f'are a structuring indicator.',
                })
        except statistics.StatisticsError:
            pass

    # 5. Round-number outputs (structuring indicator)
    round_count = sum(1 for v in vals if _is_round_btc(v))
    if round_count >= 3 and round_count / n_out >= 0.6:
        signals.append({
            'code': 'round_outputs', 'stage': 'rule_detection',
            'detector': 'Round-value heuristic',
            'title': 'Round-number output values',
            'feature': 'round_output_fraction', 'observed': round_count,
            'operator': '>=', 'threshold': 3, 'baseline': None,
            'unit': 'count', 'detected_at': rule_time,
            'reason': f'{round_count} of {n_out} outputs have round BTC/mBTC values. '
                      f'Round values are associated with deliberate amount selection (structuring).',
        })

    # 6. Tor/VPN relay
    for obs in obs_for_tx:
        if obs.get('is_tor'):
            signals.append({
                'code': 'tor_relay', 'stage': 'rule_detection',
                'detector': 'Tor exit node detection',
                'title': 'Transaction relayed via Tor',
                'feature': 'tor_vpn_flag', 'observed': 1,
                'operator': '==', 'threshold': 1, 'baseline': 0,
                'unit': 'binary', 'detected_at': rule_time,
                'reason': f'Network observation from IP {obs.get("src_ip") or obs.get("dst_ip")} '
                          f'identified as a Tor exit node. Tor is used to obscure the originating IP.',
            })
            break
        if obs.get('is_vpn'):
            signals.append({
                'code': 'vpn_relay', 'stage': 'rule_detection',
                'detector': 'VPN ASN detection',
                'title': 'Transaction relayed via known VPN',
                'feature': 'tor_vpn_flag', 'observed': 1,
                'operator': '==', 'threshold': 1, 'baseline': 0,
                'unit': 'binary', 'detected_at': rule_time,
                'reason': f'Network observation ASN {obs.get("asn")} is associated with commercial VPN infrastructure.',
            })
            break

    # 7. Cross-border relay
    countries = {obs.get('country', 'Unknown') for obs in obs_for_tx
                 if obs.get('country') and obs.get('country') not in ('Unknown', 'private', 'loopback')}
    if len(countries) > 2:
        signals.append({
            'code': 'cross_border', 'stage': 'rule_detection',
            'detector': 'Cross-border relay rule',
            'title': 'Multi-country relay path',
            'feature': 'cross_border_flag', 'observed': len(countries),
            'operator': '>', 'threshold': 2, 'baseline': 1,
            'unit': 'country_count', 'detected_at': rule_time,
            'reason': f'This transaction was relayed from {len(countries)} countries '
                      f'({", ".join(sorted(countries)[:5])}). Multi-jurisdiction relay paths '
                      f'complicate geographic attribution.',
        })

    # 8. Off-hours large-value: >1 BTC transacted between midnight and 5am UTC
    ts = t.get('observed_at') or t.get('block_time')
    if ts:
        try:
            hour = ts.hour if hasattr(ts, 'hour') else datetime.fromisoformat(str(ts).replace('Z', '+00:00')).hour
            if hour < 5 and total > 100_000_000:  # >1 BTC
                signals.append({
                    'code': 'off_hours_large', 'stage': 'rule_detection',
                    'detector': 'Temporal anomaly rule',
                    'title': 'Large off-hours transaction',
                    'feature': 'is_off_hours', 'observed': hour,
                    'operator': '<', 'threshold': 5, 'baseline': None,
                    'unit': 'hour_utc', 'detected_at': rule_time,
                    'reason': f'High-value transaction ({total/1e8:.4f} BTC) observed at {hour:02d}:xx UTC. '
                              f'Off-hours activity can indicate automated or cross-timezone operation.',
                })
        except Exception:
            pass

    return signals


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def analyze(rows: list[dict], observations: list[dict] | None = None, on_stage=None):
    """Full 5-stage analysis pipeline. Returns (alerts, features)."""
    from bisect import bisect_left, bisect_right

    if callable(observations) and on_stage is None:
        on_stage = observations
        observations = None
    if observations is None:
        observations = []

    def stage(name, status, **detail):
        stamp = datetime.now(timezone.utc)
        if on_stage:
            on_stage(name, status, detail, stamp)
        return stamp

    obs_index = _build_obs_index(observations)

    # --- Stage 1: Feature engineering ---
    stage('feature_engineering', 'started', records=len(rows))
    vectors: list[list[float]] = []
    for t in rows:
        obs_for_tx = obs_index.get(t['txid'], [])
        vectors.append(_extract_features(t, obs_for_tx))
    stage('feature_engineering', 'completed', records=len(rows), features=len(FEATURE_NAMES))

    # Dataset medians for rule baselines
    median_out = statistics.median(len(t['outputs']) for t in rows)
    median_in = statistics.median(len(t['inputs']) for t in rows)

    # --- Stage 2: Rule detection ---
    stage('rule_detection', 'started', records=len(rows))
    detections: list[list[dict]] = [[] for _ in rows]
    rule_time = datetime.now(timezone.utc)
    for t, signals in zip(rows, detections):
        obs_for_tx = obs_index.get(t['txid'], [])
        signals.extend(_detect_rules(t, obs_for_tx, median_out, median_in, rule_time))
    stage('rule_detection', 'completed',
          matched_transactions=sum(bool(x) for x in detections),
          rules=['fan_out', 'fan_in', 'peel_chain', 'structuring',
                 'round_outputs', 'tor_relay', 'vpn_relay', 'cross_border', 'off_hours_large'])

    # --- Stage 3: Isolation Forest scoring ---
    stage('model_scoring', 'started', records=len(rows))
    shap_data: list[list[float]] = []
    if len(rows) >= 40:
        import numpy as np
        X = np.array(vectors)
        model = IsolationForest(n_estimators=200, contamination='auto',
                                random_state=42, n_jobs=1)
        model.fit(X)
        raw = -model.score_samples(X)
        ordered = sorted(raw)
        scores = [
            round(100 * (bisect_left(ordered, v) + 0.5 * (bisect_right(ordered, v) - bisect_left(ordered, v))) / len(raw), 1)
            for v in raw
        ]
        model_time = datetime.now(timezone.utc)

        # Baseline = dataset medians per feature
        baseline = [float(statistics.median(X[:, i])) for i in range(X.shape[1])]

        for signals, score, vector in zip(detections, scores, vectors):
            if score >= 97:
                signals.append({
                    'code': 'isolation_forest', 'stage': 'model_scoring',
                    'detector': 'Isolation Forest (IForest v3)',
                    'title': 'Multivariate transaction anomaly',
                    'feature': 'anomaly_percentile', 'observed': score,
                    'operator': '>=', 'threshold': 97, 'baseline': None,
                    'unit': 'percentile', 'detected_at': model_time,
                    'reason': f'In-dataset anomaly percentile {score:g} meets the 97th-percentile '
                              f'review threshold. Trained on {len(rows)} transactions with '
                              f'{len(FEATURE_NAMES)} blockchain+network features. '
                              f'This is not a crime probability.',
                })
            # Compute SHAP-style contributions for this transaction
            shap_data.append(_shap_contributions(model, vector, baseline))

        stage('model_scoring', 'completed', records=len(rows), model_version=MODEL_VERSION,
              n_estimators=200, features=len(FEATURE_NAMES))
    else:
        scores = [0.0] * len(rows)
        shap_data = [[0.0] * len(FEATURE_NAMES)] * len(rows)
        stage('model_scoring', 'skipped',
              reason='At least 40 records are required; rules remain active.')

    # --- Stage 4 implicitly embedded in alert generation ---
    stage('alert_generation', 'started')
    alerts: list[dict] = []
    features: list[dict] = []

    for t, vector, score, signals, shap_vals in zip(rows, vectors, scores, detections, shap_data):
        version = MODEL_VERSION if len(rows) >= 40 else 'rules-only-v3'

        # Build feature-contribution explanation sorted by impact
        named_contributions = sorted(
            [{'feature': FEATURE_NAMES[i], 'contribution': shap_vals[i],
              'description': FEATURE_DESCRIPTIONS.get(FEATURE_NAMES[i], ''),
              'value': round(vector[i], 4)}
             for i in range(len(FEATURE_NAMES))],
            key=lambda x: abs(x['contribution']), reverse=True
        )

        if signals:
            reasons = [s['reason'] for s in signals]
            # Feature evidence narrative
            top_features = [f['feature'] for f in named_contributions[:3] if f['contribution'] > 0]
            if top_features:
                reasons.append(
                    f'Top anomalous features: {", ".join(top_features)}. '
                    f'Feature evidence is descriptive, not causal attribution.'
                )
            reasons.append(
                f'Blockchain evidence: {len(t["inputs"])} inputs, {len(t["outputs"])} outputs, '
                f'total {sum(o["value_sats"] for o in t["outputs"])} satoshis.'
            )

            priority = 'high' if any(s['stage'] == 'rule_detection' for s in signals) else 'medium'
            risk_score = round(max(70 if priority == 'high' else 0, score), 1)

            alerts.append({
                'txid': t['txid'],
                'title': signals[0]['title'],
                'severity': priority,
                'priority': priority,
                'risk_score': risk_score,
                'confidence_score': risk_score,
                'confidence_basis': 'Composite investigative lead score; not a probability of criminal activity.',
                'score': score,
                'reasons': reasons,
                'status': 'open',
                'detections': signals,
                'feature_contributions': named_contributions[:8],  # top 8 for display
                'first_detected_stage': signals[0]['stage'],
                'detection_stages': list(dict.fromkeys(x['stage'] for x in signals)),
                'detected_at': signals[0]['detected_at'],
                'transaction_observed_at': t.get('observed_at'),
                'transaction_block_time': t.get('block_time'),
                'created_at': datetime.now(timezone.utc),
                'alternative': ('Payment batching, wallet consolidation, or other ordinary activity may '
                                'explain this pattern. Ownership and intent remain unknown.'),
                'model_version': version,
            })

        features.append({
            'txid': t['txid'],
            'values': vector,
            'score': score,
            'model_version': version,
            'feature_names': FEATURE_NAMES,
            'feature_contributions': named_contributions,
        })

    stage('alert_generation', 'completed', alerts=len(alerts))
    return sorted(alerts, key=lambda a: (a['severity'] == 'high', a['confidence_score']), reverse=True), features


# ---------------------------------------------------------------------------
# Rich synthetic dataset generator (full SIH-2026 field spec)
# ---------------------------------------------------------------------------

def training_data() -> bytes:
    """Generate a comprehensive synthetic dataset matching the full SIH-2026 spec.

    Patterns included:
    - Normal: standard P2P payments, 1-2 inputs/outputs
    - Fan-out: mixing/batching (>10 outputs)
    - Fan-in: consolidation (>10 inputs)
    - Peel-chain: 1-in-2-out with 90%+ value concentration
    - Structuring: many outputs with near-identical round values
    - Ransomware-like: single very large output, no change, off-hours
    - Darknet market: rapid small outputs, round values
    - Cross-border relay with Tor/VPN observations
    """
    import random
    rng = random.Random(42)
    rows = []
    available = []
    base = datetime(2026, 1, 15, tzinfo=timezone.utc)

    # Synthetic IPs for observations
    ip_pools = {
        'US': ['13.52.1.1', '52.86.4.2', '18.144.3.3', '34.212.4.4', '54.172.5.5'],
        'RU': ['46.148.1.10', '77.88.2.20', '81.19.3.30', '176.9.4.40', '194.87.5.50'],
        'CN': ['1.179.1.100', '27.155.2.200', '114.114.3.3', '221.12.4.4', '58.218.5.5'],
        'DE': ['78.46.1.1', '88.198.2.2', '85.10.3.3', '213.239.4.4', '87.106.5.5'],
        'NL': ['185.220.1.1', '89.163.2.2', '91.218.3.3', '84.200.4.4', '80.249.5.5'],
        'TOR': ['185.220.101.1', '185.220.102.4', '185.220.101.15', '185.220.103.5', '192.42.116.16'],
    }

    def make_txid(seed_str: str) -> str:
        return sha256(f'sih2026-v3-{seed_str}'.encode()).hexdigest()

    def make_obs(txid: str, src_ip: str, dst_ip: str, src_port: int, dst_port: int,
                 country: str, asn: str, ts: datetime, is_tor: bool = False, is_vpn: bool = False) -> dict:
        return {
            'txid': txid, 'observed_at': ts.isoformat(),
            'src_ip': src_ip, 'dst_ip': dst_ip,
            'src_port': src_port, 'dst_port': dst_port,
            'country': country, 'asn': asn,
            'is_tor': is_tor, 'is_vpn': is_vpn,
            'sensor': 'synthetic-sensor-v3',
        }

    observations = []

    for i in range(500):
        txid = make_txid(str(i))
        ts = base + timedelta(hours=rng.randint(0, 720))

        # Select scenario
        scenario = (
            'fan_out' if i in range(20, 30) else
            'fan_in' if i in range(60, 70) else
            'peel_chain' if i in range(100, 120) else
            'structuring' if i in range(150, 165) else
            'ransomware' if i in range(200, 208) else
            'darknet' if i in range(240, 255) else
            'tor_relay' if i in range(290, 300) else
            'cross_border' if i in range(330, 345) else
            'normal'
        )

        # Budget from UTXO pool
        if available:
            prev = available.pop(0)
            ins = [{'prev_txid': prev['txid'], 'prev_vout': prev['index']}]
            budget = prev['value_sats']
        else:
            ins = []
            budget = rng.randint(5_000_000_000, 50_000_000_000)

        fee = max(200, min(100_000, budget // 500))

        if scenario == 'fan_out':
            count = rng.randint(12, 20)
            each = (budget - fee) // count
            outputs = [{'index': j, 'value_sats': each + (budget - fee - each * count if j == 0 else 0),
                        'address': f'syn-fanout-{i}-{j}', 'script_type': 'p2wpkh'} for j in range(count)]
            # Add VPN observation
            ip = rng.choice(ip_pools['NL'])
            observations.append(make_obs(txid, ip, '13.52.1.1', 54321, 8333, 'NL', 'AS60068', ts, is_vpn=True))

        elif scenario == 'fan_in':
            # Multiple inputs from UTXO pool
            extra_ins = []
            extra_budget = 0
            for _ in range(rng.randint(8, 14)):
                if available:
                    p = available.pop(0)
                    extra_ins.append({'prev_txid': p['txid'], 'prev_vout': p['index']})
                    extra_budget += p['value_sats']
            ins.extend(extra_ins)
            total_budget = budget + extra_budget
            fee = max(1000, total_budget // 200)
            outputs = [{'index': 0, 'value_sats': max(1000, total_budget - fee),
                        'address': f'syn-fanin-{i}-dest', 'script_type': 'p2wpkh'}]
            ip = rng.choice(ip_pools['RU'])
            observations.append(make_obs(txid, ip, '52.86.4.2', 12345, 8333, 'RU', 'AS12389', ts))

        elif scenario == 'peel_chain':
            big = int((budget - fee) * rng.uniform(0.92, 0.97))
            small = budget - fee - big
            outputs = [
                {'index': 0, 'value_sats': big, 'address': f'syn-peel-{i}-main', 'script_type': 'p2wpkh'},
                {'index': 1, 'value_sats': max(1, small), 'address': f'syn-peel-{i}-change', 'script_type': 'p2wpkh'},
            ]
            ip = rng.choice(ip_pools['DE'])
            observations.append(make_obs(txid, ip, '13.52.1.1', 44321, 8333, 'DE', 'AS3320', ts))

        elif scenario == 'structuring':
            # Near-uniform round values
            base_val = rng.choice([100_000, 500_000, 1_000_000, 10_000_000])
            count = rng.randint(5, 9)
            each = base_val
            remainder = budget - fee - each * count
            outputs = [{'index': j, 'value_sats': each, 'address': f'syn-struct-{i}-{j}',
                        'script_type': 'p2wpkh'} for j in range(count)]
            if remainder > 0:
                outputs.append({'index': count, 'value_sats': remainder,
                                'address': f'syn-struct-{i}-change', 'script_type': 'p2wpkh'})
            ip = rng.choice(ip_pools['US'])
            observations.append(make_obs(txid, ip, '13.52.1.1', 22222, 8333, 'US', 'AS16509', ts))

        elif scenario == 'ransomware':
            # Large single payment, off hours, cross-border relay
            ts = ts.replace(hour=rng.randint(0, 4))  # off hours
            budget = rng.randint(100_000_000_000, 500_000_000_000)  # 1000-5000 BTC
            fee = 5000
            outputs = [{'index': 0, 'value_sats': budget - fee,
                        'address': f'syn-ransom-{i}-wallet', 'script_type': 'p2wpkh'}]
            # Multi-country relay
            for country, pool in [('RU', ip_pools['RU']), ('US', ip_pools['US']), ('CN', ip_pools['CN'])]:
                ip = rng.choice(pool)
                asn = 'AS12389' if country == 'RU' else 'AS16509' if country == 'US' else 'AS4134'
                observations.append(make_obs(txid, ip, rng.choice(ip_pools['US']),
                                             rng.randint(10000, 65000), 8333, country, asn, ts))

        elif scenario == 'darknet':
            # Many small round outputs
            count = rng.randint(8, 15)
            unit = rng.choice([500_000, 1_000_000, 5_000_000])  # 0.005, 0.01, 0.05 BTC
            fee = 2000
            outputs = [{'index': j, 'value_sats': unit, 'address': f'syn-dark-{i}-{j}',
                        'script_type': 'p2wpkh'} for j in range(count)]
            remainder = budget - fee - unit * count
            if remainder > 0:
                outputs.append({'index': count, 'value_sats': remainder,
                                'address': f'syn-dark-{i}-change', 'script_type': 'p2wpkh'})
            # Tor relay
            ip = rng.choice(ip_pools['TOR'])
            observations.append(make_obs(txid, ip, '13.52.1.1', rng.randint(10000, 65000),
                                         8333, 'XX', 'AS9009', ts, is_tor=True))

        elif scenario == 'tor_relay':
            each = (budget - fee) // 2
            outputs = [
                {'index': 0, 'value_sats': each, 'address': f'syn-tor-{i}-0', 'script_type': 'p2wpkh'},
                {'index': 1, 'value_sats': budget - fee - each, 'address': f'syn-tor-{i}-1', 'script_type': 'p2wpkh'},
            ]
            ip = rng.choice(ip_pools['TOR'])
            observations.append(make_obs(txid, ip, '34.212.4.4', rng.randint(10000, 65000),
                                         8333, 'XX', 'AS9009', ts, is_tor=True))

        elif scenario == 'cross_border':
            each = (budget - fee) // 3
            outputs = [{'index': j, 'value_sats': each, 'address': f'syn-cross-{i}-{j}',
                        'script_type': 'p2wpkh'} for j in range(3)]
            for ccode, pool in [('CN', ip_pools['CN']), ('RU', ip_pools['RU']),
                                 ('NL', ip_pools['NL']), ('DE', ip_pools['DE'])]:
                ip = rng.choice(pool)
                asns = {'CN': 'AS4134', 'RU': 'AS12389', 'NL': 'AS60068', 'DE': 'AS3320'}
                observations.append(make_obs(txid, ip, rng.choice(ip_pools['US']),
                                             rng.randint(10000, 65000), 8333, ccode, asns[ccode], ts))
        else:
            # Normal: 1-3 outputs
            count = rng.choice([1, 1, 2, 2, 2, 3])
            each = (budget - fee) // count
            outputs = [{'index': j, 'value_sats': each + (budget - fee - each * count if j == 0 else 0),
                        'address': f'syn-normal-{i}-{j}', 'script_type': 'p2wpkh'} for j in range(count)]
            if rng.random() < 0.4:  # 40% have an IP observation
                country = rng.choice(['US', 'DE', 'NL', 'RU'])
                ip = rng.choice(ip_pools[country])
                asns = {'US': 'AS16509', 'DE': 'AS3320', 'NL': 'AS9009', 'RU': 'AS12389'}
                observations.append(make_obs(txid, ip, rng.choice(ip_pools['US']),
                                             rng.randint(10000, 65000), 8333, country, asns[country], ts))

        # Ensure outputs don't exceed budget
        output_total = sum(o['value_sats'] for o in outputs)
        if output_total > budget:
            # Clip last output
            excess = output_total - budget + fee
            last = outputs[-1]
            last['value_sats'] = max(1, last['value_sats'] - excess)

        # Add UTXO pool
        for o in outputs:
            if o['value_sats'] > 10_000:
                available.append({'txid': txid, **o})

        is_confirmed = i < 450
        rows.append({
            'txid': txid,
            'observed_at': ts.isoformat(),
            'inputs': ins,
            'outputs': outputs,
            'fee_sats': fee if scenario != 'ransomware' or rng.random() > 0.2 else None,
            'vsize': 141 + len(ins) * 41 + len(outputs) * 32,
            'size_bytes': 190 + len(ins) * 41 + len(outputs) * 32,
            'weight': (141 + len(ins) * 41 + len(outputs) * 32) * 4,
            'version': 2,
            'locktime': 0,
            'confirmed': is_confirmed,
            'confirmations': rng.randint(1, 500) if is_confirmed else 0,
            'block_height': 880_000 + i // 10 if is_confirmed else None,
            'block_time': (ts + timedelta(minutes=10)).isoformat() if is_confirmed else None,
        })

    return json.dumps({
        'synthetic': True,
        'version': 'sih2026-v3',
        'description': 'Rich synthetic dataset with 8 criminal patterns + GeoIP observations',
        'transactions': rows,
        'observations': observations,
    }).encode()
