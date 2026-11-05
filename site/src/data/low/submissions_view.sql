CREATE VIEW submissions AS
SELECT *,
    CASE
        WHEN CAST(start_time AS VARCHAR) LIKE '%+06:00%' THEN CAST(start_time AS TIMESTAMP)
        WHEN CAST(start_time AS VARCHAR) LIKE '%Z%' OR CAST(start_time AS VARCHAR) LIKE '%+00:00%'
            THEN CAST(start_time AS TIMESTAMP) + INTERVAL 6 HOUR
        ELSE CAST(start_time AS TIMESTAMP)
    END AS start_local,
    CASE
        WHEN CAST(end_time AS VARCHAR) LIKE '%+06:00%' THEN CAST(end_time AS TIMESTAMP)
        WHEN CAST(end_time AS VARCHAR) LIKE '%Z%' OR CAST(end_time AS VARCHAR) LIKE '%+00:00%'
            THEN CAST(end_time AS TIMESTAMP) + INTERVAL 6 HOUR
        ELSE CAST(end_time AS TIMESTAMP)
    END AS end_local
FROM _raw_submissions;
