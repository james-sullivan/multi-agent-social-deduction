from src.roles import Townsfolk, Outsider, Minion, Demon, Role
from enum import Enum
import random
from game import Alignment

class Character(Enum):
    WASHERWOMAN = "Washerwoman"
    LIBRARIAN = "Librarian"
    INVESTIGATOR = "Investigator"
    CHEF = "Chef"
    EMPATH = "Empath"
    FORTUNETELLER = "Fortuneteller"
    UNDERTAKER = "Undertaker"
    MONK = "Monk"
    RAVENKEEPER = "Ravenkeeper"
    VIRGIN = "Virgin"
    SLAYER = "Slayer"
    SOLDIER = "Soldier"
    MAYOR = "Mayor"
    BUTLER = "Butler"
    SAINT = "Saint"
    RECLUSE = "Recluse"
    DRUNK = "Drunk"
    POISONER = "Poisoner"
    SPY = "Spy"
    BARON = "Baron"
    SCARLET_WOMAN = "Scarlet_Woman"
    IMP = "Imp"

### Townsfolk ###
class Washerwoman(Townsfolk):
    def get_character(self) -> Character:
        return Character.WASHERWOMAN    

class Librarian(Townsfolk):
    def get_character(self) -> Character:
        return Character.LIBRARIAN

class Investigator(Townsfolk):
    def get_character(self) -> Character:
        return Character.INVESTIGATOR

class Chef(Townsfolk):
    def get_character(self) -> Character:
        return Character.CHEF

class Empath(Townsfolk):
    def get_character(self) -> Character:
        return Character.EMPATH

class FortuneTeller(Townsfolk):
    def get_character(self) -> Character:
        return Character.FORTUNETELLER

class Undertaker(Townsfolk):
    def get_character(self) -> Character:
        return Character.UNDERTAKER


class Monk(Townsfolk):
    def get_character(self) -> Character:
        return Character.MONK

class Ravenkeeper(Townsfolk):
    def get_character(self) -> Character:
        return Character.RAVENKEEPER
    
    def use_ravenkeeper_ability(self, public_game_state: dict) -> None:
        pass

class Virgin(Townsfolk):
    def get_character(self) -> Character:
        return Character.VIRGIN

class Slayer(Townsfolk):
    def get_character(self) -> Character:
        return Character.SLAYER
    
    def use_slayer_ability(self, public_game_state: dict) -> None:
        pass

class Soldier(Townsfolk):
    def get_character(self) -> Character:
        return Character.SOLDIER

class Mayor(Townsfolk):
    def get_character(self) -> Character:
        return Character.MAYOR


### Outsiders ###
class Butler(Outsider):
    def get_character(self) -> Character:
        return Character.BUTLER

class Saint(Outsider):
    def get_character(self) -> Character:
        return Character.SAINT

class Recluse(Outsider):
    def get_alignment(self) -> Alignment:
        return Alignment.EVIL
    
    def get_role(self) -> Role:
        return Role.DEMON

    def get_character(self) -> Character:
        return random.choice([Character.POISONER, Character.BARON, Character.SCARLET_WOMAN, Character.IMP])

class Drunk(Outsider):
    def get_character(self) -> Character:
        return Character.DRUNK


### Minions ###
class Poisoner(Minion):
    def get_character(self) -> Character:
        return Character.POISONER

class Spy(Minion):
    def get_alignment(self) -> Alignment:
        return Alignment.GOOD
    
    def get_role(self) -> Role:
        return random.choice([Role.TOWNSFOLK, Role.OUTSIDER])
    
    def get_character(self) -> Character:
        return random.choice([Character.EMPATH, Character.FORTUNETELLER, Character.INVESTIGATOR, Character.SOLDIER, Character.SLAYER, Character.VIRGIN, Character.BUTLER, Character.SAINT, Character.DRUNK])

class Baron(Minion):
    def get_character(self) -> Character:
        return Character.BARON

class ScarletWoman(Minion):
    def get_character(self) -> Character:
        return Character.SCARLET_WOMAN


### Demons ###
class Imp(Demon):
    def get_character(self) -> Character:
        return Character.IMP
