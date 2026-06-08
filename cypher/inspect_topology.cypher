// Cluster to application to host paths.
MATCH p=(c:Cluster)-[:HAS_APPLICATION]->(a:Application)-[:DEPLOYED_ON]->(h:Host)
RETURN p
LIMIT 50;

// Application technology usage, including obsolete/risky technologies.
MATCH p=(a:Application)-[r:USES_TECHNOLOGY]->(t:Technology)
RETURN p, r.risk_levels AS risk_levels, r.statuses AS statuses
LIMIT 50;

// Application-to-application derived relationships.
MATCH p=(a:Application)-[r:RELATED_TO]->(b:Application)
RETURN p, r.reasons AS reasons, r.strength AS strength
ORDER BY r.strength DESC
LIMIT 50;

// Full neighborhood for one application.
MATCH p=(a:Application {id: "app_payments"})-[*1..2]-(n)
RETURN p
LIMIT 100;

// Hosts with multiple applications.
MATCH (h:Host)<-[:DEPLOYED_ON]-(a:Application)
WITH h, collect(a.name) AS applications
WHERE size(applications) > 1
RETURN h.name AS host, applications
ORDER BY host;
