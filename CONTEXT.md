# curbstone — project context (do not modify without instruction)

Purpose: detect likely fabricated survey interviews (curbstoning) at the
enumerator level, using synthetic data with known ground truth.

Stack: Python 3.11+ (numpy, pandas, pyarrow, duckdb, scipy, pyyaml, pytest).
TypeScript/Observable Framework comes later — do not create it yet.

Hard rules:
- All randomness goes through a single seeded numpy Generator passed as an argument.
  No global random state.
- Every function with statistical logic gets a pytest test.
- Never invent calibration numbers. If a value is needed and not given,
  put it in config/params.yaml with the comment `# ASSUMPTION – verify`.
- Do not implement detection, scoring, or fraud logic unless the task says so.
- Do not add dependencies beyond the list above without asking.
- Keep each file under ~300 lines; split modules if larger.
- End every task with a short summary: files changed, how to run, open questions.
- engine/ must never read truth/ or import generator.fraud.
- Rules may use only: the submissions table, and a reference table
  `villages(village_id, upazila_code, ref_lat, ref_lon)` written by the generator to
  data/reference/villages.parquet (real MIS systems hold village reference locations).
