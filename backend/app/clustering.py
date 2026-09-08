"""Entity clustering for Bitcoin intelligence analysis.

Two complementary approaches:
  1. Wallet clustering via common-input-ownership heuristic (Union-Find)
     + address reuse detection.
  2. IP/network clustering via co-occurrence with flagged TXIDs (DBSCAN on
     shared-TXID Jaccard distance). Detects coordinated relay infrastructure.

All clusters are assigned a risk score based on the proportion of their
members appearing in high-priority alerts.
"""
from __future__ import annotations
import hashlib
import secrets
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Union-Find for wallet clustering
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self):
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self._rank.get(px, 0) < self._rank.get(py, 0):
            px, py = py, px
        self._parent[py] = px
        if self._rank.get(px, 0) == self._rank.get(py, 0):
            self._rank[px] = self._rank.get(px, 0) + 1

    def components(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for node in list(self._parent.keys()):
            groups[self.find(node)].append(node)
        return dict(groups)


# ---------------------------------------------------------------------------
# Wallet clustering (common-input-ownership + address reuse)
# ---------------------------------------------------------------------------

def cluster_wallets(transactions: list[dict], alerts: list[dict]) -> list[dict]:
    """
    Apply common-input-ownership heuristic: all input addresses in the same TX
    are likely controlled by the same entity (they must all sign).

    Also merge on address reuse: an address appearing in both inputs and outputs
    across different TXs belongs to the same entity cluster.

    Returns a list of cluster dicts with risk scores.
    """
    uf = UnionFind()
    address_to_txids: dict[str, set[str]] = defaultdict(set)

    # Pass 1: common-input-ownership
    for tx in transactions:
        input_addrs: list[str] = []
        for inp in tx.get('inputs', []):
            addr = inp.get('address') or inp.get('prev_txid', '')
            if addr:
                input_addrs.append(addr)
                address_to_txids[addr].add(tx['txid'])
        # Union all input addresses together
        for i in range(1, len(input_addrs)):
            uf.union(input_addrs[0], input_addrs[i])

        # Also record output addresses for reuse detection
        for out in tx.get('outputs', []):
            addr = out.get('address')
            if addr:
                address_to_txids[addr].add(tx['txid'])

    # Pass 2: address reuse — if an address appears as both input (in any tx)
    # and output (in another tx), it links those spending paths.
    output_addrs: set[str] = set()
    input_addrs_all: set[str] = set()
    for tx in transactions:
        for out in tx.get('outputs', []):
            addr = out.get('address')
            if addr:
                output_addrs.add(addr)
        for inp in tx.get('inputs', []):
            addr = inp.get('address')
            if addr:
                input_addrs_all.add(addr)
    reused = output_addrs & input_addrs_all
    # Reused addresses: group them with any co-input address in TXs where they appear as input
    for tx in transactions:
        tx_input_addrs = [i.get('address') for i in tx.get('inputs', []) if i.get('address')]
        tx_reused = [a for a in tx_input_addrs if a in reused]
        for i in range(1, len(tx_reused)):
            uf.union(tx_reused[0], tx_reused[i])

    # Build cluster records
    components = uf.components()

    # Determine alert-flagged TXIDs for risk scoring
    flagged_txids: set[str] = {a['txid'] for a in alerts if a.get('severity') == 'high'}
    medium_txids: set[str] = {a['txid'] for a in alerts if a.get('severity') == 'medium'}

    cluster_records: list[dict] = []
    for root, members in components.items():
        if len(members) < 2:
            continue  # Singletons are not interesting clusters
        # Find all TXIDs associated with cluster members
        txids_in_cluster: set[str] = set()
        for addr in members:
            txids_in_cluster |= address_to_txids.get(addr, set())

        high_hits = len(txids_in_cluster & flagged_txids)
        med_hits = len(txids_in_cluster & medium_txids)
        total = len(txids_in_cluster) or 1
        risk_score = round(min(100, (high_hits * 30 + med_hits * 10) / total * 100 / 100 * 100 + (high_hits > 0) * 20), 1)
        if risk_score == 0 and not txids_in_cluster:
            continue
        cluster_id = 'wc-' + hashlib.sha256(root.encode()).hexdigest()[:12]
        cluster_records.append({
            '_id': secrets.token_hex(12),
            'cluster_id': cluster_id,
            'type': 'wallet',
            'size': len(members),
            'addresses': sorted(members)[:50],  # cap for storage
            'txid_count': len(txids_in_cluster),
            'txids': sorted(txids_in_cluster)[:50],
            'high_alert_hits': high_hits,
            'medium_alert_hits': med_hits,
            'risk_score': risk_score,
            'risk_level': 'high' if risk_score >= 60 else 'medium' if risk_score >= 20 else 'low',
            'heuristic': 'common_input_ownership+address_reuse',
        })

    return sorted(cluster_records, key=lambda c: -c['risk_score'])


# ---------------------------------------------------------------------------
# IP co-occurrence clustering (simple shared-TXID grouping)
# ---------------------------------------------------------------------------

def cluster_ips(observations: list[dict], alerts: list[dict]) -> list[dict]:
    """
    Group IPs that co-occur (relayed) the same set of TXIDs.
    Uses a Jaccard-similarity Union-Find approach:
    IPs sharing >= 2 TXIDs are merged into the same cluster.

    Returns cluster records with risk scores.
    """
    ip_txids: dict[str, set[str]] = defaultdict(set)
    txid_ips: dict[str, set[str]] = defaultdict(set)

    for obs in observations:
        ip = obs.get('src_ip') or obs.get('dst_ip') or obs.get('peer_ip')
        txid = obs.get('txid')
        if ip and txid:
            ip_txids[ip].add(txid)
            txid_ips[txid].add(ip)

    if not ip_txids:
        return []

    uf = UnionFind()

    # Union IPs that share ≥ 2 TXIDs (Jaccard threshold ~0.15)
    ips = list(ip_txids.keys())
    for i, ip_a in enumerate(ips):
        for ip_b in ips[i + 1:]:
            shared = len(ip_txids[ip_a] & ip_txids[ip_b])
            if shared >= 2:
                uf.union(ip_a, ip_b)

    components = uf.components()
    flagged_txids: set[str] = {a['txid'] for a in alerts}

    cluster_records: list[dict] = []
    for root, members in components.items():
        if len(members) < 2:
            continue
        all_txids: set[str] = set()
        for ip in members:
            all_txids |= ip_txids[ip]
        flagged_hits = len(all_txids & flagged_txids)
        risk_score = round(min(100, flagged_hits * 25), 1)

        # Geo/TOR info from first observation for each IP
        geo_info: dict[str, Any] = {}
        for obs in observations:
            ip = obs.get('src_ip') or obs.get('dst_ip') or obs.get('peer_ip')
            if ip in members and ip not in geo_info:
                geo_info[ip] = {
                    'country': obs.get('country', 'Unknown'),
                    'asn': obs.get('asn', ''),
                    'is_tor': obs.get('is_tor', False),
                    'is_vpn': obs.get('is_vpn', False),
                }

        cluster_id = 'ic-' + hashlib.sha256(root.encode()).hexdigest()[:12]
        countries = list({v['country'] for v in geo_info.values() if v['country'] != 'Unknown'})
        has_tor = any(v['is_tor'] for v in geo_info.values())
        has_vpn = any(v['is_vpn'] for v in geo_info.values())

        if has_tor or has_vpn:
            risk_score = min(100, risk_score + 30)

        cluster_records.append({
            '_id': secrets.token_hex(12),
            'cluster_id': cluster_id,
            'type': 'ip',
            'size': len(members),
            'ips': sorted(members)[:50],
            'txid_count': len(all_txids),
            'txids': sorted(all_txids)[:50],
            'flagged_alert_hits': flagged_hits,
            'risk_score': risk_score,
            'risk_level': 'high' if risk_score >= 60 else 'medium' if risk_score >= 20 else 'low',
            'countries': countries[:10],
            'has_tor': has_tor,
            'has_vpn': has_vpn,
            'heuristic': 'ip_txid_cooccurrence',
        })

    return sorted(cluster_records, key=lambda c: -c['risk_score'])
