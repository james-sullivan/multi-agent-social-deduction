from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import random
import logging

from agent import Agent, Role

logger = logging.getLogger(__name__)

class Phase(Enum):
    NIGHT = "night"
    DAY = "day"

class GameState:
    def __init__(self, players: Dict[str, Agent]):
        self.players = players
        self.alive_players = list(players.keys())
        self.phase = Phase.DAY
        self.day_count = 0
        self.night_count = 0
        self.eliminations: List[str] = []
        self.history: List[str] = []
        self.game_over = False
        self.winner: Optional[str] = None
        
    def get_alive_players(self) -> List[str]:
        return self.alive_players
    
    def get_alive_werewolves(self) -> List[str]:
        return [name for name in self.alive_players 
                if self.players[name].role == Role.WEREWOLF]
    
    def get_alive_villagers(self) -> List[str]:
        return [name for name in self.alive_players 
                if self.players[name].role != Role.WEREWOLF]
    
    def eliminate_player(self, player_name: str) -> None:
        if player_name in self.alive_players:
            self.alive_players.remove(player_name)
            self.eliminations.append(player_name)
            role = self.players[player_name].role
            logger.info(f"{player_name} ({role.name}) has been eliminated")
            
    def check_win_condition(self) -> bool:
        werewolves = self.get_alive_werewolves()
        villagers = self.get_alive_villagers()
        
        if not werewolves:
            self.game_over = True
            self.winner = "Villagers"
            return True
        
        if len(werewolves) >= len(villagers):
            self.game_over = True
            self.winner = "Werewolves"
            return True
            
        return False
    
    def record_event(self, event: str) -> None:
        self.history.append(event)
        logger.info(event)

class Game:
    def __init__(self, players: Dict[str, Agent]):
        self.state = GameState(players)
        self.players = players
        
    def setup_game(self) -> None:
        # Inform werewolves about each other
        werewolves = [name for name, agent in self.players.items() 
                      if agent.role == Role.WEREWOLF]
        
        for wolf_name in werewolves:
            self.players[wolf_name].set_known_werewolves(werewolves)
            
        # Record initial game state - without revealing roles to agents in game history
        player_names = ", ".join(list(self.players.keys()))
        self.state.record_event(f"Game started with players: {player_names}")
        
        # Log complete role information for admin/debugging (but don't add to game history)
        roles_info = ", ".join([f"{name}: {agent.role.name}" 
                              for name, agent in self.players.items()])
        logger.info(f"Game roles: {roles_info}")
    
    def print_status_summary(self) -> None:
        """Print a summary of each character's role and status"""
        summary = "\n" + "=" * 50
        summary += "\n               CHARACTER STATUS SUMMARY"
        summary += "\n" + "=" * 50
        summary += "\nName        | Role       | Status"
        summary += "\n" + "-" * 40
        
        # Sort by role first, then by alive status, then by name
        # Villagers first, then Seers, then Werewolves
        def sort_key(item):
            name, agent = item
            # Priority by role (1=Villager, 2=Seer, 3=Werewolf)
            role_priority = {
                Role.VILLAGER: 1,
                Role.SEER: 2,
                Role.WEREWOLF: 3
            }
            is_dead = name not in self.state.alive_players
            return (role_priority[agent.role], is_dead, name)
        
        sorted_players = sorted(self.players.items(), key=sort_key)
        
        for name, agent in sorted_players:
            status = "ALIVE" if name in self.state.alive_players else "DEAD"
            # Format with consistent spacing
            summary += f"\n{name:<12}| {agent.role.name:<10} | {status}"
        
        summary += "\n" + "=" * 50
        
        # Print directly to console with color formatting
        # but don't also log it (which would cause duplicate output)
        print(f"\033[1;36m{summary}\033[0m")  # Cyan, bold text for better visibility
        
        # Add summary to game history without logging to console
        self.state.history.append(f"CHARACTER STATUS SUMMARY: {len(self.state.alive_players)} alive, {len(self.players) - len(self.state.alive_players)} dead")
    
    def run_night_phase(self) -> None:
        self.state.phase = Phase.NIGHT
        self.state.night_count += 1
        self.state.record_event(f"Night {self.state.night_count} has begun")
        
        # Print night phase header to console
        print(f"\n\033[1;35m=== NIGHT {self.state.night_count} ===\033[0m\n")
        
        # Werewolves choose a victim
        werewolves = self.state.get_alive_werewolves()
        if not werewolves:
            return
            
        # Get werewolf votes
        votes: Dict[str, int] = {}
        werewolf_votes: Dict[str, str] = {}  # Track which werewolf voted for whom
        
        for wolf_name in werewolves:
            wolf = self.players[wolf_name]
            vote = wolf.night_action(self.state.get_alive_players(), 
                                    self.state.get_alive_werewolves())
            if vote and vote in self.state.get_alive_players() and vote not in werewolves:
                votes[vote] = votes.get(vote, 0) + 1
                werewolf_votes[wolf_name] = vote
                
                # Log and print each werewolf's vote
                self.state.record_event(f"Werewolf {wolf_name} voted to eliminate {vote}")
                print(f"\033[1;31mWerewolf {wolf_name} voted to eliminate {vote}\033[0m")
        
        # Determine victim
        victim: Optional[str] = None
        max_votes = 0
        for player_name, vote_count in votes.items():
            if vote_count > max_votes:
                max_votes = vote_count
                victim = player_name
                
        if victim:
            self.state.record_event(f"Werewolves chose to eliminate {victim}")
            self.state.eliminate_player(victim)
            
            # Print werewolf attack to console
            print(f"\033[1;31mThe werewolves attacked and eliminated {victim}!\033[0m\n")
        
        # Seer investigates a player
        for player_name in self.state.get_alive_players():
            player = self.players[player_name]
            if player.role == Role.SEER:
                target = player.night_action(
                    self.state.get_alive_players(), 
                    self.state.get_alive_werewolves()
                )
                if target in self.state.get_alive_players():
                    is_werewolf = self.players[target].role == Role.WEREWOLF
                    player.receive_investigation_result(target, is_werewolf)
                    self.state.record_event(f"Seer investigated {target}")
                    
                    # Print seer investigation to console (only visible to us as observers)
                    result = "ARE" if is_werewolf else "are NOT"
                    print(f"\033[1;34mThe Seer investigated {target} and discovered they {result} a werewolf.\033[0m\n")
        
        # Print status summary at the end of the phase
        self.print_status_summary()
    
    def run_day_phase(self) -> None:
        self.state.phase = Phase.DAY
        self.state.day_count += 1
        self.state.record_event(f"Day {self.state.day_count} has begun")
        
        # Print day phase header to console
        print(f"\n\033[1;32m=== DAY {self.state.day_count} ===\033[0m\n")
        
        # Inform players about the night's events
        for player_name in self.state.get_alive_players():
            player = self.players[player_name]
            player.update_game_state(self.state)
        
        # Discussion phase
        discussion: List[Tuple[str, str]] = []
        for player_name in self.state.get_alive_players():
            player = self.players[player_name]
            message = player.discuss(discussion)
            if message:
                discussion.append((player_name, message))
                # Add a newline after the message for better readability
                self.state.record_event(f"{player_name} says: {message}\n")
                
                # Also print directly to console with a better format
                print(f"\n\033[1m{player_name}:\033[0m {message}\n")
        
        # Voting phase
        votes: Dict[str, int] = {}
        for player_name in self.state.get_alive_players():
            player = self.players[player_name]
            vote = player.vote(self.state.get_alive_players(), discussion)
            if vote and vote in self.state.get_alive_players():
                votes[vote] = votes.get(vote, 0) + 1
                self.state.record_event(f"{player_name} voted for {vote}")
                
                # Also print the vote directly to console
                print(f"\033[1;33m{player_name} voted for {vote}\033[0m")
        
        # Determine elimination
        if not votes:
            self.state.record_event("No valid votes were cast")
            return
            
        max_votes = 0
        eliminated: Optional[str] = None
        for player_name, vote_count in votes.items():
            if vote_count > max_votes:
                max_votes = vote_count
                eliminated = player_name
            elif vote_count == max_votes:
                # In case of a tie, randomly select
                if random.random() > 0.5:
                    eliminated = player_name
        
        if eliminated:
            self.state.record_event(f"{eliminated} was voted out")
            self.state.eliminate_player(eliminated)
            
            # Print elimination result with emphasis
            print(f"\n\033[1;31m{eliminated} was voted out and eliminated!\033[0m\n")
        
        # Print status summary at the end of the phase
        self.print_status_summary()
    
    def run_game(self, max_days=10) -> str:
        self.setup_game()
        
        # Print initial status summary
        logger.info("Initial game state:")
        self.print_status_summary()
        
        while not self.state.game_over and self.state.day_count < max_days:
            self.run_day_phase()
            
            if self.state.check_win_condition():
                break
                
            self.run_night_phase()
            
            if self.state.check_win_condition():
                break
        
        if self.state.winner:
            result = f"Game over! {self.state.winner} win!"
            # Print game over message with emphasis
            print(f"\n\033[1;31m{result}\033[0m\n")
        else:
            result = "Game ended with no clear winner after maximum days"
            print(f"\n\033[1;33m{result}\033[0m\n")
        
        self.state.record_event(result)
        
        # Remove final status summary - we don't need it
        # logger.info("Final game state:")
        # self.print_status_summary()
        
        return result 