#!/usr/bin/env bats
load "lib/utils"
load "lib/linter"

@test "linting tests" {

	run lint "test-horizontal-platform/horizontal-platform-up-and-running-first.bats"
	[ "$status" -eq 0 ]

	run lint "test-horizontal-platform/horizontal-platform-up-and-running-second.bats"
	[ "$status" -eq 0 ]

	run lint "test-horizontal-platform/horizontal-platform-up-and-running-third.bats"
	[ "$status" -eq 0 ]
	
	run lint "test-horizontal-platform/horizontal-platform-up-and-running-velero.bats"
	[ "$status" -eq 0 ]

	run lint "test-operators/operators-are-up.bats"
	[ "$status" -eq 0 ]

	run lint "test-operators/operators-are-up-minio.bats"
	[ "$status" -eq 0 ]

	run lint "test-operators/operators-are-up-cert-manager.bats"
	[ "$status" -eq 0 ]

	run lint "test-jobs/keycloak-realm-import-job-is-up.bats"
	[ "$status" -eq 0 ]

	run lint "test-bridges/test-alerta-bridge.bats"
	[ "$status" -eq 0 ]

	run lint "test-bridges/test-debezium-bridge.bats"
	[ "$status" -eq 0 ]

	run lint "test-bridges/test-ngsild-updates-bridge.bats"
	[ "$status" -eq 0 ]
}