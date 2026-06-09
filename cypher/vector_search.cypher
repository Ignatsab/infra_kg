// These examples assume the graph was exported or loaded with embeddings:
// python3 scripts/load_memgraph.py --clear --embed openai

// Create a vector index manually if needed. The loader also tries to create
// per-label vector indexes automatically when nodes have an embedding property.
CREATE VECTOR INDEX application_embedding_index ON :Application(embedding)
WITH CONFIG {'dimension': 1536, 'capacity': 10000, 'metric': 'cos'};

// Semantic search, then graph expansion from the retrieved node.
CALL vector_search.search('application_embedding_index', 5, $query_vector)
YIELD node, similarity
MATCH p=(node)-[*1..2]-(neighbor)
RETURN node.id AS seed_id,
       node.name AS seed_name,
       similarity,
       p
ORDER BY similarity DESC
LIMIT 50;

// Search technologies by meaning, then find affected applications and hosts.
CALL vector_search.search('technology_embedding_index', 5, $query_vector)
YIELD node, similarity
MATCH p=(app:Application)-[:USES_TECHNOLOGY]->(node)<-[:HAS_TECHNOLOGY]-(host:Host)
RETURN node.name AS technology,
       node.version AS version,
       similarity,
       app.name AS application,
       host.name AS host,
       p
ORDER BY similarity DESC;
