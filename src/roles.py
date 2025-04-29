from player import Player
from game import Alignment
from enum import Enum

class Role(Enum):
    TOWNSFOLK = "Townsfolk"
    OUTSIDER = "Outsider"
    MINION = "Minion"
    DEMON = "Demon"

class Townsfolk(Player):
    def __init__(self, name: str):
        super().__init__(name, Alignment.GOOD)

    def get_role(self) -> Role:
        return Role.TOWNSFOLK

class Outsider(Player):
    def __init__(self, name: str):
        super().__init__(name, Alignment.GOOD)

    def get_role(self) -> Role:
        return Role.OUTSIDER

class Minion(Player):
    def __init__(self, name: str):
        super().__init__(name, Alignment.EVIL)

    def get_role(self) -> Role:
        return Role.MINION

class Demon(Player):
    def __init__(self, name: str):
        super().__init__(name, Alignment.EVIL)

    def get_role(self) -> Role:
        return Role.DEMON