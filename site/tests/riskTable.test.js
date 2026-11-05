import test from "node:test";
import assert from "node:assert";
import { JSDOM } from "jsdom";

test("renderRiskTable creates real DOM Node instances and no stringified [object ...]", async () => {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
  global.document = dom.window.document;
  global.Event = dom.window.Event;
  global.Node = dom.window.Node;

  const { renderRiskTable, renderRowNode } = await import("../src/components/riskTable.js");

  const sampleRows = [
    { rank: 1, enumerator_id: "enum_01", n: 20, risk_score: 2.5, evidence: "F1", strongest_est: -1.2, strongest_ci_low: -0.5, strongest_ci_high: 0.5, rule_hits: 1, allocated_backchecks: 5, truth_label: "TN" },
    { rank: 2, enumerator_id: "enum_02", n: 15, risk_score: 1.8, evidence: "F3, F7", strongest_est: 0.3, strongest_ci_low: 0.0, strongest_ci_high: 0.1, rule_hits: 0, allocated_backchecks: 3, truth_label: "TN" },
    { rank: 3, enumerator_id: "enum_03", n: 18, risk_score: 1.2, evidence: "", strongest_est: null, strongest_ci_low: null, strongest_ci_high: null, rule_hits: 0, allocated_backchecks: 2, truth_label: "TN" },
    { rank: 4, enumerator_id: "enum_04", n: 25, risk_score: 0.9, evidence: "F2", strongest_est: 1.1, strongest_ci_low: -0.2, strongest_ci_high: 0.2, rule_hits: 0, allocated_backchecks: 1, truth_label: "TN" },
    { rank: 5, enumerator_id: "enum_05", n: 10, risk_score: 0.2, evidence: "", strongest_est: null, strongest_ci_low: null, strongest_ci_high: null, rule_hits: 0, allocated_backchecks: 0, truth_label: "TN" },
  ];

  // 1. Assert renderRowNode returns a real HTMLTableRowElement node
  const rowNode = renderRowNode(sampleRows[0], false, 2.5, false, () => {});
  assert.ok(rowNode instanceof dom.window.HTMLTableRowElement, "rowNode must be an HTMLTableRowElement");

  // 2. Assert renderRiskTable returns a real HTMLDivElement container
  const tableContainer = renderRiskTable({
    rows: sampleRows,
    selectedId: "enum_01",
    onSelect: () => {},
    isRevealed: true,
  });
  assert.ok(tableContainer instanceof dom.window.HTMLDivElement, "tableContainer must be an HTMLDivElement");

  // 3. Assert tbody has real row elements and divider and drawer
  const tbody = tableContainer.querySelector("tbody");
  assert.ok(tbody, "tbody must exist");

  const trs = tbody.querySelectorAll("tr");
  // 5 rows + 1 divider (after rank 4) + 1 drawer (enum_01 is selected) = 7 trs
  assert.strictEqual(trs.length, 7, "tbody must have 7 tr elements (5 rows + 1 divider + 1 drawer)");

  // 4. Assert no stringified "[object HTMLTableRowElement]" text anywhere
  assert.strictEqual(tbody.textContent.includes("[object"), false, "tbody must not contain '[object' text");
  assert.strictEqual(tbody.innerHTML.includes("[object"), false, "tbody HTML must not contain '[object'");
});
