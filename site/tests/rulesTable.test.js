import test from "node:test";
import assert from "node:assert";
import { JSDOM } from "jsdom";

test("renderRuleTableRow returns HTMLTableRowElement with exactly 8 cells in correct header order", async () => {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
  global.document = dom.window.document;

  const { renderRuleTableRow, renderExecutedRulesTable } = await import("../src/components/ruleEngineHelpers.js");

  const sampleRule = {
    id: "RULE_01",
    level: "submission",
    severity: "critical",
    description: "GPS coordinate is exactly (0,0)",
    hits: 5,
    expected: 5,
    pass: true,
    ms: 7.54,
  };

  // 1. Assert row is a real HTMLTableRowElement with exactly 8 cells
  const row = renderRuleTableRow(sampleRule);
  assert.ok(row instanceof dom.window.HTMLTableRowElement, "row must be an HTMLTableRowElement");
  assert.strictEqual(row.cells.length, 8, "row must have exactly 8 cells");

  // 2. Assert header order: Rule, Level, Severity, Description, Browser, Python, Parity, Time
  assert.strictEqual(row.cells[0].textContent, "RULE_01", "Cell 0 must be Rule");
  assert.strictEqual(row.cells[1].textContent, "submission", "Cell 1 must be Level");
  assert.strictEqual(row.cells[2].textContent, "critical", "Cell 2 must be Severity");
  assert.strictEqual(row.cells[3].textContent, "GPS coordinate is exactly (0,0)", "Cell 3 must be Description");
  assert.strictEqual(row.cells[4].textContent, "5", "Cell 4 must be Browser hits");
  assert.strictEqual(row.cells[5].textContent, "5", "Cell 5 must be Python expected hits");
  assert.strictEqual(row.cells[6].textContent, "✓", "Cell 6 must be Parity pass");
  assert.strictEqual(row.cells[7].textContent, "7.5 ms", "Cell 7 must be Time with 1 decimal ms");
  assert.ok(row.cells[7].style.cssText.includes("white-space: nowrap"), "Time cell must have white-space: nowrap");

  // 3. Assert full table structure: thead has 8 th, tbody contains only tr elements with 8 cells
  const tableContainer = renderExecutedRulesTable([sampleRule, { ...sampleRule, id: "RULE_02", pass: false }]);
  const table = tableContainer.querySelector("table");
  assert.ok(table, "table must exist");
  assert.strictEqual(table.rows.length, 3, "table.rows.length must be 3 (1 thead + 2 tbody)");

  const ths = table.querySelectorAll("thead th");
  assert.strictEqual(ths.length, 8, "thead must have exactly 8 th headers");

  const tbodyTrs = table.querySelectorAll("tbody tr");
  assert.strictEqual(tbodyTrs.length, 2, "tbody must contain exactly 2 tr elements");
  for (const tr of tbodyTrs) {
    assert.ok(tr instanceof dom.window.HTMLTableRowElement, "tbody child must be an HTMLTableRowElement");
    assert.strictEqual(tr.cells.length, 8, "each tbody row must have exactly 8 cells");
  }
});
