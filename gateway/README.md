# Gateway Emulator

[![Build Gateway](https://github.com/IndustryFusion/DigitalTwin/actions/workflows/gateway.yml/badge.svg)](https://github.com/IndustryFusion/DigitalTwin/actions/workflows/gateway.yml)

This Gateway Emulator mimics the data from the Gateway.

## Install Dependencies
Make sure `libncurses-dev` is installed.

```console
$ sudo apt install libncurses-dev
```

Setup the rust toolchain (see: https://rustup.rs/)

```console
$ sudo apt install build-essential
$ curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

## Build and Run
Setup a Kafka broker and create a topic (explained [HERE](https://github.com/wagmarcel/Digital-Twin-POC/tree/master/streaming-analytics#use-standalone-kafka))

_note: to create a topic, you can just run the `kafkacat` producer with empty input_

```console
$ cd gateway
$ cargo build
$ cargo run
# ALTERNATIVELY:
$ cargo run -- --conf /path/to/gateway.toml
```

### Customization
The configuration is done through a file called [`gateway.toml`](./gateway.toml) in the current working directory.

Simulator randomly selects a message from: `messages.list_of_messages` to publish to broker.
