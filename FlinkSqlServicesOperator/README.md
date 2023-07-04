# Flink SQL Operator

This operator uses 3 CRDs:

- beamsqlstatementsets.industry-fusion.com/v1alpha[23]
- beamsqltables.industry-fusion.com/v1alpha2
- beamsqlviews.industry-fusion.com/v1alpha1


# beamsqlstatementsets

Are defining a set of SQL statements. These statements are deployed on an Apache Flink cluster.
The SQL statements are either put directly into the `sqlstatements` field. If the size of statements is larger, the statements can put into
configmaps and reference them in `sqlstatementmaps.

```yaml
---
apiVersion: industry-fusion.com/v1alpha2
kind: BeamSqlStatementSet
metadata:
  name: beamsqlstatementset-example
  namespace: iff
spec:
  sqlstatements:
    - insert into `metrics-copy` select `aid`, `cid`, `dataType`, `on`, `systemon`, `value` FROM `metrics`;
  tables:
    - metrics
    - metrics-copy
---
apiVersion: industry-fusion.com/v1alpha3
kind: BeamSqlStatementSet
metadata:
  name: beamsqlstatementset-example
  namespace: iff
spec:
  sqlstatementmaps:
    - iff/configmap1-example
    - iff/configmap2-example
  tables:
    - test
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: configmap1-example
  namespace: iff
data:
  0: insert into test select '1', 'type';
  1: insert into test select '2', 'type';;
  2: insert into test select '3', 'type';;
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: configmap2-example
  namespace: iff
data:
  0: insert into test select '1', 'type';;

```

# BeamSqlTable

The CRDs `BeamSqlTable`  define SQL tables and views which can be used by sql statementsets.

```yaml
---
apiVersion: industry-fusion.com/v1alpha2
kind: BeamSqlTable
metadata:
  name: test
  namespace: iff
spec:
  name: test
  connector: kafka
  fields:
  - 'id': STRING
  - 'type': STRING
  kafka:
    topic: iff.ngsild.entities.test
    properties:
      bootstrap.servers: test-bootstrap:9092
    scan.startup.mode: latest-offset
  value:
    format: json
    json.fail-on-missing-field: false
    json.ignore-parse-errors: true

```


# BeamSqlView

`BeamSqlView` defines a table view as SQL statement:

```
apiVersion: industry-fusion.com/v1alpha1
kind: BeamSqlView
metadata:
  name: test-view
spec:
  name: test_view
  sqlstatement: |
    SELECT id, `type`
    FROM (
      SELECT *,
      ROW_NUMBER() OVER (PARTITION BY `id`
         ORDER BY ts DESC) AS rownum
      FROM `test`)
      WHERE rownum = 1 and entityId is NOT NULL;

```


# Test and Debug

Test locally with

```
python3 -m kopf run beamsqlstatementsetoperator.py
```

To debug locally with VS-Code:

```
python3 -m debugpy --listen 5678 --wait-for-client -m kopf run beamsqlstatementsetoperator.py
```