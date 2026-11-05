import test from "node:test";
import assert from "node:assert/strict";
import { allocateBackChecks, mulberry32 } from "../src/components/allocator.js";

function generateMockData() {
  const enumerators = [
    { id: "enum_01", n: 10, risk: 9.5 },
    { id: "enum_02", n: 20, risk: 4.2 },
    { id: "enum_03", n: 15, risk: 0.1 },
    { id: "enum_04", n: 5,  risk: 0.0 },
    { id: "enum_05", n: 30, risk: 1.5 },
  ];
  const submissions = [];
  const evidenceIds = [];
  let subId = 1;
  for (const e of enumerators) {
    for (let i = 0; i < e.n; i++) {
      const sId = `sub_${subId++}`;
      if (i < 3 && e.risk > 1.0) {
        evidenceIds.push(sId);
      }
      submissions.push({
        submission_id: sId,
        enumerator_id: e.id,
        duration_min: 25.0,
      });
    }
  }
  return { enumerators, submissions, evidenceIds };
}

test("Budget cap respected: total = min(B, total submissions)", () => {
  const { enumerators, submissions, evidenceIds } = generateMockData();
  const totalSubs = submissions.length; // 80

  // 1. Normal budget
  const res1 = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 30 });
  assert.equal(res1.totalAllocated, 30);
  assert.equal(res1.selectedSubmissions.length, 30);

  // 2. Excess budget (greater than total submissions)
  const res2 = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 150 });
  assert.equal(res2.totalAllocated, totalSubs);
  assert.equal(res2.selectedSubmissions.length, totalSubs);

  // 3. Zero budget
  const res3 = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 0 });
  assert.equal(res3.totalAllocated, 0);
  assert.equal(res3.selectedSubmissions.length, 0);
});

test("Enumerator caps respected: allocated <= n for each enumerator", () => {
  const { enumerators, submissions, evidenceIds } = generateMockData();
  const res = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 60, floorShare: 0.10 });

  for (const e of enumerators) {
    const allocated = res.allocatedCounts[e.id] || 0;
    assert.ok(
      allocated <= e.n,
      `Enumerator ${e.id} allocated ${allocated} which exceeds capacity ${e.n}`
    );
  }
});

test("Determinism: same inputs and seed produce identical allocation", () => {
  const { enumerators, submissions, evidenceIds } = generateMockData();

  const run1 = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 40, seed: 12345 });
  const run2 = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 40, seed: 12345 });

  assert.deepEqual(run1.allocatedCounts, run2.allocatedCounts);
  assert.deepEqual(
    run1.selectedSubmissions.map(s => s.submission_id),
    run2.selectedSubmissions.map(s => s.submission_id)
  );

  // Different seed should differ
  const run3 = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 40, seed: 99999 });
  const ids1 = run1.selectedSubmissions.map(s => s.submission_id).join(",");
  const ids3 = run3.selectedSubmissions.map(s => s.submission_id).join(",");
  assert.notEqual(ids1, ids3);
});

test("Floor share > 0 gives every enumerator positive selection probability", () => {
  const { enumerators, submissions, evidenceIds } = generateMockData();
  const pickedCounts = Object.fromEntries(enumerators.map(e => [e.id, 0]));
  const nSimulations = 200;

  for (let s = 1; s <= nSimulations; s++) {
    const res = allocateBackChecks({
      enumerators,
      submissions,
      evidenceIds,
      budget: 15,
      floorShare: 0.30,
      seed: s * 101,
    });
    for (const e of enumerators) {
      if ((res.allocatedCounts[e.id] || 0) > 0) {
        pickedCounts[e.id]++;
      }
    }
  }

  // Every enumerator (even enum_04 with risk = 0) must be picked in a positive share of simulations
  for (const e of enumerators) {
    assert.ok(
      pickedCounts[e.id] > 0,
      `Enumerator ${e.id} with risk ${e.risk} was never selected despite floor share > 0`
    );
  }
});

test("Evidence prioritization: picks evidence submissions first", () => {
  const { enumerators, submissions, evidenceIds } = generateMockData();
  // Allocate to high-risk enum_01 with 3 evidence items
  const res = allocateBackChecks({ enumerators, submissions, evidenceIds, budget: 50, floorShare: 0.0, seed: 42 });

  const e1Selected = res.selectedSubmissions.filter(s => s.enumerator_id === "enum_01");
  const e1EvCount = e1Selected.filter(s => s.is_evidence).length;
  // All 3 evidence items for enum_01 should be picked before non-evidence items
  assert.equal(e1EvCount, 3);
});

