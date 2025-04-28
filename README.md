# Werewolf Multi-Agent Implementation

A social deduction game where AI agents play the classic Werewolf (Mafia) game using LangChain and Claude 3.5 Haiku.

## Overview

This implementation features:
- Multiple AI agents playing different roles (Villager, Werewolf, Seer)
- Day and night phases with appropriate communication channels
- Role-specific abilities and decision making
- Configurable game parameters

## Requirements

- Python 3.8+
- An Anthropic API key with access to Claude 3.5 Haiku

## Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/werewolf-multi-agent.git
   cd werewolf-multi-agent
   ```

2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   ```

## Running the Game

To run the game with default settings:
```
python main.py
```

To use a specific configuration from `config.yaml`:
```
python main.py --config small_game
```

To run in debug mode with verbose logging (including HTTP requests):
```
python main.py --debug
```

You can combine options:
```
python main.py --config large_game --debug
```

Available configurations:
- `default`: 3 villagers, 2 werewolves, 1 seer, 10 days max
- `small_game`: 2 villagers, 1 werewolf, 1 seer, 5 days max
- `large_game`: 5 villagers, 3 werewolves, 1 seer, 15 days max
- `no_seer`: 4 villagers, 2 werewolves, no seer, 10 days max

## Game Mechanics

### Roles

- **Villager**: Regular player whose goal is to identify and eliminate werewolves
- **Werewolf**: Must pretend to be a villager while secretly eliminating one villager each night
- **Seer**: Special villager who can investigate one player each night to determine if they're a werewolf

### Phases

1. **Day Phase**:
   - All players discuss and share their suspicions
   - Players vote on who to eliminate
   - The player with the most votes is eliminated

2. **Night Phase**:
   - Werewolves choose a villager to eliminate
   - The Seer investigates one player to learn their role

### Win Conditions

- **Villagers win**: If all werewolves are eliminated
- **Werewolves win**: If werewolves equal or outnumber villagers

## Logs

The game generates logs in `werewolf_game.log`, showing all game events and player interactions.

## Customization

Edit `config.yaml` to create your own game configurations with different numbers of players and roles.

## Implementation Details

See `werewolf-langchain-guide.md` for detailed implementation specifications. 