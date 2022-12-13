import logging
import sys

from pathlib import Path
from argparse import ArgumentParser, Namespace

from yaml import safe_load, YAMLError

from platform_kickstart.scenarios import Scenario
from platform_kickstart.scenarios.local import LocalScenario
from platform_kickstart.scenarios.ionos import IonosScenario


def initialize_logging() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def parse_cmd_args() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("-f", "--file", dest="filename", help="DigitalTwinPlatform k8s object.",
                        metavar="FILE", required=True)
    args = parser.parse_args()

    return args


def parse_k8s_object(path: Path) -> str:
    with open(path, "r") as stream:
        try:
            data = safe_load(stream)
        except YAMLError:
            logging.error(f"Couldn't parse DigitalTwinPlatform k8s object: {path}")
    try:
        provider = data["spec"]["compositionSelector"]["matchLabels"]["provider"]
    except KeyError:
        logging.error(f"Couldn't determine Digital Twin Platform environment!")
        sys.exit(1)

    return provider


def get_scenario(scenario: str) -> Scenario:
    if scenario == "local":
        return LocalScenario()
    elif scenario == "ionos":
        return IonosScenario()
    else:
        logging.error(f'Scenario "{scenario}" not supported!')
        sys.exit(1)


def main() -> None:
    initialize_logging()
    args = parse_cmd_args()
    source = parse_k8s_object(args.filename)

    scenario = get_scenario(source)

    logging.info(f'Trying to run "{source}" scenario.')
    scenario.run()
    logging.info(f'Scenario "{source}" completed.')


if __name__ == "__main__":
    main()
