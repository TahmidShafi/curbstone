"""Mathematical and statistical helper routines for peer-relative feature extraction."""

import math
from typing import List, Tuple
import numpy as np


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two lat/lon coordinates."""
    r_earth = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    return 2.0 * r_earth * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def median_nn_distance(lats: np.ndarray, lons: np.ndarray) -> float:
    """Median nearest-neighbour haversine distance among an array of coordinates."""
    n = len(lats)
    if n <= 1:
        return 0.0
    nn_dists = []
    for i in range(n):
        min_d = float("inf")
        for j in range(n):
            if i != j:
                d = haversine_m(lats[i], lons[i], lats[j], lons[j])
                if d < min_d:
                    min_d = d
        nn_dists.append(min_d)
    return float(np.median(nn_dists))


def count_near_dups(records: List[Tuple]) -> int:
    """Count number of records that differ in <= 1 field from another record in the set."""
    n = len(records)
    if n <= 1:
        return 0
    is_nd = [False] * n
    for i in range(n):
        r1 = records[i]
        for j in range(i + 1, n):
            if sum(1 for a, b in zip(r1, records[j]) if a != b) <= 1:
                is_nd[i] = is_nd[j] = True
    return sum(is_nd)
