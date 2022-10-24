# Digital Twin of Industry Fusion

---

[![Build](https://github.com/IndustryFusion/DigitalTwin/actions/workflows/build.yaml/badge.svg)](https://github.com/IndustryFusion/DigitalTwin/actions/workflows/build.yaml) [![Coverity Scan](https://scan.coverity.com/projects/24133/badge.svg)](https://scan.coverity.com/projects/industryfusion-digitaltwin)
[![E2E tests](https://github.com/IndustryFusion/DigitalTwin/actions/workflows/k8s-tests.yaml/badge.svg)](https://github.com/IndustryFusion/DigitalTwin/actions/workflows/k8s-tests.yaml)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2FIndustryFusion%2FDigitalTwin.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2FIndustryFusion%2FDigitalTwin?ref=badge_shield)

This repository contains the ingredients for the Ditigal Twin Concept of Industry Fusion. The Digital Twin allows to manage NGSI-LD based entities and allow StreamingSQL and SHACL based descriptions of the processes.

## Architecture

```mermaid
  flowchart LR;
      subgraph Frontend
      A(Gateway)-->B(EMQX/MQTT);
      B-->B1{Kafka/MQTT\nBridge}
      end
      subgraph Digital Twin
      subgraph kafka [Kafka]
      B1-->C[[ Topic\n metrics ]]
      D[[Topic\n iff.alerts]]
      E[[Topic\n iff.ngsildUpdates]]
      F[[Topic\n iff.ngsild.public.entity]]
      G[[ Topics\n iff.entities.filter\niff.entities.cutter\niff.entities.attributes]]
      end
      D --> H1{Alerta\nBridge}
      H1-->H(Alerta)
      E --> O;
      I("Scorpio\n(NGSI-LD Broker)")
      J(Flink)<-->D
      J <--> E
      J <--> G
      J <--> C
      I--> K(Debezium)
      K--> L{Debezium\nBridge}
      L-->G
      O{NGSILD\nBridge}-->I
      end
      subgraph TSDB Backend
        M[(TSDB\nKairos/Cassandra)]
        C-->N{Kafka\nBridge}
        N<-->M
      end
      P(Fusion Application)-->H
      P-->I
      P-->N
      click H "https://github.com/IndustryFusion/DigitalTwin/tree/main/helm/charts/alerta"
      click kafka "https://github.com/IndustryFusion/DigitalTwin/tree/main/helm/charts/kafka"
      click K "https://github.com/IndustryFusion/DigitalTwin/tree/main/DebeziumPostgresConnector"
      click I "https://github.com/IndustryFusion/ScorpioBroker"
      click J "https://github.com/IndustryFusion/DigitalTwin/tree/main/helm/charts/flink"
```

## Contents

* [E2E tests](test/README.md)
* [Kafka Bridges](KafkaBridge/README.md)
* [Helm Deployment](helm/README.md)


## License
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2FIndustryFusion%2FDigitalTwin.svg?type=large)](https://app.fossa.com/projects/git%2Bgithub.com%2FIndustryFusion%2FDigitalTwin?ref=badge_large)
