# Blood on the Clocktower Multi-Agent Implementation

A sophisticated social deduction game where AI agents play Blood on the Clocktower. This implementation features detailed character powers, enhanced game tracking, and comprehensive event logging.

## Overview

This implementation features:
- **Multiple AI agents** playing different Blood on the Clocktower characters
- **14+ unique characters** including Townsfolk, Outsiders, Minions, and Demons
- **Day and night phases** with character-specific abilities and decision making
- **Enhanced status tracking** showing dead votes and drunk/poisoned status
- **Detailed event logging** with specific event types for each character power
- **Visual game summaries** with colored console output
- **Configurable game parameters** and multiple game scripts

## Supported Characters

### Townsfolk (Good Team)
- **Washerwoman** 🧺: Learns which of two players is a specific Townsfolk
- **Librarian** 📚: Learns which of two players is a specific Outsider  
- **Investigator** 🔍: Learns which of two players is a specific Minion
- **Chef** 👨‍🍳: Learns how many pairs of adjacent evil players there are
- **Empath** 💝: Learns how many of their living neighbors are evil
- **Fortuneteller** 🔮: Learns if one of two chosen players is the Demon
- **Monk** 🙏: Protects a chosen player from the Demon
- **Ravenkeeper** 🐦: If killed by the Demon, learns any player's character
- **Undertaker** ⚰️: Learns the character of the player executed yesterday
- **Slayer** ⚔️: Can attempt to kill the Demon once per game
- **Soldier**: Safe from the Demon
- **Mayor** 🏛️: Wins if only 3 players remain with no execution
- **Virgin**: First Townsfolk to nominate them dies

### Outsiders (Good Team, but harder to win)
- **Butler** 🤵: May only vote when their chosen master votes
- **Drunk**: Thinks they are a Townsfolk but has no ability
- **Recluse**: Registers as evil and as a Minion/Demon
- **Saint**: If executed, evil wins

### Minions (Evil Team)
- **Poisoner** 💉: Poisons a player each night, disabling their ability
- **Spy** 🕵️: Sees the complete game state and registers as good
- **Scarlet Woman** 🔄: Becomes the Demon if the Demon dies
- **Baron**: Adds two Outsiders to the game

### Demons (Evil Team)
- **Imp** 😈: Kills a player each night

## Requirements

- Python 3.8+

## Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/multi-agent-social-deduction.git
   cd multi-agent-social-deduction
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure any required environment variables (if needed for your AI provider)

## Running the Game

To run the game with default settings:
```bash
python src/main.py
```

To use a specific script configuration:
```bash
python src/main.py --script trouble_brewing
```

To run in debug mode with verbose logging:
```bash
python src/main.py --debug
```

You can combine options:
```bash
python src/main.py --script trouble_brewing --debug
```

Available script configurations:
- `trouble_brewing`: Classic Trouble Brewing setup with balanced character distribution
- `custom_small`: Smaller game for testing (5-7 players)
- `custom_large`: Larger game with more complexity (10+ players)

## Game Features

### Enhanced Status Summary
The game displays a comprehensive character status table showing:
- **Player names** and **character roles**
- **Alive/Dead status**
- **Drunk/Poisoned status** (affecting ability reliability)
- **Dead vote availability** (dead players get one vote)

```
=====================================================================================
                         CHARACTER STATUS SUMMARY
=====================================================================================
Name        | Role       | Status | Drunk/Poisoned | Dead Vote
-------------------------------------------------------------------------------------
Susan       | Imp        | ALIVE  | NO             | N/A
John        | Poisoner   | DEAD   | NO             | Available
Emma        | Butler     | ALIVE  | YES            | N/A
Michael     | Empath     | DEAD   | NO             | Used
Olivia      | Virgin     | ALIVE  | NO             | N/A
=====================================================================================
```

### Detailed Event Tracking
Every game action is tracked with specific event types:
- **Character Power Events**: Each character's ability gets its own event type (🧺 Washerwoman, 🔮 Fortuneteller, 😈 Imp, etc.)
- **Game Flow Events**: Nominations ⚖️, Voting 🗳️, Executions ⚔️, Deaths 💀
- **Special Events**: Scarlet Woman transformations 🔄, Mayor wins 🏛️
- **Communication**: Messages 💬 and player passes ⏭️

### Game Phases

1. **Night Phase**:
   - Characters use their abilities in a specific order
   - Evil team learns each other's identities
   - Demon attempts to kill a player
   - Information-gathering characters learn clues

2. **Day Phase**:
   - Players discuss and share information
   - Nomination and voting rounds
   - Players can use day abilities (like Slayer power)
   - Execution occurs if someone receives enough votes

### Win Conditions

- **Good Team wins**: If all Demons are eliminated
- **Evil Team wins**: If evil players equal or outnumber good players (≤2 players alive)
- **Mayor wins**: If exactly 3 players remain alive with no execution

## Logs and Output

The game generates comprehensive logs showing:
- **Console output**: Real-time colored event display with emojis
- **Game logs**: Detailed event history in `logs/` directory
- **JSON exports**: Complete game data for analysis
- **Round summaries**: Key events for each game round

## Technical Features

### Event System
- **31 distinct event types** for granular tracking
- **Colored console output** with character-specific styling
- **JSON serialization** for game state persistence
- **Event filtering** and statistics generation

### AI Integration
- **Character-specific prompts** for authentic role-playing
- **Context-aware decision making** based on game state
- **Dynamic conversation and voting behaviors**
- **Flexible AI provider integration**

### Game Mechanics
- **Drunk/Poisoned system**: Characters may receive false information
- **Dead voting**: Dead players get one vote they can use
- **Reminder tokens**: Track ongoing effects and character states
- **Multiple win conditions**: Complex victory scenarios

## Customization

Edit the script configurations in `src/scripts.py` to create custom character combinations and game sizes. Each script defines:
- Character counts for each role type
- First night and other night ability orders
- Character descriptions and interactions
