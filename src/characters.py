# from roles import Townsfolk, Outsider, Minion, Demon, Role
from enum import Enum, auto
import random
import sys

# Use different import paths depending on how the file is being run
try:
    from game_enums import Alignment
except ModuleNotFoundError:
    # Fall back to prefixed import when run from outside src directory
    from src.game_enums import Alignment

class ReminderTokens(Enum):
    RED_HERRING = "Fortuneteller_Red_Herring"
    WASHERWOMAN_TOWNSFOLK = "Washerwoman_Townsfolk"
    WASHERWOMAN_OTHER = "Washerwoman_Other"
    LIBRARIAN_OUTSIDER = "Librarian_Outsider"
    LIBRARIAN_OTHER = "Librarian_Other"
    INVESTIGATOR_MINION = "Investigator_Minion"
    INVESTIGATOR_OTHER = "Investigator_Other"
    MONK_PROTECTED = "Monk_Protected"
    RAVENKEEPER_WOKEN = "Ravenkeeper_Woken"
    IMP_KILLED = "Imp_Killed"
    UNDERTAKER_EXECUTED = "Undertaker_Executed"
    BUTLER_MASTER = "Butler_Master"
    IS_THE_DRUNK = "Is_the_Drunk"
    VIRGIN_POWER_USED = "Virgin_Power_Used"
    SLAYER_POWER_USED = "Slayer_Power_Used"

class Character(Enum):
    """Base enum for all characters - empty by design"""
    pass

class Townsfolk(Character):
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

class Outsider(Character):
    BUTLER = "Butler"
    SAINT = "Saint"
    RECLUSE = "Recluse"
    DRUNK = "Drunk"

class Minion(Character):
    POISONER = "Poisoner"
    SPY = "Spy"
    BARON = "Baron"
    SCARLET_WOMAN = "Scarlet_Woman"

class Demon(Character):
    IMP = "Imp"
