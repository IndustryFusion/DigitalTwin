# Fuseki SPARQL / RDF Triplestore API

Apache Jena Fuseki 6 serves as the persistent RDF triplestore for the DigitalTwin platform. It stores named graphs per Keycloak realm and exposes standard SPARQL and Graph Store Protocol (GSP) endpoints, protected by a JWT-validating auth proxy.

## Base URL

```
https://fuseki.local
```

All endpoints are relative to this base. Replace `<realm>` with the Keycloak realm name (default: `iff`).

---

## Authentication

Every request (except the health check) requires a Bearer JWT issued by Keycloak.

### Obtain a token

```bash
curl -sf \
  -d "client_id=fuseki" \
  -d "client_secret=<client-secret>" \
  -d "grant_type=client_credentials" \
  "https://keycloak.local/auth/realms/<realm>/protocol/openid-connect/token" \
  | jq -r ".access_token"
```

Retrieve the client secret from the cluster:

```bash
kubectl -n iff get secret/keycloak-client-secret-fuseki \
  -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d
```

### Required roles

| Role | Grants |
|---|---|
| `Factory-Admin` | Read + Write (PUT, POST, DELETE, SPARQL Update) |
| `Factory-Reader` | Read only (GET, SPARQL SELECT/ASK/CONSTRUCT/DESCRIBE) |

Roles are carried in the JWT under `resource_access.fuseki.roles`. The auth proxy enforces them per endpoint and HTTP method — a missing or wrong role returns **403**, an invalid/expired token returns **401**.

---

## Named graph convention

Graphs follow this naming scheme:

```
https://fuseki.local/<realm>/<graph-name>
```

Examples for the `iff` realm:
- `http://fuseki.local/iff/shacl.ttl`
- `http://fuseki.local/iff/knowledge.ttl`

---

## Endpoints

### Health check

```
GET /$/ping
```

No auth required. Returns the server timestamp as plain text. Use for liveness/readiness probes.

```bash
curl https://fuseki.local/$/ping
# 2026-06-28T19:34:17.373+00:00
```

---

### Graph Store Protocol (GSP)

Base path: `/<realm>/data`

All GSP write operations require the `Factory-Admin` role. Reads require at least `Factory-Reader`.

#### Retrieve a named graph

```
GET /<realm>/data?graph=<graph-uri>
```

Returns the graph as RDF. Use the `Accept` header to control the serialisation format.

```bash
curl -s \
  -H "Authorization: Bearer <token>" \
  -H "Accept: text/turtle" \
  "https://fuseki.local/iff/data?graph=http://fuseki.local/iff/shacl.ttl"
```

| Status | Meaning |
|---|---|
| 200 | Graph returned |
| 404 | Graph does not exist |
| 401 | Missing or invalid token |
| 403 | Token valid but lacks `Factory-Reader` role |

Supported `Accept` types: `text/turtle`, `application/n-triples`, `application/ld+json`, `application/rdf+xml`.

#### Replace a named graph (full upload)

```
PUT /<realm>/data?graph=<graph-uri>
```

Replaces the entire graph. Creates it if it does not exist.

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X PUT \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: text/turtle" \
  --data-binary @shacl.ttl \
  "https://fuseki.local/iff/data?graph=http://fuseki.local/iff/shacl.ttl"
```

| Status | Meaning |
|---|---|
| 201 | Graph created |
| 200 | Graph replaced |
| 401 | Missing or invalid token |
| 403 | Token valid but lacks `Factory-Admin` role |

#### Add triples to a named graph

```
POST /<realm>/data?graph=<graph-uri>
```

Merges the uploaded triples into the existing graph (does not remove existing triples).

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: text/turtle" \
  --data-binary @extra-triples.ttl \
  "https://fuseki.local/iff/data?graph=http://fuseki.local/iff/knowledge.ttl"
```

| Status | Meaning |
|---|---|
| 200 | Triples merged |
| 401/403 | Auth failure |

#### Delete a named graph

```
DELETE /<realm>/data?graph=<graph-uri>
```

Removes the graph and all its triples.

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE \
  -H "Authorization: Bearer <token>" \
  "https://fuseki.local/iff/data?graph=http://fuseki.local/iff/shacl.ttl"
```

| Status | Meaning |
|---|---|
| 200 | Graph deleted |
| 404 | Graph did not exist |
| 401/403 | Auth failure |

---

### SPARQL Query endpoint

```
GET  /<realm>/sparql?query=<url-encoded-sparql>
POST /<realm>/sparql
```

Supports SELECT, ASK, CONSTRUCT, and DESCRIBE. Requires at least `Factory-Reader`.

#### SELECT via GET

```bash
TOKEN=$(curl -sf \
  -d "client_id=fuseki" -d "client_secret=<secret>" \
  -d "grant_type=client_credentials" \
  "https://keycloak.local/auth/realms/iff/protocol/openid-connect/token" \
  | jq -r ".access_token")

curl -sG \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/sparql-results+json" \
  --data-urlencode "query=SELECT ?shape WHERE {
      GRAPH <http://fuseki.local/iff/shacl.ttl> {
          ?shape a <http://www.w3.org/ns/shacl#NodeShape>
      }
  } LIMIT 10" \
  "https://fuseki.local/iff/sparql"
```

Response (JSON):

```json
{
  "head": { "vars": ["shape"] },
  "results": {
    "bindings": [
      { "shape": { "type": "uri", "value": "https://example.com/cutterTemperatureWithMinMaxShape" } }
    ]
  }
}
```

#### SELECT via POST (for long queries)

```bash
curl -s \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/sparql-query" \
  -H "Accept: application/sparql-results+json" \
  --data "SELECT ?cls WHERE { GRAPH <http://fuseki.local/iff/knowledge.ttl> { ?cls a <http://www.w3.org/2002/07/owl#Class> } }" \
  "https://fuseki.local/iff/sparql"
```

#### CONSTRUCT

```bash
curl -sG \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: text/turtle" \
  --data-urlencode "query=CONSTRUCT { ?s ?p ?o } WHERE {
      GRAPH <http://fuseki.local/iff/knowledge.ttl> { ?s ?p ?o }
  }" \
  "https://fuseki.local/iff/sparql"
```

Supported `Accept` types for SPARQL results: `application/sparql-results+json`, `application/sparql-results+xml`, `text/csv`, `text/tab-separated-values`.

Supported `Accept` types for CONSTRUCT/DESCRIBE: same as GSP read above.

| Status | Meaning |
|---|---|
| 200 | Query executed, results returned |
| 400 | Malformed SPARQL |
| 401/403 | Auth failure |

---

### SPARQL Update endpoint

```
POST /<realm>/update
```

Executes SPARQL Update operations (INSERT DATA, DELETE DATA, LOAD, etc.). Requires `Factory-Admin`.

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/sparql-update" \
  --data "INSERT DATA {
      GRAPH <http://fuseki.local/iff/knowledge.ttl> {
          <http://example.com/Machine> a <http://www.w3.org/2002/07/owl#Class> .
      }
  }" \
  "https://fuseki.local/iff/update"
```

| Status | Meaning |
|---|---|
| 200 | Update executed |
| 400 | Malformed SPARQL Update |
| 401/403 | Auth failure |

---

## Common HTTP status codes

| Code | Cause |
|---|---|
| 200 | Success |
| 201 | Resource created (first PUT of a graph) |
| 400 | Bad request (malformed query or body) |
| 401 | No token, expired token, or invalid JWT signature |
| 403 | Valid token but role insufficient for the operation |
| 404 | Named graph does not exist |
| 500 | Upstream error — check Fuseki pod logs and Traefik ForwardAuth connectivity |

A 500 on authenticated requests usually means the auth proxy (`fuseki-auth`) is unreachable. Verify with:

```bash
kubectl -n iff get pods -l app=fuseki-auth
kubectl -n iff logs -l app=fuseki-auth --tail=50
```
