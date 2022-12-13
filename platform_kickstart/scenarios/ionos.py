import logging

from platform_kickstart.scenarios import Scenario


class IonosScenario(Scenario):
    def __init__(self):
        pass

    def run(self):
        logging.info("Ionos scenario")
