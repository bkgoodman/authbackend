#!/bin/sh 

echo "Users trained on each resource per hear (Jan 1 - Nov 15)"
/usr/bin/sqlite3 ../../../log.db << EOF
.mode csv
ATTACH DATABASE '../../../makeit.db' AS makeit;

SELECT 
    r.name AS resource_name,
    l.resource_id,
    strftime('%Y', l.time_logged) AS year,
    COUNT(*) AS event_count
FROM main.log AS l
JOIN makeit.resources AS r ON l.resource_id = r.id
WHERE l.event_type = 4000
  AND strftime('%m-%d', l.time_logged) <= '11-15'
GROUP BY l.resource_id, strftime('%Y', l.time_logged)
ORDER BY r.name, year;
EOF
