from enum import Enum
import random
import logging
from dataclasses import dataclass

from src.agent_old import Role
from src.player import DayAction, MessageAction, NominationAction, SlayerPowerAction, NoAction, Player
from src.characters import Character, Townsfolk, Outsider, Demon, Minion
logger = logging.getLogger(__name__)

class Vote(Enum):
    YES = "Yes"
    NO = "No"
    CANT_VOTE = "Cant_Vote"

class Alignment(Enum):
    GOOD = "Good"
    EVIL = "Evil"

class Phase(Enum):
    NIGHT = "Night"
    DAY = "Day"

@dataclass
class PublicGameState:
    player_state: list[dict]
    current_phase: Phase
    round_number: int

class Game:
    def __init__(self, characters: list[Character], outsiders: int, townsfolk: int, minons: int):
        names = ["Susan", "John", "Emma", "Michael", "Olivia", "James", "Sophia", "William", "Ava", "Steve", "Emily", "Daniel", "Isabella", "David", "Mia"]
        random.shuffle(names)
        self.players: list[Player] = []

        if characters:
            for character in characters:
                self.players.append(Player(name=names[-1], role=character))
                names.pop()
        else:
            for _ in range(outsiders):
                self.players.append(Player(name=names[-1], role=Role.OUTSIDER))
                names.pop()

            for _ in range(townsfolk):
                self.players.append(Player(name=names[-1], role=Role.TOWNSFOLK))
                names.pop()

            for _ in range(minons):
                self.players.append(Player(name=names[-1], role=Role.MINION))
                names.pop()

        random.shuffle(self.players)
        self.player_dict: dict[str, Player] = {player.name: player for player in self.players}
        self.round_number = 1
        self.current_phase = Phase.NIGHT
        self.drunk_and_poisoned: dict[Player, list[Player]] = {}

    def _get_public_game_state(self) -> PublicGameState:
        """
        Returns the public game state that can be shared with all players.
        This includes information about all players without revealing their roles.
        """
        player_state = []
        
        for player in self.players:
            player_info = {
                "name": player.name,
                "alive": player.is_alive,
                "used_dead_vote": player.used_dead_vote if not player.is_alive else False,
            }
            
            player_state.append(player_info)
        
        return PublicGameState(
            player_state=player_state,
            current_phase=self.current_phase,
            round_number=self.round_number
        )

    def _scarlet_woman_check(self, dead_player: Player) -> bool:
        scarlet_woman = [player for player in self.players if player.is_alive and player.character == Minion.SCARLET_WOMAN and not self._is_drunk_or_poisoned(player)]

        if isinstance(dead_player.character, Demon) and len(scarlet_woman) == 1:
            woman = scarlet_woman[0]
            woman.character = dead_player.character
            self._broadcast_info([woman], f"Storyteller: The Demon has died and you have become the new Demon. Your chacter is now {woman.character.value}")
            return True
        return False
    
    def _kill_player(self, player: Player) -> None:
        player.is_alive = False
        self._scarlet_woman_check(player)
        self._broadcast_info(self._all_players(), f"Storyteller: {player.name} has been died.")

    def _print_status_summary(self) -> None:
        """Print a summary of each character's role and status"""
        summary = "\n" + "=" * 50
        summary += "\n               CHARACTER STATUS SUMMARY"
        summary += "\n" + "=" * 50
        summary += "\nName        | Role       | Status"
        summary += "\n" + "-" * 40
        
        # Sort alphabetically by name
        sorted_players = sorted(self.players)
        
        for player in sorted_players:
            status = "ALIVE" if player.is_alive else "DEAD"
            # Format with consistent spacing
            summary += f"\n{player.name:<12}| {player.role.name:<10} | {status}"
        
        summary += "\n" + "=" * 50
        
        # Print directly to console with color formatting
        # but don't also log it (which would cause duplicate output)
        print(f"\033[1;36m{summary}\033[0m")  # Cyan, bold text for better visibility

    def _all_players(self, exclude: list[Player] | None = None) -> list[Player]:
        return [player for player in self.players if player not in exclude]
    
    def _is_drunk_or_poisoned(self, player: Player, visited: set[Player] = None) -> bool:
        # Initialize visited set and check in one step
        if visited is None:
            visited = set()
             
        if player.character == Townsfolk.DRUNK:
            return True
        
        visited.add(player)
        
        for affecting_player in self.drunk_and_poisoned[player]:
            if affecting_player not in visited and affecting_player.is_alive and not self._is_drunk_or_poisoned(affecting_player, visited):
                return True
        
        return False
    
    def _broadcast_info(self, recipients: list[str | Player], info: str) -> None:    
        for recipient in recipients:
            if isinstance(recipient, Player):
                recipient.give_info(info)
            else:
                self.player_dict[recipient].give_info(info)
    
    def _run_night_phase(self) -> None:
        self.current_phase = Phase.NIGHT
    
    def _slayer_power(self, player: Player, action: SlayerPowerAction) -> bool:
        it_works: bool = (player.character == Townsfolk.SLAYER and 
                          not self._is_drunk_or_poisoned(player) and 
                          isinstance(self.player_dict[action.target].character, Demon))
        # If it works
        if it_works:
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and killed them.")
        # If it doesn't work
        else:
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and nothing happened.")

        return it_works

    def _run_day_phase(self) -> None:
        self.current_phase = Phase.DAY
        for player in self.players:
            player.start_of_day()
        
        day_players: list[Player] = list(self.players)
        random.shuffle(day_players)

        for _ in range(2):
            for player in day_players:
                action: DayAction = player.day_action()

                if isinstance(action, MessageAction):
                    self._broadcast_info(action.recipients, f"Message {player.name} to {action.recipients}: {action.message}")
                elif isinstance(action, NominationAction):
                    self._broadcast_info(self._all_players(), f"{player.name} has nominated {action.player} for execution.")
                elif isinstance(action, SlayerPowerAction):
                    self._slayer_power(action)
                elif isinstance(action, NoAction):
                    pass

    def _game_over(self) -> tuple[bool, Alignment | None]:
        alive_count = sum(player.is_alive for player in self.players)
        alive_demons = sum(player.role == Role.DEMON for player in self.players)
        
        if alive_demons == 0:
            return True, Alignment.GOOD
        
        if alive_count <= 2:
            return True, Alignment.EVIL
        
        return False, None
    
    def run_game(self, max_rounds=6) -> Alignment | None:
        logger.info("Initial game state:")
        self._print_status_summary()
        
        while self.round_number <= max_rounds:
            self._run_night_phase()

            game_over, alignment = self._game_over()
            if game_over:
                return alignment
            
            self._run_day_phase()

            game_over, alignment = self._game_over()
            if game_over:
                return alignment

            self.round_number += 1
               
        return None