"""Enumerator model: assignments, individual speed/care effects, and workload allocation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List
import numpy as np


@dataclass
class Enumerator:
    enumerator_id: str
    speed_effect: float
    care_effect: float
    total_workload: int
    assigned_villages: List[str]
    village_workloads: Dict[str, int] = field(default_factory=dict)


def assign_enumerator_villages(
    enumerator_ids: List[str],
    village_ids: List[str],
    rng: np.random.Generator,
    min_villages: int = 1,
    max_villages: int = 3,
    min_enumerators_per_village: int = 2,
) -> Dict[str, List[str]]:
    """Assign enumerators to overlapping villages guaranteeing all design constraints (dgp §4).

    Constraints:
        1. Each enumerator has Uniform integer [min_villages, max_villages] assigned villages.
        2. Every village has at least min_enumerators_per_village assigned enumerators.
        3. Every enumerator shares at least one village with a peer enumerator.
    """
    n_enum = len(enumerator_ids)
    n_vil = len(village_ids)

    # Initial target village capacity per enumerator
    k_targets = rng.integers(min_villages, max_villages + 1, size=n_enum)

    # Ensure total slots are at least n_vil * min_enumerators_per_village
    min_total_slots = n_vil * min_enumerators_per_village
    while k_targets.sum() < min_total_slots:
        expandable = np.where(k_targets < max_villages)[0]
        if len(expandable) == 0:
            break
        idx = rng.choice(expandable)
        k_targets[idx] += 1

    assignments: Dict[int, List[int]] = {e: [] for e in range(n_enum)}

    # Pass 1 & Pass 2: Ensure every village gets at least min_enumerators_per_village
    for _ in range(min_enumerators_per_village):
        v_order = rng.permutation(n_vil)
        for v in v_order:
            candidates = [
                e for e in range(n_enum)
                if len(assignments[e]) < k_targets[e] and v not in assignments[e]
            ]
            if not candidates:
                candidates = [
                    e for e in range(n_enum)
                    if len(assignments[e]) < max_villages and v not in assignments[e]
                ]
            chosen_e = int(rng.choice(candidates))
            assignments[chosen_e].append(int(v))

    # Fill any remaining capacity for each enumerator up to k_targets[e]
    for e in range(n_enum):
        while len(assignments[e]) < k_targets[e]:
            possible_v = [v for v in range(n_vil) if v not in assignments[e]]
            if not possible_v:
                break
            v = int(rng.choice(possible_v))
            assignments[e].append(v)

    # Map back to string IDs
    result: Dict[str, List[str]] = {}
    for e_idx, e_id in enumerate(enumerator_ids):
        result[e_id] = [village_ids[v_idx] for v_idx in assignments[e_idx]]

    return result


def allocate_workload_across_villages(
    workload: int,
    villages: List[str],
    rng: np.random.Generator,
) -> Dict[str, int]:
    """Split enumerator workload W_e across assigned villages with multinomial draw (equal prob).

    Each assigned village receives >= 1 interview.
    """
    k = len(villages)
    if k == 0:
        return {}
    if workload < k:
        workload = k  # Ensure each village can receive at least 1 interview

    # Guarantee 1 interview per village
    counts = np.ones(k, dtype=int)
    remaining = workload - k

    if remaining > 0:
        # Multinomial draw with equal probabilities 1/k
        probs = np.full(k, 1.0 / k)
        additional = rng.multinomial(remaining, probs)
        counts += additional

    return {village: int(cnt) for village, cnt in zip(villages, counts)}


def build_enumerators(
    config: Dict[str, Any],
    village_ids: List[str],
    rng: np.random.Generator,
) -> Dict[str, Enumerator]:
    """Generate all enumerators with speed/care effects and allocated village workloads."""
    enum_cfg = config["enumerators"]
    n_enumerators = int(enum_cfg.get("n_enumerators", 40))
    v_range = enum_cfg.get("villages_per_enumerator", [1, 3])
    min_v, max_v = int(v_range[0]), int(v_range[1])
    workload_range = enum_cfg.get("workload", [5, 60])
    w_min, w_max = int(workload_range[0]), int(workload_range[1])
    speed_sd = float(enum_cfg.get("speed_sd", 0.20))
    care_sd = float(enum_cfg.get("care_sd", 0.30))
    min_per_village = int(enum_cfg.get("min_enumerators_per_village", 2))

    enumerator_ids = [f"enum_{i+1:02d}" for i in range(n_enumerators)]

    assignments = assign_enumerator_villages(
        enumerator_ids=enumerator_ids,
        village_ids=village_ids,
        rng=rng,
        min_villages=min_v,
        max_villages=max_v,
        min_enumerators_per_village=min_per_village,
    )

    enumerators: Dict[str, Enumerator] = {}
    for e_id in enumerator_ids:
        speed_effect = float(rng.normal(0.0, speed_sd))
        care_effect = float(rng.normal(0.0, care_sd))
        w = int(rng.integers(w_min, w_max + 1))
        e_villages = assignments[e_id]
        v_workloads = allocate_workload_across_villages(w, e_villages, rng)

        enumerators[e_id] = Enumerator(
            enumerator_id=e_id,
            speed_effect=speed_effect,
            care_effect=care_effect,
            total_workload=sum(v_workloads.values()),
            assigned_villages=e_villages,
            village_workloads=v_workloads,
        )

    return enumerators

