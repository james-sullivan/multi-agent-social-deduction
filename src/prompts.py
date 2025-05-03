BOTC_RULES = '''
# Rules Summary
Blood on the Clocktower is a social deduction game similar to Werewolf (or Mafia). At the start of the game each player is secretly given a character that determines what team they are on and what special abilities they have. There can only be one of each character in the game. Players are either on the Good team or the Evil team. The Evil team members know who each other are but the Good team does not know who anyone but themselves are. The game is moderated by the Storyteller who is a neutral agent that will enforce the rules and give informaiton to players.

## Objectives
The Good team wins if they execute the Demon.

The Evil team wins if there are only 2 players left alive (and one of them is the Demon).

## Gameplay
The game is played in rounds. Each round has a day phase and then a night phase. The game continues until either team wins.

During the day players can send messages to each other to persuade, strategize, coordinate, theorize, and share information. At the end of the day players will vote on who they want to nominate for execution and at the end of the day, if a player has been nominated, that player will die.

During the night the Storyteller will secretly give information to players based on their character's ability or allow them to secretly use their ability. All information at night is secret and only the player receiving the information or using their ability knows about it.

## Nomination for Execution
Towards the end of the day the Storyteller will allow players to nomiate each other for execution. Each living player can only nominate one person per day and each person may only be nominated once per day. You can nominate any player including yourself or any other living or dead player.

During a nomination each player will vote starting with the player who is being nominated and proceeding clockwise. Players can vote yes or no. When each player votes, they first get to see the votes of the players who voted before them. 

The number of votes needed for a successful nomination is at least half of the living players rounded up. If a player is successfully nominated, future nominations will need to exceed the number of votes previously cast for that player to become the next nominee. If there is a tie, neither player is nominated and both players are safe for the day.

## Roles
The Good team is made up of Townsfolk and Outsiders. Townsfolk are Good players who have an ability that is helpful to the Good team. Outsiders are Good players who have an ability that is harmful to the Good team.

The Evil team is made up of one Demon and one to three Minions. The Demon is the most important Evil player and the player that the Good team is trying to kill. Minions are also Evil players who have an ability that is helpful to the Evil team. At the start of the game, the Demon is secretly told three good players that are not in play.

## Dead Players
Dead players are still in the game and can still talk to other players, but they no longer have their character's ability, they cannot nominate players for execution, and they only get one vote for the rest of the game.

## Being Poisoned and Drunk
Posioned and Drunk are status effects that can be applied to players. They function the exact same way and a player will not know if they are Poisoned or Drunk. If a player is Poisoned or Drunk their character's ability will not work and any information that they recieve from the Storyteller may be false.

A player's abliity stops affecting the game as soon as they die, or they become poisoned or drunk.
'''

TROUBLE_BREWING_SCRIPT = '''
The following is the complete list of all characters that can be in the game.
## Townsfolk (Good)
• Washerwoman: Starts knowing that 1 of 2 players is a particular Townsfolk
• Librarian: Starts knowing that 1 of 2 players is a particular Outsider (or that zero are in play)
• Investigator: Starts knowing that 1 of 2 players is a particular Minion
• Chef: Starts knowing how many adjacent pairs of Evil players there are. (If three evil players are adjacent in a line, there are two pairs)
• Empath: Each night, learns how many of their 2 alive neighbors are Evil
• Fortune Teller: Each night, chooses 2 players and learns if either is a Demon. There is a good player who registers as a Demon.
• Undertaker: Each night (except the first), learns which character died by execution that day
• Monk: Each night (except the first), chooses a player to protect from the Demon's attack
• Ravenkeeper: If dies at night, wakes to choose a player and learn their character
• Virgin: The first time nominated, if the nominator is a Townsfolk, the nominator dies immediately and the nomination continues.
• Slayer: Once per game during the day, publicly choose a player; if they're the Demon, they die
• Mayor: If only 3 players live and no execution occurs, their team wins; if they die at night, the Storyteller might choose another player to die instead
• Soldier: Cannot be killed by the Demon

## Outsiders (Good)
• Butler: Each night, chooses a player and can only vote if that player votes Yes before it is their turn to vote
• Drunk: Thinks they are a Townsfolk but they are Drunk. They Storyteller will treat them as if they are the Townsfolk they think they are but their ability does not work.
• Recluse: Might register as Evil and as a Minion or Demon, even if dead
• Saint: If executed, their team loses

## Minions (Evil)
• Poisoner: Each night they choose a player to poison for that night and the next day
• Spy: Each night, sees the Grimoire (contains complete informaiton about the game state); might register as Good and as a Townsfolk or Outsider
• Scarlet_Woman: If 5+ players are alive and the Demon dies, becomes the Demon
• Baron: Adds extra Outsiders to the game during setup. Player count stays the same and Townsfolk are removed to make room. (+2 Outsiders)

## Demon (Evil)
• Imp: Each night (except the first), chooses a player to kill; if they kill themselves, the Storyteller picks a Minion to become the new Imp
'''