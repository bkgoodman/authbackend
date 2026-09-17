#!/bin/sh 

echo "HTML:"
echo "</pre>"
echo "<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
echo "<h2 style='color: #333; margin-top: 0;'>Users trained on each resource per year (Jan 1 - Nov 15)</h2>"
echo "<table class='table table-striped table-bordered table-sm mt-3'>"
echo "<thead class='thead-dark'><tr><th>Resource Name</th><th>Resource ID</th><th>Year</th><th>Event Count</th></tr></thead>"
echo "<tbody>"
/usr/bin/sqlite3 ../../../log.db << EOF
.mode html
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
echo "</tbody>"
echo "</table>"
echo "</div>"
echo "<pre>"
