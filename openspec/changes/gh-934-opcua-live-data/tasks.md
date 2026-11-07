# Tasks

## 1. Clean install

- [x] 1.1 Move `pyshacl` to `requirements.txt` of `semantic-model/opcua`; verify `owl2instances.py` creates the pump's entities in a fresh virtual environment with only that file
- [ ] 1.2 Make the dataservice and both test servers resolve relative paths; add unit tests for `../` paths, and verify they fail without the fix
- [x] 1.3 Check the commands of `semantic-model/dataservice/README.md`; verify they run as written from a clean install

## 2. Specification pointers and access control

- [x] 2.1 Add a unit test to `KafkaBridge/test/lib_authServiceTest.js`: a device ID with a `/` in the topic is denied; verify it passes with `npm test` in `KafkaBridge`
- [x] 2.2 Point `AGENTS.md` and `CONTRIBUTING.md` to the contract; verify the links resolve

## 3. Chain test

- [x] 3.1 Add the test's stages under `test/opcua-chain/`, from the spike without its bug injection, with the update records of stage 4 marked as a copy of Core Services' format; verify each stage passes locally
- [x] 3.2 Add `.github/workflows/opcua-chain.yaml` for Python 3.10 and 3.12, with the paths from `design.md` and the Scorpio image from `.env`; verify it runs on this Pull Request and finishes in under 10 minutes
- [x] 3.3 Stage 3 also checks the agent's schema for each label; verify with a label the schema rejects
- [x] 3.4 Fail the test on a logged bridge error; verify with a bridge change which logs a refusal while the value still arrives
- [x] 3.5 Put each known bug back on a throwaway branch: `PropertyIri`, Python booleans, `None` on an outage, enums without the lookup, the bridge dropping `IriProperty`, IRI values in a batch merge; verify each one fails, and report the runs in the Pull Request
- [x] 3.6 Run the unchanged code at least twice more; verify both pass, and report them in the Pull Request
- [x] 3.7 Verify that a Pull Request outside the listed paths doesn't trigger the workflow, and that `build.yaml` and `k8s-tests.yaml` are unchanged by this change

## 4. Tutorial

- [x] 4.1 Add `semantic-model/dataservice/opcua-pump-tutorial.md` with its system requirements, the hosts to reach and the platform prerequisites, the optional test server, the agent's external MQTT address and device onboarding, the clean-up, and the table for other machines; verify its links resolve
- [x] 4.2 Mark the blocks the test runs, and have stages 1 and 2 extract them; verify that breaking a marked command fails the test
- [x] 4.3 State in the tutorial which Python and Node.js versions the test covers and how far; verify it matches the workflow's matrix
- [x] 4.4 Follow the whole tutorial on a deployed platform from a fresh clone; verify a written value is readable over REST, and report the result in the Pull Request
- [x] 4.5 Link the tutorial from `semantic-model/dataservice/README.md`, replacing the recipe's duplicated steps; verify the link resolves
- [x] 4.6 Add the troubleshooting table, with each error met while validating the tutorial and the silent failure of an entity ID with a `/`; verify each entry names a symptom, its cause and its fix

## 5. Integration check

- [x] 5.1 Run `openspec validate --all --strict` and `openspec status --change gh-934-opcua-live-data`; verify validation passes and all artifacts are complete
- [x] 5.2 Report the result per scenario of both capabilities in the Pull Request, naming which are verified by the test, by hand, or only documented
- [x] 5.3 Verify `Build` and `K8s tests` pass on this Pull Request

## Workflow follow-up

- Issue #934 stays open until the archive. Its Pull Request references it with `Refs #934`.
- After merge, run `/opsx:archive gh-934-opcua-live-data` in a follow-up Pull Request; the archive commit message closes #934, as this is the issue's only change.
