#!/usr/bin/env python3

import sys
sys.path.append('.')
from src.game import Game
from src.scripts import Script
from src.characters import Townsfolk, Outsider, Minion, Demon

# Get the script from the module
from src.scripts import TROUBLE_BREWING

# Create a simple test game
characters = [
    Townsfolk.WASHERWOMAN,
    Townsfolk.LIBRARIAN,
    Townsfolk.INVESTIGATOR,
    Minion.POISONER, 
    Demon.IMP
]

# Create the game with the script
game = Game(
    script=TROUBLE_BREWING, 
    characters=characters, 
    townsfolk_count=3,  # 3 townsfolk characters
    outsider_count=0,   # 0 outsider characters
    minion_count=1,     # 1 minion character
    random_seed=42
)

# Save a checkpoint
game._save_checkpoint('test')
print('Checkpoint saved successfully!')

# Get the log file path
log_file_path = str(game.event_tracker._log_file_path)
print(f'Log file: {log_file_path}')

# Now try to load the checkpoint
print('\nTrying to load the checkpoint...')
loaded_game = Game.load_from_checkpoint(log_file_path)

if loaded_game:
    print(f'Game loaded successfully! Round: {loaded_game._round_number}, Phase: {loaded_game._current_phase.value}')
else:
    print('Failed to load game from checkpoint.') 