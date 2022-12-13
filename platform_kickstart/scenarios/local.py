import logging

from platform_kickstart.scenarios import Scenario


class LocalScenario(Scenario):
    def __init__(self):
        pass

    def run(self) -> None:
        logging.info("Local scenario")


