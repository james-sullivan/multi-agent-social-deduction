from roles import Townsfolk, Outsider, Minion, Demon, Role
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
    def __init__(self, name: str):
        super().__init__(name, Character.WASHERWOMAN)

class Librarian(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.LIBRARIAN)

class Investigator(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.INVESTIGATOR)

class Chef(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.CHEF)

class Empath(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.EMPATH)

class FortuneTeller(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.FORTUNETELLER)

class Undertaker(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.UNDERTAKER)

class Monk(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.MONK)

class Ravenkeeper(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.RAVENKEEPER)
    
    def use_ravenkeeper_ability(self, public_game_state: dict) -> None:
        pass

class Virgin(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.VIRGIN)

class Slayer(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.SLAYER)
    
    def use_slayer_ability(self, public_game_state: dict) -> None:
        pass

class Soldier(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.SOLDIER)

class Mayor(Townsfolk):
    def __init__(self, name: str):
        super().__init__(name, Character.MAYOR)

### Outsiders ###
class Butler(Outsider):
    def __init__(self, name: str):
        super().__init__(name, Character.BUTLER)

class Saint(Outsider):
    def __init__(self, name: str):
        super().__init__(name, Character.SAINT)

class Recluse(Outsider):
    def __init__(self, name: str):
        super().__init__(name, Character.RECLUSE)
        
    def get_alignment(self) -> Alignment:
        return Alignment.EVIL
    
    def get_role(self) -> Role:
        return Role.DEMON
    
    # Override get_character to implement Recluse's special ability
    def get_character(self):
        return random.choice([Character.POISONER, Character.BARON, Character.SCARLET_WOMAN, Character.IMP])

class Drunk(Outsider):
    def __init__(self, name: str):
        super().__init__(name, Character.DRUNK)

### Minions ###
class Poisoner(Minion):
    def __init__(self, name: str):
        super().__init__(name, Character.POISONER)

class Spy(Minion):
    def __init__(self, name: str):
        super().__init__(name, Character.SPY)
        
    def get_alignment(self) -> Alignment:
        return Alignment.GOOD
    
    def get_role(self) -> Role:
        return random.choice([Role.TOWNSFOLK, Role.OUTSIDER])
    
    # Override get_character to implement Spy's special ability
    def get_character(self):
        return random.choice([Character.EMPATH, Character.FORTUNETELLER, Character.INVESTIGATOR, 
                             Character.SOLDIER, Character.SLAYER, Character.VIRGIN, 
                             Character.BUTLER, Character.SAINT, Character.DRUNK])

class Baron(Minion):
    def __init__(self, name: str):
        super().__init__(name, Character.BARON)

class ScarletWoman(Minion):
    def __init__(self, name: str):
        super().__init__(name, Character.SCARLET_WOMAN)

### Demons ###
class Imp(Demon):
    def __init__(self, name: str):
        super().__init__(name, Character.IMP)
