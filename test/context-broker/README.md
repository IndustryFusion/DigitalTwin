# Context broker contract test

Checks a broker image against
[contracts/context-broker](../../openspec/specs/contracts/context-broker/spec.md) from the outside: through
the broker's API and health checks only, never its code. It runs without Kubernetes and without Keycloak, on
the broker startup of the OPC UA chain test (`test/opcua-chain/broker.sh`), and takes about three minutes.

```bash
test/context-broker/run.sh                                   # the broker the platform pins (test/build-local-platform.sh), built if missing
IMAGE=<image> test/context-broker/run.sh                     # any image built for the platform, e.g. a fork build
IMAGE=scorpiobroker/all-in-one-runner:java-kafka-latest MODE=upstream test/context-broker/run.sh
                                                             # upstream Scorpio: no authorisation, those checks skip
```

It needs Docker, Node 18 or newer, openssl and curl. Results and the broker's logs go to `OUT`
(default `.context-broker`).

Each line of the output is one scenario of the specification:

| Mark | Meaning |
|---|---|
| `ok` | the broker meets the scenario |
| `dev` | a known deviation still stands (`MODE=upstream`); the line names its issue, what the broker answered and the workaround |
| `FAIL` | the broker doesn't meet the scenario, a known deviation is fixed and its workaround can go, a deviation that a fork patch removes still stands in `MODE=platform` (the build lacks that patch), or the test's own setup (e.g. the MQTT subscriber) broke |
| `skip` | not applicable to the image, e.g. authorisation on an upstream image |

Notifications go to an HTTP sink and to an MQTT server (Mosquitto) that `run.sh` starts on the broker's
network. The MQTT scenario runs as the first subscription of the freshly started broker, where upstream 6.0.2
loses a notification without `receiverInfo`. The sub-attribute scenario stops every notification on an image
with that deviation, so it runs last, on a broker of its own. The requirements that need Debezium (the entity
store) are checked by the K8s tests in `test/bats/test-bridges/test-debezium-bridge.bats`; the platform's MQTT
path by `test/bats/test-scorpio/test-scorpio-mqtt-subscriptions.bats`.
