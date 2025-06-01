#!/usr/bin/env python3
"""
Load a Blood on the Clocktower game from a checkpoint in a log file
"""

import argparse
import json
import os
import sys
from pathlib import Path

def list_checkpoints(log_path):
    """List all checkpoints in a log file"""
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
            
            # Print the checkpoints
            if checkpoints:
                print(f"\nFound {len(checkpoints)} checkpoints in {log_path}:")
                for cp in checkpoints:
                    print(f"{cp['index']}. Round {cp['round']}, {cp['phase']} phase - {cp['timestamp']}")
                
                print("\nTo load a checkpoint, use: python load_checkpoint.py <log_path> <checkpoint_index>")
            else:
                print(f"No checkpoints found in {log_path}")
                
            return checkpoints
    except Exception as e:
        print(f"Error reading log file {log_path}: {e}")
        return []

def load_checkpoint(log_path, checkpoint_index):
    """Load a game from a checkpoint in a log file"""
    if not os.path.exists(log_path):
        print(f"Error: Log file {log_path} does not exist")
        sys.exit(1)
    
    print(f"Loading game from checkpoint {checkpoint_index} in log file: {log_path}")
    
    # Add proper import paths
    import sys
    sys.path.append('.')
    
    from src.game import Game
    game = Game.load_from_checkpoint(log_path, int(checkpoint_index))
    
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
    
    # Ask if user wants to resume the game
    resume = input("\nResume game from this checkpoint? (y/n): ")
    if resume.lower() == 'y':
        print("\nResuming game...")
        try:
            winner = game.run_game()
            print(f"\nGame ended with winner: {winner.value if winner else 'None'}")
        except Exception as e:
            print(f"Error during game: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if hasattr(game, 'event_tracker'):
                game.event_tracker.close()
    else:
        print("Game not resumed.")

def main():
    parser = argparse.ArgumentParser(description='Load a Blood on the Clocktower game from a checkpoint')
    parser.add_argument('log_path', nargs='?', help='Path to the log file containing checkpoints')
    parser.add_argument('checkpoint_index', nargs='?', type=int, help='Index of the checkpoint to load')
    
    args = parser.parse_args()
    
    if not args.log_path:
        # List log files in the logs directory
        logs_dir = Path("logs")
        if logs_dir.exists():
            log_files = list(logs_dir.glob("*.log")) + list(logs_dir.glob("*.jsonl"))
            if log_files:
                print(f"\nFound {len(log_files)} log files:")
                for i, log_file in enumerate(sorted(log_files)):
                    print(f"{i}. {log_file}")
                print("\nTo list checkpoints in a log file, use: python load_checkpoint.py <log_path>")
            else:
                print("No log files found in the logs directory")
        else:
            print("Logs directory not found")
        return
    
    if args.log_path and not args.checkpoint_index:
        list_checkpoints(args.log_path)
    elif args.log_path and args.checkpoint_index is not None:
        load_checkpoint(args.log_path, args.checkpoint_index)
    else:
        parser.print_help()

if __name__ == '__main__':
    main() 