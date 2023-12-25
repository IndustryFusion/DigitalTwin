#!/bin/bash

( cd lib && curl https://raw.githubusercontent.com/bats-core/bats-detik/v1.1.0/lib/detik.bash > detik.bash &&
    curl https://raw.githubusercontent.com/bats-core/bats-detik/v1.1.0/lib/linter.bash > linter.bash &&
    curl https://raw.githubusercontent.com/bats-core/bats-detik/v1.1.0/lib/utils.bash > utils.bash
)