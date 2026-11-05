-- Standard submissions view with offset-free local timestamp derivations
CREATE OR REPLACE VIEW submissions AS
SELECT *,
    CAST(substr(start_time, 1, 19) AS TIMESTAMP) AS start_local,
    CAST(substr(end_time, 1, 19) AS TIMESTAMP) AS end_local
FROM _raw_submissions;

