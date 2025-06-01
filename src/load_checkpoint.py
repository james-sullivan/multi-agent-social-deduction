#!/usr/bin/env python3
"""
Load a Blood on the Clocktower game from a checkpoint in the log file
"""

import argparse
import os
import sys
import json
from pathlib import Path
import logging
from datetime import datetime
from dotenv import load_dotenv

# Ensure project root is on Python path so 'src' module can be imported
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables from .env at project root
load_dotenv(os.path.join(project_root, '.env'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_log_files():
    """Find all available log files with checkpoints"""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return []
    
    # Get all log files
    log_files = list(logs_dir.glob("*.jsonl"))
    
    # Check each log file for checkpoint events
    log_info = []
    for log_file in log_files:
        try:
            with open(log_file, 'r') as f:
                checkpoint_count = 0
                latest_checkpoint = None
                latest_game_state = None
                
                # Read the file line by line
                for line in f:
                    try:
                        event = json.loads(line)
                        # Track the latest game state for any file
                        if "game_state" in event and "player_state" in event["game_state"]:
                            latest_game_state = event["game_state"]
                            
                        # Count checkpoint events
                        if event.get("event_type") == "checkpoint" and "metadata" in event and "save_game" in event["metadata"]:
                            checkpoint_count += 1
                            latest_checkpoint = event
                    except json.JSONDecodeError:
                        continue
                
                # Only include files with checkpoints
                if checkpoint_count > 0 and latest_checkpoint and latest_game_state:
                    # Get information about the latest game state
                    round_num = latest_game_state.get("round_number", "?")
                    phase = latest_game_state.get("current_phase", "?")
                    players_alive = sum(1 for p in latest_game_state.get("player_state", []) if p.get("alive", False))
                    players_total = len(latest_game_state.get("player_state", []))
                    
                    # Get timestamp from latest checkpoint
                    timestamp = latest_checkpoint["metadata"].get("timestamp", 
                                datetime.fromtimestamp(log_file.stat().st_mtime).isoformat())
                    
                    log_info.append({
                        "path": str(log_file),
                        "round": round_num,
                        "phase": phase,
                        "players": f"{players_alive}/{players_total}",
                        "checkpoints": checkpoint_count,
                        "timestamp": timestamp,
                        "mtime": log_file.stat().st_mtime
                    })
        except Exception as e:
            logger.warning(f"Error processing log file {log_file}: {e}")
    
    # Sort by modification time (newest first)
    log_info.sort(key=lambda x: x["mtime"], reverse=True)
    return log_info

def list_checkpoints_in_log(log_path):
    """List all checkpoints in a specific log file"""
    try:
        with open(log_path, 'r') as f:
            checkpoints = []
            line_num = 0
            
            # Read the file line by line
            for line in f:
                line_num += 1
                try:
                    event = json.loads(line)
                    if event.get("event_type") == "checkpoint" and "metadata" in event:
                        metadata = event["metadata"]
                        round_num = metadata.get("round", "?")
                        phase = metadata.get("checkpoint_type", metadata.get("phase", "?"))
                        timestamp = metadata.get("timestamp", "?")
                        
                        checkpoints.append({
                            "index": len(checkpoints),
                            "line": line_num,
                            "round": round_num,
                            "phase": phase,
                            "timestamp": timestamp
                        })
                except json.JSONDecodeError:
                    continue
            
            return checkpoints
    except Exception as e:
        logger.error(f"Error reading log file {log_path}: {e}")
        return []

def list_logs():
    """List all available log files with checkpoints"""
    logs = find_log_files()
    
    if not logs:
        print("No log files with checkpoints found")
        return
    
    print("\nAvailable log files with checkpoints:")
    for i, log in enumerate(logs, 1):
        print(f"{i}. {Path(log['path']).name}")
        print(f"   Round {log['round']}, {log['phase']} phase - {log['timestamp']}")
        print(f"   Players alive: {log['players']}, Checkpoints: {log['checkpoints']}")
        print(f"   Path: {log['path']}")
    
    print("\nTo list checkpoints in a log file, use: python load_checkpoint.py --log <log_path>")
    print("To load a checkpoint, use: python load_checkpoint.py --log <log_path> [--checkpoint <index>]")

def list_checkpoints(log_path):
    """List all checkpoints in a log file"""
    checkpoints = list_checkpoints_in_log(log_path)
    
    if not checkpoints:
        print(f"No checkpoints found in log file: {log_path}")
        return
    
    print(f"\nCheckpoints in {Path(log_path).name}:")
    for cp in checkpoints:
        print(f"{cp['index']}. Round {cp['round']}, {cp['phase']} phase - {cp['timestamp']}")
        print(f"   (Line {cp['line']})")
    
    print("\nTo load a checkpoint, use: python load_checkpoint.py --log <log_path> --checkpoint <index>")

def load_checkpoint(log_path, checkpoint_index=None):
    """Load a game from a checkpoint in a log file"""
    from src.game import Game
    
    if not os.path.exists(log_path):
        print(f"Error: Log file {log_path} does not exist")
        sys.exit(1)
    
    # If no checkpoint index specified, list checkpoints and exit
    if checkpoint_index is None:
        list_checkpoints(log_path)
        return
    
    print(f"Loading game from checkpoint {checkpoint_index} in log file: {log_path}")
    game = Game.load_from_checkpoint(log_path, int(checkpoint_index))
    
    # Copy previous events up to the checkpoint into the new log file
    checkpoints = list_checkpoints_in_log(log_path)
    target_cp = next((cp for cp in checkpoints if cp['index'] == checkpoint_index), None)
    if target_cp:
        cp_line = target_cp['line']
        new_log_path = game.event_tracker._log_file_path
        # Append old events up to checkpoint to the new log file
        with open(new_log_path, 'a', encoding='utf-8') as new_log, open(log_path, 'r', encoding='utf-8') as old_log:
            for idx, line in enumerate(old_log, start=1):
                if idx > cp_line:
                    break
                new_log.write(line)

    if game is None:
        print("Failed to load game from checkpoint")
        sys.exit(1)
    
    # Display game info
    print(f"\nGame loaded successfully")
    print(f"Round: {game._round_number}, Phase: {game._current_phase.value}")
    print(f"Players alive: {sum(1 for p in game._players if p.alive)}/{len(game._players)}")
    
    # Print player status
    print("\nPlayer status:")
    for player in game._players:
        status = "Alive" if player.alive else "Dead"
        print(f"- {player.name}: {player.character.value} ({status})")
    
    # Run the game
    print("\nResuming game...")
    try:
        winner = game.run_game()
        print(f"\nGame ended with winner: {winner}")
    except Exception as e:
        print(f"Error during game: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if hasattr(game, 'event_tracker'):
            game.event_tracker.close()

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Load a Blood on the Clocktower game from a checkpoint in a log file')
    parser.add_argument('--log', help='Path to the log file containing checkpoints')
    parser.add_argument('--checkpoint', type=int, help='Index of the checkpoint to load')
    parser.add_argument('--list', action='store_true', help='List all available log files with checkpoints')
    
    args = parser.parse_args()
    
    if args.list or (not args.log and not args.checkpoint):
        list_logs()
    elif args.log and not args.checkpoint:
        list_checkpoints(args.log)
    elif args.log and args.checkpoint is not None:
        load_checkpoint(args.log, args.checkpoint)
    else:
        parser.print_help()

if __name__ == '__main__':
    main() 