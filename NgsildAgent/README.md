# OISP IoT Agent
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2FOpen-IoT-Service-Platform%2Foisp-iot-agent.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2FOpen-IoT-Service-Platform%2Foisp-iot-agent?ref=badge_shield)


This project consists of two components:

### oisp-admin
This is a command line "wrapper" for the [REST API](https://github.com/Open-IoT-Service-Platform/platform-launcher/wiki/REST-API), enabling you to test connectivity, activate a device, register time series and send observations all from the command line.

### oisp-agent
This is a "agent" program intended to run as a service. You can send a very simple message, such as
```
{"n": "temp", "v": 26.9}
```
or an array like this
```
[{"n": "temp", "v": 26.9, "t": 1618325707931},{"n": "temp", "v": 27.2, "t": 1618325787105}]
```
or a component registration
```
{"n": "temp", "t": "temperature.v1.0"}
```
or a device update
```
{"attributes": {"owner": "Scott Ware"}, "tags": ["home","intel","x86_64"], "loc": [32.149989, -110.835842, 0]}
```
to a UDP socket on port 41234 or TCP socket on port 7070. The agent will handle secure communication with the upstream OISP instance.

## Installing using git
``` bash
git clone https://github.com/Open-IoT-Service-Platform/oisp-iot-agent.git
cd oisp-iot-agent
npm install
```

#### Configuration
Before using the agent you need to configure it so it knows how to communicate with your OISP instance. The agent looks for the configuration file 'config.json' in the 'config' directory. A template is provided in the 'config' directory which you can copy and modify using your favourite text editor.

``` bash
cp config/config.json.template config/config.json
```
  
#### Testing the connection
Run the following command to test the connection: 
``` bash
./oisp-admin.js test
```

#### Configuring and Activating the Agent

Set a unique Device Id with this command:
``` bash
./oisp-admin.js set-device-id <device_id>
```

You can also set a different Device name with this command:
``` bash
./oisp-admin.js set-device-name <device_name>
```

After the device registration, copy the activation code in _My Account_ UI, tab _Details_ (in _Account_ menu) and execute the activation command:
``` bash
./oisp-admin.js activate <activation_code>     
```
To verify activation, go back to your OISP dashboard and verify the status of the device previously registered.

#### Adding Sensors and Actuators

View in _My Account_ the _Catalog_ tab. You see predefined Sensors and Actuators but can also define your own types. For instance a default sensor is the _temperature.v1.0_ sensor. It can be added by the following command with the name _temp_:
``` bash
./oisp-admin.js register <name> <type>
```
e.g.
``` bash
./oisp-admin.js register temp temperature.v1.0
```

You can also register a component by sending
```
{"n": "temp", "t": "temperature.v1.0"}
```
to a UDP socket on port 41234 or TCP socket on port 7070.

#### Sending Metrics

After that, values for the component _temp_ can be sent by either the _oisp-admin_ to test, e.g.
```
./oisp-admin.js observation temp 22.1
```

or when the oisp-agent is running by sending
```
{"n": "temp", "v": 26.9}
```
or an array like this
```
[{"n": "temp", "v": 26.9, "t": 1618325707931},{"n": "temp", "v": 27.2, "t": 1618325787105}]
```
to a UDP socket on port 41234 or TCP socket on port 7070.

Dependent of the configuration, the agent sends data with REST or MQTT. If MQTT is configured, agent and admin always try to use MQTT for data submission and control. All other calls, like activation of devices or registration of components is always done with REST.

#### Starting the Agent

To start the oisp-agent service simply execute the start script:
``` bash
./oisp-agent.js
```
## Usage

For examples of how to use the 'oisp-agent' please see the [Examples](https://github.com/Open-IoT-Service-Platform/oisp-iot-agent/tree/master/examples) provided.

### Enabling SparkPlugB Standard 

1. To enable SparkplugB standard data format, you need to update the agent config as below:

``` bash
 "mqtt": {
              "host": "emqx",
              "port": 1883,
              "qos": 1,
              "retain": false,
              "secure": false,
              "strictSSL": false,
              "retries": 5,
              "sparkplugB": true, 
              "version": "spBv1.0"            
          }
```
 - "SparkplugB":true -> enables the sparkplugB feature of agent
 - "version": "spBv1.0", -> version of spB standard, default is spBv1.0
 
 2.  CID is used as alias, as sparkplugB standard suggest unique id as alias in data metric element.
   Data message looks like below:

``` bash
    var cid = "0c574252-31d5-4b76-bce6-53f2c56b544d";
    var DataMessage = {
            timestamp: 12345,
            metrics: [{
                name : "temp",
                alias : cid,
                timestamp : 12345,
                dataType : "float",
                value: 123
            }],
            seq: 1
         };
```

3. Sending NGSI-LD compatible data over Mqtt-SparkplugB
- Register devices for custom Relationship and Property catalog
- Use device name for Relationship as " Name : Relationship/Name_of_device",

    Datatype is iri (String):

    Eg. Name: "Relationship/https://industry-fusion.com/types/v0.9/hasFilter"

- Use device name format for Property as " Name: Property/Name_of_device"

  Datatype can be literals(string, integer,boolean) and iri(string)

  Eg. Name: "Property/https://industry-fusion.com/types/v0.9/state"

## Test

The oisp-agent project uses [gruntjs](http://gruntjs.com/) [mocha](http://visionmedia.github.io/mocha/) as its test framework. 
To run all tests:
``` bash
npm install 
./node_modules/grunt-cli/bin/grunt
```

## Certificates

> Do not use the default certificates in production.

The OISP Agent includes default certificates to provide "out of the box" connectivity. These are fine for public data submissions but should not be used for production deployments.

## Using Docker

### Build the image
````bash
make
````

### Start container with bash to configure agent
````bash
make configure
````

### Start container (connect to production server)
````bash
make start
````

### Start container (connect to local server)
````bash
make start-local
````

### Stop container
````bash
make stop
````

### Remove container and image 
````bash
make clean
````
#### Known limitations
 
* Components registered through the OISP Cloud API will not be known by the oisp-agent.

## License

Copyright (c) 2014, Intel Corporation

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
* Neither the name of Intel Corporation nor the names of its contributors
  may be used to endorse or promote products derived from this software
  without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2FOpen-IoT-Service-Platform%2Foisp-iot-agent.svg?type=large)](https://app.fossa.com/projects/git%2Bgithub.com%2FOpen-IoT-Service-Platform%2Foisp-iot-agent?ref=badge_large)