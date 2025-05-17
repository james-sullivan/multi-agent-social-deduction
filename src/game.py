from enum import Enum
import random
import logging
from dataclasses import dataclass

from src.agent_old import Role
from src.player import DayAction, MessageAction, NominationAction, SlayerPowerAction, NoAction, Player
from src.characters import Character, Townsfolk, Outsider, Demon, Minion
from src.utils import format_vote_history

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
        self.round_number: int = 1
        self.current_phase: Phase = Phase.NIGHT
        self.drunk_and_poisoned: dict[Player, list[Player]] = {}
        self.chopping_block: tuple[int, Player] | None = None
        self.nominations_open: bool = False

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
    
    def _kill_player(self, player: Player, broadcast: bool = True) -> tuple[list[Player], str]:
        player.is_alive = False
        self._scarlet_woman_check(player)
        message = f"Storyteller: {player.name} has been died."
        if broadcast:
            self._broadcast_info(self._all_players(), message)
        return self._all_players(), message

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
            self._kill_player(self.player_dict[action.target])
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and killed them.")
        # If it doesn't work
        else:
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and nothing happened.")

        return it_works
    
    def _send_message(self, from_player: Player, recipients: list[str], message: str) -> None:
        recipient_str = ", ".join([name for name in recipients])
        self._broadcast_info(recipients, f"Message from {from_player.name} to {recipient_str}: {message}")

    def _run_nomination(self, player: Player, action: NominationAction) -> None:
        nominee = self.player_dict[action.nominee]
        if player.used_nomination or nominee.nominated_today:
            return
        
        nominee.nominated_today = True
        player.used_nomination = True

        self._broadcast_info(self._all_players(), f"{player.name} has nominated {nominee.name} for execution. Their reason is: {action.reason}")

        if self.chopping_block:
            prev_count, _ = self.chopping_block
            required_to_tie = prev_count
            required_to_nominate = prev_count + 1
        else:
            living_count = sum(1 for player in self.players if player.is_alive)
            required_to_nominate = living_count // 2 if living_count % 2 == 0 else living_count // 2 + 1
            required_to_tie = None

        count = 0
        previous_votes: list[tuple[str, Vote]] = []
        for player in self.players:
            if player.is_alive:
                vote = player.vote(
                    nominee=nominee.name,
                    public_game_state=self._get_public_game_state(),
                    current_tally=count,
                    required_to_tie=required_to_tie,
                    required_to_nominate=required_to_nominate,
                    previous_votes=previous_votes
                )
                previous_votes.append((player.name, vote))
                if vote == Vote.YES:
                    count += 1

        if count >= required_to_nominate:
            self.chopping_block = (count, nominee)
            self._broadcast_info(self._all_players(), f"Storyteller: {nominee.name} has been nominated for execution with {count} votes. They will die at the end of the day if no one else is nominated. Vote record: {format_vote_history(previous_votes)}")
        elif required_to_tie is not None and count == required_to_tie:
            self.chopping_block = None
            self._broadcast_info(self._all_players(), f"Storyteller: {nominee.name} has received {count} votes. This ties the previous nominee. The chopping block is now empty. Vote record: {format_vote_history(previous_votes)}")


    def _run_day_phase(self) -> Alignment | None:
        self.current_phase = Phase.DAY
        for player in self.players:
            player.start_of_day()

        loops = 3
        for i in range(loops):
            if i == loops - 1:
                self.nominations_open = True
                self._broadcast_info(self._all_players(), "Storyteller: Nominations are now open.")
        
            day_players: list[Player] = list(self.players)
            random.shuffle(day_players)

            for player in day_players:
                action: DayAction = player.day_action(self._get_public_game_state(), self.nominations_open)

                if isinstance(action, MessageAction):
                    self._send_message(player, action.recipients, action.message)
                elif isinstance(action, NominationAction):
                    self._run_nomination(player, action)
                elif isinstance(action, SlayerPowerAction):
                    if self._slayer_power(action):
                        game_over, alignment = self._game_over()
                        if game_over:
                            return alignment
                elif isinstance(action, NoAction):
                    pass

    def _game_over(self) -> Alignment | None:
        alive_count = sum(player.is_alive for player in self.players)
        alive_demons = sum(player.role == Role.DEMON for player in self.players)
        
        if alive_demons == 0:
            return Alignment.GOOD
        
        if alive_count <= 2:
            return Alignment.EVIL
        
        return None
    
    def run_game(self, max_rounds=6) -> Alignment | None:
        logger.info("Initial game state:")
        self._print_status_summary()
        
        while self.round_number <= max_rounds:
            self._run_night_phase()

            game_over = self._game_over()
            if game_over:
                return game_over
            
            game_over = self._run_day_phase()
            if game_over:
                return game_over

            game_over = self._game_over()
            if game_over:
                return game_over

            self.round_number += 1
               
        return None