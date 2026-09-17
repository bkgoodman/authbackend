#!/bin/sh 

echo "HTML:"
echo "</pre>"
echo "<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
echo "<h2 style='color: #333; margin-top: 0;'>Number of Users who have used each resource (Jan 1 - Nov 15)</h2>"
echo "<table class='table table-striped table-bordered table-sm mt-3'>"
echo "<thead class='thead-dark'><tr><th>Resource Name</th><th>Year</th><th>Unique Members</th></tr></thead>"
echo "<tbody>"
/usr/bin/sqlite3 ../../../log.db << EOF
.mode html
ATTACH DATABASE '../../../makeit.db' AS makeit;

SELECT
    r.name AS resource_name,
    strftime('%Y', l.time_logged) AS year,
    COUNT(DISTINCT l.member_id) AS unique_members
FROM main.log AS l
JOIN makeit.resources AS r ON l.resource_id = r.id
WHERE strftime('%m-%d', l.time_logged) <= '11-15'
    AND  (l.event_type = 3013 OR l.event_type = 1025)
    AND  l.member_id > 0
GROUP BY r.name, strftime('%Y', l.time_logged)
ORDER BY r.name, year;
EOF
echo "</tbody>"
echo "</table>"
echo "</div>"
echo "<pre>"
