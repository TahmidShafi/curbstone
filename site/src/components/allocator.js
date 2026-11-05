/**
 * Pure function back-check allocator for survey quality audits.
 *
 * Implements:
 * 1. Floor allocation: floor = round(f * B) interviews spread uniformly at random over all enumerators.
 * 2. Risk allocation: remainder allocated in proportion to max(risk, 0), capped at available submissions, largest-remainder rounding.
 * 3. Submission selection: picks evidence submissions first, then random remaining submissions.
 */

export function mulberry32(seed) {
  let a = (seed >>> 0) || 1;
  return function() {
    let t = (a += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffleArray(array, rng) {
  const arr = [...array];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export function allocateBackChecks({
  enumerators,
  submissions,
  evidenceIds = [],
  budget = 60,
  floorShare = 0.20,
  seed = 42,
}) {
  const rng = mulberry32(seed);
  const evSet = new Set(evidenceIds);

  // Group submissions by enumerator
  const subsByEnum = new Map();
  for (const e of enumerators) {
    subsByEnum.set(e.id, []);
  }
  for (const sub of submissions) {
    const list = subsByEnum.get(sub.enumerator_id);
    if (list) list.push(sub);
  }

  // Cap totals
  const totalSubmissions = submissions.length;
  const effectiveBudget = Math.min(Math.max(0, Math.floor(budget)), totalSubmissions);

  const allocated = new Map();
  const available = new Map();
  for (const e of enumerators) {
    allocated.set(e.id, 0);
    available.set(e.id, subsByEnum.get(e.id)?.length || 0);
  }

  // 1. Floor allocation: round(f * B) interviews spread uniformly across enumerators
  const floorTarget = Math.min(effectiveBudget, Math.round(floorShare * effectiveBudget));
  let floorCount = 0;

  while (floorCount < floorTarget) {
    const candidates = enumerators.filter(e => available.get(e.id) > 0);
    if (candidates.length === 0) break;
    const idx = Math.floor(rng() * candidates.length);
    const chosen = candidates[idx].id;
    allocated.set(chosen, allocated.get(chosen) + 1);
    available.set(chosen, available.get(chosen) - 1);
    floorCount++;
  }

  // 2. Risk allocation: remainder proportional to max(risk, 0), capped at remaining available
  let remainderBudget = effectiveBudget - floorCount;
  const weights = new Map();
  let totalWeight = 0;
  for (const e of enumerators) {
    const w = Math.max(0, Number(e.risk) || 0);
    weights.set(e.id, w);
    if (available.get(e.id) > 0) {
      totalWeight += w;
    }
  }

  if (remainderBudget > 0 && totalWeight > 0) {
    // Quotas and largest-remainder method
    const quotas = [];
    let initialAssigned = 0;

    for (const e of enumerators) {
      const cap = available.get(e.id);
      if (cap <= 0) continue;
      const exactQuota = (weights.get(e.id) / totalWeight) * remainderBudget;
      const intPart = Math.min(cap, Math.floor(exactQuota));
      initialAssigned += intPart;
      quotas.push({
        id: e.id,
        cap,
        assigned: intPart,
        remainder: exactQuota - Math.floor(exactQuota),
      });
    }

    for (const q of quotas) {
      allocated.set(q.id, allocated.get(q.id) + q.assigned);
      available.set(q.id, available.get(q.id) - q.assigned);
    }
    remainderBudget -= initialAssigned;

    // Distribute remaining units by largest remainder
    quotas.sort((a, b) => b.remainder - a.remainder);
    while (remainderBudget > 0) {
      let madeProgress = false;
      for (const q of quotas) {
        if (remainderBudget <= 0) break;
        if (available.get(q.id) > 0) {
          allocated.set(q.id, allocated.get(q.id) + 1);
          available.set(q.id, available.get(q.id) - 1);
          remainderBudget--;
          madeProgress = true;
        }
      }
      if (!madeProgress) break;
    }
  }

  // If any remainder still unallocated (e.g. totalWeight was 0), distribute randomly among available
  while (remainderBudget > 0) {
    const candidates = enumerators.filter(e => available.get(e.id) > 0);
    if (candidates.length === 0) break;
    const idx = Math.floor(rng() * candidates.length);
    const chosen = candidates[idx].id;
    allocated.set(chosen, allocated.get(chosen) + 1);
    available.set(chosen, available.get(chosen) - 1);
    remainderBudget--;
  }

  // 3. Selection of exact submissions: evidence submissions first, then random
  const selectedSubmissions = [];
  for (const e of enumerators) {
    const k = allocated.get(e.id);
    if (k <= 0) continue;
    const allSubs = subsByEnum.get(e.id) || [];
    const evSubs = allSubs.filter(s => evSet.has(s.submission_id));
    const otherSubs = allSubs.filter(s => !evSet.has(s.submission_id));

    const shuffledEv = shuffleArray(evSubs, rng);
    const shuffledOther = shuffleArray(otherSubs, rng);

    const picked = [];
    for (const s of shuffledEv) {
      if (picked.length < k) picked.push({ ...s, is_evidence: true, selection_reason: "evidence" });
    }
    for (const s of shuffledOther) {
      if (picked.length < k) picked.push({ ...s, is_evidence: false, selection_reason: "random" });
    }
    selectedSubmissions.push(...picked);
  }

  return {
    allocatedCounts: Object.fromEntries(allocated),
    selectedSubmissions,
    totalAllocated: selectedSubmissions.length,
    floorAllocated: floorCount,
    riskAllocated: selectedSubmissions.length - floorCount,
  };
}
