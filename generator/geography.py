"""Geography model: upazila -> village -> household hierarchy and spatial coordinates."""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


# Approximate conversion constants for Bangladesh latitudes (~24.5 deg N)
METERS_PER_DEG_LAT = 111320.0


def _meters_to_deg(meters_y: float, meters_x: float, lat_deg: float) -> Tuple[float, float]:
    """Convert offset in meters (y=North, x=East) to latitude and longitude delta degrees."""
    delta_lat = meters_y / METERS_PER_DEG_LAT
    cos_lat = max(0.1, math.cos(math.radians(lat_deg)))
    delta_lon = meters_x / (METERS_PER_DEG_LAT * cos_lat)
    return delta_lat, delta_lon


@dataclass
class Village:
    village_id: str
    upazila_code: str
    centroid_lat: float
    centroid_lon: float
    frame_size: int
    household_ids: List[str] = field(default_factory=list)
    household_locations: Dict[str, Tuple[float, float]] = field(default_factory=dict)


@dataclass
class Geography:
    upazila_codes: List[str]
    villages: Dict[str, Village]
    frame_expansion_log: List[Dict[str, Any]] = field(default_factory=list)

    def get_village(self, village_id: str) -> Village:
        return self.villages[village_id]

    def enlarge_frame_if_needed(
        self,
        village_id: str,
        needed_count: int,
        rng: np.random.Generator,
        scatter_m: float = 300.0,
    ) -> Optional[Dict[str, Any]]:
        """If needed_count exceeds current frame size, enlarge the frame and log the change."""
        village = self.villages[village_id]
        original_size = village.frame_size
        if needed_count <= original_size:
            return None

        # Add additional households
        extra_count = needed_count - original_size
        for i in range(original_size + 1, needed_count + 1):
            hh_id = f"{village_id}_HH{i:04d}"
            village.household_ids.append(hh_id)
            # True location: village centroid + bivariate Normal(0, sigma = scatter_m)
            dy, dx = rng.normal(0.0, scatter_m, size=2)
            dlat, dlon = _meters_to_deg(dy, dx, village.centroid_lat)
            village.household_locations[hh_id] = (
                village.centroid_lat + dlat,
                village.centroid_lon + dlon,
            )

        village.frame_size = needed_count
        log_entry = {
            "village_id": village_id,
            "original_size": original_size,
            "new_size": needed_count,
        }
        self.frame_expansion_log.append(log_entry)
        return log_entry


def generate_village_centroids(
    n_upazilas: int,
    villages_per_upazila: int,
    rng: np.random.Generator,
    min_separation_km: float = 1.5,
) -> List[Tuple[float, float]]:
    """Generate village centroids in Bangladesh coordinate space with minimum separation constraint."""
    min_separation_m = min_separation_km * 1000.0
    total_villages = n_upazilas * villages_per_upazila
    centroids: List[Tuple[float, float]] = []

    # Placeholder base coordinates centered in rural Bangladesh (~Tangail / Mymensingh area)
    base_lat = 24.50
    base_lon = 90.00

    attempts = 0
    max_attempts = total_villages * 500
    while len(centroids) < total_villages and attempts < max_attempts:
        attempts += 1
        # Spread villages across ~30 km radius
        dy = rng.uniform(-15000.0, 15000.0)
        dx = rng.uniform(-15000.0, 15000.0)
        lat = base_lat + dy / METERS_PER_DEG_LAT
        lon = base_lon + dx / (METERS_PER_DEG_LAT * math.cos(math.radians(base_lat)))

        # Check separation from existing centroids
        separated = True
        for clat, clon in centroids:
            d_lat_m = (lat - clat) * METERS_PER_DEG_LAT
            d_lon_m = (lon - clon) * (METERS_PER_DEG_LAT * math.cos(math.radians(base_lat)))
            dist_m = math.hypot(d_lat_m, d_lon_m)
            if dist_m < min_separation_m:
                separated = False
                break

        if separated:
            centroids.append((lat, lon))

    # Fallback grid if rejection sampling falls short
    while len(centroids) < total_villages:
        idx = len(centroids)
        row = idx // villages_per_upazila
        col = idx % villages_per_upazila
        lat = base_lat + (row * min_separation_m * 1.2) / METERS_PER_DEG_LAT
        lon = base_lon + (col * min_separation_m * 1.2) / (METERS_PER_DEG_LAT * math.cos(math.radians(base_lat)))
        centroids.append((lat, lon))

    return centroids


def build_geography(config: Dict[str, Any], rng: np.random.Generator) -> Geography:
    """Build the upazila -> village -> household hierarchy from configuration."""
    geo_cfg = config["geography"]
    gps_cfg = config.get("gps", {})

    n_upazilas = int(geo_cfg.get("n_upazilas", 3))
    villages_per_upazila = int(geo_cfg.get("villages_per_upazila", 12))
    hh_range = geo_cfg.get("households_per_village", [40, 100])
    min_hh, max_hh = int(hh_range[0]), int(hh_range[1])
    upazila_codes = geo_cfg.get("upazila_codes", [f"UPA{i+1:02d}" for i in range(n_upazilas)])
    min_sep_km = float(geo_cfg.get("village_min_separation_km", 1.5))
    scatter_m = float(gps_cfg.get("scatter_m", 300.0))

    centroids = generate_village_centroids(
        n_upazilas=n_upazilas,
        villages_per_upazila=villages_per_upazila,
        rng=rng,
        min_separation_km=min_sep_km,
    )

    villages: Dict[str, Village] = {}
    v_idx = 0
    for u_idx, upa_code in enumerate(upazila_codes[:n_upazilas]):
        for _ in range(villages_per_upazila):
            v_idx += 1
            vil_id = f"VIL{v_idx:03d}"
            c_lat, c_lon = centroids[v_idx - 1]
            frame_size = int(rng.integers(min_hh, max_hh + 1))

            hh_ids: List[str] = []
            hh_locs: Dict[str, Tuple[float, float]] = {}
            for h in range(1, frame_size + 1):
                hh_id = f"{vil_id}_HH{h:04d}"
                hh_ids.append(hh_id)
                dy, dx = rng.normal(0.0, scatter_m, size=2)
                dlat, dlon = _meters_to_deg(dy, dx, c_lat)
                hh_locs[hh_id] = (c_lat + dlat, c_lon + dlon)

            villages[vil_id] = Village(
                village_id=vil_id,
                upazila_code=upa_code,
                centroid_lat=c_lat,
                centroid_lon=c_lon,
                frame_size=frame_size,
                household_ids=hh_ids,
                household_locations=hh_locs,
            )

    return Geography(upazila_codes=upazila_codes[:n_upazilas], villages=villages)

