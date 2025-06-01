from dataclasses import dataclass
import sys

# Use different import paths depending on how the file is being run
try:
    from characters import Character, Townsfolk, Outsider, Minion, Demon
except ModuleNotFoundError:
    # Fall back to prefixed import when run from outside src directory
    from src.characters import Character, Townsfolk, Outsider, Minion, Demon

@dataclass
class Script:
    townsfolk: list[Townsfolk]
    outsiders: list[Outsider]
    minions: list[Minion]
    demons: list[Demon]
    first_night_order: list[Character]
    other_night_order: list[Character]
    character_str: str

TROUBLE_BREWING_CHARACTERS = '''
The following is the complete list of all characters that can be in the game.
## Townsfolk (Good)
• Washerwoman: Starts knowing that 1 of 2 players is a particular Townsfolk
• Librarian: Starts knowing that 1 of 2 players is a particular Outsider (or that zero are in play)
• Investigator: Starts knowing that 1 of 2 players is a particular Minion
• Chef: Starts knowing how many adjacent pairs of Evil players there are. 0 means evil players are not sitting next to each other, 1 means there is one pair, and 2 means there are two pairs.
• Empath: Each night, learns how many of their 2 alive neighbors are Evil. They will be told a 0 if neither neighbor is Evil, a 1 if one neighbor is Evil, and a 2 if both neighbors are Evil.
• Fortune Teller: Each night, chooses 2 players and learns if either is a Demon. There is a good player who registers as a Demon.
• Undertaker: Each night (except the first), learns which character died by execution that day (players killed by the Demon are not considered executed)
• Monk: Each night (except the first), chooses a player to protect from the Demon's attack
• Ravenkeeper: If dies at night, wakes to choose a player and learn their character
• Virgin: The first time nominated, if the nominator is a Townsfolk (Good), the nominator is executed immediately and the day ends.
• Slayer: Once per game during the day, publicly choose a player; if they're the Demon, they die. This will not kill Minions. Any player can attempt to use the Slayer ability but only the real Slayer can kill the Demon.
• Mayor: If only 3 players live and no execution occurs, their team wins; if they die at night, the Storyteller might choose another player to die instead
• Soldier: Cannot be killed by the Demon

## Outsiders (Good)
• Butler: Each night, chooses a player and can only vote if that player votes Yes before it is their turn to vote
• Drunk: Thinks they are a Townsfolk character, but they are the Drunk. They will be treated as if they are the Townsfolk character, but information they are given may be false and their ability will not work.
• Recluse: Might register as Evil and as a Minion or Demon, even if you are a ghost
• Saint: If executed, their team loses

## Minions (Evil)
• Poisoner: Each night they choose a player to poison for that night and the next day
• Spy: Each night, sees the Grimoire (contains complete information about the game state); might register as Good and as a Townsfolk or Outsider
• Scarlet_Woman: If 5+ players are alive and the Demon dies, becomes the Demon and the game continues.
• Baron: Adds two extra Outsiders to the game during setup. The player count stays the same and Townsfolk are removed to make room

## Demon (Evil)
• Imp: Each night (except the first), chooses a player to kill; if they kill themselves, the Storyteller picks a Minion to become the new Imp
'''

TROUBLE_BREWING = Script(
    townsfolk=[Townsfolk.WASHERWOMAN, Townsfolk.LIBRARIAN, Townsfolk.INVESTIGATOR, Townsfolk.CHEF, Townsfolk.EMPATH, Townsfolk.FORTUNETELLER, Townsfolk.UNDERTAKER, Townsfolk.MONK, Townsfolk.RAVENKEEPER, Townsfolk.VIRGIN, Townsfolk.SLAYER, Townsfolk.SOLDIER, Townsfolk.MAYOR],
    outsiders=[Outsider.BUTLER, Outsider.SAINT, Outsider.RECLUSE, Outsider.DRUNK],
    minions=[Minion.POISONER, Minion.SPY, Minion.BARON, Minion.SCARLET_WOMAN],
    demons=[Demon.IMP],
    first_night_order=[Minion.POISONER, Minion.SPY, Townsfolk.WASHERWOMAN, Townsfolk.LIBRARIAN, Townsfolk.INVESTIGATOR, Townsfolk.CHEF, Townsfolk.EMPATH, Townsfolk.FORTUNETELLER, Outsider.BUTLER],
    other_night_order=[Minion.POISONER, Townsfolk.MONK, Minion.SPY, Demon.IMP, Townsfolk.RAVENKEEPER, Townsfolk.UNDERTAKER, Townsfolk.EMPATH, Townsfolk.FORTUNETELLER, Outsider.BUTLER],
    character_str=TROUBLE_BREWING_CHARACTERS
)


