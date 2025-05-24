import random
import logging
from dataclasses import dataclass
from collections import defaultdict

from player import DayAction, MessageAction, NominationAction, SlayerPowerAction, NoAction, Player
from characters import Character, Townsfolk, Outsider, Demon, Minion
from utils import format_vote_history
from scripts import Script
from prompts import POISONER_PROMPT, FORTUNETELLER_PROMPT, MONK_PROMPT, RAVENKEEPER_PROMPT, IMP_PROMPT, BUTLER_PROMPT
from characters import ReminderTokens
from game_events import GameEventTracker, EventType
from game_enums import Vote, Alignment, Phase
logger = logging.getLogger(__name__)

@dataclass
class ChoppingBlockInfo:
    nominee: str
    votes: int

@dataclass
class PublicGameState:
    character_str: str
    player_state: list[dict]
    current_phase: Phase
    round_number: int
    chopping_block: ChoppingBlockInfo | None
    nominatable_players: list[str]

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
                alignment = self._get_character_alignment(character)
                self._players.append(Player(name=names.pop(), alignment=alignment, character=character))
        else:
            demon_char = demons.pop()
            alignment = self._get_character_alignment(demon_char)
            self._players.append(Player(name=names.pop(), alignment=alignment, character=demon_char))

            for _ in range(minion_count):
                minion_char = minions.pop()
                alignment = self._get_character_alignment(minion_char)
                self._players.append(Player(name=names.pop(), alignment=alignment, character=minion_char))
                if self._players[-1].character == Minion.BARON:
                    outsider_count += 2
                    townsfolk_count = max(townsfolk_count - 2, 0)

            for _ in range(outsider_count):
                outsider_char = outsiders.pop()
                alignment = self._get_character_alignment(outsider_char)
                player = Player(name=names.pop(), alignment=alignment, character=outsider_char)
                self._players.append(player)
                if player.character == Outsider.DRUNK:
                    player.drunk_character = random.choice(townsfolk)

            for _ in range(townsfolk_count):
                townsfolk_char = townsfolk.pop()
                alignment = self._get_character_alignment(townsfolk_char)
                self._players.append(Player(name=names.pop(), alignment=alignment, character=townsfolk_char))

        random.shuffle(self._players)

        # Lookup players by name and character
        self._player_dict: dict[str, Player] = {player.name: player for player in self._players}
        self._character_dict: dict[Character, Player] = {player.character: player for player in self._players}

        self._reminder_tokens: dict[Character, dict[ReminderTokens, Player]] = defaultdict(dict)
        self._round_number: int = 1
        self._current_phase: Phase = Phase.NIGHT
        self._drunk_and_poisoned: dict[Player, list[Player]] = {player: [] for player in self._players}
        self._chopping_block: tuple[int, Player] | None = None
        self._nominations_open: bool = False
        self._script: Script = script
        
        # Initialize event tracker
        self.event_tracker = GameEventTracker()

        # Fortuneteller setup
        if Townsfolk.FORTUNETELLER in self._character_dict:
            good_players = [player for player in self._players if (self._get_player_alignment(player) == Alignment.GOOD)]
            self._reminder_tokens[Townsfolk.FORTUNETELLER] = {ReminderTokens.RED_HERRING: random.choice(good_players)}

        # Investigator setup
        if Townsfolk.INVESTIGATOR in self._character_dict:
            minion_players = [player for player in self._players if isinstance(player.character, Minion)]
            non_minion_players = [player for player in self._players if not isinstance(player.character, Minion)]
            self._reminder_tokens[Townsfolk.INVESTIGATOR] = {
                ReminderTokens.INVESTIGATOR_MINION: random.choice(minion_players),
                ReminderTokens.INVESTIGATOR_OTHER: random.choice(non_minion_players)
            }

        # Washerwoman setup
        if Townsfolk.WASHERWOMAN in self._character_dict:
            townsfolk_players = [player for player in self._players if isinstance(player.character, Townsfolk)]
            non_townsfolk_players = [player for player in self._players if not isinstance(player.character, Townsfolk)]
            self._reminder_tokens[Townsfolk.WASHERWOMAN] = {
                ReminderTokens.WASHERWOMAN_TOWNSFOLK: random.choice(townsfolk_players),
                ReminderTokens.WASHERWOMAN_OTHER: random.choice(non_townsfolk_players)
            }

        # Librarian setup
        if Townsfolk.LIBRARIAN in self._character_dict:
            outsider_players = [player for player in self._players if isinstance(player.character, Outsider)]
            non_outsider_players = [player for player in self._players if not isinstance(player.character, Outsider)]
            if outsider_players:
                self._reminder_tokens[Townsfolk.LIBRARIAN] = {
                    ReminderTokens.LIBRARIAN_OUTSIDER: random.choice(outsider_players),
                    ReminderTokens.LIBRARIAN_OTHER: random.choice(non_outsider_players)
                }
            # If no outsiders, don't set any tokens - the power will handle this case

    def _get_character_alignment(self, character: Character) -> Alignment:
        """Get the alignment for a character"""
        if isinstance(character, (Townsfolk, Outsider)):
            return Alignment.GOOD
        elif isinstance(character, (Minion, Demon)):
            return Alignment.EVIL
        else:
            raise ValueError(f"Unknown character type: {character}")

    def _get_player_alignment(self, player: Player) -> Alignment:
        if player.character == Outsider.RECLUSE:
            return Alignment.EVIL
        elif player.character == Minion.SPY:
            return Alignment.GOOD
        
        return player.alignment
    
    def _get_player_roles(self, player: Player) -> set[type[Character]]:
        if player.character == Minion.SPY:
            return {Townsfolk, Outsider}
        elif player.character == Outsider.RECLUSE:
            return {Minion, Demon}
        
        return {type(player.character)}

    def _get_public_game_state(self) -> PublicGameState:
        """
        Returns all of the current public information about the game state.
        """
        player_state = []
        
        for player in self._players:
            player_info = {
                "name": player.name,
                "alive": player.alive,
                "used_dead_vote": player.used_dead_vote if not player.alive else False,
            }
            
            player_state.append(player_info)
        
        # Format chopping block information
        chopping_block_info = None
        if self._chopping_block is not None:
            votes, nominee = self._chopping_block
            chopping_block_info = ChoppingBlockInfo(
                nominee=nominee.name,
                votes=votes
            )
        
        # Determine which players can be nominated
        # Players can be nominated if:
        # 1. They exist in the game (always true for players in self._players)
        # 2. They haven't been nominated today (nominated_today = False)
        # 3. Nominations are currently open (self._nominations_open = True)
        nominatable_players = []
        if self._nominations_open:
            nominatable_players = [
                player.name for player in self._players 
                if not player.nominated_today
            ]
        
        return PublicGameState(
            character_str=self._script.character_str,
            player_state=player_state,
            current_phase=self._current_phase,
            round_number=self._round_number,
            chopping_block=chopping_block_info,
            nominatable_players=nominatable_players
        )

    def _scarlet_woman_check(self, dead_player: Player) -> bool:
        scarlet_woman = [player for player in self._players if player.alive and player.character == Minion.SCARLET_WOMAN and not self._is_drunk_or_poisoned(player)]

        if isinstance(dead_player.character, Demon) and len(scarlet_woman) == 1:
            woman = scarlet_woman[0]
            old_character = woman.character
            woman.character = dead_player.character
            self._broadcast_info(woman, f"Storyteller: The Demon has died and you have become the new Demon. Your chacter is now {woman.character.value}")
            
            # Track the Scarlet Woman transformation
            self.event_tracker.add_event(
                event_type=EventType.SCARLET_WOMAN_TRANSFORM,
                description=f"{woman.name} (Scarlet Woman) became the new {woman.character.value}",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[woman.name],
                metadata={
                    "character": "Scarlet Woman",
                    "old_character": old_character.value,
                    "new_character": woman.character.value,
                    "dead_demon": dead_player.name
                }
            )
            return True
        return False
    
    def _kill_player(self, player: Player, broadcast: bool = True, killed_by_demon: bool = False) -> tuple[list[Player], str]:
        player.alive = False
        
        # Track the death event
        self.event_tracker.add_event(
            event_type=EventType.PLAYER_DEATH,
            description=f"{player.name} ({player.character.value}) died",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={"character": player.character.value, "killed_by_demon": killed_by_demon}
        )
        
        # If the Ravenkeeper is killed by a demon, mark them to be woken during the next night
        if player.character == Townsfolk.RAVENKEEPER and killed_by_demon:
            self._reminder_tokens[Townsfolk.RAVENKEEPER][ReminderTokens.RAVENKEEPER_WOKEN] = player
        
        self._scarlet_woman_check(player)
        message = f"Storyteller: {player.name} died."
        if broadcast:
            for player_obj in self._all_players():
                self._broadcast_info(player_obj, message)
        return self._all_players(), message
    
    def _safe_from_demon(self, player: Player) -> bool:
        if player.character == Townsfolk.SOLDIER and not self._is_drunk_or_poisoned(player):
            return True
        
        # If the monk is protecting this player
        if (Townsfolk.MONK in self._reminder_tokens and 
            ReminderTokens.MONK_PROTECTED in self._reminder_tokens[Townsfolk.MONK] and 
            self._reminder_tokens[Townsfolk.MONK][ReminderTokens.MONK_PROTECTED] is player and
            Townsfolk.MONK in self._character_dict and
            self._character_dict[Townsfolk.MONK].alive and
            not self._is_drunk_or_poisoned(self._character_dict[Townsfolk.MONK])):
            return True
        
        return False
    
    def _print_status_summary(self) -> None:
        """Print a summary of each character's role and status"""
        summary = "\n" + "=" * 85
        summary += "\n                         CHARACTER STATUS SUMMARY"
        summary += "\n" + "=" * 85
        summary += "\nName        | Role       | Status | Drunk/Poisoned | Dead Vote"
        summary += "\n" + "-" * 85
        
        # Use seating order (original order in self._players)
        for player in self._players:
            status = "ALIVE" if player.alive else "DEAD"
            
            if player.alive:
                dead_vote = "N/A"
            else:
                dead_vote = "Used" if player.used_dead_vote else "Available"
            
            drunk_poisoned = "YES" if self._is_drunk_or_poisoned(player) else "NO"
            
            # Format with consistent spacing
            summary += f"\n{player.name:<12}| {player.character.value:<10} | {status:<6} | {drunk_poisoned:<14} | {dead_vote}"
        
        summary += "\n" + "=" * 85
        
        # Print directly to console with color formatting
        # but don't also log it (which would cause duplicate output)
        print(f"\033[1;36m{summary}\033[0m")  # Cyan, bold text for better visibility

    def _all_players(self, exclude: list[Player] | None = None) -> list[Player]:
        if exclude is None:
            exclude = []
        return [player for player in self._players if player not in exclude]
    
    def _is_drunk_or_poisoned(self, player: Player, visited: set[Player] | None = None) -> bool:
        if visited is None:
            visited = set()
             
        if player.character == Outsider.DRUNK:
            return True
        
        visited.add(player)
        
        for affecting_player in self._drunk_and_poisoned[player]:
            if affecting_player not in visited and affecting_player.alive and not self._is_drunk_or_poisoned(affecting_player, visited):
                return True
        
        return False
    
    def _broadcast_info(self, recipients: str | Player | list[str | Player] | list[Player] | list[str], info: str, event_type: EventType = EventType.INFO_BROADCAST) -> None:    
        if not isinstance(recipients, list):
            recipients = [recipients]

        formatted_info = f"Round: {self._round_number}, Phase: {self._current_phase.value}, {info}"
        
        # Get recipient names for event tracking
        recipient_names = []
        for recipient in recipients:
            if isinstance(recipient, Player):
                recipient.give_info(formatted_info)
                recipient_names.append(recipient.name)
            else:
                self._player_dict[recipient].give_info(formatted_info)
                recipient_names.append(recipient)
        
        # Track the event (but don't track generic info broadcasts to avoid spam)
        if event_type != EventType.INFO_BROADCAST:
            self.event_tracker.add_event(
                event_type=event_type,
                description=info,
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=recipient_names if len(recipient_names) <= 5 else ["Multiple players"]
            )

    def _washerwoman_power(self, player: Player) -> None:
        # Get the players from reminder tokens
        townsfolk_player = self._reminder_tokens[Townsfolk.WASHERWOMAN][ReminderTokens.WASHERWOMAN_TOWNSFOLK]
        other_player = self._reminder_tokens[Townsfolk.WASHERWOMAN][ReminderTokens.WASHERWOMAN_OTHER]
        townsfolk_character = townsfolk_player.character
        if self._is_drunk_or_poisoned(player):
            # Pick two random players and a random townsfolk character
            available_players = [p for p in self._players if p is not townsfolk_player and p is not other_player]
            random_players = random.sample(available_players, 2)
            townsfolk_character = random.choice(self._script.townsfolk)
            townsfolk_player, other_player = random_players[0], random_players[1]
            
        info_msg = f"Storyteller: One of these players is the {townsfolk_character.value}: {townsfolk_player.name}, {other_player.name}"
        self._broadcast_info(player, info_msg, EventType.WASHERWOMAN_POWER)
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.WASHERWOMAN_POWER,
            description=f"{player.name} ({player.character.value}) received information about {townsfolk_character.value}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={
                "character": player.character.value,
                "shown_players": [townsfolk_player.name, other_player.name],
                "shown_character": townsfolk_character.value
            }
        )

    def _librarian_power(self, player: Player) -> None:
        # Check if there are any outsiders in the game
        if ReminderTokens.LIBRARIAN_OUTSIDER not in self._reminder_tokens[Townsfolk.LIBRARIAN]:
            # No outsiders in the game
            info_msg = "Storyteller: There are no Outsiders in play."
            self._broadcast_info(player, info_msg, EventType.LIBRARIAN_POWER)
            
            # Track the power usage
            self.event_tracker.add_event(
                event_type=EventType.LIBRARIAN_POWER,
                description=f"{player.name} ({player.character.value}) learned there are no Outsiders in play",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name],
                metadata={"character": player.character.value, "result": "no_outsiders"}
            )
            return
            
        # Get the players from reminder tokens
        outsider_player = self._reminder_tokens[Townsfolk.LIBRARIAN][ReminderTokens.LIBRARIAN_OUTSIDER]
        other_player = self._reminder_tokens[Townsfolk.LIBRARIAN][ReminderTokens.LIBRARIAN_OTHER]
        outsider_character = outsider_player.character
        if self._is_drunk_or_poisoned(player):
            # Pick two random players and a random outsider character
            available_players = [p for p in self._players if p is not outsider_player and p is not other_player]
            random_players = random.sample(available_players, 2)
            outsider_character = random.choice(self._script.outsiders)
            outsider_player, other_player = random_players[0], random_players[1]
            
        info_msg = f"Storyteller: One of these players is the {outsider_character.value}: {outsider_player.name}, {other_player.name}"
        self._broadcast_info(player, info_msg, EventType.LIBRARIAN_POWER)
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.LIBRARIAN_POWER,
            description=f"{player.name} ({player.character.value}) received information about {outsider_character.value}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={
                "character": player.character.value,
                "shown_players": [outsider_player.name, other_player.name],
                "shown_character": outsider_character.value
            }
        )

    def _investigator_power(self, player: Player) -> None:
        # Get the players from reminder tokens
        minion_player = self._reminder_tokens[Townsfolk.INVESTIGATOR][ReminderTokens.INVESTIGATOR_MINION]
        other_player = self._reminder_tokens[Townsfolk.INVESTIGATOR][ReminderTokens.INVESTIGATOR_OTHER]
        minion_character = minion_player.character
        if self._is_drunk_or_poisoned(player):
            # Pick two random players and a random minion character
            available_players = [p for p in self._players if p is not minion_player and p is not other_player]
            random_players = random.sample(available_players, 2)
            minion_character = random.choice(self._script.minions)
            minion_player, other_player = random_players[0], random_players[1]
            
        info_msg = f"Storyteller: One of these players is the {minion_character.value}: {minion_player.name}, {other_player.name}"
        self._broadcast_info(player, info_msg, EventType.INVESTIGATOR_POWER)
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.INVESTIGATOR_POWER,
            description=f"{player.name} ({player.character.value}) received information about {minion_character.value}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={
                "character": player.character.value,
                "shown_players": [minion_player.name, other_player.name],
                "shown_character": minion_character.value
            }
        )

    def _chef_power(self, player: Player) -> None:
        evil_pairs = 0
        for idx in range(len(self._players)):
            next_idx = (idx + 1) % len(self._players)
            if self._get_player_alignment(self._players[idx]) == Alignment.EVIL and self._get_player_alignment(self._players[next_idx]) == Alignment.EVIL:
                evil_pairs += 1

        if self._is_drunk_or_poisoned(player):
            evil_count = sum(1 for neighbor in self._players if neighbor.alignment == Alignment.EVIL)
            evil_pairs = (evil_pairs + 1) % (evil_count - 1)

        info_msg = f"Storyteller: There are {evil_pairs} adjacent pairs of evil players."
        self._broadcast_info(player, info_msg, EventType.CHEF_POWER)
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.CHEF_POWER,
            description=f"{player.name} ({player.character.value}) detected {evil_pairs} adjacent evil pairs",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={"character": player.character.value, "evil_pairs": evil_pairs}
        )

    def _empath_power(self, player: Player) -> None:
        player_index = self._players.index(player)
        total_players = len(self._players)
        
        # Find first living neighbor in each direction
        def find_neighbor(start_idx: int, step: int) -> Player | None:
            idx = start_idx
            checked_positions = 0
            while checked_positions < total_players - 1:  # Don't check the empath's own position
                if self._players[idx].alive:
                    return self._players[idx]
                idx = (idx + step) % total_players
                checked_positions += 1
            return None
            
        left = find_neighbor((player_index - 1) % total_players, -1)
        right = find_neighbor((player_index + 1) % total_players, 1)
        assert left is not None and right is not None, "Empath should have two living neighbors"
        
        evil_count = sum(1 for neighbor in [left, right] if self._get_player_alignment(neighbor) == Alignment.EVIL)

        if self._is_drunk_or_poisoned(player):
            evil_count = (evil_count + 1) % 3
            
        self._broadcast_info(player, f"Storyteller: {evil_count} of your 2 alive neighbors are evil.")
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.EMPATH_POWER,
            description=f"{player.name} ({player.character.value}) detected {evil_count} evil neighbors",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={"character": player.character.value, "evil_count": evil_count, "neighbors": [left.name, right.name]}
        )

    def _fortuneteller_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), FORTUNETELLER_PROMPT)
        
        try:
            if len(player_choice) != 2:
                raise ValueError("Fortuneteller must choose exactly 2 players")
            
            choice1: Player = self._player_dict[player_choice[0]]
            choice2: Player = self._player_dict[player_choice[1]]
            
            # Get the red herring player
            red_herring = self._reminder_tokens[Townsfolk.FORTUNETELLER][ReminderTokens.RED_HERRING]
            
            # Check if either chosen player is a Demon or the red herring
            either_is_demon_or_red_herring = (
                isinstance(choice1.character, Demon) or choice1 is red_herring or
                isinstance(choice2.character, Demon) or choice2 is red_herring
            )
            
            if self._is_drunk_or_poisoned(player):
                # Give false information
                either_is_demon_or_red_herring = not either_is_demon_or_red_herring
            
            if either_is_demon_or_red_herring:
                info_msg = f"Storyteller: Yes, one of {choice1.name} and {choice2.name} is the Demon."
                self._broadcast_info(player, info_msg, EventType.FORTUNETELLER_POWER)
            else:
                info_msg = f"Storyteller: No, neither {choice1.name} nor {choice2.name} is the Demon."
                self._broadcast_info(player, info_msg, EventType.FORTUNETELLER_POWER)
            
            # Track the power usage
            self.event_tracker.add_event(
                event_type=EventType.FORTUNETELLER_POWER,
                description=f"{player.name} ({player.character.value}) asked about {choice1.name} and {choice2.name}",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name],
                metadata={
                    "character": player.character.value,
                    "choices": [choice1.name, choice2.name],
                    "result": "yes" if either_is_demon_or_red_herring else "no"
                }
            )
        except KeyError:
            logger.error(f"Player {player.name} tried to choose {player_choice} but one of them is not in the game.")
        except ValueError as e:
            logger.error(f"Player {player.name} made invalid choice for Fortuneteller: {player_choice}. {str(e)}")
    
    def _poisoner_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), POISONER_PROMPT)
        
        try:
            if not player_choice or len(player_choice) != 1:
                if not player_choice:
                    self._broadcast_info(player, "Storyteller: You chose no one to poison tonight.")
                    logger.info(f"Player {player.name} (Poisoner) chose no one to poison")
                else:
                    self._broadcast_info(player, f"Storyteller: You must choose exactly one player to poison (you chose {len(player_choice)}).")
                    logger.error(f"Player {player.name} tried to poison {player_choice}. len(player_choice) != 1")
                return
            
            target_name = player_choice[0]
            if target_name not in self._player_dict:
                self._broadcast_info(player, f"Storyteller: You cannot poison '{target_name}' - player not found.")
                logger.error(f"Player {player.name} tried to poison '{target_name}' but they are not in the game.")
                return
            
            # Remove the poison from any other player
            for player_list in self._drunk_and_poisoned.values():
                if player in player_list:
                    player_list.remove(player)

            choice: Player = self._player_dict[target_name]
            self._drunk_and_poisoned[choice].append(player)
            
            self._broadcast_info(player, f"Storyteller: You have poisoned {choice.name} for the night and next day.")
            
            # Track the power usage
            self.event_tracker.add_event(
                event_type=EventType.POISONER_POWER,
                description=f"{player.name} ({player.character.value}) poisoned {choice.name}",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name, choice.name],
                metadata={"character": player.character.value, "target": choice.name}
            )
        except Exception as e:
            logger.error(f"Error in poisoner power for {player.name}: {str(e)}")
            self._broadcast_info(player, "Storyteller: Something went wrong with your poisoning attempt.")

    def _spy_power(self, player: Player) -> None:
        # The Spy sees the complete game state (the "Grimoire")
        grimoire_info = []
        
        # All players and their true characters (dead and alive)
        grimoire_info.append("=== PLAYER CHARACTERS ===")
        for p in self._players:
            status = "ALIVE" if p.alive else "DEAD"
            grimoire_info.append(f"{p.name}: {p.character.value} ({status})")
        
        # Drunk and poisoned status
        if self._drunk_and_poisoned:
            grimoire_info.append("\n=== DRUNK & POISONED ===")
            for affected_player, poisoners in self._drunk_and_poisoned.items():
                if poisoners:  # Only show if actually poisoned by someone
                    poisoner_names = [poisoner.name for poisoner in poisoners]
                    grimoire_info.append(f"{affected_player.name} is poisoned by: {', '.join(poisoner_names)}")
        
        # Active reminder tokens
        if self._reminder_tokens:
            grimoire_info.append("\n=== ACTIVE REMINDER TOKENS ===")
            for character, tokens in self._reminder_tokens.items():
                for token, target_player in tokens.items():
                    if target_player:
                        grimoire_info.append(f"{character.value} - {token.value}: {target_player.name}")
                    else:
                        grimoire_info.append(f"{character.value} - {token.value}: (no target)")
        
        # Special character info (Drunk's false character)
        if Outsider.DRUNK in self._character_dict:
            drunk_player = self._character_dict[Outsider.DRUNK]
            if hasattr(drunk_player, 'drunk_character') and drunk_player.drunk_character:
                grimoire_info.append(f"\n=== SPECIAL INFO ===")
                grimoire_info.append(f"{drunk_player.name} (Drunk) thinks they are: {drunk_player.drunk_character.value}")
        
        full_grimoire = "\n".join(grimoire_info)
        self._broadcast_info(player, f"Storyteller: THE GRIMOIRE:\n{full_grimoire}", EventType.SPY_POWER)
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.SPY_POWER,
            description=f"{player.name} ({player.character.value}) viewed the complete game state",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={"character": player.character.value, "info_sections": len(grimoire_info)}
        )

    def _monk_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), MONK_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Monk can only choose one player")
            
            choice: Player = self._player_dict[player_choice[0]]
            self._reminder_tokens[Townsfolk.MONK][ReminderTokens.MONK_PROTECTED] = choice
            self._broadcast_info(player, f"Storyteller: You have protected {choice.name} from the Demon tonight.")
            
            # Track the power usage
            self.event_tracker.add_event(
                event_type=EventType.MONK_POWER,
                description=f"{player.name} ({player.character.value}) protected {choice.name}",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name, choice.name],
                metadata={"character": player.character.value, "target": choice.name}
            )
        except KeyError:
            logger.error(f"Player {player.name} tried to protect {player_choice[0]} but they are not in the game.")
        except ValueError:
            logger.error(f"Player {player.name} tried to protect {player_choice}. len(player_choice) != 1")

    def _imp_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), IMP_PROMPT)
        
        try:
            if not player_choice or len(player_choice) != 1:
                if not player_choice:
                    self._broadcast_info(player, "Storyteller: You chose no one to kill tonight.")
                    logger.info(f"Player {player.name} (Imp) chose no one to kill")
                else:
                    self._broadcast_info(player, f"Storyteller: You must choose exactly one player to kill (you chose {len(player_choice)}).")
                    logger.error(f"Player {player.name} tried to kill {player_choice}. len(player_choice) != 1")
                return
            
            target_name = player_choice[0]
            if target_name not in self._player_dict:
                self._broadcast_info(player, f"Storyteller: You cannot kill '{target_name}' - player not found.")
                logger.error(f"Player {player.name} tried to kill '{target_name}' but they are not in the game.")
                return
            
            choice = self._player_dict[target_name]
            
            self._reminder_tokens[Demon.IMP][ReminderTokens.IMP_KILLED] = choice

            if not self._safe_from_demon(choice):
                self._kill_player(choice, False, killed_by_demon=True)
                self._broadcast_info(player, f"Storyteller: You have chosen to kill {choice.name} tonight.")
                
                # Track the successful kill
                self.event_tracker.add_event(
                    event_type=EventType.IMP_POWER,
                    description=f"{player.name} ({player.character.value}) killed {choice.name}",
                    round_number=self._round_number,
                    phase=self._current_phase.value,
                    participants=[player.name, choice.name],
                    metadata={"character": player.character.value, "target": choice.name, "success": True}
                )
            else:
                self._broadcast_info(player, f"Storyteller: You tried to kill {choice.name} but they were protected.")
                
                # Track the failed attack
                self.event_tracker.add_event(
                    event_type=EventType.IMP_POWER,
                    description=f"{player.name} ({player.character.value}) tried to kill {choice.name} but they were protected",
                    round_number=self._round_number,
                    phase=self._current_phase.value,
                    participants=[player.name, choice.name],
                    metadata={"character": player.character.value, "target": choice.name, "success": False, "reason": "protected"}
                )

        except Exception as e:
            logger.error(f"Error in imp power for {player.name}: {str(e)}")
            self._broadcast_info(player, "Storyteller: Something went wrong with your killing attempt.")

    def _ravenkeeper_power(self, player: Player) -> None:
        # Only allow Ravenkeeper to use power if they've died and been marked as woken
        if (Townsfolk.RAVENKEEPER not in self._reminder_tokens or 
            ReminderTokens.RAVENKEEPER_WOKEN not in self._reminder_tokens[Townsfolk.RAVENKEEPER] or
            self._reminder_tokens[Townsfolk.RAVENKEEPER][ReminderTokens.RAVENKEEPER_WOKEN] is not player):
            return
        
        player_choice = player.night_player_choice(self._get_public_game_state(), RAVENKEEPER_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Ravenkeeper must choose exactly 1 player")
            
            choice: Player = self._player_dict[player_choice[0]]
            learned_character = choice.character
            
            # If the Ravenkeeper was drunk or poisoned when they died, give false information
            if self._is_drunk_or_poisoned(player):
                # Choose a random character from the script that isn't the actual character
                all_characters = self._script.townsfolk + self._script.outsiders + self._script.minions + self._script.demons
                other_characters = [char for char in all_characters if char != choice.character]
                learned_character = random.choice(other_characters)
            
            self._broadcast_info(player, f"Storyteller: {choice.name} is the {learned_character.value}.")
            
            # Track the power usage
            self.event_tracker.add_event(
                event_type=EventType.RAVENKEEPER_POWER,
                description=f"{player.name} ({player.character.value}) learned {choice.name}'s character",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name],
                metadata={
                    "character": player.character.value,
                    "target": choice.name,
                    "learned_character": learned_character.value
                }
            )
            
            # Clear the reminder token after use
            del self._reminder_tokens[Townsfolk.RAVENKEEPER][ReminderTokens.RAVENKEEPER_WOKEN]
            
        except KeyError:
            logger.error(f"Player {player.name} tried to learn about {player_choice[0]} but they are not in the game.")
        except ValueError as e:
            logger.error(f"Player {player.name} made invalid choice for Ravenkeeper: {player_choice}. {str(e)}")

    def _undertaker_power(self, player: Player) -> None:
        # Check if there was an execution yesterday
        if (Townsfolk.UNDERTAKER not in self._reminder_tokens or 
            ReminderTokens.UNDERTAKER_EXECUTED not in self._reminder_tokens[Townsfolk.UNDERTAKER]):
            info_msg = "Storyteller: No one was executed yesterday."
            self._broadcast_info(player, info_msg, EventType.UNDERTAKER_POWER)
            
            # Track the power usage (no execution case)
            self.event_tracker.add_event(
                event_type=EventType.UNDERTAKER_POWER,
                description=f"{player.name} ({player.character.value}) learned no one was executed yesterday",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name],
                metadata={"character": player.character.value, "result": "no_execution"}
            )
            return
        
        executed_player = self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED]
        learned_character = executed_player.character
        
        # If the Undertaker is drunk or poisoned, give false information
        if self._is_drunk_or_poisoned(player):
            # Choose a random character from the script that isn't the actual character
            all_characters = self._script.townsfolk + self._script.outsiders + self._script.minions + self._script.demons
            other_characters = [char for char in all_characters if char != executed_player.character]
            learned_character = random.choice(other_characters)
        
        info_msg = f"Storyteller: {executed_player.name} was the {learned_character.value}."
        self._broadcast_info(player, info_msg, EventType.UNDERTAKER_POWER)
        
        # Track the power usage
        self.event_tracker.add_event(
            event_type=EventType.UNDERTAKER_POWER,
            description=f"{player.name} ({player.character.value}) learned {executed_player.name} was {learned_character.value}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name],
            metadata={
                "character": player.character.value,
                "executed_player": executed_player.name,
                "learned_character": learned_character.value
            }
        )
        
        # Clear the reminder token after use
        del self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED]

    def _butler_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), BUTLER_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Butler must choose exactly 1 player")
            
            choice: Player = self._player_dict[player_choice[0]]
            
            # Butler cannot choose themselves
            if choice == player:
                raise ValueError("Butler cannot choose themselves")
            
            # Set reminder token for the Butler's master
            self._reminder_tokens[Outsider.BUTLER][ReminderTokens.BUTLER_MASTER] = choice
            
            self._broadcast_info(player, f"Storyteller: You have chosen {choice.name} as your master. Tomorrow, you may only vote if they are voting too.")
            
            # Track the power usage
            self.event_tracker.add_event(
                event_type=EventType.BUTLER_POWER,
                description=f"{player.name} ({player.character.value}) chose {choice.name} as their master",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name],
                metadata={"character": player.character.value, "master": choice.name}
            )
            
        except KeyError:
            logger.error(f"Player {player.name} tried to choose {player_choice[0]} but they are not in the game.")
        except ValueError as e:
            logger.error(f"Player {player.name} made invalid choice for Butler: {player_choice}. {str(e)}")

    def _check_mayor_win_condition(self) -> bool:
        """
        Check if the Mayor's win condition is met: 
        only 3 players alive and no execution occurred.
        """
        alive_count = sum(1 for p in self._players if p.alive)
        
        # Must be exactly 3 players alive
        if alive_count != 3:
            return False
        
        # Must have a living Mayor who isn't drunk/poisoned
        mayor_player = self._character_dict.get(Townsfolk.MAYOR)
        if not mayor_player or not mayor_player.alive or self._is_drunk_or_poisoned(mayor_player):
            return False
        
        # No execution must have occurred (chopping block should be None at end of day)
        if self._chopping_block is not None:
            return False
        
        return True
    
    def _clear_night_tokens(self) -> None:
        """Clear reminder tokens that should only last for one night"""
        tokens_to_clear = [
            (Townsfolk.MONK, ReminderTokens.MONK_PROTECTED),
            (Demon.IMP, ReminderTokens.IMP_KILLED),
            (Outsider.BUTLER, ReminderTokens.BUTLER_MASTER),
        ]
        
        for character, token in tokens_to_clear:
            if (character in self._reminder_tokens and 
                token in self._reminder_tokens[character]):
                del self._reminder_tokens[character][token]
    
    def _run_night_phase(self) -> None:
        self._current_phase = Phase.NIGHT
        self._broadcast_info(self._all_players(), f"Storyteller: Night has begun on round {self._round_number}.", EventType.STORYTELLER_INFO)

        # Track who is alive at the start of the night
        alive_at_start = {player.name for player in self._players if player.alive}

        # Define helper function for getting night players
        def get_night_player(character: Character) -> Player | None:
            # Check if there is a drunk who thinks they are this character
            player = self._character_dict.get(character)
            if Outsider.DRUNK in self._character_dict:
                drunk = self._character_dict[Outsider.DRUNK]
                if drunk.drunk_character == character:
                    return drunk
            
            if player is None or not player.alive:
                return None

            return player

        # First night
        if self._round_number == 1:
            # Give demon and minion info
            demon_list: list[Player] = [player for player in self._players if isinstance(player.character, Demon)]
            assert len(demon_list) == 1, "There should be exactly one demon"
            demon: Player = demon_list[0]
            minions: list[Player] = [player for player in self._players if isinstance(player.character, Minion)]
            assert len(minions) >= 1, "There should be at least one minion"

            townsfolk_not_in_play = [character.value for character in self._script.townsfolk if character not in self._character_dict]
            outsiders_not_in_play = [character.value for character in self._script.outsiders if character not in self._character_dict]

            random.shuffle(townsfolk_not_in_play)
            random.shuffle(outsiders_not_in_play)

            not_in_play = [townsfolk_not_in_play[0], townsfolk_not_in_play[1], outsiders_not_in_play[0]]

            self._broadcast_info(demon, f"Storyteller: Three good roles not in play are {', '.join([character for character in not_in_play])} and your minion(s) are {', '.join([player.name for player in minions])}")
            
            # Track demon information event
            self.event_tracker.add_event(
                event_type=EventType.PLAYER_SETUP,
                description=f"{demon.name} (Demon) learned not in play characters ({', '.join(not_in_play)}) and minion identities ({', '.join([m.name for m in minions])})",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[demon.name],
                metadata={
                    "character": "Demon",
                    "not_in_play": not_in_play,
                    "minions": [m.name for m in minions]
                }
            )

            self._broadcast_info(minions, f"Storyteller: The Demon is {demon.name}.")
            
            # Track minion information event
            self.event_tracker.add_event(
                event_type=EventType.PLAYER_SETUP,
                description=f"Minions learned demon identity: {demon.name}",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[m.name for m in minions],
                metadata={
                    "character": "Minions",
                    "demon": demon.name
                }
            )

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

        # Announce deaths at the end of the night
        alive_at_end = {player.name for player in self._players if player.alive}
        died_during_night = alive_at_start - alive_at_end
        
        if died_during_night:
            if len(died_during_night) == 1:
                dead_player_name = list(died_during_night)[0]
                self._broadcast_info(self._all_players(), f"Storyteller: This morning, {dead_player_name} was found dead.", EventType.STORYTELLER_INFO)
            else:
                dead_players = ", ".join(sorted(died_during_night))
                self._broadcast_info(self._all_players(), f"Storyteller: This morning, {dead_players} were found dead.", EventType.STORYTELLER_INFO)
        else:
            self._broadcast_info(self._all_players(), "Storyteller: This morning, everyone is still alive.", EventType.STORYTELLER_INFO)

    
    def _slayer_power(self, player: Player, action: SlayerPowerAction) -> bool:
        it_works: bool = (player.character == Townsfolk.SLAYER and 
                          not self._is_drunk_or_poisoned(player) and 
                          isinstance(self._player_dict[action.target].character, Demon))
        # If it works
        if it_works:
            self._kill_player(self._player_dict[action.target])
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and killed them.")
            
            # Track successful slayer usage
            self.event_tracker.add_event(
                event_type=EventType.SLAYER_POWER,
                description=f"{player.name} ({player.character.value}) successfully killed {action.target} (Demon)",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name, action.target],
                metadata={
                    "character": player.character.value,
                    "target": action.target,
                    "success": True
                }
            )
        # If it doesn't work
        else:
            self._broadcast_info(self._all_players(), f"{player.name} has used their slayer power on {action.target} and nothing happened.")
            
            # Track failed slayer usage
            self.event_tracker.add_event(
                event_type=EventType.SLAYER_POWER,
                description=f"{player.name} ({player.character.value}) tried to kill {action.target} but it failed",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name, action.target],
                metadata={
                    "character": player.character.value,
                    "target": action.target,
                    "success": False
                }
            )

        return it_works
    
    def _send_message(self, from_player: Player, recipients: list[str], message: str) -> None:
        recipient_str = ", ".join([name for name in recipients])
        
        # Store the message in each recipient's info history
        formatted_info = f"Round: {self._round_number}, Phase: {self._current_phase.value}, Message from {from_player.name} to {recipient_str}: {message}"
        for recipient_name in recipients:
            self._player_dict[recipient_name].give_info(formatted_info)
        
        # Track the message event with cleaner format
        self.event_tracker.add_event(
            event_type=EventType.MESSAGE,
            description=f"{from_player.name} → {recipient_str}: {message}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[from_player.name] + recipients,
            metadata={"message": message, "full_message": message}
        )

    # Returns True if someone died from the Virgin's power
    def _run_nomination(self, player: Player, action: NominationAction) -> bool:
        # At this point, validation should already be done in _run_day_phase
        nominee = self._player_dict[action.nominee]
        
        nominee.nominated_today = True
        player.used_nomination = True

        # Track the nomination event
        self.event_tracker.add_event(
            event_type=EventType.NOMINATION,
            description=f"{player.name} nominated {nominee.name} for execution. Public reason: {action.public_reasoning}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[player.name, nominee.name],
            metadata={
                "private_reasoning": action.private_reasoning,
                "public_reasoning": action.public_reasoning, 
                "nominee_character": nominee.character.value
            }
        )

        if nominee.character == Townsfolk.VIRGIN and Townsfolk in self._get_player_roles(player):
            self._kill_player(nominee)
            self._broadcast_info(self._all_players(), f"{player.name} has nominated {nominee.name} for execution. {nominee.name} has been killed.")
            return True

        self._broadcast_info(self._all_players(), f"{player.name} has nominated {nominee.name} for execution. Their reason is: {action.public_reasoning}")

        if self._chopping_block:
            prev_count, _ = self._chopping_block
            required_to_tie = prev_count
            required_to_nominate = prev_count + 1
        else:
            living_count = sum(1 for player in self._players if player.alive)
            required_to_nominate = living_count // 2 if living_count % 2 == 0 else living_count // 2 + 1
            required_to_tie = None

        count = 0
        previous_votes: list[tuple[str, Vote]] = []
        for player in self._players:
            if player.alive:
                # Check if this player is the Butler and has a master choice
                butler_master_choice = None
                if (player.character == Outsider.BUTLER and 
                    Outsider.BUTLER in self._reminder_tokens and 
                    ReminderTokens.BUTLER_MASTER in self._reminder_tokens[Outsider.BUTLER]):
                    butler_master_choice = self._reminder_tokens[Outsider.BUTLER][ReminderTokens.BUTLER_MASTER].name
                
                vote = player.vote(
                    nominee=nominee.name,
                    public_game_state=self._get_public_game_state(),
                    current_tally=count,
                    required_to_tie=required_to_tie,
                    required_to_nominate=required_to_nominate,
                    previous_votes=previous_votes,
                    bulter_player_choice=butler_master_choice
                )
                previous_votes.append((player.name, vote))
                
                # Track each individual vote
                self.event_tracker.add_event(
                    event_type=EventType.VOTING,
                    description=f"{player.name} voted {vote.value} on {nominee.name}'s nomination",
                    round_number=self._round_number,
                    phase=self._current_phase.value,
                    participants=[player.name, nominee.name],
                    metadata={
                        "voter": player.name,
                        "nominee": nominee.name,
                        "vote": vote.value,
                        "voter_character": player.character.value,
                        "nominee_character": nominee.character.value
                    }
                )
                
                if vote == Vote.YES:
                    count += 1

        # Track the voting event
        vote_details = [f"{name}: {vote.value}" for name, vote in previous_votes]
        self.event_tracker.add_event(
            event_type=EventType.VOTING,
            description=f"Voting for {nominee.name}: {count} yes votes out of {len(previous_votes)} total",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[nominee.name],
            metadata={"votes": count, "total_voters": len(previous_votes), "vote_details": vote_details}
        )

        if count >= required_to_nominate:
            self._chopping_block = (count, nominee)
            self._broadcast_info(self._all_players(), f"Storyteller: {nominee.name} has been nominated for execution with {count} votes. They will die at the end of the day if no one else is nominated. Vote record: {format_vote_history(previous_votes)}")
        elif required_to_tie is not None and count == required_to_tie:
            self._chopping_block = None
            self._broadcast_info(self._all_players(), f"Storyteller: {nominee.name} has received {count} votes. This ties the previous nominee. The chopping block is now empty. Vote record: {format_vote_history(previous_votes)}")

        # Track the end of voting with result
        if count >= required_to_nominate:
            vote_result = f"placed on chopping block with {count} votes"
        elif required_to_tie is not None and count == required_to_tie:
            vote_result = f"tied previous nominee with {count} votes (chopping block cleared)"
        else:
            vote_result = f"failed with {count} votes (needed {required_to_nominate})"
        
        self.event_tracker.add_event(
            event_type=EventType.VOTING,
            description=f"Voting on {nominee.name}'s nomination has ended: {vote_result}",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[nominee.name],
            metadata={
                "nominee": nominee.name,
                "final_vote_count": count,
                "total_voters": len(previous_votes),
                "required_to_nominate": required_to_nominate,
                "required_to_tie": required_to_tie,
                "on_chopping_block": count >= required_to_nominate,
                "voting_ended": True,
                "result": vote_result
            }
        )

        return False


    def _run_day_phase(self) -> Alignment | None:
        self._current_phase = Phase.DAY
        self._clear_night_tokens()
        for player in self._players:
            player.start_of_day()

        # Print character summary at the start of each day
        self._print_status_summary()

        # Allow one round of messaging, then open nominations
        loops = 4
        for i in range(loops):
            if i == 1:  # Open nominations on the second iteration
                self._nominations_open = True
                self._broadcast_info(self._all_players(), "Storyteller: Nominations are now open.", EventType.STORYTELLER_INFO)
                
                # Track that nominations are now open
                self.event_tracker.add_event(
                    event_type=EventType.PHASE_CHANGE,
                    description="Nominations are now open",
                    round_number=self._round_number,
                    phase=self._current_phase.value,
                    metadata={"nominations_open": True}
                )
        
            day_players: list[Player] = list(self._players)
            random.shuffle(day_players)

            for player in day_players:
                action: DayAction | None = player.day_action(self._get_public_game_state(), self._nominations_open)

                if isinstance(action, MessageAction):
                    self._send_message(player, action.recipients, action.message)
                elif isinstance(action, NominationAction):
                    # Dead players cannot nominate
                    if not player.alive:
                        self._broadcast_info(self._all_players(), f"Storyteller: {player.name} cannot nominate (dead players cannot nominate).")
                        # Track the attempt as a pass
                        self.event_tracker.add_event(
                            event_type=EventType.PLAYER_PASS,
                            description=f"{player.name} passed their turn: dead players cannot nominate",
                            round_number=self._round_number,
                            phase=self._current_phase.value,
                            participants=[player.name],
                            metadata={"character": player.character.value, "reason": "dead_cannot_nominate"}
                        )
                    # Check if nomination is valid before proceeding
                    elif player.used_nomination:
                        self._broadcast_info(self._all_players(), f"Storyteller: {player.name} cannot nominate again (already used nomination today).")
                        # Track the attempt as a pass
                        self.event_tracker.add_event(
                            event_type=EventType.PLAYER_PASS,
                            description=f"{player.name} passed their turn: already used nomination today",
                            round_number=self._round_number,
                            phase=self._current_phase.value,
                            participants=[player.name],
                            metadata={"character": player.character.value, "reason": "already_nominated"}
                        )
                    elif action.nominee not in self._player_dict:
                        self._broadcast_info(self._all_players(), f"Storyteller: {player.name} cannot nominate {action.nominee} (player not found).")
                        # Track the attempt as a pass
                        self.event_tracker.add_event(
                            event_type=EventType.PLAYER_PASS,
                            description=f"{player.name} passed their turn: invalid nominee '{action.nominee}'",
                            round_number=self._round_number,
                            phase=self._current_phase.value,
                            participants=[player.name],
                            metadata={"character": player.character.value, "reason": "invalid_nominee"}
                        )
                    elif self._player_dict[action.nominee].nominated_today:
                        self._broadcast_info(self._all_players(), f"Storyteller: {player.name} cannot nominate {action.nominee} (already nominated today).")
                        # Track the attempt as a pass
                        self.event_tracker.add_event(
                            event_type=EventType.PLAYER_PASS,
                            description=f"{player.name} passed their turn: {action.nominee} already nominated today",
                            round_number=self._round_number,
                            phase=self._current_phase.value,
                            participants=[player.name],
                            metadata={"character": player.character.value, "reason": "already_nominated_today"}
                        )
                    else:
                        # Valid nomination - process it
                        if self._run_nomination(player, action):
                            return None  # End the day if someone died from the Virgin's power
                elif isinstance(action, SlayerPowerAction):
                    # Dead players cannot use abilities (but this should be handled by the Player class)
                    if self._slayer_power(player, action):
                        game_over = self._game_over()
                        if game_over:
                            return game_over
                elif isinstance(action, NoAction):
                    # Track when players pass their turn
                    self._broadcast_info(self._all_players(), f"Storyteller: {player.name} passes their turn. {action.reason}")
                    self.event_tracker.add_event(
                        event_type=EventType.PLAYER_PASS,
                        description=f"{player.name} passed their turn: {action.reason}",
                        round_number=self._round_number,
                        phase=self._current_phase.value,
                        participants=[player.name],
                        metadata={"character": player.character.value, "reason": action.reason}
                    )

        # Close nominations and move to execution phase
        if self._nominations_open:
            self._nominations_open = False
            self._broadcast_info(self._all_players(), "Storyteller: Nominations are now closed.", EventType.STORYTELLER_INFO)
            
            # Track that nominations are now closed
            self.event_tracker.add_event(
                event_type=EventType.PHASE_CHANGE,
                description="Nominations are now closed",
                round_number=self._round_number,
                phase=self._current_phase.value,
                metadata={"nominations_open": False}
            )

        # Execute player on chopping block at end of day
        if self._chopping_block is not None:
            _, executed_player = self._chopping_block
            
            # Track the execution event
            self.event_tracker.add_event(
                event_type=EventType.EXECUTION,
                description=f"{executed_player.name} ({executed_player.character.value}) has been executed",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[executed_player.name],
                metadata={"character": executed_player.character.value}
            )
            
            # Mark for Undertaker if they're alive
            if Townsfolk.UNDERTAKER in self._character_dict and self._character_dict[Townsfolk.UNDERTAKER].alive:
                self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED] = executed_player
            
            self._kill_player(executed_player)
            self._broadcast_info(self._all_players(), f"Storyteller: {executed_player.name} has been executed.", EventType.STORYTELLER_INFO)
            self._chopping_block = None
        else:
            # No execution occurred - check Mayor's win condition
            if self._check_mayor_win_condition():
                self._broadcast_info(self._all_players(), 
                    "Storyteller: The Mayor's win condition has been met! Only 3 players remain alive and no execution occurred. Good team wins!")
                
                # Track the Mayor win event
                self.event_tracker.add_event(
                    event_type=EventType.MAYOR_WIN,
                    description="Mayor's win condition triggered - Good team wins",
                    round_number=self._round_number,
                    phase=self._current_phase.value,
                    participants=["Mayor"],
                    metadata={"character": "Mayor", "win_condition": "3_players_no_execution"}
                )
                
                return Alignment.GOOD
        
        return None

    def _game_over(self) -> Alignment | None:
        alive_count = sum(player.alive for player in self._players)
        alive_demons = sum(isinstance(player.character, Demon) for player in self._players if player.alive)
        
        if alive_demons == 0:
            return Alignment.GOOD
        
        if alive_count <= 2:
            return Alignment.EVIL
        
        return None
    
    def run_game(self, max_rounds=6) -> Alignment | None:
        # Track game start
        players_info = [f"{p.name} ({p.character.value})" for p in self._players]
        self.event_tracker.add_event(
            event_type=EventType.GAME_START,
            description=f"Blood on the Clocktower game started with {len(self._players)} players",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[p.name for p in self._players],
            metadata={"max_rounds": max_rounds, "players": players_info}
        )
        
        logger.info("Initial game state:")
        self._print_status_summary()
        
        while self._round_number <= max_rounds:
            # Track round start
            self.event_tracker.add_event(
                event_type=EventType.ROUND_START,
                description=f"Round {self._round_number} begins",
                round_number=self._round_number,
                phase=self._current_phase.value
            )
            
            # Track phase changes
            self.event_tracker.add_event(
                event_type=EventType.PHASE_CHANGE,
                description=f"Night phase begins",
                round_number=self._round_number,
                phase="NIGHT"
            )
            
            self._run_night_phase()

            game_over = self._game_over()
            if game_over:
                return game_over
            
            # Track phase change to day
            self.event_tracker.add_event(
                event_type=EventType.PHASE_CHANGE,
                description=f"Day phase begins",
                round_number=self._round_number,
                phase="DAY"
            )
            
            game_over = self._run_day_phase()
            if game_over:
                return game_over

            game_over = self._game_over()
            if game_over:
                return game_over
            
            for player in self._players:
                player.summarize_history(self._get_public_game_state(), self.event_tracker)

            self._round_number += 1
               
        return None