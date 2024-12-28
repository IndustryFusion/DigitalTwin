# Supported Features for the SHACL to Flink transformation

## Target Nodes

SHACL defines a mechanism to select the node which is validated. The following mechanisms are supported


<table>
<tr>
<th> Feature </th>
<th> Example </th>
<th> Implemented </th>
</tr>
<tr>
<td>

```turtle
sh:targetNode
```
</td>
<td>

```turtle
cutterTemperatureShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
</table>


## Constraint Components

<table>

<tr>
<th> Feature </th>
<th> Example </th>
<th> Implemented </th>
</tr>

<tr>
<td>

```turtle
sh:class
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasState ;
        sh:property [
            sh:class ontology:MachineState ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>

<tr>
<td>

```turtle
sh:datatype
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:datatype xsd:double ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: red">&#10007;</td>
</tr>
<tr>
<td>

```turtle
sh:nodeKind
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:nodeKind sh:Literal ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minCount
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:minCount 1 ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxCount
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:maxCount 1 ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minExclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:minExclusive 20.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minInclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:minExclusive 20.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxExclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:maxExclusive 50.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxInclusive
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:property [
            sh:maxInclusive 50.0 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:minLength
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:minLength 5 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:maxLength
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:maxLength 5 ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:pattern
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:pattern "^1\\.\\d{4,5}" ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:in
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:in ("Hello" "World") ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:hasValue
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:path iffbase:hasStringExample ;
        sh:property [
            sh:hasValue "Hello World" ;
        ]
    ] .
```

</td>
<td style="font-size: 50px;color: red">&#10007;</td>
</tr>
<tr>
<td>

```turtle
sh:not
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:not
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ] .
```

</td>
<td style="font-size: 50px;color: red">&#10007;</td>
</tr>
<tr>
<td>

```turtle
sh:or
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:or (
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ]
        [
            sh:property [
                sh:path iffbase:hasTemperature2 ;
                sh:property [
                    sh:minInclusive 20.0 ;
                ]
            ]
        ]
    ) .
```

</td>
<td style="font-size: 50px;color: red">&#10007;</td>
</tr>
<tr>
<td>

```turtle
sh:and
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:and (
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ]
        [
            sh:property [
                sh:path iffbase:hasTemperature2 ;
                sh:property [
                    sh:minInclusive 20.0 ;
                ]
            ]
        ]
    ) .
```

</td>
<td style="font-size: 50px;color: red">&#10007;</td>
</tr>
<tr>
<td>

```turtle
sh:xone
```

</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:xone (
        [
            sh:property [
                sh:path iffbase:hasTemperature ;
                sh:property [
                    sh:maxInclusive 50.0 ;
                ]
            ]
        ]
        [
            sh:property [
                sh:path iffbase:hasTemperature2 ;
                sh:property [
                    sh:minInclusive 20.0 ;
                ]
            ]
        ]
    ) .
```

</td>
<td style="font-size: 50px;color: red">&#10007;</td>
</tr>
<tr>
<td>

```turtle
sh:sparql
```
</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:select """
        """
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:message
```
</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:sparql [
        sh:message "Cutter {?this} executing without executing filter {?filter}" ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```turtle
sh:severity
```
</td>
<td>

```turtle
:demoShape a sh:NodeShape ;
    sh:property [
        sh:severity iffbase:severityCritical ] ;
        sh:path iffbase:hasAttribute ;
    ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
</table>

## Sparql based constraints

### Sparql Query

The following SPARQL features are supported

<table>
<tr>
<th> Feature </th>
<th> Example </th>
<th> Implemented </th>
</tr>
<tr>
<td>

```
Basic Graph Pattern (BGP)
```
</td>
<td>

```sparql
    ?this iffbase:hasFilter [ ngsi-ld:hasObject ?filter ] .
    ?this iffbase:hasState [ ngsi-ld:hasValue ?cstate ] .
    ?filter iffbase:hasState [ ngsi-ld:hasValue ?fstate ] .
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```

OPTIONAL {}
(only single triple supported)
```
</td>
<td>

```sparql
OPTIONAL{ ?this iffbase:hasFilter [ ngsi-ld:hasObject ?filter ] }
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
BIND
```
</td>
<td>

```turtle
BIND("hello world") as ?value
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
BOUND
```
</td>
<td>

```turtle
BOUND(?value)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
IF
```
</td>
<td>

```turtle
IF(condition, true, false)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
FILTER
```
</td>
<td>

```turtle
FILTER (?cstate = ontology:executingState && ?fstate != ontology:executingState)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
ConditionalOrExpression
```
</td>
<td>

```turtle
?cstate = ontology:executingState || ?fstate != ontology:executingState
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
ConditionalAndExpression
```
</td>
<td>

```turtle
?cstate = ontology:executingState && ?fstate != ontology:executingState
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
RelationalExpression
(=, !=, <,>, <=, >=, IN, NOT IN)
```
</td>
<td>

```turtle
?x > 5 
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
JOIN
```
</td>
<td>

```sparql
{BGP}
{BGP}
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
NOT EXISTS
```
</td>
<td>

```turtle
    FILTER NOT EXISTS{
        BGP
    }

```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
DISTINCT
```
</td>
<td>

```turtle
SELECT DISTINCT ?value
    WHERE {}
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>

<tr>
<td>

```
Now
```
</td>
<td>

```turtle
NOW()
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
CAST
(xsd:integer, xsd:float, xsd:dateTime, xsd:string)
```
</td>
<td>

```turtle
xsd:integer(?value)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
Additive Expression
```
</td>
<td>

```turtle
?value1 + ?value2
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
UnaryNot
```
</td>
<td>

```turtle
!(?value)
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
<tr>
<td>

```
Multiplicative Expression
(*, /)
```
</td>
<td>

```turtle
?value1 * ?value2
```

</td>
<td style="font-size: 50px;color: green;">&#10003;</td>
</tr>
</table>

### Construct
TBD