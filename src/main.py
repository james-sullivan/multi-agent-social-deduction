import os
import logging
import random
import yaml
import argparse
from dotenv import load_dotenv
import http.client as http_client

from src.agent_old import Agent, Role
from game import Game

# Load environment variables
load_dotenv()

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
            logging.FileHandler("werewolf_game.log")
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

def create_players(num_villagers=3, num_werewolves=2, has_seer=True, debug=False):
    """Create a set of players for the game"""
    players = {}
    
    # Generate player names
    name_options = ["Alex", "Blake", "Casey", "Dana", "Emerson", "Finley", 
                   "Gray", "Harper", "Indigo", "Jordan", "Kai", "Logan"]
    random.shuffle(name_options)
    
    # Assign roles
    total_players = num_villagers + num_werewolves + (1 if has_seer else 0)
    if total_players > len(name_options):
        raise ValueError(f"Too many players requested. Maximum is {len(name_options)}")
    
    # Assign werewolves
    for _ in range(num_werewolves):
        name = name_options.pop()
        players[name] = Agent(name, Role.WEREWOLF, debug=debug)
        logger.info(f"Created werewolf: {name}")
    
    # Assign seer if requested
    if has_seer:
        name = name_options.pop()
        players[name] = Agent(name, Role.SEER, debug=debug)
        logger.info(f"Created seer: {name}")
    
    # Assign villagers
    for i in range(num_villagers):
        name = name_options.pop()
        players[name] = Agent(name, Role.VILLAGER, debug=debug)
        logger.info(f"Created villager: {name}")
    
    return players

def load_config(config_name="default"):
    """Load game configuration from config.yaml"""
    try:
        with open("config.yaml", "r") as f:
            configs = yaml.safe_load(f)
        
        if config_name not in configs:
            logger.warning(f"Config '{config_name}' not found. Using default.")
            config_name = "default"
            
        return configs[config_name]
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        logger.info("Using fallback configuration")
        return {
            "num_villagers": 3,
            "num_werewolves": 2,
            "has_seer": True,
            "max_days": 10
        }

def run_game(config_name="default", debug=False):
    """Initialize and run a werewolf game"""
    logger.info(f"Initializing new Werewolf game with config: {config_name}")
    
    # Load configuration
    config = load_config(config_name)
    
    # Create players
    players = create_players(
        config["num_villagers"],
        config["num_werewolves"],
        config["has_seer"],
        debug=debug
    )
    
    # Initialize game
    game = Game(players)
    
    # Run the game
    result = game.run_game(config["max_days"])
    
    logger.info(f"Game completed: {result}")
    
    return result

if __name__ == "__main__":
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Run a Werewolf game simulation")
    parser.add_argument("--config", "-c", default="default",
                        help="Configuration preset from config.yaml")
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