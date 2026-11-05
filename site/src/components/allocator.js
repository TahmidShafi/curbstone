/**
 * Back-check allocator interface placeholder for Step 1 scaffold.
 * Full implementation with Mulberry32 PRNG and evidence prioritization implemented in Step 2.
 */
export function allocateBackChecks({ enumerators }) {
  const allocatedCounts = {};
  for (const e of enumerators) {
    allocatedCounts[e.id] = 0;
  }
  return {
    allocatedCounts,
    selectedSubmissions: [],
    totalAllocated: 0,
    floorAllocated: 0,
    riskAllocated: 0,
  };
}
