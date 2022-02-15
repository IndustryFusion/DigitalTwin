#!/usr/bin/env bats
load "lib/utils"
load "lib/linter"

@test "linting tests" {

	run lint "horizontal-platform-up-and-running.bats"
	[ "$status" -eq 0 ]

	run lint "operators-are-up.bats"
	[ "$status" -eq 0 ]

    run lint "operators-are-up-minio.bats"
	[ "$status" -eq 0 ]
}