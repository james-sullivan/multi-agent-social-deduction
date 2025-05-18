from enum import Enum
import random
import logging
from dataclasses import dataclass

from src.player import DayAction, MessageAction, NominationAction, SlayerPowerAction, NoAction, Player
from src.characters import Character, Townsfolk, Outsider, Demon, Minion
from src.utils import format_vote_history
from src.scripts import Script
from src.prompts import POISONER_PROMPT, FORTUNETELLER_PROMPT, MONK_PROMPT, RAVENKEEPER_PROMPT, IMP_PROMPT, BUTLER_PROMPT

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
    character_str: str
    player_state: list[dict]
    current_phase: Phase
    round_number: int

class Game:
    def __init__(self, 
                 script: Script, 
                 characters: list[Character] | None = None, 
                 outsider_count: int = 0, 
                 townsfolk_count: int = 0, 
                 minion_count: int = 0, 
                 random_seed: int | None = None):
        assert characters is not None or (sum([outsider_count, townsfolk_count, minion_count]) >= 5), \
        "Must provide at least 5 characters or specify counts for each role"

        names = ["Susan", "John", "Emma", "Michael", "Olivia", "James", "Sophia", "William", "Erick", \
                 "Steve", "Emily", "Daniel", "Jack", "David", "Mia"]
        outsiders = script.outsiders.copy()
        townsfolk = script.townsfolk.copy()
        minions = script.minions.copy()
        demons = script.demons.copy()

        if random_seed:
            random.seed(random_seed)

        random.shuffle(names)
        random.shuffle(outsiders)
        random.shuffle(townsfolk)
        random.shuffle(minions)
        random.shuffle(demons)
        
        self._players: list[Player] = []

        if characters:
            for character in characters:
                self._players.append(Player(name=names.pop(), character=character))
        else:
            for _ in range(outsider_count):
                self._players.append(Player(name=names.pop(), character=outsiders.pop()))

            for _ in range(townsfolk_count):
                self._players.append(Player(name=names.pop(), character=townsfolk.pop()))

            for _ in range(minion_count):
                self._players.append(Player(name=names.pop(), character=minions.pop()))

            self._players.append(Player(name=names.pop(), character=demons.pop()))

        random.shuffle(self._players)

        # Lookup players by name and character
        self._player_dict: dict[str, Player] = {player.name: player for player in self._players}
        self._character_dict: dict[Character, Player] = {player.character: player for player in self._players}

        self._round_number: int = 1
        self._current_phase: Phase = Phase.NIGHT
        self._drunk_and_poisoned: dict[Player, list[Player]] = {}
        self._chopping_block: tuple[int, Player] | None = None
        self._nominations_open: bool = False
        self._script: Script = script

    def _get_player_alignment(self, player: Player) -> Alignment:
        if player.character == Outsider.RECLUSE:
            return Alignment.EVIL
        elif player.character == Minion.SPY:
            return Alignment.GOOD
        
        return player.alignment
    
    def _get_player_roles(self, player: Player) -> set[Character]:
        if player.character == Minion.SPY:
            return {Townsfolk, Outsider}
        elif player.character == Outsider.RECLUSE:
            return {Minion, Demon}
        
        return {player.character}

    def _get_public_game_state(self) -> PublicGameState:
        """
        Returns the public game state that can be shared with all players.
        This includes information about all players without revealing their roles.
        """
        player_state = []
        
        for player in self._players:
            player_info = {
                "name": player.name,
                "alive": player.is_alive,
                "used_dead_vote": player.used_dead_vote if not player.is_alive else False,
            }
            
            player_state.append(player_info)
        
        return PublicGameState(
            character_str=self._script.character_str,
            player_state=player_state,
            current_phase=self._current_phase,
            round_number=self._round_number
        )

    def _scarlet_woman_check(self, dead_player: Player) -> bool:
        scarlet_woman = [player for player in self._players if player.is_alive and player.character == Minion.SCARLET_WOMAN and not self._is_drunk_or_poisoned(player)]

        if isinstance(dead_player.character, Demon) and len(scarlet_woman) == 1:
            woman = scarlet_woman[0]
            woman.character = dead_player.character
            self._broadcast_info(woman, f"Storyteller: The Demon has died and you have become the new Demon. Your chacter is now {woman.character.value}")
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
        sorted_players = sorted(self._players)
        
        for player in sorted_players:
            status = "ALIVE" if player.is_alive else "DEAD"
            # Format with consistent spacing
            summary += f"\n{player.name:<12}| {player.character.value:<10} | {status}"
        
        summary += "\n" + "=" * 50
        
        # Print directly to console with color formatting
        # but don't also log it (which would cause duplicate output)
        print(f"\033[1;36m{summary}\033[0m")  # Cyan, bold text for better visibility

    def _all_players(self, exclude: list[Player] | None = None) -> list[Player]:
        return [player for player in self._players if player not in exclude]
    
    def _is_drunk_or_poisoned(self, player: Player, visited: set[Player] | None = None) -> bool:
        if visited is None:
            visited = set()
             
        if player.character == Townsfolk.DRUNK:
            return True
        
        visited.add(player)
        
        for affecting_player in self._drunk_and_poisoned[player]:
            if affecting_player not in visited and affecting_player.is_alive and not self._is_drunk_or_poisoned(affecting_player, visited):
                return True
        
        return False
    
    def _broadcast_info(self, recipients: str | Player | list[str | Player], info: str) -> None:    
        if not isinstance(recipients, list):
            recipients = [recipients]

        info = f"Round: {self._round_number}, Phase: {self._current_phase.value}, {info}"
        for recipient in recipients:
            if isinstance(recipient, Player):
                recipient.give_info(info)
            else:
                self._player_dict[recipient].give_info(info)

    def _washerwoman_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), WASHERWOMAN_PROMPT)
        if self._is_drunk_or_poisoned(player):
            # If drunk/poisoned, give false info
            random_player = random.choice(self._players)
            random_townsfolk = random.choice([p for p in self._players if isinstance(p.character, Townsfolk)])
            self._broadcast_info(player, f"Storyteller: {random_player.name} is the {random_townsfolk.character.value}")
        else:
            # Find a random townsfolk player and tell the washerwoman about them
            townsfolk_players = [p for p in self._players if isinstance(p.character, Townsfolk)]
            if townsfolk_players:
                chosen_player = random.choice(townsfolk_players)
                self._broadcast_info(player, f"Storyteller: {chosen_player.name} is the {chosen_player.character.value}")
            else:
                self._broadcast_info(player, "Storyteller: There are no Townsfolk in the game")

    def _librarian_power(self, player: Player) -> None:
        pass

    def _investigator_power(self, player: Player) -> None:
        pass
    
    def _chef_power(self, player: Player) -> None:
        evil_pairs = 0
        for idx in range(len(self._players)):
            next_idx = (idx + 1) % len(self._players)
            if self._get_player_alignment(self._players[idx]) == Alignment.EVIL and self._get_player_alignment(self._players[next_idx]) == Alignment.EVIL:
                evil_pairs += 1

        if self._is_drunk_or_poisoned(player):
            evil_count = sum(1 for neighbor in self._players if neighbor.alignment == Alignment.EVIL)
            evil_pairs = (evil_pairs + 1) % (evil_count - 1)

        self._broadcast_info(player, f"Storyteller: There are {evil_pairs} adjacent pairs of evil players.")
    
    def _empath_power(self, player: Player) -> None:
        player_index = self._players.index(player)
        total_players = len(self._players)
        
        # Find first living neighbor in each direction
        def find_neighbor(start_idx: int, step: int) -> Player | None:
            idx = start_idx
            while idx != player_index:
                if self._players[idx].is_alive:
                    return self._players[idx]
                idx = (idx + step) % total_players
            return None
            
        left = find_neighbor((player_index - 1) % total_players, -1)
        right = find_neighbor((player_index + 1) % total_players, 1)
        assert left is not None and right is not None, "Empath should have two living neighbors"
        
        evil_count = sum(1 for neighbor in [left, right] if self._get_player_alignment(neighbor) == Alignment.EVIL)

        if self._is_drunk_or_poisoned(player):
            evil_count = (evil_count + 1) % 3
            
        self._broadcast_info(player, f"Storyteller: {evil_count} of your 2 alive neighbors are evil.")

    def _fortuneteller_power(self, player: Player) -> None:
        pass
    
    def _poisoner_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), POISONER_PROMPT)
        if self._is_drunk_or_poisoned(player):
            return
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Poisoner can only choose one player")
            
            choice = player_choice[0]
            self._drunk_and_poisoned[choice].append(player)
            
            self._broadcast_info(player, f"Storyteller: You have posioned {choice} for the night and next day.")
        except KeyError:
            logger.error(f"Player {player.name} tried to poison {player_choice[0]} but they are not in the game.")
        except ValueError:
            logger.error(f"Player {player.name} tried to posion {player_choice}. len(player_choice) != 1")

    def _spy_power(self, player: Player) -> None:
        pass
    
    def _monk_power(self, player: Player) -> None:
        pass

    def _imp_power(self, player: Player) -> None:
        pass

    def _ravenkeeper_power(self, player: Player) -> None:
        pass

    def _undertaker_power(self, player: Player) -> None:
        pass

    def _butler_power(self, player: Player) -> None:
        pass
    
    def _run_night_phase(self) -> None:
        self._current_phase = Phase.NIGHT
        self._broadcast_info(self._all_players(), f"Storyteller: Night has begun on round {self._round_number}.")
        broadcast_buffer: list[Player] = []

        # First night
        if self._round_number == 1:
            # Give demon and minion info
            demon = [player for player in self._players if isinstance(player.character, Demon)]
            assert len(demon) == 1, "There should be exactly one demon"
            demon = demon[0]
            minions = [player for player in self._players if isinstance(player.character, Minion)]
            assert len(minions) >= 1, "There should be at least one minion"

            townsfolk_not_in_play = [character.value for character in self._script.townsfolk if character not in self._character_dict]
            outsiders_not_in_play = [character.value for character in self._script.outsiders if character not in self._character_dict]

            random.shuffle(townsfolk_not_in_play)
            random.shuffle(outsiders_not_in_play)

            not_in_play = [townsfolk_not_in_play[0], townsfolk_not_in_play[1], outsiders_not_in_play[0]]

            self._broadcast_info(demon, f"Storyteller: Three good roles not in play are {', '.join([character.value for character in not_in_play])} and your minion(s) are {', '.join([player.name for player in minions])}")

            self._broadcast_info(minions, f"Storyteller: The Demon is {demon.name}.")

            def get_night_player(character: Character) -> Player | None:
                # Check if there is a drunk who thinks they are this character
                player = self._character_dict.get(character)
                if Outsider.DRUNK in self._character_dict:
                    drunk = self._character_dict[Outsider.DRUNK]
                    if drunk.drunk_character == character:
                        return drunk
                
                if player is None or not player.is_alive:
                    return None

                return player
            
            # First night character actions and info
            for character in self._script.first_night_order:
                player = get_night_player(character)
                if player is None:
                    continue
                
                match character:
                    case Minion.POISONER:
                        self._poisoner_power(player)
                    case Minion.SPY:
                        self._spy_power(player)
                    case Townsfolk.WASHERWOMAN:
                        self._washerwoman_power(player)
                    case Townsfolk.LIBRARIAN:
                        self._librarian_power(player)
                    case Townsfolk.INVESTIGATOR:
                        self._investigator_power(player)
                    case Townsfolk.CHEF:
                        self._chef_power(player)
                    case Townsfolk.EMPATH:
                        self._empath_power(player)
                    case Townsfolk.FORTUNETELLER:
                        self._fortuneteller_power(player)
                    case Outsider.BUTLER:
                        self._butler_power(player)
        # Other nights
        else:
            for character in self._script.other_night_order:
                player = get_night_player(character)
                if player is None:
                    continue
                
                match character:
                    case Minion.POISONER:
                        self._poisoner_power(player)
                    case Townsfolk.MONK:
                        self._monk_power(player)
                    case Minion.SPY:
                        self._spy_power(player)
                    case Demon.IMP:
                        self._imp_power(player)
                    case Townsfolk.RAVENKEEPER:
                        self._ravenkeeper_power(player)
                    case Townsfolk.UNDERTAKER:
                        self._undertaker_power(player)
                    case Townsfolk.EMPATH:
                        self._empath_power(player)
                    case Townsfolk.FORTUNETELLER:
                        self._fortuneteller_power(player)
                    case Outsider.BUTLER:
                        self._butler_power(player)

    
    def _slayer_power(self, player: Player, action: SlayerPowerAction) -> bool:
        it_works: bool = (player.character == Townsfolk.SLAYER and 
                          not self._is_drunk_or_poisoned(player) and 
                          isinstance(self._player_dict[action.target].character, Demon))
        # If it works
        if it_works:
            self._kill_player(self._player_dict[action.target])
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and killed them.")
        # If it doesn't work
        else:
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and nothing happened.")

        return it_works
    
    def _send_message(self, from_player: Player, recipients: list[str], message: str) -> None:
        recipient_str = ", ".join([name for name in recipients])
        self._broadcast_info(recipients, f"Message from {from_player.name} to {recipient_str}: {message}")

    # Returns True if someone died from the Virgin's power
    def _run_nomination(self, player: Player, action: NominationAction) -> bool:
        try:
            nominee = self._player_dict[action.nominee]
        except KeyError:
            logger.error(f"Player {player.name} tried to nominate {action.nominee} but they are not in the game.")
            return
        
        if player.used_nomination:
            logger.error(f"Player {player.name} tried to nominate {nominee.name} but they have already used their nomination today.")
            return
            
        if nominee.nominated_today:
            logger.error(f"Player {player.name} tried to nominate {nominee.name} but they have already been nominated today.")
            return
        
        nominee.nominated_today = True
        player.used_nomination = True

        if nominee.character == Townsfolk.VIRGIN and Townsfolk in self._get_player_roles(player):
            self._kill_player(nominee)
            self._broadcast_info(self._all_players(), f"{player.name} has nominated {nominee.name} for execution. {nominee.name} has been killed.")
            return True

        self._broadcast_info(self._all_players(), f"{player.name} has nominated {nominee.name} for execution. Their reason is: {action.reason}")

        if self._chopping_block:
            prev_count, _ = self._chopping_block
            required_to_tie = prev_count
            required_to_nominate = prev_count + 1
        else:
            living_count = sum(1 for player in self._players if player.is_alive)
            required_to_nominate = living_count // 2 if living_count % 2 == 0 else living_count // 2 + 1
            required_to_tie = None

        count = 0
        previous_votes: list[tuple[str, Vote]] = []
        for player in self._players:
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
            self._chopping_block = (count, nominee)
            self._broadcast_info(self._all_players(), f"Storyteller: {nominee.name} has been nominated for execution with {count} votes. They will die at the end of the day if no one else is nominated. Vote record: {format_vote_history(previous_votes)}")
        elif required_to_tie is not None and count == required_to_tie:
            self._chopping_block = None
            self._broadcast_info(self._all_players(), f"Storyteller: {nominee.name} has received {count} votes. This ties the previous nominee. The chopping block is now empty. Vote record: {format_vote_history(previous_votes)}")

        return False


    def _run_day_phase(self) -> Alignment | None:
        self._current_phase = Phase.DAY
        for player in self._players:
            player.start_of_day()

        loops = 3
        for i in range(loops):
            if i == loops - 1:
                self._nominations_open = True
                self._broadcast_info(self._all_players(), "Storyteller: Nominations are now open.")
        
            day_players: list[Player] = list(self._players)
            random.shuffle(day_players)

            for player in day_players:
                action: DayAction = player.day_action(self._get_public_game_state(), self._nominations_open)

                if isinstance(action, MessageAction):
                    self._send_message(player, action.recipients, action.message)
                elif isinstance(action, NominationAction):
                    # End the day if someone died from the Virgin's power
                    if self._run_nomination(player, action):
                        return
                elif isinstance(action, SlayerPowerAction):
                    if self._slayer_power(action):
                        game_over, alignment = self._game_over()
                        if game_over:
                            return alignment
                elif isinstance(action, NoAction):
                    pass

    def _game_over(self) -> Alignment | None:
        alive_count = sum(player.is_alive for player in self._players)
        alive_demons = sum(isinstance(player.character, Demon) for player in self._players if player.is_alive)
        
        if alive_demons == 0:
            return Alignment.GOOD
        
        if alive_count <= 2:
            return Alignment.EVIL
        
        return None
    
    def run_game(self, max_rounds=6) -> Alignment | None:
        logger.info("Initial game state:")
        self._print_status_summary()
        
        while self._round_number <= max_rounds:
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
            
            for player in self._players:
                player.summarize_history(self._get_public_game_state())

            self._round_number += 1
               
        return None