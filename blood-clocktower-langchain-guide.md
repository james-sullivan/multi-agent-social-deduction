# Blood on the Clocktower Multi-Agent Implementation with LangChain and Claude 3.5 Haiku

## Game Overview

Blood on the Clocktower is a social deduction game of murder, mystery, and demons taking place in the town of Ravenswood Bluff. Unlike traditional social deduction games, Blood on the Clocktower features a Storyteller (game moderator) who orchestrates the experience, and uniquely allows dead players to remain active participants who can still contribute to discussions and victory.

### Core Game Structure

- **Player Count**: 5-20 players plus a Storyteller
- **Game Duration**: 30-90 minutes
- **Two Opposing Teams**:
  - **Good Team**: Townsfolk and Outsiders trying to identify and execute the Demon
  - **Evil Team**: A Demon and Minions trying to eliminate enough villagers to gain majority

### Game Objective

- **Good Team Wins**: When the Demon is executed
- **Evil Team Wins**: When the number of living players is reduced to two (meaning the evil players equal or outnumber the good)

## Character Types

Blood on the Clocktower features several distinct character types that will need to be modeled in our multi-agent implementation:

### 1. Townsfolk (Good)

Townsfolk have abilities that benefit the good team. Most players in the game are typically Townsfolk. These characters often have information-gathering abilities or protective powers. They are the backbone of the good team's efforts.

### 2. Outsiders (Good)

Outsiders have abilities that hinder the good team in some way. The number of Outsiders in play varies based on player count. Their presence complicates matters for the good team, often creating confusion or disadvantages.

### 3. Minions (Evil)

Minions support the Demon with abilities that undermine the good team. They know who the Demon is from the start of the game and work to protect them while sowing discord among the good team.

### 4. Demon (Evil)

The Demon is the primary antagonist with the power to kill one player each night. The good team must identify and execute the Demon to win, while the evil team wins if the Demon remains alive until only two players remain.

## Game Phases

The game alternates between two main phases:

### 1. Night Phase

- All players close their eyes
- The Storyteller calls on specific characters to wake up one by one to use their abilities
- The Demon selects a player to kill
- Some characters receive information or perform actions while others are asleep
- The Storyteller may provide false information to players who are "drunk" or "poisoned"

### 2. Day Phase

- All players open their eyes and discover who died during the night
- Players freely discuss, share information, and form theories
- Any player can nominate another player for execution
- Players vote on the nomination
- The player with majority votes is executed and their character is revealed
- The game continues with another night phase unless a win condition is met

## Key Game Mechanics to Implement

### 1. Information Flow

- Some players have true information, some have false information
- The Storyteller may deliberately misinform certain players due to game effects
- Dead players retain their knowledge but lose their abilities

### 2. Social Dynamics

- Players can claim to be any character, truthfully or not
- Players can share or withhold information strategically
- Private conversations are allowed but limited in time

### 3. Execution Voting

- Any player can nominate once per day
- Nominations require a second
- All living players vote on each nomination
- Dead players have limited voting power (typically one vote for the entire game)

## Multi-Agent Implementation with LangChain

To implement Blood on the Clocktower using LangChain's multi-agent framework with Claude 3.5 Haiku, we need to create several components:

### 1. The Storyteller Agent

This is the central coordinator that:
- Manages game state (tracks which players are alive/dead, poisoned, etc.)
- Enforces game rules
- Provides accurate or deliberately false information as required
- Orchestrates the night and day phases
- Processes player actions and determines outcomes
- Checks for win conditions

The Storyteller agent needs access to complete game information while controlling what information is available to player agents.

### 2. Player Agents

Each player is represented by a Claude 3.5 Haiku agent that:
- Has knowledge of their own character and abilities
- Can interact with other players and the Storyteller
- Makes strategic decisions based on available information
- Can bluff, share information, or remain silent as desired
- Votes during nominations

### 3. Game State Management

The implementation needs to track:
- Character assignments and alignment (good/evil)
- Living and dead players
- Night actions and their results
- Nomination and voting history
- Character status effects (drunk, poisoned, etc.)

### 4. Communication System

A structured communication framework that allows:
- Public messages during day phases
- Private communications between specific players
- Storyteller communications to individual players
- Announcement of game events to all players

### 5. Voting Mechanism

Implement a system that:
- Allows nominations only from living players
- Restricts each living player to one nomination per day
- Collects votes from all players (living and dead)
- Applies the one-vote-per-game limitation for dead players
- Determines execution outcome based on majority rule

## Character Role Implementation: Trouble Brewing

The implementation should specifically focus on the Trouble Brewing script, which includes the following roles:

### Townsfolk (Good)

1. **Washerwoman**: Starts knowing that 1 of 2 players is a particular Townsfolk
2. **Librarian**: Starts knowing that 1 of 2 players is a particular Outsider (or that zero are in play)
3. **Investigator**: Starts knowing that 1 of 2 players is a particular Minion
4. **Chef**: Starts knowing how many pairs of evil players there are
5. **Empath**: Each night, learns how many of their 2 alive neighbors are evil
6. **Fortune Teller**: Each night, chooses 2 players and learns if either is a Demon (with a "good player registers as Demon" complication)
7. **Undertaker**: Each night (except the first), learns which character died by execution that day
8. **Monk**: Each night (except the first), chooses a player to protect from the Demon's attack
9. **Ravenkeeper**: If dies at night, wakes to choose a player and learn their character
10. **Virgin**: The first time nominated, if the nominator is a Townsfolk, they are executed immediately
11. **Slayer**: Once per game during the day, can publicly choose a player; if they're the Demon, they die
12. **Mayor**: If only 3 players live and no execution occurs, their team wins; if they die at night, another player might die instead
13. **Soldier**: Cannot be killed by the Demon

### Outsiders (Good)

1. **Butler**: Each night, chooses a player and can only vote if that player votes the next day
2. **Drunk**: Does not know they are the Drunk; thinks they are a Townsfolk but has no ability
3. **Recluse**: Might register as evil and as a Minion or Demon, even if dead
4. **Saint**: If executed, their team loses

### Minions (Evil)

1. **Poisoner**: Each night, chooses a player to poison for that night and the next day
2. **Spy**: Each night, sees the Grimoire; might register as good and as a Townsfolk or Outsider
3. **Scarlet Woman**: If 5+ players are alive and the Demon dies, becomes the Demon
4. **Baron**: Adds extra Outsiders to the game (+2 Outsiders)

### Demon (Evil)

1. **Imp**: Each night (except the first), chooses a player to kill; if kills themselves, a Minion becomes the Imp

Note: All character abilities must be implemented through the Storyteller agent, never by the player agents directly. This is critical because abilities can be affected by game effects like being drunk or poisoned.

## Implementation Approach

To create this multi-agent system with LangChain and Claude 3.5 Haiku:

### 1. Existing Codebase Integration

The implementation should respect and integrate with the existing files in the src directory:
- `roles.py`: Contains definitions for the various character roles
- `characters.py`: Implements character types and their abilities
- `player.py`: Manages player state and interactions

Any new code should build upon these existing components rather than replacing them.

### 2. Storyteller Agent

The Storyteller should be implemented as its own Claude 3.5 Haiku agent that:
- Initializes the game with appropriate character distribution
- Maintains the "Grimoire" (the complete game state)
- Controls the flow between night and day phases
- Processes all character abilities and their effects
- Provides information to players based on their character abilities
- Announces deaths, executions, and other game events
- Manages the nomination and voting process

### 3. Player Agent Design

Each player agent should:
- Understand their character's abilities and win conditions
- Receive appropriate information about the game state
- Make decisions based on available information
- Take actions according to their character's abilities
- Participate in discussions and voting
- Maintain a history of all information received
- Keep a notes string for persistent memory

Agent memory should be implemented with two components:
1. **History**: A chronological record of all information the agent has received, including:
   - Storyteller communications
   - Public discussions
   - Private conversations
   - Character ability results
   - Game events (deaths, executions, etc.)
   
2. **Notes**: A string where the agent can store synthesized information, including:
   - Theories about other players
   - Strategy considerations
   - Important observations

Both history and notes should be included as context in each prompt when the agent needs to make a decision or communicate.

At the end of each day phase (starting after the second night phase), the agent should:
1. Summarize its history into its notes
2. Clear its history to prevent context overflow

### 4. Communication Framework

The system should implement:
- Public forum for day phase discussions
- Private channels for evil team coordination
- Individual channels for Storyteller-player interaction
- Structured formats for role actions and voting
- Mechanism to close private conversations when nominations open

### 5. Game Loop Implementation

The main game loop should:
- Alternate between night and day phases
- Process character abilities during the night phase
- Facilitate open discussion during the day phase
- Have the Storyteller open the floor for nominations at the end of the day phase
- Prevent private conversations once nominations begin
- Handle nominations and voting
- Check win conditions after each phase

## Specific Multi-Agent Considerations

### 1. Agent Communication Design

Each Claude agent should be designed with basic capabilities to:
- Communicate with other players during the day phase
- Process information received from the Storyteller
- Convey their character's actions to the Storyteller
- Make nominations (if alive) and cast votes
- Express their reasoning and conclusions about the game state

### 2. Information Processing

Agents need basic information processing capabilities to:
- Maintain awareness of known game facts
- Track which players are alive or dead
- Remember the outcomes of votes and nominations
- Process character-specific information they receive
- Understand their own abilities and how to use them

### 3. Information Flow Control

The system must carefully control:
- What information each agent has access to
- When information is revealed
- How information might be deliberately falsified (for poisoned/drunk characters)
- How dead players continue to participate

### 4. Day Phase: Nomination Process

The nomination process should follow these steps:
- After discussion period, the Storyteller announces that nominations are open
- Once nominations begin, private conversations are no longer allowed
- Only living players can nominate, and each can only nominate once per day
- After each nomination, all players vote (living and dead)
- Dead players have exactly one vote for the entire rest of the game (not "typically" - this is a firm rule)
- A majority of living players must vote in favor for an execution to occur
- If a majority of living players votes in favor, that player is executed
- If the nomination fails to get a majority of living players' votes, discussion continues until another nomination
- Important: An execution is not required to end the day. If enough time passes without a successful nomination, the Storyteller SHOULD end the day phase and move to night with no execution

### 5. Agent Prompt Construction

When an agent needs to make a decision or take action, the prompt should include:
- The agent's complete history of information received
- The agent's notes containing synthesized information and observations
- Their character's abilities and constraints
- The current game state relevant to their decision
- Clear options for possible actions

The prompt should be structured to ensure the agent has all necessary context without explicitly directing their decision-making strategy.

## Implementation Challenges

Several key challenges that Cursor will need to address:

### 1. Hidden Information Management

The game revolves around hidden information, requiring the system to:
- Maintain private state for each agent
- Track what information has been revealed to which agents
- Process information that may be true or false
- Manage the Storyteller's knowledge of the complete game state

### 2. Character Ability Implementation

Many characters have abilities that interact in complex ways:
- Some abilities only trigger under specific conditions
- Abilities can conflict or override one another
- Status effects like "drunk" or "poisoned" can change how abilities function
- **Critical**: All character abilities and game state changes must be executed by the Storyteller agent, never by player agents directly

### 3. Communication Framework

The system needs to handle multiple communication channels:
- Public discussions visible to all players
- Private conversations between players
- Storyteller communications to individual players
- Notifications about game events
- Transition between free discussion and the nomination phase

### 4. Rules Enforcement

The implementation must enforce game rules properly:
- Preventing players from acting out of turn
- Ensuring character abilities function correctly
- Managing the transition between game phases
- Controlling information flow to maintain the game's integrity
- Enforcing the end of private conversations when nominations begin

### 5. Game State Management

The Storyteller agent must maintain the complete game state, including:
- Which characters each player has been assigned
- Which players are alive or dead
- Which players are drunk, poisoned, or protected
- All night actions and their results
- Nomination and voting history
- Win condition checks

## Conclusion

Blood on the Clocktower provides an excellent framework for a multi-agent implementation using LangChain and Claude 3.5 Haiku. The implementation should focus on creating a neutral system that provides agents with accurate game state information, clear rules, and available actions without strategic guidance.

Key elements for a successful implementation include:

1. Integration with existing code in roles.py, characters.py, and player.py
2. A Storyteller implemented as its own Claude agent to manage the game
3. Player agents with persistent memory through:
   - A complete history of all information received
   - A notes string for synthesized information
   - Summarization of history into notes at the end of each day
4. A robust communication system that handles both public and private conversations, with proper restrictions during nominations
5. A structured game loop that alternates between night and day phases
6. Proper implementation of character abilities and their interactions
7. A fair nomination and voting system that:
   - Restricts nominations to living players (one nomination per day)
   - Gives dead players only one vote for the rest of the game

The implementation should start with the "Trouble Brewing" edition, which is designed for beginners and provides a solid foundation for the game's core mechanics. Once successful, the system can be expanded to include the more complex "Sects & Violets" or "Bad Moon Rising" editions, which introduce additional characters and mechanics.

By creating a system that faithfully implements the rules and mechanics of Blood on the Clocktower without providing strategic guidance, Cursor can build a compelling multi-agent environment where Claude 3.5 Haiku agents can demonstrate emergent social deduction and decision-making in a structured game context.
