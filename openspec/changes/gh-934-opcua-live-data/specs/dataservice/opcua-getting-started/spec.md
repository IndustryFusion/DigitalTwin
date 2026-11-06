# Delta for OPC UA Getting Started

## Purpose

Defines what a newcomer needs to get a machine's live data from an OPC UA server into the context broker: a tutorial, its system requirements, and tools which work after a clean install.

## ADDED Requirements

### Requirement: Tutorial from nodesets to REST
The repository SHALL contain a tutorial which uses the pump example. It SHALL cover providing the nodesets, building the model, loading the entities, onboarding the device, starting the connector and reading values over REST, and SHALL name what to change for another machine.

#### Scenario: Clean machine
- **WHEN** someone follows the tutorial on a clean machine with a deployed platform
- **THEN** a value written to the OPC UA server is readable over REST within two connector cycles, and they needed nothing the tutorial doesn't mention

#### Scenario: Another machine
- **WHEN** someone wants to use their own nodeset
- **THEN** the tutorial names each option or value to replace

### Requirement: The test server is optional
The tutorial SHALL include a test server for the pump, and SHALL state that it isn't needed with an existing server which runs the model.

#### Scenario: Existing server
- **WHEN** a reader already has a server with their model
- **THEN** the tutorial tells them to skip the test server and point the connector at their server

### Requirement: System requirements
The tutorial SHALL state its system requirements: operating system, Python, Node.js and other tools with versions, network access and free ports. It SHALL state how far each listed version was tested.

#### Scenario: Version in CI
- **WHEN** the chain test runs on a Python version
- **THEN** the tutorial lists that version, and states what that test covers

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
