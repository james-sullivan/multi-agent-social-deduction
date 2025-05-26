import os
import logging
import random
import argparse
from dotenv import load_dotenv
import http.client as http_client

# Import character types
from characters import Townsfolk, Minion, Demon, Outsider

from scripts import Script, TROUBLE_BREWING
from game import Game
from game_enums import Alignment
from game_events import EventType
from inference import reset_cost_tracker, get_cost_tracker

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
    
    characters = [
        Demon.IMP,
        Minion.POISONER,
        Townsfolk.SLAYER,
        Townsfolk.FORTUNETELLER,
        Townsfolk.UNDERTAKER,
        Outsider.DRUNK,
    ]
    
    # Create game with hardcoded characters
    game = Game(
        script=TROUBLE_BREWING,
        characters=characters,
        random_seed=config.get("random_seed", 42),  # Use config seed or default to 42
        model=config.get("model", "claude-3-5-haiku-20241022")  # Use config model or default
    )
    
    return game

def run_game(config_name="default", debug=False):
    """Initialize and run a Blood on the Clocktower game"""
    logger.info(f"Initializing new Blood on the Clocktower game with config: {config_name}")
    
    # Reset cost tracking for this game session
    reset_cost_tracker()
    
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
    
    logger.info(f"Game completed: {result_str}")
    
    # Print game summary
    try:
        # Get cost summary
        cost_tracker = get_cost_tracker()
        cost_summary = cost_tracker.get_summary()
        
        print("\n🎯 Game Summary:")
        stats = game.event_tracker.get_game_statistics()
        print(f"   • Total rounds: {stats['total_rounds']}")
        print(f"   • Total events: {stats['total_events']}")
        print(f"   • Deaths: {len(stats['deaths'])} players")
        print(f"   • Executions: {len(stats['executions'])} players")
        print(f"   • Nominations: {len(stats['nominations'])}")
        
        # Add cost information
        print(f"\n💰 API Cost Summary:")
        if cost_summary['cost_incomplete']:
            print(f"   ⚠️  Warning: Cost calculation incomplete (unknown models: {', '.join(cost_summary['unknown_models'])})")
        print(f"   • Total cost: ${cost_summary['total_cost_usd']:.4f}")
        print(f"   • API calls: {cost_summary['total_api_calls']}")
        print(f"   • Input tokens: {cost_summary['total_input_tokens']:,}")
        print(f"   • Output tokens: {cost_summary['total_output_tokens']:,}")
        print(f"   • Cache writes: {cost_summary['total_cache_creation_tokens']:,}")
        print(f"   • Cache reads: {cost_summary['total_cache_read_tokens']:,}")
        if cost_summary['total_cache_read_tokens'] > 0 or cost_summary['total_cache_creation_tokens'] > 0:
            savings = cost_summary['cache_savings_usd']
            print(f"   • Cache savings: ${savings:.4f}")
        
        # Show per-model breakdown if multiple models used
        if len(cost_summary['models_used']) > 1:
            print(f"   • Model breakdown:")
            for model, usage in cost_summary['models_used'].items():
                cost_str = f"${usage['cost_usd']:.4f}" if usage['pricing_available'] else "unknown cost"
                print(f"     - {model}: {cost_str} ({usage['calls']} calls)")
        elif len(cost_summary['models_used']) == 1:
            # Show single model details
            model, usage = list(cost_summary['models_used'].items())[0]
            if not usage['pricing_available']:
                print(f"   • Model: {model} (pricing unavailable)")
        
        print(f"\n{result_str}")
    except Exception as e:
        logger.error(f"Failed to generate game statistics: {e}")
        print(f"⚠️  Warning: Could not generate game summary - {e}")
        print(f"\n{result_str}")
    
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