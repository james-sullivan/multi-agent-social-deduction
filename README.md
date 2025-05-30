# Multi-Agent Social Deduction

A Python implementation of **Blood on the Clocktower** featuring AI agents powered by Anthropic's Claude models. Watch AI players engage in strategic social deduction gameplay, complete with bluffing, deduction, and complex role interactions.

## Overview

This project simulates Blood on the Clocktower games where AI agents take on different character roles, make strategic decisions, and attempt to deduce each other's identities through social interaction and logical reasoning. Each AI player has access to character-specific abilities and information, creating emergent gameplay patterns.

### Features

- **Multi-Agent AI Gameplay**: AI players with distinct personalities and strategies
- **Complete Role Implementation**: Full suite of Blood on the Clocktower characters including Townsfolk, Outsiders, Minions, and Demons
- **Strategic Decision Making**: AI agents use reasoning, bluffing, and social deduction
- **Game Visualization**: React-based web interface for viewing game progression
- **Detailed Logging**: Comprehensive game logs with cost tracking for API usage
- **Configurable Games**: Customizable player counts and character distributions

## Project Structure

```
├── src/                    # Main Python game engine
│   ├── main.py            # Entry point and game orchestration
│   ├── game.py            # Core game logic and state management
│   ├── player.py          # AI player implementation
│   ├── characters.py      # Character roles and abilities
│   ├── game_events.py     # Event tracking and game state changes
│   ├── inference.py       # Claude API integration and cost tracking
│   └── prompts.py         # Character-specific prompts for AI agents
├── botc-visualizer/       # React web app for game visualization
├── config.yaml           # Game configuration settings
└── requirements.txt       # Python dependencies
```

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+ (for the visualizer)
- Anthropic API key

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd multi-agent-social-deduction
   ```

2. **Set up Python environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your Anthropic API key:
   # ANTHROPIC_API_KEY=your_api_key_here
   ```

4. **Set up the visualizer (optional):**
   ```bash
   cd botc-visualizer
   npm install
   npm start
   ```

## Usage

### Running a Game

Run a basic 5-player game with default settings:

```bash
source venv/bin/activate && python src/main.py
```

#### Command Line Options

- `--debug` or `-d`: Enable verbose logging including HTTP request details
- `--config` or `-c`: Specify configuration name (for future use)

Examples:
```bash
# Run with debug logging
source venv/bin/activate && python src/main.py --debug

# Specify configuration
source venv/bin/activate && python src/main.py --config custom
```

### Game Output

The game will:
1. Set up characters and assign roles to AI players
2. Run through day/night phases with AI interactions
3. Track voting, nominations, and character abilities
4. Display final results with cost breakdown
5. Generate detailed logs in `blood_on_the_clocktower.log`

### Cost Tracking

The game automatically tracks Anthropic API usage:
- Total tokens used (input/output)
- Cost breakdown by model
- Cache usage and savings
- Per-game cost summary

## Game Mechanics

### Supported Characters

**Townsfolk**: Washerwoman, Librarian, Investigator, Chef, Empath, Fortuneteller, Undertaker, Monk, Ravenkeeper, Virgin, Slayer, Soldier, Mayor

**Outsiders**: Butler, Saint, Recluse, Drunk

**Minions**: Poisoner, Spy, Baron, Scarlet Woman

**Demons**: Imp

### AI Behavior

Each AI player:
- Receives character-specific prompts and abilities
- Makes strategic decisions based on available information
- Engages in social deduction and bluffing
- Adapts strategies based on game state
- Uses logical reasoning to identify opponents

## Development

### Adding New Characters

1. Add the character to the appropriate enum in `characters.py`
2. Implement character-specific logic in `game.py`
3. Create character prompts in `prompts.py`
4. Add any special abilities or interactions

### Extending AI Behavior

- Modify prompts in `prompts.py` for different AI personalities
- Adjust reasoning strategies in `player.py`
- Add new action types in `game_events.py`

### Configuration

Edit `config.yaml` to customize:
- Player counts
- Character distributions
- Game variants
- AI model settings

## Logging

Games generate comprehensive logs including:
- Player decisions and reasoning
- Character ability activations
- Voting patterns and nominations
- Game state changes
- API cost tracking

Logs are saved to `blood_on_the_clocktower.log` and `logs/` directory.

