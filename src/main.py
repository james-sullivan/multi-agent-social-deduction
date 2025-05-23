import os
import logging
import random
import argparse
from dotenv import load_dotenv
import http.client as http_client

from scripts import Script, TROUBLE_BREWING
from game import Game
from game_enums import Alignment
from game_events import EventType

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Create logger
logger = logging.getLogger(__name__)

def configure_logging(debug=False):
    """Configure logging based on debug flag"""
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Configure root logger to write only to file, not to console
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("blood_on_the_clocktower.log")
        ]
    )
    
    # Set up HTTP-related logging
    if debug:
        # Enable HTTP connection debugging
        http_client.HTTPConnection.debuglevel = 1
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
        
        # Keep httpx logs visible in debug mode
        logger.debug("Debug mode enabled - HTTP requests will be logged")
    else:
        # Disable HTTP connection debugging
        http_client.HTTPConnection.debuglevel = 0
        
        # Silence httpx logs by setting its level to WARNING (suppresses INFO messages)
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.setLevel(logging.WARNING)
        
        # Also silence urllib3 logs that might be used by requests
        urllib3_logger = logging.getLogger("urllib3")
        urllib3_logger.setLevel(logging.WARNING)

def load_config(config_name="default"):
    """Load simple game configuration"""
    # For the simple 5-player game, we just need basic settings
    return {
        "max_rounds": 6,
        "random_seed": 42  # Fixed seed for consistent games
    }

def create_game(config, debug=False):
    """Create a simple 5-player Blood on the Clocktower game with hardcoded characters"""
    
    # Import character types
    from characters import Townsfolk, Minion, Demon
    
    # Define the 5 characters for our simple game
    characters = [
        Demon.IMP,           # The evil demon who kills at night
        Minion.POISONER,     # Can poison players to disable their abilities
        Townsfolk.MAYOR,     # Can win if 3 players remain with no execution
        Townsfolk.EMPATH,    # Learns how many evil neighbors they have
        Townsfolk.SLAYER,    # Can attempt to slay the demon during the day
    ]
    
    print("🎭 Starting a Simple 5-Player Blood on the Clocktower Game!")
    print("=" * 60)
    print("Characters in play:")
    print("- 👹 Imp (Demon): Kills each night")
    print("- 🧪 Poisoner (Minion): Poisons abilities")
    print("- 🏛️  Mayor (Townsfolk): Wins with 3 players + no execution")
    print("- 💝 Empath (Townsfolk): Senses evil neighbors")
    print("- ⚔️  Slayer (Townsfolk): Can attempt to kill the demon")
    print("=" * 60)
    
    # Create game with hardcoded characters
    game = Game(
        script=TROUBLE_BREWING,
        characters=characters,
        random_seed=config.get("random_seed", 42)  # Use config seed or default to 42
    )
    
    logger.info("Created simple 5-player game")
    logger.info("Characters: Imp, Poisoner, Mayor, Empath, Slayer")
    
    return game

def run_game(config_name="default", debug=False):
    """Initialize and run a Blood on the Clocktower game"""
    logger.info(f"Initializing new Blood on the Clocktower game with config: {config_name}")
    
    # Load configuration
    config = load_config(config_name)
    
    # Create game
    game = create_game(config, debug=debug)
    
    # Run the game
    max_rounds = config.get("max_rounds", 6)
    result = game.run_game(max_rounds)
    
    if result == Alignment.GOOD:
        result_str = "Good team wins!"
    elif result == Alignment.EVIL:
        result_str = "Evil team wins!"
    else:
        result_str = "Game ended in a draw or reached maximum rounds."
    
    # Track game end event
    game.event_tracker.add_event(
        event_type=EventType.GAME_END,
        description=result_str,
        round_number=game._round_number,
        phase=game._current_phase.value,
        metadata={"result": result.value if result else "Max Rounds"}
    )
    
    logger.info(f"Game completed: {result_str}")
    
    # Save events to JSON file
    try:
        game.event_tracker.save_to_json()
        print("\n🎯 Game Summary:")
        stats = game.event_tracker.get_game_statistics()
        print(f"   • Total rounds: {stats['total_rounds']}")
        print(f"   • Total events: {stats['total_events']}")
        print(f"   • Deaths: {len(stats['deaths'])} players")
        print(f"   • Executions: {len(stats['executions'])} players")
        print(f"   • Nominations: {len(stats['nominations'])}")
    except Exception as e:
        logger.error(f"Failed to save game events: {e}")
        print(f"⚠️  Warning: Could not save game log - {e}")
    
    return result_str

if __name__ == "__main__":
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Run a simple 5-player Blood on the Clocktower game")
    parser.add_argument("--config", "-c", default="default",
                        help="Configuration name (not used, kept for compatibility)")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Enable debug mode with verbose logging including HTTP statuses")
    args = parser.parse_args()
    
    # Configure logging based on debug flag
    configure_logging(args.debug)
    
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("No Anthropic API key found. Please set ANTHROPIC_API_KEY environment variable.")
        print("ERROR: No Anthropic API key found. Please set ANTHROPIC_API_KEY environment variable.")
        exit(1)
    
    # Run the game with specified configuration
    result = run_game(args.config, debug=args.debug)
    print(result) 