# Setup Manual - IndustryFusion Open

The following documentation steps illustrates the setup of IndustryFusion Foundation (IFF) open source components including Process Digital Twin (PDT) inside a factory premise as shown in the figure below. The main goal is to enable a Kuberenets expert to setup the IFF open stack and start with the creation of digital assets, semantic model and validation for industrial machines/processes supporting MQTT/OPC-UA protocols at the machine end.


![image](https://github.com/IndustryFusion/docs/assets/128161316/dfa28417-bd79-465f-9e6e-c25d4029251b)


The documentation has two parts:

1. Infrastructure Layer - Provisioning of central Server Harware, OS, Kubernetes, SUSE Rancher for managing gateways inside the factory, Gateway hardware preparation from Rancher and supporting services.
2. Application Layer - Provisioning of DigitalTwin on the above central server, DigitalTwin API interaction for creating Asset objects and validation jobs, Building and deploying Gateway services using Rancher Fleet and IFF Akri controller, interaction with DigitalTwin APIs.

**Note:** The Infrastrutre layer utilizes SUSE building blocks. The application layer is independent of Infrastructure layer. Any existing or new Kubernetes cluster at Edge or Cloud can be used for both server and gateway service deployments. Make sure the IFF-Akri controller and PDT services are deployed properly on desired Kubernetes cluster by setting KUBECONFIG variable before installation procedures.



### 1. OPC-UA Server / MQTT Publisher

a. In order to enable the digitization of the machines with OPC-UA server, make sure that the machine is connected to the factory LAN. Note down the IP address and port of the OPC-UA server. For example, "opc.tcp://192.168.49.198:62548".

Also, to enable the automated dicovery later with Akri Discovery Handler, note down the 'applicationName' (if available) value of the OPC-UA server, as shown in the example below.

![image](https://github.com/IndustryFusion/docs/assets/128161316/c7f19949-8e1b-42de-8962-7668e690fccd)

b. In order to enable the digitization of the machines with MQTT Publisher, make sure that the machine is connected to the factory LAN. The machines with MQTT publisher usually comes with an user interface for configuring the MQTT central broker IP address and port as shown below in an example. This page will be used later to configure broker IP and other details, once the MQTT broker is functional in the central factory server. Note down the main topic of each device to use it in the Akri handler in the later section.

![image](https://github.com/IndustryFusion/docs/assets/128161316/7d2eda97-9797-4b08-9285-ca7f4060d443)

## Infrastructure Layer

### 2. Factory Server

#### a. Hardware Requirements:
* Intel Xeon Processor - Minimum, 4 Cores (8 CPU Threads).
* Memory - Minimum, 32 GB.
* Storage - Minimum, 512 GB.


#### b. SLE Micro OS - 5.5
Visit this page [OS download](https://www.suse.com/download/sle-micro/) and download the 'SLE-Micro-5.5-DVD-x86_64-GM-Media1.iso' image. Flash the ISO to an USB drive (Min. 16GB drive). Insert and boot the server from the USB drive. Follow the on-screen steps to complete the OS installation. Skip the 'Product Registration' page if the free version is desired.

For more detailed installation steps follow this [documentation](https://documentation.suse.com/sle-micro/5.5/html/SLE-Micro-all/cha-install.html).


#### c. RKE2 - Kubernetes Distribution
Install the RKE2 latest stable version on the installed OS. IFF stack currently uses single node for the factory server, follow the instructions [here](https://docs.rke2.io/install/quickstart#server-node-installation) to install the server node.

Once the installation of RKE2 is done, Kubectl CLI must be able to communicate with the Kubernetes API and execute commands.


#### d. Rancher with Fleet and Elemental Plugins
Follow these [instructions](https://ranchermanager.docs.rancher.com/pages-for-subheaders/install-upgrade-on-a-kubernetes-cluster#install-the-rancher-helm-chart) to install the Rancher tool using Helm charts.

**Note:**
1. Use the 'rancher-stable' Helm chart.
2. Use the 'Rancher-generated TLS certificate', so install cert-manager as described.
3. At the last step, set the --version tag to 2.7.3 or any latest stable version.
4. Also, global.cattle.psp.enabled to false.
5. Set the hostname to your desired name. For e.g, rancher.iff.org


**Important:** 

Once the installation is done, set the DNS for the factory server in the LAN and set the hostname from last step. If not, update /etc/hosts file to have this DNS atleast. The Rancher UI will be live at this DNS in the LAN.


**Troubleshooting:**

If there any issue with resolving DNS name in the factory server. Most probably it is because of NetworkManager of the factory server node.

**Solution:**

Login to the factory server, and perform following steps.

* Edit /etc/NetworkManager/NetworkManager.conf and make sure the below params are defined as shown.
        
         dns=none
         rc-manager=unmanaged

* Restart the below services.

        sudo service network restart
        sudo service NetworkManager restart


**Fleet** - This Continous Delivery Plugin will be installed by default in the Rancher. 


**Elemental** - OS management plugin must be installed seperatley. Follow these [instructions](https://elemental.docs.rancher.com/quickstart-ui#install-elemental-operator) to install Elemental using Rancher UI.


**Note** - Follow the above document untill you can see the OS Manamagent option in the Rancher Manager menu. Further steps for creating Machine Registration Endpoint and Preparing Seed Image will be described below.


**Machine Registration Endpoint Creation**

Go to OS management option in the Rancher - Click on 'Registration Endpoints' and click 'Create'.

![image](https://github.com/IndustryFusion/docs/assets/128161316/3ad21d4d-a8fa-4eab-9a8b-45a5af26e697)

IFF has tested two types of smartbox/gateway configurations - With Truted Platform Module 2.0 (TPM) and Without TPM 2.0.

* With Truted Platform Module 2.0

For TPM 2.0 enabled smartboxes, use the following cloud config in the above shown screen.

```
config:
  cloud-config:
    users:
      - name: root
        passwd: password
  elemental:
    install:
      debug: true
      device: /dev/mmcblk0
      eject-cd: true
      no-format: false
      reboot: true
    reset:
      reboot: true
      reset-oem: true
      reset-persistent: true
machineInventoryLabels:
  machineUUID: ${System Information/UUID}
  manufacturer: ${System Information/Manufacturer}
  productName: ${System Information/Product Name}
  serialNumber: ${System Information/Serial Number}
```

* Without Truted Platform Module 2.0

For TPM 2.0 disabled smartboxes, use the following cloud config in the above shown screen.

```
config:
  cloud-config:
    users:
      - name: root
        passwd: password
  elemental:
    install:
      debug: true
      device: /dev/sda
      eject-cd: true
      no-format: false
      reboot: true
    registration:
      auth: tpm
      emulate-tpm: true
      emulated-tpm-seed: 1
    reset:
      reboot: true
      reset-oem: true
      reset-persistent: true
machineInventoryLabels:
  machineUUID: ${System Information/UUID}
  manufacturer: ${System Information/Manufacturer}
  productName: ${System Information/Product Name}
  serialNumber: ${System Information/Serial Number}
```

**Note:** Update the 'emulated-tpm-seed' to a unique number everytime for each TPM 2.0 disabled machine. Also, according to the smartbox configuration, update the device path and desired password.


Click 'Create' in the 'Registration Endpoint: Create' page after entering the above cloud configs accordingly. The below page will be visible, select the latest Elemental OS version and click 'Build ISO', then Click 'Download ISO' to download the ISO file.

![image](https://github.com/IndustryFusion/docs/assets/128161316/a0d4dfd4-3c30-440d-b9a9-19f4cb3616b3)


### 3. Smartbox Onboarding

#### a. Hardware Requirements
* Intel Atom Processor - 4 Cores.
* Memory - Minimum, 16 GB.
* Storage - Minimum, 64 GB.

Burn the downloaded ISO file in to an USB drive and boot the smartbox from the drive, click 'Elemental Install'. Rest of the process is automated untill a new machine appears in the below shown 'Inventory of Machines' page and becomes active. The same USB drive can be used again to onboard the devices in case of TMP 2.0 enabled smartboxes. In TPM 2.0 disabled devices, create a new registration endpoint with new 'emulated-tpm-seed' value, build the ISO, download and install for every new machine.

![image](https://github.com/IndustryFusion/docs/assets/128161316/75d9202f-c3d2-48cf-a3f7-f072fa0209ee)


#### b. RKE2 for Smartbox

Select one free device (single node cluster) from inventory list as shown below and click 'Create Elemental Cluster'.

![image](https://github.com/IndustryFusion/docs/assets/128161316/512357d8-1e9b-41f8-8ac6-5180f8622be9)

In the next page, give a name to the cluster, select the latest RKE2 version, select the configurations as shown below, click 'Create'.

![image](https://github.com/IndustryFusion/docs/assets/128161316/8b89f886-3e17-4624-bb03-a5d58951ebf3)

The process of RKE2 provisioning can be watched in the 'Cluster Management' page of Rancher. Once the cluster is active, further IFF smartbox services can be deployed. (Will be described in the later section).


### 4. NeuVector - Container Security Platform

If needed, The NeuVector must be installed on both factory server and all smartboxes.

Visit the documentation [here](https://open-docs.neuvector.com/deploying/rancher) for installing NeuVector from Rancher for both factory server and smartboxes.

Once the installtion is done, to use the federated multi-cluster management from factroy server as primary cluster and smartboxes as secondary, use these [instructions](https://open-docs.neuvector.com/navigation/multicluster#configuring-the-primary-and-remote-clusters). 

Once the federated management is active, the dashboard of NeuVector from the primary cluster looks like as shown below.

![image](https://github.com/IndustryFusion/docs/assets/128161316/bd8f7cfb-45ad-49c5-aec4-0a007dab8bae)


## Application Layer

### 5. MQTT Broker on the Factory Server

The MQTT broker must be deployed to the factory server as a Kubernetes pod. Copy the given 'mqtt-broker-gateway' folder to the factory server node, using Kubectl targeting the local cluster, execute the following commands.

**Note:** Create an empty sub-folder with name 'mosquitto' inside the 'mqtt-broker-gateway' folder, before running below command. Also make sure contents of the 'broker.yaml' is pointing to the right folder paths.

`cd mqtt-broker-gateway`

`mkdir mosquitto`

`kubectl apply -f broker.yaml`

Once the MQTT broker pod is active, the machines with MQTT publishers can be updated with the IP address of the factory server with port 1883. Also, note down the broker URL to use it in the Akri handler in the later section.


### 6. Deployment of Process Digital Twin (PDT) on Factory Server

**Note:** The PDT build and tests must be performed on a Ubuntu 20 or 22 OS that is present in the local LAN as a jump machine for deployment on the desired cluster. Build PDT in the jump machine, and then use the kubeconfig of the Factory Server's RKE2 cluster for the deployment. (If using existing cluster, set KUBECONFIG accordingly)

Follow the local deployment documentation [here](https://github.com/IndustryFusion/DigitalTwin/blob/main/helm/README.md#building-and-installation-of-platform-locally) to install the PDT components on the factory server.

Once the local tests are passed in the above documentation, perform the following.

* Verify all pods are running using `kubectl -n iff get pods`, in some slow systems keycloak realm import job might fail and needs to be restarted, this is due to postgres database not being ready on time.

* In the machine which needs PDT access, edit the /etc/hosts file and add DNS entry for PDT APIs as shown below. In local deployment, all services must be used with HTTP if no valid CA is provided. In production, HTTPS must be used with valid domain name and CA certificate.

  ```
  <IP address of the factory server> keycloak.local
  <IP address of the factory server> ngsild.local
  <IP address of the factory server> alerta.local
  <IP address of the factory server> pgrest.local
  ```

* Login to keycloak with a browser connected to the LAN using `http://keycloak.local/auth`

  a. The username is `admin`, the password can be found by
  
     ```
     kubectl -n iff get secret/keycloak-initial-admin -o=jsonpath='{.data.password}' | base64 -d | xargs echo
     ```

* Verify that there are 2 realms `master`, `iff`

* Verify that there is a user in realm `iff`, named: `realm_user`

  a. The password for `realm_user` can be found by
     ```
     kubectl -n iff get secret/credential-iff-realm-user-iff -o jsonpath='{.data.password}'| base64 -d | xargs echo
     ```

**Note:** The realm_user and the associated password will be used in the IFF smartbox services.


### 7. Deployment of IFF Smartbox Services

Before deploying these services, respective Docker images must be built and pushed to a custom Docker Hub repo. 


**1. fusionopcuadataservice**


Build the Docker image using the Dockerfile located in this [repo](https://github.com/IndustryFusion/fusionopcuadataservice). Push the image with a desired name and version to your Docker Hub repo.

   
**2. fusionmqttdataservice**


Build the Docker image using the Dockerfile located in this [repo](https://github.com/IndustryFusion/fusionmqttdataservice). Push the image with a desired name and version to your Docker Hub repo.


**3. iff-iot-agent**


Build the Docker image using the Dockerfile and instructions located in this [repo](https://github.com/IndustryFusion/DigitalTwin/tree/main/NgsildAgent). Push the image with a desired name and version to your Docker Hub repo.


**4. iff-akri-controller**


Build the Docker image using the Dockerfile and instructions located in this [repo](https://github.com/IndustryFusion/iff-akri-controller). Push the image with a desired name and version to your Docker Hub repo.


**Akri Helm Charts** 

For OPC-UA and MQTT based machines, with the help of Helm charts, Akri discovery handler and IFF-Akri-controller will be deployed on the respective smartbox. The Helm charts for both OPC-UA and MQTT is in this GitHub [repo] (https://github.com/IndustryFusion/iff-akri-fleet-configs). This repo also contains charts for the smartbox which deals with both OPC-UA and MQTT at the same time (Example, a power measuring device (MQTT), and the machine(OPC-UA)). Further details of deployment follows.

Clone the correct branch according to the machine protocol to local. For MQTT Helm, update the Broker URL and the main topic of the device before deploying to each smartbox. For OPC-UA Helm, update the OPC-UA URL and the applicationName (If available, or else empty list) of the device before deploying to each smartbox. Also update the docker image name of IFF-Akri-controller with your custom image name.

Once the changes are done, push the helm chart branch to a different GitHub remote repository with a desired branch name. Note down the URL and branch of this new repo. (If using existing cluster for gateway, directly install the Helm chart instead of keeping the chart in a repository and using Rancher's Fleet Plugin later.)


**Create a sample Asset in PDT using Scorpio REST API**

Login in to the factory server, and follow te below instructions.

1. Get Keycloak Access Token. Update the username and password in below <>.

   ```
   curl --location 'http://keycloak.local/auth/realms/iff/protocol/openid-connect/token' \
   --header 'Content-Type: application/x-www-form-urlencoded' \
   --data-urlencode 'grant_type=password' \
   --data-urlencode 'client_id=scorpio' \
   --data-urlencode 'username=<keycloak realm user>' \
   --data-urlencode 'password=<keycloak real user's password>'
   ```
   
Copy the access token from the response.

2. Create an simple asset in the PDT without relationships. Update token from last step.

   ```
   curl --location 'http://ngsild.local/ngsi-ld/v1/entities/' \
   --header 'Content-Type: application/ld+json' \
   --header 'Accept: application/ld+json' \
   --header 'Authorization: Bearer <token>' \
   --data-raw '{
       "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
       "id": "urn:ngsi-ld:asset:2:47",
       "type": "iff:laser-cutter",
       "alias": "Smart Laser",
       "product-name": "MSE Smart FL"
   }'
   ```

The asset is successfully created if the response is 200. JSON-LD is used as the data model to define assets in PDT. More details on the model of the data can be found [here](https://github.com/IndustryFusion/DigitalTwin/tree/main/semantic-model/datamodel#json-ld-json-for-linked-data).


**Fleet - Continous Delivery**

The Rancher's Fleet plugin is used to deploy the IFF smartbox services directly from the above created new GitHub repo and branch of Akri Helm chart. 

Go to the 'Continuous Delivery' page in Rancher tool, click 'Git Repos' and then click 'Add Repository'. In the below shown page, add a name, paste the URL of the GitHub repo from last step, mention the branch name. If the repository is private, add credentials in 'Git Authentication', then click 'Next'.

![image](https://github.com/IndustryFusion/docs/assets/128161316/a8b308de-24f6-40f9-898a-f771f0ac57cb)

In the below shown page, select a target Elemental created RKE2 smartbox cluster, then Click 'Create'.

![image](https://github.com/IndustryFusion/docs/assets/128161316/11eb8da3-e4a3-4780-9c61-6ccae3ebcecd)

The IFF smartbox related Akri services will deployed to the single node cluster that will be responsbile for deploying the IFF data and gateway agent services automatically upon device discovery and also PDT asset details. Any further changes to the deployment configs in the associated GitHub repo will be deployed automatically in future.


**Gateway Asset Configurations** 

Once the Akri Helm charts are deployed to smartbox in the last step, the Akri discovery handler will continously scan the network for the given IP and details. If the device is present, Akri creates an 'Instance' custom resource in the cluster. The iff-akri-controller will then take these instances and searches for the relevant asset in the PDT using the configuration files in this [repository] (https://github.com/IndustryFusion/gateway-configs).

For the PDT asset created in the last step the configuration file in the above repo should look like this.

Filename: urn:ngsi-ld:asset:2:47.yaml

If the device is OPC-UA,

```yaml

ip_address: '<IP address of the OPC-UA server>'
main_topic: ''
protocol: opcua
app_config: | 
  {
       "fusionopcuadataservice": {
           "specification": [
               {
                 "node_id": "ns=2",
                 "identifier": "s=1:MergedRootGroupNode/MsncCoreRootNode/ActualStateOfCuttingMachine/ActualState?msnc.mMov",
                 "parameter": "machine-state"
               },
               {
                   "node_id": "ns=2",
                   "identifier": "s=1:MergedRootGroupNode/MsncCoreRootNode/ActualStateOfCuttingMachine/ActualPosition?msnc.mAxX",
                   "parameter": "machine-position-x"
               },
               {
                 "node_id": "ns=2",
                 "identifier": "s=1:MergedRootGroupNode/MsncCoreRootNode/ActualStateOfCuttingMachine/ActualPosition?msnc.mAxY",
                 "parameter": "machine-position-y"
               },
               {
                 "node_id": "ns=2",
                 "identifier": "s=1:MergedRootGroupNode/MsncCoreRootNode/ActualStateOfCuttingMachine/ActualPosition?msnc.mAxZ",
                 "parameter": "machine-position-z"
               }
           ]
         }
      }

pod_name: 'mse-smartfl-opcua'
pdt_mqtt_hostname: '<IP of the PDT Gateway>'
pdt_mqtt_port: '1883'
device_id: urn:ngsi-ld:asset:2:47
gateway_id: urn:ngsi-ld:asset:2:47
keycloak_url: http://keycloak.local/auth/realms
realm_password: <realm password>
secure_config: 'false'
username_config: ''
password_config: ''
dataservice_image_config: <OPC-UA data service image name>
agentservice_image_config: <iff iot agent image name>

```

If the device is MQTT,

```yaml

ip_address: '<IP address of the MQTT broker>'
main_topic: 'airtracker-74145/relay1'
protocol: mqtt
app_config: | 
   {
       "fusionmqttdataservice": {
           "specification": [
              {
                  "topic": "airtracker-74145/relay1",
                  "key": [],
                  "parameter": ["machine-state"]
              },
              {
                  "topic": "airtracker-74145/dust",
                  "key": [],
                  "parameter": ["dustiness"]
              }
           ]
       }
    }

pod_name: 'machine-name-mqtt'
pdt_mqtt_hostname: '<IP of the PDT Gateway>'
pdt_mqtt_port: '1883'
device_id: urn:ngsi-ld:asset:2:47
gateway_id: urn:ngsi-ld:asset:2:47
keycloak_url: http://keycloak.local/auth/realms
realm_password: <realm password>
secure_config: 'false'
username_config: ''
password_config: ''
dataservice_image_config: <MQTT data service image name>
agentservice_image_config: <iff iot agent image name>

```

If the Instance discovered and the asset configurations shown above match, the iff-akri-controller will deploy IFF data and GW services to the smartbox. The lifecycle of these services will then be managed by Akri according to the instance discovery. If these is no asset config but instance, no services will be deployed.

**Note:** If the asset configs are updated, either delete the instance resource and let the Akri to rediscover the instance, or switch the OPC-UA server of the machine off and then on. The controller will then update the services accordingly.

### 8. Semantic Modelling

Once the asset JSON-LD is created with Scorpio API, and the real-time data from the machine starts flowing in to PDT, the validation rules for the entire asset type category can be created using modelling tools and JSON-Schema. However, PDT requires SHACL (Shapes Constraints Language) backed with RDF knowledge to create streaming validation jobs for Apache Flink (Details in later section). The PDT offers tools to use JSON-Schema to create the constraints and validate them against JSON-LD object, then convert the JSON-Schema to SHACL. Detailed documentation of this process can be found [here](https://github.com/IndustryFusion/DigitalTwin/tree/main/semantic-model/datamodel#readme).

For Example:

JSON-LD object created in last step: Also contains a real-time property related to temperature now as the smartboxe services are sending it.

```
{
       "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
       "id": "urn:ngsi-ld:asset:2:47",
       "type": "iff:laser-cutter",
       "alias": "Smart Laser",
       "product-name": "MSE Smart FL",
       "temperature": "21"
}
```

JSON-Schema can be created to validate this object as shown below with some constraints.

```
{
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "<URL-Encoded expanded type, schema ID>",
        "title": "Laser cutter",
        "description": "Laser cutter template for IFF",
        "type": "object",
        "properties": {
           "type": {
            "const": "iff:laser-cutter"
            },
            "id": {
              "type": "string",
              "pattern": "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
            },
            "alias": {
             "type": "string"
            },
            "product-name": {
              "type": "string",
            },
            "temperature": {
              "type": "string",
              "minimum": "15",
              "maximum": "25"
            }
        },
        "required": ["type", "id"]
}
```

Once the JSON-Schema is created as shown above, it can be validated with the JSON-LD and converted to SHACL using the tools [here](https://github.com/IndustryFusion/DigitalTwin/tree/main/semantic-model/datamodel#translating-json-schema-to-shacl). Detailed tutorial for such semantic modelling also with relationship concept to other assets can be found [here].(https://github.com/IndustryFusion/DigitalTwin/blob/main/semantic-model/datamodel/Tutorial.md)


#### Converting the SHACL to Flink Streaming Validation Jobs

Once the SHACL is ready using the above described tools, the [shacl2flink](https://github.com/IndustryFusion/DigitalTwin/tree/main/semantic-model/shacl2flink) tool can be used to convert and deploy it as jobs on Apache Flink as described in the following steps.

Step 1: Clone the [PDT](https://github.com/IndustryFusion/DigitalTwin.git) to factory server.

Step 2: Go to semantic-model/kms/ folder. Create a new folder with a desired name, for example 'demo'.

Step 3: Inside the newly created 'demo' folder, create 3 files with contents as shown below.

 a. knowledge.ttl, that acts as a base to the SHACL file. Here for our example, this file only contains the type definition.
 
 ```
 @prefix : <http://www.industry-fusion.org/schema#> .
 @prefix owl: <http://www.w3.org/2002/07/owl#> .
 @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
 @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
 @prefix schema: <https://industry-fusion.com/schema#> .
 @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

 :laser-cutter
   rdf:type rdfs:Class ;
 .
 ```

 b. model-example.jsonld, paste the JSON-LD created in the previous steps.
 
 c. shacl.ttl, paste the result of the conversion from JSON-Schema.


Step 4: Go the semantic-model/shacl2flink folder, and execute the following command.

`make setup`

`KMS_DIR=./../kms/demo make prepare-kms`

`make flink-undeploy`

`make flink-deploy`

Once these steps are completed, the jobs will running in Apache Flink. According to the constraints written in the SHACL file, the alerts can be seen in Alerta UI and API.


#### PDT Endpoints

1. Scorpio Broker

- http://ngsild.local/
- API documentation: [Docs](https://scorpio.readthedocs.io/en/latest/introduction.html)

2. Alerta

- http://alerta.local/
- API documentation: [Docs](https://docs.alerta.io/api/reference.html)

#### Alerts in Alerta UI

For our example, the constraint for the temperature value is minimum inclusive 15 and maximum inclusive 25. When the value goes out of the range, an alert will be automatically visible in the Alerta UI avaliable at 'alerta.local' endpoint. (Use Keycloak real_user credentials for login)

![image](https://github.com/IndustryFusion/docs/assets/128161316/02196980-4fe2-43cc-9329-76980e71ad62)

Similarly, if two assets are linked to each other using relationships in semantic modelling of the asset, the validation rules can also be extended to check whether the relationship graph is intact or not using SHACL.

3. PGRest

- http://pgrest.local/
- API documentation: [Docs](https://postgrest.org/en/stable/)

The PGRest API uses the Postgres service connected to Scorpio Broker (acid cluster pods), and fetches the rows from all columns of 'tsdb' database, 'entityhistory' table with a timestamp.

The sample query in PGRest looks like below.

```
http://pgrest.local/entityhistory?limit=2

```

Note: Pass the keycloak Bearer token in headers for the above request.

The example result for the above query looks like below.

```
[
    {
        "observedAt": "2024-01-25T11:56:01+00:00",
        "modifiedAt": "2024-01-25T11:56:01+00:00",
        "entityId": "urn:ngsi-ld:asset:2:002",
        "attributeId": "http://www.industry-fusion.org/schema#hasFilter",
        "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
        "datasetId": "urn:ngsi-ld:asset:2:002\\http://www.industry-fusion.org/schema#hasFilter",
        "nodeType": "@id",
        "value": "urn:ngsi-ld:asset:2:000",
        "valueType": null,
        "index": 0
    },
    {
        "observedAt": "2024-01-25T15:10:05.393+00:00",
        "modifiedAt": "2024-01-25T15:10:05.393+00:00",
        "entityId": "urn:ngsi-ld:asset:2:001",
        "attributeId": "http://www.industry-fusion.org/fields#dustiness",
        "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
        "datasetId": "urn:ngsi-ld:asset:2:001\\http://www.industry-fusion.org/fields#dustiness",
        "nodeType": "@value",
        "value": "0.005",
        "valueType": null,
        "index": 0
    }
]

```

The query can be modififed to accomadate filters to the above result as shown below.

```
http://pgrest.local/entityhistory?limit=10&attributeId=eq.http://www.industry-fusion.org/fields%23dustiness

```

The result would only contain results with attributeId equal to (.eq) http://www.industry-fusion.org/fields%23dustiness. (%23 = #)

```
[
   {
        "observedAt": "2024-01-25T15:10:05.393+00:00",
        "modifiedAt": "2024-01-25T15:10:05.393+00:00",
        "entityId": "urn:ngsi-ld:asset:2:001",
        "attributeId": "http://www.industry-fusion.org/fields#dustiness",
        "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
        "datasetId": "urn:ngsi-ld:asset:2:001\\http://www.industry-fusion.org/fields#dustiness",
        "nodeType": "@value",
        "value": "0.005",
        "valueType": null,
        "index": 0
    }
]

```

Further filter options can be found in the API documentation.

Complex queries on Postgres service can also be made using PGRest by adding a custom function/view in the database and addressing that view in PGRest HTTP request. For example, the below complex query can be created as a view in the database.


```

CREATE VIEW value_change_state_entries AS SELECT * FROM ( SELECT *, LAG(value) OVER (ORDER BY "entityId", "observedAt" ASC) AS prev_value FROM entityhistory WHERE "attributeId"='http://www.industry-fusion.org/fields#machine-state' ) AS subquery WHERE value IS DISTINCT FROM prev_value;

GRANT SELECT ON value_change_state_entries TO pgrest;

```

The above view creates a table where the row has entries only when the 'machine-state' is toggled. This predefined view of the database can then called in PGRest as shown below with required filters.

```
http://pgrest.local/value_change_state_entries?entityId=eq.urn:ngsi-ld:asset:2:101

```

4. Keycloak

- http://keycloak.local/auth
- API documentation: [Docs](https://www.keycloak.org/documentation)