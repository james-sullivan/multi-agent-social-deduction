BOTC_RULES = '''
# Rules Summary
Blood on the Clocktower is a social deduction game similar to Werewolf (or Mafia). At the start of the game each player is secretly given a character that determines what team they are on and what special abilities they have. There can only be one of each character in the game. Players are either on the Good team or the Evil team. The Evil team members know who each other are but the Good team does not know who anyone but themselves are. 

## Storyteller
The game is moderated by the Storyteller who is a neutral agent that will enforce the rules and give informaiton to players. The Storyteller will also have decisions to make about things like what false information to give to players. The Storyteller maintains the complete game state inside of the Grimoire. This include what character each player is and what status effects they have.

## Objectives
The Good team wins if they execute the Demon.

The Evil team wins if there are only 2 players left alive no matter what team they are on.

## Gameplay
The game is played in rounds. Each round has a night phase and then a day phase. The game continues until either team wins.

During the day players can send messages to each other to persuade, strategize, coordinate, theorize, and share information. At the end of the day players will vote on who they want to nominate for execution and at the end of the day, if a player has been nominated, that player will die.

During the night the Storyteller will secretly give information to players based on their character's ability or allow them to secretly use their ability. All information at night is secret and only the player receiving the information or using their ability knows about it.

## Nomination for Execution
Towards the end of the day the Storyteller will allow players to nominate each other for execution. Each living player can only nominate one person per day and each person may only be nominated once per day. You can nominate any player including yourself or any other living or ghost player.

During a nomination each player will vote starting with the player who is being nominated and proceeding left to right until all players have voted. Players can vote yes or no. When each player votes, they first get to see the votes of the players who voted before them. 

The number of votes needed for a successful nomination is at least half of the living players rounded up. If a player is successfully nominated, future nominations will need to exceed the number of votes previously cast for that player to replace the old nominee. If there is a tie, neither player is nominated and both players are safe for the day. At the end of the day, the currently nominated player will be executed and will become a ghost player. Only one player can be executed per day. You do NOT learn what character players are when they die or what team they are on.

## Alignment
The alignment of a player is the team they are on. A player can be on the Good team or the Evil team. By default, Townsfolk and Outsiders are Good players. Minions and the Demon are Evil players.

## Characters
Each player has a character. Each character has an ability. A player's character is seperate from their alignment. The moment a player dies, or becomes poisoned or drunk, their character's ability stops affecting the game. No one's character will be confirmed or denied by the Storyteller. For example, if a player uses the Slayer power you will be either told the target dies or nothing happened. If nothing happens the player who used the power may or may not be the real Slayer.

## Roles
The Good team is made up of Townsfolk and Outsiders. Townsfolk are Good players who have an ability that is helpful to the Good team. Outsiders are Good players who have an ability that is harmful to the Good team.

The Evil team is made up of one Demon and one to three Minions. The Demon is the most important Evil player and the player that the Good team is trying to kill. Minions are also Evil players who have an ability that is helpful to the Evil team. At the start of the game, the Demon is secretly told three good players that are not in play so the evil team can bluff as those roles.

## Ghost Players
Ghost players are still in the game and can still talk to other players, but they no longer have their character's ability, they cannot nominate players for execution, and they only get one vote for the rest of the game.

## Being Poisoned and Drunk
Poisoned and Drunk are status effects that can be applied to players. They function the exact same way and a player will not know if they are Poisoned or Drunk. If a player is Poisoned or Drunk their character's ability will not work and any information that they receive from the Storyteller may be false. The Drunk is an Outsider who is told that they are one of the Townsfolk characters.

## Registers
The rules and characters abilities sometimes talk about a player "registering" as good/evil, a particular role, or a particular character. This means that the game mechanics will treat them as the character, alignment, or role they are registering as, even if they are not that character, alignment, or role. For example, if a player "might" register as evil, then the Storyteller can decide to show another player a demon character when another player uses their ability to check what character they are.
'''

POISONER_PROMPT = '''Choose the name of one player to poison for the night and next day. Posioned player's abilites will not work and they may receive false information.'''

FORTUNETELLER_PROMPT = '''Choose any 2 players and learn if either is the Demon.'''

MONK_PROMPT = '''Choose a player to protect from the Demon's attack tonight.'''

RAVENKEEPER_PROMPT = '''Choose a player to learn their character.'''

BUTLER_PROMPT = '''Choose a player to be your master. Tomorrow during voting, you may only vote if your master votes first. You cannot choose yourself.'''

IMP_PROMPT = '''Choose a player to kill tonight. If you choose yourself, one of your living minions will become the new Imp.'''
