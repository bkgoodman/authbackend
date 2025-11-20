#!/bin/sh 

echo "Number of Users who have used each resource (Jan 1 - Nov 15)"
/usr/bin/sqlite3 ../../../log.db << EOF
.mode csv
ATTACH DATABASE '../../../makeit.db' AS makeit;

SELECT
    r.name AS resource_name,
    strftime('%Y', l.time_logged) AS year,
    COUNT(DISTINCT l.member_id) AS unique_members
FROM main.log AS l
JOIN makeit.resources AS r ON l.resource_id = r.id
WHERE strftime('%m-%d', l.time_logged) <= '11-15'
GROUP BY r.name, strftime('%Y', l.time_logged)
ORDER BY r.name, year;

