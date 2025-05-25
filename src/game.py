import random
import logging
from dataclasses import dataclass
from collections import defaultdict
from typing import Any

from player import DayAction, MessageAction, NominationAction, SlayerPowerAction, NoAction, Player
from characters import Character, Townsfolk, Outsider, Demon, Minion
from utils import format_vote_history
from scripts import Script
from prompts import POISONER_PROMPT, FORTUNETELLER_PROMPT, MONK_PROMPT, RAVENKEEPER_PROMPT, IMP_PROMPT, BUTLER_PROMPT
from characters import ReminderTokens
from game_events import GameEventTracker, EventType
from game_enums import Vote, Alignment, Phase
from inference import get_cost_tracker
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

        # Track that setup is complete
        characters_in_play = [f"{p.name} ({p.character.value})" for p in self._players]
        self.event_tracker.add_event(
            event_type=EventType.GAME_SETUP,
            description=f"Game setup complete with {len(self._players)} players",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[p.name for p in self._players],
            public_game_state=self._get_enhanced_game_state_for_logging(),
            metadata={
                "player_count": len(self._players),
                "characters": characters_in_play,
                "script": self._script.__class__.__name__
            }
        )

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

    def _get_enhanced_game_state_for_logging(self) -> dict[str, Any]:
        """Convert the current public game state to an enhanced dictionary with character info for event tracking only"""
        public_game_state = self._get_public_game_state()
        
        # Enhance player state with character information for event tracking
        enhanced_player_state = []
        for player_info in public_game_state.player_state:
            # Find the corresponding player object to get character info
            player_name = player_info["name"]
            player_obj = self._player_dict[player_name]
            
            enhanced_info = player_info.copy()
            enhanced_info["character"] = player_obj.character.value
            enhanced_player_state.append(enhanced_info)
        
        return {
            "player_state": enhanced_player_state,
            "current_phase": public_game_state.current_phase.value,
            "round_number": public_game_state.round_number,
            "chopping_block": {
                "nominee": public_game_state.chopping_block.nominee,
                "votes": public_game_state.chopping_block.votes
            } if public_game_state.chopping_block else None,
            "nominatable_players": public_game_state.nominatable_players
        }

    def _scarlet_woman_check(self, dead_player: Player) -> bool:
        scarlet_woman = [player for player in self._players if player.alive and player.character == Minion.SCARLET_WOMAN and not self._is_drunk_or_poisoned(player)]
        alive_count = sum(1 for player in self._players if player.alive)
        if isinstance(dead_player.character, Demon) and len(scarlet_woman) == 1 and alive_count >= 4:
            woman = scarlet_woman[0]
            old_character = woman.character
            woman.character = dead_player.character
            self._broadcast_info("Storyteller", woman, f"The Demon has died and you have become the new Demon. Your chacter is now {woman.character.value}",
                                event_type=EventType.SCARLET_WOMAN_TRANSFORM,
                                metadata={
                                    "character": "Scarlet Woman",
                                    "old_character": old_character.value,
                                    "new_character": woman.character.value,
                                    "dead_demon": dead_player.name
                                })
            return True
        return False
    
    def _kill_player(self, player: Player, broadcast: bool = True, killed_by_demon: bool = False) -> tuple[list[Player], str]:
        player.alive = False
        
        # If the Ravenkeeper is killed by a demon, mark them to be woken during the next night
        if player.character == Townsfolk.RAVENKEEPER and killed_by_demon:
            self._reminder_tokens[Townsfolk.RAVENKEEPER][ReminderTokens.RAVENKEEPER_WOKEN] = player
        
        self._scarlet_woman_check(player)
        message = f"{player.name} died."
        if broadcast:
            self._broadcast_info(sender="Storyteller", 
                                 recipients=self._all_players(), 
                                 info=message, 
                                 event_type=EventType.PLAYER_DEATH,
                                 description=f"{player.name} ({player.character.value}) died",
                                 metadata={"character": player.character.value, "killed_by_demon": killed_by_demon})
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
        summary = "\n" + "=" * 95
        summary += "\n                            CHARACTER STATUS SUMMARY"
        summary += "\n" + "=" * 95
        summary += "\nName         | Role            | Status | Drunk/Poisoned | Dead Vote"
        summary += "\n" + "-" * 95
        
        # Use seating order (original order in self._players)
        for player in self._players:
            status = "ALIVE" if player.alive else "DEAD"
            
            if player.alive:
                dead_vote = "N/A"
            else:
                dead_vote = "Used" if player.used_dead_vote else "Available"
            
            drunk_poisoned = "YES" if self._is_drunk_or_poisoned(player) else "NO"
            
            # Format with consistent spacing
            summary += f"\n{player.name:<12} | {player.character.value:<15} | {status:<6} | {drunk_poisoned:<14} | {dead_vote}"
        
        summary += "\n" + "=" * 95
        
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
    
    def _broadcast_info(self,
                        sender: str, 
                        recipients: str | Player | list[str | Player] | list[Player] | list[str], 
                        info: str, 
                        event_type: EventType = EventType.INFO_BROADCAST,
                        **kwargs) -> None:    
        if not isinstance(recipients, list):
            recipients = [recipients]

        # Get recipient names for event tracking
        recipient_names = []
        for recipient in recipients:
            if isinstance(recipient, Player):
                recipient_names.append(recipient.name)
            else:
                recipient_names.append(recipient)

        # Always use MESSAGE format for consistency but preserve event type
        recipient_str = ", ".join(recipient_names)
        formatted_info = f"Round: {self._round_number}, Phase: {self._current_phase.value}, Message from {sender} to {recipient_str}: {info}"
        
        # Extract description from kwargs if provided, otherwise use default
        description = kwargs.pop("description", f"{sender} → {recipient_str}: {info}")
        participants = [sender] + recipient_names

        # Send info to each recipient
        for recipient in recipients:
            if isinstance(recipient, Player):
                recipient.give_info(formatted_info)
            else:
                self._player_dict[recipient].give_info(formatted_info)
        
        # Use the provided event_type while keeping consistent formatting
        self.event_tracker.add_event(   
            event_type=event_type,
            description=description,
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=participants,
            public_game_state=self._get_enhanced_game_state_for_logging(),
            **kwargs
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
            
        info_msg = f"One of these players is the {townsfolk_character.value}: {townsfolk_player.name}, {other_player.name}"
        self._broadcast_info("Storyteller", player, info_msg, EventType.WASHERWOMAN_POWER, 
                            metadata={
                                "character": player.character.value,
                                "shown_players": [townsfolk_player.name, other_player.name],
                                "shown_character": townsfolk_character.value
                            })

    def _librarian_power(self, player: Player) -> None:
        # Check if there are any outsiders in the game
        if ReminderTokens.LIBRARIAN_OUTSIDER not in self._reminder_tokens[Townsfolk.LIBRARIAN]:
            # No outsiders in the game
            info_msg = "There are no Outsiders in play."
            self._broadcast_info("Storyteller", player, info_msg, EventType.LIBRARIAN_POWER,
                                metadata={"character": player.character.value, "result": "no_outsiders"})
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
            
        info_msg = f"One of these players is the {outsider_character.value}: {outsider_player.name}, {other_player.name}"
        self._broadcast_info("Storyteller", player, info_msg, EventType.LIBRARIAN_POWER,
                            metadata={
                                "character": player.character.value,
                                "shown_players": [outsider_player.name, other_player.name],
                                "shown_character": outsider_character.value
                            })

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
            
        info_msg = f"One of these players is the {minion_character.value}: {minion_player.name}, {other_player.name}"
        self._broadcast_info("Storyteller", player, info_msg, EventType.INVESTIGATOR_POWER,
                            metadata={
                                "character": player.character.value,
                                "shown_players": [minion_player.name, other_player.name],
                                "shown_character": minion_character.value
                            })

    def _chef_power(self, player: Player) -> None:
        evil_pairs = 0
        for idx in range(len(self._players)):
            next_idx = (idx + 1) % len(self._players)
            if self._get_player_alignment(self._players[idx]) == Alignment.EVIL and self._get_player_alignment(self._players[next_idx]) == Alignment.EVIL:
                evil_pairs += 1

        if self._is_drunk_or_poisoned(player):
            evil_count = sum(1 for neighbor in self._players if neighbor.alignment == Alignment.EVIL)
            evil_pairs = (evil_pairs + 1) % (evil_count - 1)

        info_msg = f"There are {evil_pairs} adjacent pairs of evil players."
        self._broadcast_info("Storyteller", player, info_msg, EventType.CHEF_POWER,
                            metadata={"character": player.character.value, "evil_pairs": evil_pairs})

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
            
        self._broadcast_info("Storyteller", player, f"{evil_count} of your 2 alive neighbors are evil.", EventType.EMPATH_POWER,
                            metadata={"character": player.character.value, "evil_count": evil_count, "neighbors": [left.name, right.name]})

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
                info_msg = f"Yes, one of {choice1.name} and {choice2.name} is the Demon."
                self._broadcast_info("Storyteller", player, info_msg, EventType.FORTUNETELLER_POWER,
                                    metadata={
                                        "character": player.character.value,
                                        "choices": [choice1.name, choice2.name],
                                        "result": "yes"
                                    })
            else:
                info_msg = f"No, neither {choice1.name} nor {choice2.name} is the Demon."
                self._broadcast_info("Storyteller", player, info_msg, EventType.FORTUNETELLER_POWER,
                                    metadata={
                                        "character": player.character.value,
                                        "choices": [choice1.name, choice2.name],
                                        "result": "no"
                                    })
        except KeyError:
            logger.error(f"Player {player.name} tried to choose {player_choice} but one of them is not in the game.")
        except ValueError as e:
            logger.error(f"Player {player.name} made invalid choice for Fortuneteller: {player_choice}. {str(e)}")
    
    def _poisoner_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), POISONER_PROMPT)
        
        try:
            if not player_choice or len(player_choice) != 1:
                if not player_choice:
                    self._broadcast_info("Storyteller", player, "You chose no one to poison tonight.")
                    logger.info(f"Player {player.name} (Poisoner) chose no one to poison")
                else:
                    self._broadcast_info("Storyteller", player, f"You must choose exactly one player to poison (you chose {len(player_choice)}).")
                    logger.error(f"Player {player.name} tried to poison {player_choice}. len(player_choice) != 1")
                return
            
            target_name = player_choice[0]
            if target_name not in self._player_dict:
                self._broadcast_info("Storyteller", player, f"You cannot poison '{target_name}' - player not found.")
                logger.error(f"Player {player.name} tried to poison '{target_name}' but they are not in the game.")
                return
            
            # Remove the poison from any other player
            for player_list in self._drunk_and_poisoned.values():
                if player in player_list:
                    player_list.remove(player)

            choice: Player = self._player_dict[target_name]
            self._drunk_and_poisoned[choice].append(player)
            
            self._broadcast_info("Storyteller", player, f"You have poisoned {choice.name} for the night and next day.", EventType.POISONER_POWER,
                                metadata={"character": player.character.value, "target": choice.name})
        except Exception as e:
            logger.error(f"Error in poisoner power for {player.name}: {str(e)}")
            self._broadcast_info("Storyteller", player, "Something went wrong with your poisoning attempt.")

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
        self._broadcast_info("Storyteller", player, f"THE GRIMOIRE:\n{full_grimoire}", EventType.SPY_POWER,
                            metadata={"character": player.character.value, "info_sections": len(grimoire_info)})

    def _monk_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), MONK_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Monk can only choose one player")
            
            choice: Player = self._player_dict[player_choice[0]]
            self._reminder_tokens[Townsfolk.MONK][ReminderTokens.MONK_PROTECTED] = choice
            self._broadcast_info("Storyteller", player, f"You have protected {choice.name} from the Demon tonight.", EventType.MONK_POWER,
                                metadata={"character": player.character.value, "target": choice.name})
        except KeyError:
            logger.error(f"Player {player.name} tried to protect {player_choice[0]} but they are not in the game.")
        except ValueError:
            logger.error(f"Player {player.name} tried to protect {player_choice}. len(player_choice) != 1")

    def _imp_power(self, player: Player) -> None:
        player_choice = player.night_player_choice(self._get_public_game_state(), IMP_PROMPT)
        
        try:
            if not player_choice or len(player_choice) != 1:
                if not player_choice:
                    self._broadcast_info("Storyteller", player, "You chose no one to kill tonight.")
                    logger.info(f"Player {player.name} (Imp) chose no one to kill")
                else:
                    self._broadcast_info("Storyteller", player, f"You must choose exactly one player to kill (you chose {len(player_choice)}).")
                    logger.error(f"Player {player.name} tried to kill {player_choice}. len(player_choice) != 1")
                return
            
            target_name = player_choice[0]
            if target_name not in self._player_dict:
                self._broadcast_info("Storyteller", player, f"You cannot kill '{target_name}' - player not found.")
                logger.error(f"Player {player.name} tried to kill '{target_name}' but they are not in the game.")
                return
            
            choice = self._player_dict[target_name]
            
            self._reminder_tokens[Demon.IMP][ReminderTokens.IMP_KILLED] = choice

            if not self._safe_from_demon(choice):
                self._kill_player(choice, False, killed_by_demon=True)
                self._broadcast_info("Storyteller", player, f"You have chosen to kill {choice.name} tonight.", EventType.IMP_POWER,
                                    metadata={"character": player.character.value, "target": choice.name, "success": True})
            else:
                self._broadcast_info("Storyteller", player, f"You tried to kill {choice.name} but they were protected.", EventType.IMP_POWER,
                                    metadata={"character": player.character.value, "target": choice.name, "success": False, "reason": "protected"})

        except Exception as e:
            logger.error(f"Error in imp power for {player.name}: {str(e)}")
            self._broadcast_info("Storyteller", player, "Something went wrong with your killing attempt.")

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
            
            self._broadcast_info("Storyteller", player, f"{choice.name} is the {learned_character.value}.", EventType.RAVENKEEPER_POWER,
                                metadata={
                                    "character": player.character.value,
                                    "target": choice.name,
                                    "learned_character": learned_character.value
                                })
            
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
            info_msg = "No one was executed yesterday."
            self._broadcast_info("Storyteller", player, info_msg, EventType.UNDERTAKER_POWER,
                                metadata={"character": player.character.value, "result": "no_execution"})
            return
        
        executed_player = self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED]
        learned_character = executed_player.character
        
        # If the Undertaker is drunk or poisoned, give false information
        if self._is_drunk_or_poisoned(player):
            # Choose a random character from the script that isn't the actual character
            all_characters = self._script.townsfolk + self._script.outsiders + self._script.minions + self._script.demons
            other_characters = [char for char in all_characters if char != executed_player.character]
            learned_character = random.choice(other_characters)
        
        info_msg = f"{executed_player.name} was the {learned_character.value}."
        self._broadcast_info("Storyteller", player, info_msg, EventType.UNDERTAKER_POWER,
                            metadata={
                                "character": player.character.value,
                                "executed_player": executed_player.name,
                                "learned_character": learned_character.value
                            })
        
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
            
            self._broadcast_info("Storyteller", player, f"You have chosen {choice.name} as your master. Tomorrow, you may only vote if they are voting too.", EventType.BUTLER_POWER,
                                metadata={"character": player.character.value, "master": choice.name})
            
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

    def _no_productive_nominations_left(self) -> bool:
        """
        Check if nominations are open but there are no productive nominations left to make.
        A productive nomination is one where a player can nominate someone other than themselves.
        Returns True if we should end the day early due to lack of productive nominations.
        """
        # Only relevant if nominations are open
        if not self._nominations_open:
            return False
        
        # Get players who haven't used their nomination yet
        players_who_can_nominate = [
            player for player in self._players 
            if player.alive and not player.used_nomination
        ]
        
        # Get players who can be nominated (haven't been nominated today)
        players_who_can_be_nominated = [
            player for player in self._players 
            if not player.nominated_today
        ]
        
        # Check if any player can make a productive nomination (nominate someone other than themselves)
        for nominator in players_who_can_nominate:
            for nominee in players_who_can_be_nominated:
                if nominator != nominee:  # Can't nominate yourself productively
                    return False  # Found at least one productive nomination possible
        
        # No productive nominations are possible
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
        self._broadcast_info("Storyteller", self._all_players(), f"Night has begun on round {self._round_number}.", EventType.STORYTELLER_INFO)

        # Track who is alive at the start of the night (only needed after first night)
        if self._round_number > 1:
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

            self._broadcast_info("Storyteller", demon, f"Three good roles not in play are {', '.join([character for character in not_in_play])} and your minion(s) are {', '.join([player.name for player in minions])}", EventType.PLAYER_SETUP,
                                metadata={
                                    "character": demon.character.value,
                                    "not_in_play": not_in_play,
                                    "minions": [player.name for player in minions]
                                })

            self._broadcast_info("Storyteller", minions, f"The Demon is {demon.name}.", EventType.PLAYER_SETUP,
                                metadata={"demon": demon.name, "demon_character": demon.character.value})

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
                    self._broadcast_info("Storyteller", self._all_players(), f"This morning, {dead_player_name} was found dead.", EventType.STORYTELLER_INFO)
                else:
                    dead_players = ", ".join(sorted(died_during_night))
                    self._broadcast_info("Storyteller", self._all_players(), f"This morning, {dead_players} were found dead.", EventType.STORYTELLER_INFO)
            else:
                self._broadcast_info("Storyteller", self._all_players(), "This morning, everyone is still alive.", EventType.STORYTELLER_INFO)

    
    def _slayer_power(self, player: Player, action: SlayerPowerAction) -> bool:
        it_works: bool = (player.character == Townsfolk.SLAYER and 
                          not self._is_drunk_or_poisoned(player) and 
                          isinstance(self._player_dict[action.target].character, Demon))
        # If it works
        if it_works:
            self._kill_player(self._player_dict[action.target])
            self._broadcast_info("Storyteller", self._all_players(), f"{player.name} has used their slayer power on {action.target} and killed them.",
                                event_type=EventType.SLAYER_POWER,
                                metadata={
                                    "character": player.character.value,
                                    "target": action.target,
                                    "success": True
                                })
        # If it doesn't work
        else:
            self._broadcast_info("Storyteller", self._all_players(), f"{player.name} has used their slayer power on {action.target} and nothing happened.",
                                event_type=EventType.SLAYER_POWER,
                                metadata={
                                    "character": player.character.value,
                                    "target": action.target,
                                    "success": False
                                })

        return it_works
    
    # Returns True if someone died from the Virgin's power
    def _run_nomination(self, player: Player, action: NominationAction) -> bool:
        # Make sure the nominee exists and hasn't been nominated today
        try:
            nominee = self._player_dict[action.nominee]
            if nominee.nominated_today:
                raise ValueError("Nominee has already been nominated today")
        except KeyError:
            logger.error(f"Player {player.name} tried to nominate {action.nominee} but they are not in the game.")
            self._broadcast_info("Storyteller", self._all_players(), f"{player.name} passed their turn.",
                                description=f"{player.name} cannot nominate {action.nominee} (player not found).",
                                metadata={"player": player.name, "character": player.character.value, "nominee": action.nominee})
            return False
        except ValueError:
            logger.error(f"Player {player.name} tried to nominate {action.nominee} but they have already been nominated today.")
            self._broadcast_info("Storyteller", self._all_players(), f"{player.name} cannot nominate {action.nominee} because they have already been nominated today.",
                                description=f"{player.name} cannot nominate {action.nominee} because they have already been nominated today.",
                                metadata={"player": player.name, "character": player.character.value, "nominee": action.nominee})
            return False
        
        nominee.nominated_today = True
        player.used_nomination = True

        if nominee.character == Townsfolk.VIRGIN and Townsfolk in self._get_player_roles(player):
            self._kill_player(player)
            self._broadcast_info(sender="Storyteller",
                                 recipients=self._all_players(), 
                                 info=f"{player.name} has nominated {nominee.name} for execution. {player.name} has been executed.",
                                 event_type=EventType.VIRGIN_POWER,
                                 metadata={"nominee": nominee.name, "nominator": player.name})
            return True

        # Include chopping block information in the nomination announcement
        chopping_block_info = ""
        if self._chopping_block:
            current_votes, current_nominee = self._chopping_block
            chopping_block_info = f" Currently, {current_nominee.name} is on the chopping block with {current_votes} votes."
        else:
            chopping_block_info = " The chopping block is currently empty."

        self._broadcast_info(sender="Storyteller", 
                             recipients=self._all_players(), 
                             info=f"{player.name} has nominated {nominee.name} for execution. Their reason is: {action.public_reasoning}{chopping_block_info}",
                             description=f"{player.name} nominated {nominee.name} for execution.{chopping_block_info}\n\nPublic Reasoning: {action.public_reasoning}\n\nPrivate Reasoning: {action.private_reasoning}",
                             event_type=EventType.NOMINATION,
                             metadata={
                                 "nominee": nominee.name, 
                                 "player": player.name, 
                                 "public_reasoning": action.public_reasoning, 
                                 "private_reasoning": action.private_reasoning,
                                 "current_chopping_block": {
                                     "nominee": self._chopping_block[1].name if self._chopping_block else None,
                                     "votes": self._chopping_block[0] if self._chopping_block else None
                                 }
                             })

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
                bulter_player_choice=butler_master_choice,
                nomination_action=action
            )

            previous_votes.append((player.name, vote))
            self.event_tracker.add_event(
                event_type=EventType.VOTING,
                description=f"{player.name} voted {vote.value} on {nominee.name}'s nomination",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name, nominee.name],
                public_game_state=self._get_enhanced_game_state_for_logging(),
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
            public_game_state=self._get_enhanced_game_state_for_logging(),
            metadata={"votes": count, "total_voters": len(previous_votes), "vote_details": vote_details}
        )

        if count >= required_to_nominate:
            self._chopping_block = (count, nominee)
            self._broadcast_info("Storyteller", self._all_players(), f"{nominee.name} has been nominated for execution with {count} votes. They will die at the end of the day if no one else is nominated. Vote record: {format_vote_history(previous_votes)}", 
                                EventType.NOMINATION_RESULT,
                                metadata={"nominee": nominee.name, "votes": count, "required": required_to_nominate, "result": "success", "vote_details": [f"{name}: {vote.value}" for name, vote in previous_votes]})
        elif required_to_tie is not None and count == required_to_tie:
            self._chopping_block = None
            self._broadcast_info("Storyteller", self._all_players(), f"{nominee.name} has received {count} votes. This ties the previous nominee. The chopping block is now empty. Vote record: {format_vote_history(previous_votes)}", 
                                EventType.NOMINATION_RESULT,
                                metadata={"nominee": nominee.name, "votes": count, "required": required_to_nominate, "result": "tie", "vote_details": [f"{name}: {vote.value}" for name, vote in previous_votes]})
        else:
            # Failed nomination - not enough votes
            self._broadcast_info("Storyteller", self._all_players(), f"{nominee.name}'s nomination failed with {count} votes (needed {required_to_nominate}). Vote record: {format_vote_history(previous_votes)}", 
                                EventType.NOMINATION_RESULT,
                                metadata={"nominee": nominee.name, "votes": count, "required": required_to_nominate, "result": "failed", "vote_details": [f"{name}: {vote.value}" for name, vote in previous_votes]})

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
                self._broadcast_info("Storyteller", self._all_players(), "Nominations are now open.", EventType.STORYTELLER_INFO)
        
            # Check if we should end the day early due to no productive nominations left
            if self._no_productive_nominations_left():
                break
        
            day_players: list[Player] = list(self._players)
            random.shuffle(day_players)

            for player in day_players:
                action: DayAction | None = player.day_action(self._get_public_game_state(), self._nominations_open)

                if isinstance(action, MessageAction):
                    self._broadcast_info(player.name, action.recipients, action.message, EventType.MESSAGE)
                elif isinstance(action, NominationAction):
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
                    self._broadcast_info("Storyteller", self._all_players(), f"{player.name} passes their turn. {action.reason}", 
                                        EventType.PLAYER_PASS,
                                        description=f"{player.name} passed their turn, reason: {action.reason}",
                                        metadata={"player": player.name, "character": player.character.value, "reason": action.reason})
                
            # Check again after each player's action in case nominations became unproductive
            if self._no_productive_nominations_left():
                break

        # Execute player on chopping block at end of day
        if self._chopping_block is not None:
            _, executed_player = self._chopping_block
            self.event_tracker.add_event(
                event_type=EventType.EXECUTION,
                description=f"{executed_player.name} ({executed_player.character.value}) has been executed",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[executed_player.name],
                public_game_state=self._get_enhanced_game_state_for_logging(),
                metadata={"character": executed_player.character.value}
            )
            
            # Mark for Undertaker if they're alive
            if Townsfolk.UNDERTAKER in self._character_dict and self._character_dict[Townsfolk.UNDERTAKER].alive:
                self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED] = executed_player
            
            self._kill_player(executed_player)
            self._chopping_block = None
        else:
            # No execution occurred - check Mayor's win condition
            if self._check_mayor_win_condition():
                self._broadcast_info("Storyteller", self._all_players(), "The Mayor's win condition has been met! Only 3 players remain alive and no execution occurred. Good team wins!")
                
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
            public_game_state=self._get_enhanced_game_state_for_logging(),
            metadata={"max_rounds": max_rounds, "players": players_info}
        )
        
        logger.info("Initial game state:")
        self._print_status_summary()
        
        try:
            while self._round_number <= max_rounds:
                self.event_tracker.add_event(
                    event_type=EventType.ROUND_START,
                    description=f"Round {self._round_number} begins",
                    round_number=self._round_number,
                    phase=self._current_phase.value,
                    public_game_state=self._get_enhanced_game_state_for_logging()
                )
                self.event_tracker.add_event(
                    event_type=EventType.PHASE_CHANGE,
                    description=f"Night phase begins",
                    round_number=self._round_number,
                    phase="NIGHT",
                    public_game_state=self._get_enhanced_game_state_for_logging()
                )
                
                self._run_night_phase()

                game_over = self._game_over()
                if game_over:
                    self._end_game(game_over)
                    return game_over
                    
                self.event_tracker.add_event(
                    event_type=EventType.PHASE_CHANGE,
                    description=f"Day phase begins",
                    round_number=self._round_number,
                    phase="DAY",
                    public_game_state=self._get_enhanced_game_state_for_logging()
                )
                
                game_over = self._run_day_phase()
                if game_over:
                    self._end_game(game_over)
                    return game_over

                game_over = self._game_over()
                if game_over:
                    self._end_game(game_over)
                    return game_over
                
                for player in self._players:
                    player.summarize_history(self._get_public_game_state(), self.event_tracker)

                self._round_number += 1
            
            # Game ended due to max rounds
            self._end_game(None)
            return None
            
        finally:
            # Ensure event tracker is always closed
            self.event_tracker.close()
            
    def _end_game(self, winner: Alignment | None) -> None:
        """Handle game ending procedures"""
        if winner:
            description = f"Game ended: {winner.value} team wins!"
            print(f"\n\033[1;32m🏁 {description}\033[0m")
        else:
            description = "Game ended: Maximum rounds reached, no winner"
            print(f"\n\033[1;33m🏁 {description}\033[0m")
        
        # Get API cost summary
        cost_tracker = get_cost_tracker()
        cost_summary = cost_tracker.get_summary()
            
        self.event_tracker.add_event(
            event_type=EventType.GAME_END,
            description=description,
            round_number=self._round_number,
            phase=self._current_phase.value,
            public_game_state=self._get_enhanced_game_state_for_logging(),
            metadata={
                "winner": winner.value if winner else None,
                "api_cost_summary": cost_summary
            }
        )