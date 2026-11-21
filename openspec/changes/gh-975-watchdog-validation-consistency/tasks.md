# Tasks

## 1. Watchdog

- [ ] 1.1 Read the complete refreshes per connector from the Connect log and when the state was last emptied from Flink and the JobManager pod (D1, D2); verify with tests of the watchdog script ("A refresh that dies halfway", "Young pods without a refresh", "A failover without a checkpoint", "A failover restored from a checkpoint", "A JobManager restart", "Flink down with a kept inconsistency", "Flink down otherwise", "Flink answers again", "One unreadable run")
- [ ] 1.2 Judge and report `ValidationConsistency` as inconsistent, rebuilding, refresh late or consistent, latched as in D3, D4 and D6, with the findings kept in `platform-watchdog-state` (D5), replacing the pod-age check; verify with tests of the watchdog script ("A missed window", "No refresh within the TTL", "The next refresh", "Closed by hand", "Emptied after it", "The repair", "No checkpoint", "A checkpoint before the state went stale", "After a failover", "The refresh comes", "The refresh does not come", "Overdue", "Installed on a running platform", "No refresh seen yet", "A gap in the watchdog's runs", "ConfigMap not readable")
- [ ] 1.3 Report `ConnectorState` from the KafkaConnector status (D7); verify with tests of the watchdog script ("A failed task", "A connector that does not exist", "A connector that can't be read", "Running again")
- [ ] 1.4 Add the state ConfigMap and the Role's rules (pod logs, that ConfigMap, KafkaConnectors); verify that the chart renders and lints

## 2. Checks

- [ ] 2.1 Run the watchdog tests and shellcheck as the Build workflow does, and measure the share of the new script lines the tests run; verify all pass and more than 80 % of the changed lines run
- [ ] 2.2 On a deployed platform, run the watchdog: once healthy, once with a connector paused, once after closing an alert by hand; verify `ValidationConsistency` and `ConnectorState` in Alerta and the state ConfigMap as the scenarios say
