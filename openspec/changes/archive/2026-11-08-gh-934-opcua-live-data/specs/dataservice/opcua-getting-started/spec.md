# Delta for OPC UA Getting Started

## Purpose

Defines what a newcomer needs to get a machine's live data from an OPC UA server into the context broker: a tutorial, its system requirements, and tools which work after a clean install.

## ADDED Requirements

### Requirement: Tutorial from nodesets to REST
The repository SHALL contain a tutorial which uses the pump example. It SHALL cover providing the nodesets, building the model, loading the entities, onboarding the device with its subcomponents, configuring and starting the agent, starting the connector, reading values over REST and cleaning up, and SHALL name what to change for another machine.

#### Scenario: Clean machine
- **WHEN** someone follows the tutorial on a clean machine with a deployed platform
- **THEN** a value written to the OPC UA server is readable over REST within two connector cycles, and they needed nothing the tutorial doesn't mention

#### Scenario: Agent outside the cluster
- **WHEN** the agent runs on the reader's machine and not in the cluster
- **THEN** the tutorial states how to obtain the broker's externally reachable MQTT address and configure the agent with it, and how to onboard the device with the other entities as its subcomponents

#### Scenario: Clean up
- **WHEN** a reader has finished the tutorial
- **THEN** the tutorial tells them how to stop the processes and remove the entities it created

#### Scenario: Another machine
- **WHEN** someone wants to use their own nodeset
- **THEN** the tutorial names each option or value to replace

### Requirement: The test server is optional
The tutorial SHALL include a test server for the pump, and SHALL state that it isn't needed with an existing server which runs the model.

#### Scenario: Existing server
- **WHEN** a reader already has a server with their model
- **THEN** the tutorial tells them to skip the test server and point the connector at their server

### Requirement: System requirements
The tutorial SHALL state its system requirements: operating system, Python, Node.js and other tools with versions, and free ports. It SHALL name each host the machine must reach and why, the parts of the platform which must already run, and the access the reader needs to it. It SHALL state how far each listed version was tested.

#### Scenario: Version in CI
- **WHEN** the chain test runs on a Python or Node.js version
- **THEN** the tutorial lists that version, and states what that test covers

#### Scenario: Checking the machine before starting
- **WHEN** a reader checks their machine and platform against the tutorial before Step 1
- **THEN** they find every host the steps contact, including the broker's REST API, the identity provider and the MQTT listener, and which platform components and access the steps rely on

#### Scenario: Reader on another version
- **WHEN** a reader's Python version isn't fully tested
- **THEN** the tutorial tells them how far it was tested

### Requirement: Documented installation is sufficient
Each tool of the chain SHALL run after installing what its documentation says, without development requirements.

#### Scenario: Model tools
- **WHEN** only the documented runtime requirements of the model tools are installed
- **THEN** `owl2instances.py` runs and creates entities

### Requirement: Relative paths
The dataservice and the test servers SHALL resolve relative paths against the working directory, also those starting with `../`.

#### Scenario: Bindings next to the dataservice
- **WHEN** `startDataservice.py` is given `../opcua` and `../opcua/bindings.ttl` from its own directory
- **THEN** it reads these files

#### Scenario: Test servers
- **WHEN** a test server is given `../opcua/bindings.ttl`
- **THEN** it reads this file

#### Scenario: Existing recipes
- **WHEN** the commands in the dataservice's README are followed from a clean install
- **THEN** they run as written

### Requirement: Tutorial and test stay in sync
Commands of the tutorial which the chain test can run SHALL be the ones it runs, so that the tutorial fails the test when it stops working.

#### Scenario: Broken command
- **WHEN** a change breaks a command of the tutorial which the test runs
- **THEN** the chain test fails

### Requirement: Troubleshooting
The tutorial SHALL list the known failure symptoms with their cause and fix, including those where a component reports success but the value never reaches the broker.

#### Scenario: Silent failure
- **WHEN** the dataservice sends a value but the broker doesn't change
- **THEN** the tutorial names which logs to check and the known causes, among them an entity ID with a `/`, which the agent reports as sent while the MQTT bridge rejects the device

#### Scenario: Error message from a step
- **WHEN** a step fails with an error the tutorial's validation ran into
- **THEN** the tutorial lists that error with its cause and fix
