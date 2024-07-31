## Documentation for IndustryFusion Open Stack

The setup manual includes the following sections and thier details.

The documentation has two parts:

1. Infrastructure Layer - Provisioning of central Server Harware, OS, Kubernetes, SUSE Rancher for managing gateways inside the factory, Gateway hardware preparation from Rancher and supporting services.
2. Application Layer - Provisioning of DigitalTwin on the above central server, DigitalTwin API interaction for creating Asset objects and validation jobs, Building and deploying Gateway services using Rancher Fleet and IFF Akri controller, interaction with DigitalTwin APIs.

**Note:** The Infrastrutre layer utilizes SUSE building blocks. The application layer is independent of Infrastructure layer. Any existing or new Kubernetes cluster at Edge or Cloud can be used for both server and gateway service deployments. Make sure the IFF-Akri controller and PDT services are deployed properly on desired Kubernetes cluster by setting KUBECONFIG variable before installation procedures.


1. OPC-UA Server / MQTT Publisher

### Infrastructure Layer

2. Factory Server
   * Hardware Requirements
   * SLE Micro OS - 5.5
   * RKE2 - Kubernetes Distribution
   * Rancher with Fleet and Elemental Plugins
4. Smartbox Onboarding
   * Hardware Requirements
   * RKE2 for Smartbox
5. NeuVector - Container Security Platform

### Application Layer

6. MQTT Broker on the Factory Server for MQTT client machines
7. Build and Deployment of Process Digital Twin (PDT) on Factory Server
8. Build and Deployment of IFF Smartbox Services
9. Semantic modelling and deployment of Flink streaming jobs
10. DigitalTwin API Examples
