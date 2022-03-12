#!/usr/bin/env bats
load "lib/utils"
load "lib/linter"

@test "linting tests" {

	run lint "test-horizontal-platform/horizontal-platform-up-and-running-first.bats"
	[ "$status" -eq 0 ]

	run lint "test-horizontal-platform/horizontal-platform-up-and-running-second.bats"
	[ "$status" -eq 0 ]
	
	run lint "test-horizontal-platform/horizontal-platform-up-and-running-rest.bats"
	[ "$status" -eq 0 ]

	run lint "test-operators/operators-are-up.bats"
	[ "$status" -eq 0 ]

	run lint "test-operators/operators-are-up-minio.bats"
	[ "$status" -eq 0 ]

}