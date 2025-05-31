import random
import logging
from dataclasses import dataclass
from collections import defaultdict
from typing import Any

from player import DayAction, MessageAction, NominationAction, SlayerPowerAction, VoteAction, NoAction, Player
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
    players_who_can_nominate: list[str]
    original_role_counts: dict[str, int]

class Game:
    def __init__(self, 
                 script: Script, 
                 characters: list[Character], 
                 outsider_count: int = 0, 
                 townsfolk_count: int = 0, 
                 minion_count: int = 0, 
                 random_seed: int | None = None,
                 model: str = "claude-3-5-haiku-20241022",
                 thinking_token_budget: int = 0):
        assert len(characters) >= 5 and (sum([outsider_count, townsfolk_count, minion_count]) >= 4), \
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

        for character in characters:
            alignment = self._get_character_alignment(character)
            self._players.append(Player(name=names.pop(), alignment=alignment, character=character, model=model, thinking_token_budget=thinking_token_budget))

        random.shuffle(self._players)

        # Lookup players by name and character
        self._player_dict: dict[str, Player] = {player.name: player for player in self._players}
        self._character_dict: dict[Character, Player] = {player.character: player for player in self._players}

        self._reminder_tokens: dict[Character, dict[ReminderTokens, Player]] = defaultdict(dict)
        self._round_number: int = 1
        self._current_phase: Phase = Phase.SETUP
        self._drunk_and_poisoned: dict[Player, list[Player]] = {player: [] for player in self._players}
        self._chopping_block: tuple[int, Player] | None = None
        self._nominations_open: bool = False
        self._mayor_kill_deflected: bool = False
        self._script: Script = script
        self._model: str = model
        
        self._original_role_counts = {
            "townsfolk": townsfolk_count,
            "outsider": outsider_count,
            "minion": minion_count,
            "demon": 1  # Always exactly 1 demon
        }
        
        # Initialize event tracker
        self.event_tracker = GameEventTracker()

        if Outsider.DRUNK in self._character_dict:
            self._reminder_tokens[Outsider.DRUNK] = {ReminderTokens.IS_THE_DRUNK: self._character_dict[Outsider.DRUNK]}
            not_in_play_townsfolk = [char for char in self._script.townsfolk if char not in self._character_dict]
            self._character_dict[Outsider.DRUNK].drunk_character = random.choice(not_in_play_townsfolk)

        # Fortuneteller setup
        if Townsfolk.FORTUNETELLER in self._character_dict:
            good_players = [player for player in self._players if (player.alignment == Alignment.GOOD)]
            self._reminder_tokens[Townsfolk.FORTUNETELLER] = {ReminderTokens.RED_HERRING: random.choice(good_players)}

        # Investigator setup
        if Townsfolk.INVESTIGATOR in self._character_dict:
            minion_players = [player for player in self._players if Minion in self._get_player_roles(player)]
            minion_players = [player for player in minion_players if player.character != Minion.SPY] if len(minion_players) > 1 else minion_players

            investigator_minion = random.choice(minion_players)

            non_minion_players = [player for player in self._players if not isinstance(player.character, Minion) and player is not investigator_minion]
            
            investigator_other = random.choice(non_minion_players)
            
            self._reminder_tokens[Townsfolk.INVESTIGATOR] = {
                ReminderTokens.INVESTIGATOR_MINION: investigator_minion,
                ReminderTokens.INVESTIGATOR_OTHER: investigator_other
            }

        # Washerwoman setup
        if Townsfolk.WASHERWOMAN in self._character_dict:
            townsfolk_players = [player for player in self._players if Townsfolk in self._get_player_roles(player)]

            washerwoman_townsfolk = random.choice(townsfolk_players)

            non_townsfolk_players = [player for player in self._players if not isinstance(player.character, Townsfolk) and player is not washerwoman_townsfolk]
            
            washerwoman_other = random.choice(non_townsfolk_players if non_townsfolk_players else non_townsfolk_players)
            
            self._reminder_tokens[Townsfolk.WASHERWOMAN] = {
                ReminderTokens.WASHERWOMAN_TOWNSFOLK: washerwoman_townsfolk,
                ReminderTokens.WASHERWOMAN_OTHER: washerwoman_other
            }
              
        # Librarian setup
        if Townsfolk.LIBRARIAN in self._character_dict:
            outsider_players = [player for player in self._players if Outsider in self._get_player_roles(player)]
            if outsider_players:
                librarian_outsider = random.choice(outsider_players)

                available_non_outsiders = [player for player in self._players if not isinstance(player.character, Outsider) and player is not librarian_outsider]
                
                librarian_other = random.choice(available_non_outsiders)
                
                self._reminder_tokens[Townsfolk.LIBRARIAN] = {
                    ReminderTokens.LIBRARIAN_OUTSIDER: librarian_outsider,
                    ReminderTokens.LIBRARIAN_OTHER: librarian_other
                }
            # If no outsiders, don't set any tokens - the power will handle this case

        # Track that setup is complete
        self.event_tracker.add_event(
            event_type=EventType.GAME_SETUP,
            description=f"Game setup complete with {len(self._players)} players",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[p.name for p in self._players],
            game_state=self._get_enhanced_game_state_for_logging(),
            metadata={
                "player_count": len(self._players),
                "players": [p.name for p in self._players],
                "script": self._script.__class__.__name__,
                "model": self._model,
                "thinking_token_budget": thinking_token_budget,
                "random_seed": random_seed
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
    
    def _get_player_character(self, player: Player) -> Character:
        if player.character == Minion.SPY:
            in_play_chars = [char for char in self._character_dict.keys() if char in {Townsfolk, Outsider}]
            return random.choice(in_play_chars)
        elif player.character == Outsider.RECLUSE:
            in_play_chars = [char for char in self._character_dict.keys() if char in {Minion, Demon}]
            return random.choice(in_play_chars)
        
        return player.character

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
                if not player.nominated_today and player.alive
            ]
        
        # Determine which players can nominate
        # Players can nominate if:
        # 1. They are alive
        # 2. They haven't used their nomination yet today
        # 3. Nominations are currently open (self._nominations_open = True)
        nominating_players = []
        if self._nominations_open:
            nominating_players = [
                player.name for player in self._players
                if player.alive and not player.used_nomination
            ]
        
        return PublicGameState(
            character_str=self._script.character_str,
            player_state=player_state,
            current_phase=self._current_phase,
            round_number=self._round_number,
            chopping_block=chopping_block_info,
            nominatable_players=nominatable_players,
            players_who_can_nominate=nominating_players,
            original_role_counts=self._original_role_counts
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
            
            # Add drunk/poisoned status
            is_drunk_or_poisoned = self._is_drunk_or_poisoned(player_obj)
            enhanced_info["drunk"] = player_obj.character == Outsider.DRUNK
            enhanced_info["poisoned"] = is_drunk_or_poisoned and player_obj.character != Outsider.DRUNK
            
            if player_obj.character == Outsider.DRUNK:
                enhanced_info["drunk_character"] = player_obj.drunk_character.value if player_obj.drunk_character else None
            
            enhanced_player_state.append(enhanced_info)

        # Add reminder token data for event tracking
        reminder_tokens_data: dict[str, str | None] = {}
        for _, tokens in self._reminder_tokens.items():
            for token, target_player in tokens.items():
                reminder_tokens_data[token.value] = target_player.name if target_player else None
        
        return {
            "player_state": enhanced_player_state,
            "current_phase": public_game_state.current_phase.value,
            "round_number": public_game_state.round_number,
            "chopping_block": {
                "nominee": public_game_state.chopping_block.nominee,
                "votes": public_game_state.chopping_block.votes
            } if public_game_state.chopping_block else None,
            "nominatable_players": public_game_state.nominatable_players,
            "nominations_open": self._nominations_open,
            "reminder_tokens": reminder_tokens_data
        }

    def _change_character(self, player: Player, new_character: Character) -> Character:
        """
        Change a player's character and update all related game state.
        Returns the old character.
        """
        old_character = player.character
        
        # Remove player from old character mapping
        if old_character in self._character_dict and self._character_dict[old_character] == player:
            del self._character_dict[old_character]
        
        # Update player's character
        player.character = new_character
        
        # Add player to new character mapping
        self._character_dict[new_character] = player
        
        return old_character

    def _scarlet_woman_check(self, dead_player: Player) -> bool:
        scarlet_woman = [player for player in self._players if player.alive and player.character == Minion.SCARLET_WOMAN and not self._is_drunk_or_poisoned(player)]
        alive_count = sum(1 for player in self._players if player.alive)
        if isinstance(dead_player.character, Demon) and len(scarlet_woman) == 1 and alive_count >= 4:
            woman = scarlet_woman[0]
            old_character = self._change_character(woman, dead_player.character)
            self._broadcast_info("Storyteller", woman, f"The Demon has died and you have become the new Demon. Your character is now {woman.character.value}",
                                event_type=EventType.SCARLET_WOMAN_TRANSFORM,
                                metadata={
                                    "player_name": woman.name,
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
                                 metadata={"player_name": player.name, "killed_by_demon": killed_by_demon})
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
                        include_sender_in_history: bool = False,
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
        
        # Get metadata from kwargs, preserving what was passed in
        metadata = kwargs.pop("metadata", {})
        
        # Only add sender/recipient info for events that don't already have specific metadata
        if event_type == EventType.MESSAGE and "sender" not in metadata:
            # Check if this is a public message (sent to everyone except the sender)
            all_player_names = [p.name for p in self._players]
            all_except_sender = [name for name in all_player_names if name != sender]
            is_public = set(recipient_names) == set(all_except_sender)
            
            metadata.update({
                "sender": sender,
                "recipients": recipient_names,
                "message": info,
                "is_public": is_public
            })
        elif event_type in [EventType.STORYTELLER_INFO, EventType.INFO_BROADCAST] and "sender" not in metadata:
            metadata.update({
                "sender": sender,
                "recipients": recipient_names
            })
        elif event_type in [EventType.PLAYER_SETUP] and "sender" not in metadata:
            metadata.update({
                "sender": sender,
                "recipient": recipient_names[0] if recipient_names else None
            })

        # Send info to each recipient
        for recipient in recipients:
            if isinstance(recipient, Player):
                recipient.give_info(formatted_info)
            else:
                self._player_dict[recipient].give_info(formatted_info)
        
        # Optionally include sender in their own history (without affecting logging/events)
        if include_sender_in_history and sender in self._player_dict:
            sender_player = self._player_dict[sender]
            if sender not in recipient_names:  # Only if sender wasn't already a recipient
                sender_player.give_info(formatted_info)
        
        # Use the provided event_type while keeping consistent formatting
        self.event_tracker.add_event(   
            event_type=event_type,
            description=description,
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[sender] + recipient_names,  # Keep for backward compatibility
            game_state=self._get_enhanced_game_state_for_logging(),
            metadata=metadata,
            **kwargs
        )

    def _washerwoman_power(self, player: Player) -> None:
        townsfolk_character: Character
        
        if self._is_drunk_or_poisoned(player):
            # Give false information - pick two random players and a random townsfolk character
            random_players = random.sample(self._players, 2)
            townsfolk_character = random.choice(self._script.townsfolk)
            townsfolk_player, other_player = random_players[0], random_players[1]
        else:
            # Get the players from reminder tokens (these should exist for a real Washerwoman)
            townsfolk_player = self._reminder_tokens[Townsfolk.WASHERWOMAN][ReminderTokens.WASHERWOMAN_TOWNSFOLK]
            other_player = self._reminder_tokens[Townsfolk.WASHERWOMAN][ReminderTokens.WASHERWOMAN_OTHER]
            # Check if this is the spy
            if not isinstance(townsfolk_player.character, Townsfolk):
                # We need to make up a townsfolk character
                not_in_play_townsfolk = [char for char in self._script.townsfolk if char not in self._character_dict]
                townsfolk_character = random.choice(not_in_play_townsfolk)
            else:
                townsfolk_character = townsfolk_player.character
            
        info_msg = f"One of these players is the {townsfolk_character.value}: {townsfolk_player.name}, {other_player.name}"
        self._broadcast_info("Storyteller", player, info_msg, EventType.WASHERWOMAN_POWER, 
                            metadata={
                                "player_name": player.name,
                                "shown_players": [townsfolk_player.name, other_player.name],
                                "shown_character": townsfolk_character.value
                            })

    def _librarian_power(self, player: Player) -> None:
        outsider_character: Character
        
        if self._is_drunk_or_poisoned(player):
            # Give false information - pick two random players and a random outsider character
            random_players = random.sample(self._players, 2)
            outsider_character = random.choice(self._script.outsiders)
            outsider_player, other_player = random_players[0], random_players[1]
        else:
            # Check if there are any outsiders in the game
            if ReminderTokens.LIBRARIAN_OUTSIDER not in self._reminder_tokens[Townsfolk.LIBRARIAN]:
                # No outsiders in the game
                info_msg = "There are no Outsiders in play."
                self._broadcast_info("Storyteller", player, info_msg, EventType.LIBRARIAN_POWER,
                                    metadata={"player_name": player.name, "result": "no_outsiders"})
                return
                
            # Get the players from reminder tokens
            outsider_player = self._reminder_tokens[Townsfolk.LIBRARIAN][ReminderTokens.LIBRARIAN_OUTSIDER]
            other_player = self._reminder_tokens[Townsfolk.LIBRARIAN][ReminderTokens.LIBRARIAN_OTHER]
            # Check if this is the spy
            if not isinstance(outsider_player.character, Outsider):
                # We need to make up an outsider character
                not_in_play_outsider = [char for char in self._script.outsiders if char not in self._character_dict]
                outsider_character = random.choice(not_in_play_outsider)
            else:
                outsider_character = outsider_player.character
            
        info_msg = f"One of these players is the {outsider_character.value}: {outsider_player.name}, {other_player.name}"
        self._broadcast_info("Storyteller", player, info_msg, EventType.LIBRARIAN_POWER,
                            metadata={
                                "player_name": player.name,
                                "shown_players": [outsider_player.name, other_player.name],
                                "shown_character": outsider_character.value
                            })

    def _investigator_power(self, player: Player) -> None:
        minion_character: Character
        
        if self._is_drunk_or_poisoned(player):
            # Give false information - pick two random players and a random minion character
            random_players = random.sample(self._players, 2)
            minion_character = random.choice(self._script.minions)
            minion_player, other_player = random_players[0], random_players[1]
        else:
            # Get the players from reminder tokens
            minion_player = self._reminder_tokens[Townsfolk.INVESTIGATOR][ReminderTokens.INVESTIGATOR_MINION]
            other_player = self._reminder_tokens[Townsfolk.INVESTIGATOR][ReminderTokens.INVESTIGATOR_OTHER]
            # Check if this is the recluse
            if not isinstance(minion_player.character, Minion):
                # We need to make up a minion character
                not_in_play_minion = [char for char in self._script.minions if char not in self._character_dict]
                minion_character = random.choice(not_in_play_minion)
            else:
                minion_character = minion_player.character
            
        info_msg = f"One of these players is the {minion_character.value}: {minion_player.name}, {other_player.name}"
        self._broadcast_info("Storyteller", player, info_msg, EventType.INVESTIGATOR_POWER,
                            metadata={
                                "player_name": player.name,
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
                            metadata={"player_name": player.name, "evil_pairs": evil_pairs})

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
                            metadata={"player_name": player.name, "evil_count": evil_count, "neighbors": [left.name, right.name]})

    def _fortuneteller_power(self, player: Player, night_start_game_state: PublicGameState) -> None:
        player_choice, reasoning, thinking = player.night_player_choice(night_start_game_state, FORTUNETELLER_PROMPT)
        
        try:
            if len(player_choice) != 2:
                raise ValueError("Fortuneteller must choose exactly 2 players")
            
            choice1: Player = self._player_dict[player_choice[0]]
            choice2: Player = self._player_dict[player_choice[1]]
            
            # Check if this is a drunk or poisoned player
            if (self._is_drunk_or_poisoned(player) or 
                Townsfolk.FORTUNETELLER not in self._reminder_tokens or 
                ReminderTokens.RED_HERRING not in self._reminder_tokens[Townsfolk.FORTUNETELLER]):
                either_is_demon_or_red_herring = (Demon in {choice1.character, choice2.character})
                # The opposite of whatever the truth is
                either_is_demon_or_red_herring = not either_is_demon_or_red_herring
            else:
                # Get the red herring player
                red_herring = self._reminder_tokens[Townsfolk.FORTUNETELLER][ReminderTokens.RED_HERRING]
                
                # Check if either chosen player is a Demon or the red herring
                either_is_demon_or_red_herring = (
                    Demon in self._get_player_roles(choice1) or choice1 is red_herring or
                    Demon in self._get_player_roles(choice2) or choice2 is red_herring
                )
            
            if either_is_demon_or_red_herring:
                info_msg = f"Yes, one of {choice1.name} and {choice2.name} is the Demon. Your reasoning: {reasoning}"
                self._broadcast_info("Storyteller", player, info_msg, EventType.FORTUNETELLER_POWER,
                                    metadata={
                                        "player_name": player.name,
                                        "choices": [choice1.name, choice2.name],
                                        "result": "yes",
                                        "private_reasoning": reasoning,
                                        "thinking": thinking
                                    })
            else:
                info_msg = f"No, neither {choice1.name} nor {choice2.name} is the Demon. Your reasoning: {reasoning}"
                self._broadcast_info("Storyteller", player, info_msg, EventType.FORTUNETELLER_POWER,
                                    metadata={
                                        "player_name": player.name,
                                        "choices": [choice1.name, choice2.name],
                                        "result": "no",
                                        "private_reasoning": reasoning,
                                        "thinking": thinking
                                    })
        except KeyError:
            logger.error(f"Player {player.name} tried to choose {player_choice} but one of them is not in the game.")
        except ValueError as e:
            logger.error(f"Player {player.name} made invalid choice for Fortuneteller: {player_choice}. {str(e)}")
    
    def _poisoner_power(self, player: Player, night_start_game_state: PublicGameState) -> None:
        player_choice, reasoning, thinking = player.night_player_choice(night_start_game_state, POISONER_PROMPT)
        
        try:
            if not player_choice or len(player_choice) != 1:
                if not player_choice:
                    self._broadcast_info("Storyteller", player, f"You chose no one to poison tonight. Your reasoning: {reasoning}")
                    logger.info(f"Player {player.name} (Poisoner) chose no one to poison")
                else:
                    self._broadcast_info("Storyteller", player, f"You must choose exactly one player to poison (you chose {len(player_choice)}). Your reasoning: {reasoning}")
                    logger.error(f"Player {player.name} tried to poison {player_choice}. len(player_choice) != 1")
                return
            
            target_name = player_choice[0]
            if target_name not in self._player_dict:
                self._broadcast_info("Storyteller", player, f"You cannot poison '{target_name}' - player not found. Your reasoning: {reasoning}")
                logger.error(f"Player {player.name} tried to poison '{target_name}' but they are not in the game.")
                return
            
            # Remove the poison from any other player
            for player_list in self._drunk_and_poisoned.values():
                if player in player_list:
                    player_list.remove(player)

            choice: Player = self._player_dict[target_name]
            self._drunk_and_poisoned[choice].append(player)
            
            self._broadcast_info("Storyteller", player, f"You have poisoned {choice.name} for the night and next day. Your reasoning: {reasoning}", EventType.POISONER_POWER,
                                metadata={"player_name": player.name, "target": choice.name, "private_reasoning": reasoning, "thinking": thinking})
        except Exception as e:
            logger.error(f"Error in poisoner power for {player.name}: {str(e)}")
            self._broadcast_info("Storyteller", player, f"Something went wrong with your poisoning attempt. Your reasoning: {reasoning}")

    def _spy_power(self, player: Player) -> None:
        # The Spy sees the complete game state (the "Grimoire")
        grimoire_info = []
        
        # All players and their true characters (ghost and alive)
        grimoire_info.append("=== PLAYER CHARACTERS ===")
        for p in self._players:
            status = "ALIVE" if p.alive else "GHOST"
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
            grimoire_info.append("\n=== ACTIVE REMINDER TOKENS ===\nThese tokens are used to track information about players such as who the Fortuneteller's Red Herring is.")
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
                            metadata={"player_name": player.name, "grimoire_info": grimoire_info})

    def _monk_power(self, player: Player, night_start_game_state: PublicGameState) -> None:
        player_choice, reasoning, thinking = player.night_player_choice(night_start_game_state, MONK_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Monk can only choose one player")
            
            choice: Player = self._player_dict[player_choice[0]]
            self._reminder_tokens[Townsfolk.MONK][ReminderTokens.MONK_PROTECTED] = choice
            self._broadcast_info("Storyteller", player, f"You have protected {choice.name} from the Demon tonight. Your reasoning: {reasoning}", EventType.MONK_POWER,
                                metadata={"player_name": player.name, "target": choice.name, "private_reasoning": reasoning, "thinking": thinking})
        except KeyError:
            logger.error(f"Player {player.name} tried to protect {player_choice[0]} but they are not in the game.")
        except ValueError:
            logger.error(f"Player {player.name} tried to protect {player_choice}. len(player_choice) != 1")

    def _imp_power(self, player: Player, night_start_game_state: PublicGameState) -> None:
        player_choice, reasoning, thinking = player.night_player_choice(night_start_game_state, IMP_PROMPT)
        
        try:
            if not player_choice or len(player_choice) != 1:
                if not player_choice:
                    self._broadcast_info("Storyteller", player, f"You chose no one to kill tonight. Your reasoning: {reasoning}")
                    logger.info(f"Player {player.name} (Imp) chose no one to kill")
                else:
                    self._broadcast_info("Storyteller", player, f"You must choose exactly one player to kill (you chose {len(player_choice)}). Your reasoning: {reasoning}")
                    logger.error(f"Player {player.name} tried to kill {player_choice}. len(player_choice) != 1")
                return
            
            target_name = player_choice[0]
            if target_name not in self._player_dict:
                self._broadcast_info("Storyteller", player, f"You cannot kill '{target_name}' - player not found. Your reasoning: {reasoning}")
                logger.error(f"Player {player.name} tried to kill '{target_name}' but they are not in the game.")
                return
            
            choice = self._player_dict[target_name]

            # Check for Mayor redirecting the kill
            if (choice.character == Townsfolk.MAYOR and choice.alive
                and not self._is_drunk_or_poisoned(choice) and not self._mayor_kill_deflected):
                # The order we look for alternative targets to deflect the kill to
                alternative_choices = [Outsider.BUTLER, Townsfolk.WASHERWOMAN, Townsfolk.LIBRARIAN, Townsfolk.INVESTIGATOR, Townsfolk.CHEF, \
                                       Outsider.RECLUSE, Townsfolk.RAVENKEEPER, Townsfolk.MONK, Townsfolk.VIRGIN, Townsfolk.SOLDIER]
                for character in alternative_choices:
                    if character in self._character_dict and self._character_dict[character].alive:
                        choice = self._character_dict[character]
                        self._mayor_kill_deflected = True
                        break

            self._reminder_tokens[Demon.IMP][ReminderTokens.IMP_KILLED] = choice

            if not self._safe_from_demon(choice) and not self._is_drunk_or_poisoned(player):
                self._kill_player(choice, False, killed_by_demon=True)
                self._broadcast_info("Storyteller", player, f"You have chosen to kill {choice.name} tonight. Your reasoning: {reasoning}", EventType.IMP_POWER,
                                    metadata={"player_name": player.name, "target": choice.name, "success": True, "private_reasoning": reasoning, "thinking": thinking})
                # If the Imp chose to kill themself, pick a minion to become the new Imp
                if player.name == choice:
                    # Pick a minion to become the new Imp
                    minions = [p for p in self._players if isinstance(p.character, Minion)]
                    if minions:
                        new_imp = random.choice(minions)
                        old_character = self._change_character(new_imp, Demon.IMP)
                        self._broadcast_info("Storyteller", new_imp, f"The Imp {player.name} chose to kill themself and you are now the new Imp.", EventType.IMP_TRANSFORM,
                                    metadata={
                                        "player_name": player.name, 
                                        "new_imp": new_imp.name, 
                                        "old_character": old_character.value,
                                        "new_character": new_imp.character.value,
                                        "private_reasoning": reasoning,
                                        "thinking": thinking
                                    })
            else:
                self._broadcast_info("Storyteller", player, f"You tried t o kill {choice.name} but they did not die. Your reasoning: {reasoning}", EventType.IMP_POWER,
                                    metadata={"player_name": player.name, "target": choice.name, "success": False, "reason": "protected", "private_reasoning": reasoning, "thinking": thinking})

        except Exception as e:
            logger.error(f"Error in imp power for {player.name}: {str(e)}")
            self._broadcast_info("Storyteller", player, f"Something went wrong with your killing attempt. Your reasoning: {reasoning}")

    def _ravenkeeper_power(self, player: Player, night_start_game_state: PublicGameState) -> None:
        # Only allow Ravenkeeper to use power if they've died and been marked as woken
        if (Townsfolk.RAVENKEEPER not in self._reminder_tokens or 
            ReminderTokens.RAVENKEEPER_WOKEN not in self._reminder_tokens[Townsfolk.RAVENKEEPER] or
            self._reminder_tokens[Townsfolk.RAVENKEEPER][ReminderTokens.RAVENKEEPER_WOKEN] is not player):
            return
        
        player_choice, reasoning, thinking = player.night_player_choice(night_start_game_state, RAVENKEEPER_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Ravenkeeper must choose exactly 1 player")
            
            choice: Player = self._player_dict[player_choice[0]]
            learned_character = self._get_player_character(choice)
            
            # If the Ravenkeeper was drunk or poisoned when they died, give false information
            if self._is_drunk_or_poisoned(player):
                # Choose a random character from the script that isn't the actual character
                all_characters = self._script.townsfolk + self._script.outsiders + self._script.minions + self._script.demons
                other_characters = [char for char in all_characters if char != choice.character]
                learned_character = random.choice(other_characters)
            
            self._broadcast_info("Storyteller", player, f"{choice.name} is the {learned_character.value}. Your reasoning: {reasoning}", EventType.RAVENKEEPER_POWER,
                                metadata={
                                    "player_name": player.name,
                                    "target": choice.name,
                                    "learned_character": learned_character.value,
                                    "private_reasoning": reasoning,
                                    "thinking": thinking
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
            # No execution yesterday - don't broadcast anything to the player
            return
        
        executed_player = self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED]
        learned_character = self._get_player_character(executed_player)
        
        # If the Undertaker is drunk or poisoned, give false information
        if self._is_drunk_or_poisoned(player):
            # Choose a random character from the script that isn't the actual character
            all_characters = self._script.townsfolk + self._script.outsiders + self._script.minions + self._script.demons
            other_characters = [char for char in all_characters if char != executed_player.character]
            learned_character = random.choice(other_characters)
        
        info_msg = f"{executed_player.name} was the {learned_character.value}."
        self._broadcast_info("Storyteller", player, info_msg, EventType.UNDERTAKER_POWER,
                            metadata={
                                "player_name": player.name,
                                "executed_player": executed_player.name,
                                "learned_character": learned_character.value
                            })
        
        # Clear the reminder token after use
        del self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED]

    def _butler_power(self, player: Player, night_start_game_state: PublicGameState) -> None:
        player_choice, reasoning, thinking = player.night_player_choice(night_start_game_state, BUTLER_PROMPT)
        
        try:
            if len(player_choice) != 1:
                raise ValueError("Butler must choose exactly 1 player")
            
            choice: Player = self._player_dict[player_choice[0]]
            
            # Butler cannot choose themselves
            if choice == player:
                raise ValueError("Butler cannot choose themselves")
            
            # Set reminder token for the Butler's master
            self._reminder_tokens[Outsider.BUTLER][ReminderTokens.BUTLER_MASTER] = choice
            
            self._broadcast_info("Storyteller", player, f"You have chosen {choice.name} as your master. Tomorrow, you may only vote if they are voting too. Your reasoning: {reasoning}", EventType.BUTLER_POWER,
                                metadata={"player_name": player.name, "master": choice.name, "private_reasoning": reasoning, "thinking": thinking})
            
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
            (Townsfolk.RAVENKEEPER, ReminderTokens.RAVENKEEPER_WOKEN),
        ]
        
        for character, token in tokens_to_clear:
            if (character in self._reminder_tokens and 
                token in self._reminder_tokens[character]):
                del self._reminder_tokens[character][token]
    
    def _should_end_day_early(self, consecutive_passes: int) -> bool:
        """Check if the day should end early due to lack of productive actions."""
        # If all living players have passed consecutively (after round 1)
        living_players_count = sum(1 for p in self._players if p.alive)
        if self._round_number > 1 and consecutive_passes >= living_players_count:
            self._broadcast_info("Storyteller", self._all_players(), "All players have passed consecutively. The day will end early.", EventType.EARLY_DAY_END)
            return True

        if self._nominations_open:
            # If someone is on the chopping block and not enough votes exist to tie or win
            if self._chopping_block:
                votes_on_block, _ = self._chopping_block
                dead_votes = sum(1 for p in self._players if not p.alive and not p.used_dead_vote)
                # If there is not enough votes to tie or beat the current chopping block, the day will end
                if living_players_count + dead_votes < votes_on_block:
                    self._broadcast_info("Storyteller", self._all_players(), "Not enough votes remaining to tie or beat the current nomination. The day will end early.", EventType.EARLY_DAY_END)
                    return True
            
            # Check if no productive nominations are left
            # (Logic from _no_productive_nominations_left)
            players_who_can_nominate = [
                player for player in self._players 
                if player.alive and not player.used_nomination
            ]
            players_who_can_be_nominated = [
                player for player in self._players 
                if player.alive and not player.nominated_today
            ]
            
            productive_nomination_possible = False
            for nominator in players_who_can_nominate:
                for nominee in players_who_can_be_nominated:
                    if nominator is not nominee and (nominee.alignment != Alignment.EVIL or nominator.alignment != Alignment.EVIL):
                        productive_nomination_possible = True
                        break
                if productive_nomination_possible:
                    break
            
            if not productive_nomination_possible:
                self._broadcast_info("Storyteller", self._all_players(), "No productive nominations left. The day will end early.", EventType.STORYTELLER_INFO)
                return True
                
        return False
    
    def _run_night_phase(self) -> None:
        self._current_phase = Phase.NIGHT
        self._broadcast_info("Storyteller", self._all_players(), f"Night has begun on round {self._round_number}.", EventType.STORYTELLER_INFO)

        # Save the public game state at the start of the night for consistent night-time decisions
        night_start_game_state = self._get_public_game_state()

        # Track who is alive at the start of the night (only needed after first night)
        if self._round_number > 1:
            alive_at_start = {player.name for player in self._players if player.alive}

        # Define helper function for getting night players
        def get_night_player(character: Character) -> Player | None:
            # Check if there is a drunk who thinks they are this character
            player = self._character_dict.get(character)
            if Outsider.DRUNK in self._character_dict:
                drunk = self._character_dict[Outsider.DRUNK]
                if drunk.drunk_character == character and drunk.alive:
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
            outsiders_not_in_play = [character.value for character in self._script.outsiders if character not in self._character_dict and character != Outsider.DRUNK]

            random.shuffle(townsfolk_not_in_play)
            random.shuffle(outsiders_not_in_play)

            not_in_play = [townsfolk_not_in_play[0], townsfolk_not_in_play[1], outsiders_not_in_play[0]]

            self._broadcast_info("Storyteller", demon, f"Three good roles not in play are {', '.join([character for character in not_in_play])}. The Evil team can use those roles to bluff since there will be no other players with those roles. Your minion(s) are {', '.join([player.name for player in minions])}", EventType.DEMON_INFO,
                                metadata={
                                    "demon": demon.name,
                                    "demon_character": demon.character.value,
                                    "not_in_play": not_in_play,
                                    "minions": [{"name": player.name, "character": player.character.value} for player in minions]
                                })

            # Create minion info message
            if len(minions) == 1:
                minion_info = f"The Demon is {demon.name}. You are the only minion."
            else:
                minion_names = [minion.name for minion in minions]
                minion_info = f"The Demon is {demon.name}. Your fellow minions are {', '.join(minion_names)}."
            
            self._broadcast_info("Storyteller", minions, minion_info, EventType.MINION_INFO,
                                metadata={
                                    "demon": demon.name,
                                    "demon_character": demon.character.value,
                                    "minions": [{"name": player.name, "character": player.character.value} for player in minions]
                                })

            # First night character actions and info
            for character in self._script.first_night_order:
                player = get_night_player(character)
                if player is None:
                    continue
                
                match character:
                    case Minion.POISONER:
                        self._poisoner_power(player, night_start_game_state)
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
                        self._fortuneteller_power(player, night_start_game_state)
                    case Outsider.BUTLER:
                        self._butler_power(player, night_start_game_state)
            
        # Other nights
        else:
            for character in self._script.other_night_order:
                player = get_night_player(character)
                if player is None:
                    continue
                
                match character:
                    case Minion.POISONER:
                        self._poisoner_power(player, night_start_game_state)
                    case Townsfolk.MONK:
                        self._monk_power(player, night_start_game_state)
                    case Minion.SPY:
                        self._spy_power(player)
                    case Demon.IMP:
                        self._imp_power(player, night_start_game_state)
                    case Townsfolk.RAVENKEEPER:
                        self._ravenkeeper_power(player, night_start_game_state)
                    case Townsfolk.UNDERTAKER:
                        self._undertaker_power(player)
                    case Townsfolk.EMPATH:
                        self._empath_power(player)
                    case Townsfolk.FORTUNETELLER:
                        self._fortuneteller_power(player, night_start_game_state)
                    case Outsider.BUTLER:
                        self._butler_power(player, night_start_game_state)

            # Announce deaths at the end of the night
            alive_at_end = {player.name for player in self._players if player.alive}
            died_during_night = alive_at_start - alive_at_end
            
            if died_during_night:
                if len(died_during_night) == 1:
                    dead_player_name = list(died_during_night)[0]
                    self._broadcast_info("Storyteller", self._all_players(), f"This morning, {dead_player_name} was found dead and is now a ghost.", 
                                        EventType.DEATH_ANNOUNCEMENT,
                                        metadata={
                                            "dead_players": [dead_player_name],
                                            "recipients": [p.name for p in self._all_players()]
                                        })
                else:
                    dead_players = ", ".join(sorted(died_during_night))
                    self._broadcast_info("Storyteller", self._all_players(), f"This morning, {dead_players} were found dead and are now ghosts.", 
                                        EventType.DEATH_ANNOUNCEMENT,
                                        metadata={
                                            "dead_players": sorted(list(died_during_night)),
                                            "recipients": [p.name for p in self._all_players()]
                                        })
            else:
                self._broadcast_info("Storyteller", self._all_players(), "This morning, everyone is still alive.", 
                                    EventType.DEATH_ANNOUNCEMENT,
                                    metadata={
                                        "dead_players": [],
                                        "recipients": [p.name for p in self._all_players()]
                                    })

    
    def _slayer_power(self, player: Player, action: SlayerPowerAction) -> bool:

        if player.character == Townsfolk.SLAYER:
            self._reminder_tokens[Townsfolk.SLAYER] = {ReminderTokens.SLAYER_POWER_USED: player}

        it_works: bool = (player.character == Townsfolk.SLAYER and 
                          not self._is_drunk_or_poisoned(player) and 
                          isinstance(self._player_dict[action.target].character, Demon))

        metadata = {
            "player_name": player.name,
            "target": action.target,
            "success": it_works,
            "private_reasoning": action.private_reasoning,
            "public_reasoning": action.public_reasoning,
            "thinking": action.thinking
        }

        # If it works
        if it_works:
            self._kill_player(self._player_dict[action.target])
            self._broadcast_info("Storyteller", self._all_players(), 
                f"{player.name} has used their slayer power on {action.target} and killed them. Their reasoning: {action.public_reasoning}",
                event_type=EventType.SLAYER_POWER,
                metadata=metadata)
        # If it doesn't work
        else:
            self._broadcast_info("Storyteller", self._all_players(),
                f"{player.name} has used their slayer power on {action.target} and nothing happened. Their reasoning: {action.public_reasoning}",
                event_type=EventType.SLAYER_POWER, 
                metadata=metadata)

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
                                metadata={"player_name": player.name, "nominee": action.nominee, "thinking": action.thinking})
            return False
        except ValueError:
            logger.error(f"Player {player.name} tried to nominate {action.nominee} but they have already been nominated today.")
            self._broadcast_info("Storyteller", self._all_players(), f"{player.name} cannot nominate {action.nominee} because they have already been nominated today.",
                                description=f"{player.name} cannot nominate {action.nominee} because they have already been nominated today.",
                                metadata={"player_name": player.name, "nominee": action.nominee, "thinking": action.thinking})
            return False
        
        nominee.nominated_today = True
        player.used_nomination = True

        # If the nominee is the Virgin and they haven't used their power yet, use their power
        if nominee.character == Townsfolk.VIRGIN and ReminderTokens.VIRGIN_POWER_USED not in self._reminder_tokens.get(Townsfolk.VIRGIN, {}):
            self._reminder_tokens[Townsfolk.VIRGIN] = {ReminderTokens.VIRGIN_POWER_USED: nominee}
            if Townsfolk in self._get_player_roles(player) and not self._is_drunk_or_poisoned(nominee):            
                self._kill_player(player)
                self._broadcast_info(sender="Storyteller",
                                    recipients=self._all_players(), 
                                    info=f"{player.name} has nominated {nominee.name} for execution. {player.name} has been executed and the day is over.",
                                    event_type=EventType.VIRGIN_POWER,
                                    metadata={"nominee": nominee.name, "nominator": player.name, "thinking": action.thinking})
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
                                 "nominator": player.name,
                                 "nominee": nominee.name, 
                                 "public_reasoning": action.public_reasoning, 
                                 "private_reasoning": action.private_reasoning,
                                 "current_chopping_block": {
                                     "nominee": self._chopping_block[1].name if self._chopping_block else None,
                                     "votes": self._chopping_block[0] if self._chopping_block else None
                                 },
                                 "thinking": action.thinking
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
        previous_votes: list[tuple[str, Vote, str, str]] = []  # Now includes private and public reasoning
        
        # Start voting with the nominee, then continue with other players
        nominee_index = self._players.index(nominee)
        voting_order = self._players[nominee_index:] + self._players[:nominee_index]
        
        for player in voting_order:
            # Check if this player is the Butler and has a master choice
            butler_master_choice = None
            if (player.character == Outsider.BUTLER and 
                Outsider.BUTLER in self._reminder_tokens and 
                ReminderTokens.BUTLER_MASTER in self._reminder_tokens[Outsider.BUTLER]):
                butler_master_choice = self._reminder_tokens[Outsider.BUTLER][ReminderTokens.BUTLER_MASTER].name
            
            vote, private_reasoning, public_reasoning, thinking = player.vote(
                nominee=nominee.name,
                public_game_state=self._get_public_game_state(),
                current_tally=count,
                required_to_tie=required_to_tie,
                required_to_nominate=required_to_nominate,
                previous_votes=previous_votes,
                nomination_action=action,
                butler_player_choice=butler_master_choice
            )

            previous_votes.append((player.name, vote, private_reasoning, public_reasoning))
            
            # Record the event
            self.event_tracker.add_event(
                event_type=EventType.VOTING,
                description=f"{player.name} voted {vote.value} on {nominee.name}'s nomination. Reasoning: {public_reasoning}",
                round_number=self._round_number,
                phase=self._current_phase.value,
                participants=[player.name],
                metadata={
                    "voter": player.name,
                    "nominee": nominee.name,
                    "vote": vote.value,
                    "private_reasoning": private_reasoning,
                    "public_reasoning": public_reasoning,
                    "thinking": thinking
                }
            )
            
            if vote == Vote.YES:
                count += 1

        # Prepare metadata once
        metadata = {
            "nominator": action.nominator,
            "nominee": nominee.name,
            "votes": count,
            "required_to_nominate": required_to_nominate,
            "required_to_tie": required_to_tie,
            "vote_details": [{"voter": name, "vote": vote.value, "private_reasoning": private_reasoning, "public_reasoning": public_reasoning} for name, vote, private_reasoning, public_reasoning in previous_votes],
            "thinking": action.thinking
        }
        # Set result and message based on vote outcome
        if count >= required_to_nominate:
            self._chopping_block = (count, nominee)
            metadata["result"] = "success"
            message = f"{nominee.name} has been nominated for execution with {count} votes. They will die at the end of the day if no one else is nominated."
        elif required_to_tie is not None and count == required_to_tie:
            self._chopping_block = None
            metadata["result"] = "tie"
            message = f"{nominee.name} has received {count} votes. This ties the previous nominee. The chopping block is now empty."
        else:
            # Failed nomination - not enough votes
            metadata["result"] = "failed" 
            message = f"{nominee.name}'s nomination failed with {count} votes (needed {required_to_nominate})."

        # Add vote record to message and broadcast result
        message += f" Vote record: {format_vote_history(previous_votes)}"
        self._broadcast_info("Storyteller", self._all_players(), message, EventType.NOMINATION_RESULT, metadata=metadata)

        return False


    def _run_day_phase(self) -> Alignment | None:
        self._current_phase = Phase.DAY
        self._nominations_open = False  # Close nominations at the start of each day
        self._clear_night_tokens()
        for player in self._players:
            player.start_of_day()

        # Print character summary at the start of each day
        self._print_status_summary()

        # Allow one round of messaging, then open nominations
        loops = 4
        consecutive_passes = 0
        for i in range(loops):
            if i == 2:  # Open nominations on the third iteration
                self._nominations_open = True
                self._broadcast_info("Storyteller", self._all_players(), "Nominations are now open.", EventType.NOMINATIONS_OPEN)
        
            day_players: list[Player] = list(self._players)
            random.shuffle(day_players)

            # Calculate remaining action rounds
            remaining_rounds = loops - 1 - i
            end_day_early = False
            for player in day_players:
                 # Check if we should end the day early before player action
                if self._should_end_day_early(consecutive_passes):
                    end_day_early = True
                    break
                
                remaining_retries = 2
                finsihed_action = False
                # We sometimes get invalid action parameters, so we retry a few times if that happens
                while not finsihed_action and remaining_retries > 0:
                    action: DayAction | None = player.day_action(self._get_public_game_state(), self._nominations_open, remaining_rounds)

                    if isinstance(action, NoAction):
                        consecutive_passes += 1
                    else:
                        consecutive_passes = 0

                    try:
                        if isinstance(action, MessageAction):
                            # Validate recipients
                            for recipient in action.recipients:
                                if recipient not in self._player_dict:
                                    raise Exception(f"Invalid recipient: {recipient} - not found in player dictionary. action.recipients: {action.recipients}")
                            self._broadcast_info(
                                player.name, 
                                action.recipients, 
                                action.message, 
                                EventType.MESSAGE,
                                metadata={
                                    "sender": player.name,
                                    "recipients": action.recipients,
                                    "message": action.message,
                                    "thinking": action.thinking
                                },
                                include_sender_in_history=True
                            )
                        elif isinstance(action, NominationAction):
                            # Validate nominee
                            if action.nominee not in self._player_dict:
                                raise Exception(f"Invalid nominee: {action.nominee} - not found in player dictionary.")
                            # Valid nomination - process it
                            if self._run_nomination(player, action):
                                return None  # End the day if someone died from the Virgin's power
                        elif isinstance(action, SlayerPowerAction):
                            # Validate target
                            if action.target not in self._player_dict:
                                raise Exception(f"Invalid Slayer target: {action.target} - not found in player dictionary.")
                            # Dead players cannot use abilities (but this should be handled by the Player class)
                            if self._slayer_power(player, action):
                                game_over = self._game_over()
                                if game_over:
                                    return game_over
                        elif isinstance(action, NoAction):
                            # Send private confirmation to the player who passed
                            self._broadcast_info(
                                "Storyteller", 
                                player, 
                                f"You passed your turn. Your reasoning: {action.private_reasoning}",
                                EventType.PLAYER_PASS,
                                metadata={
                                    "player_name": player.name,
                                    "private_reasoning": action.private_reasoning,
                                    "thinking": action.thinking
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error in day action: remaining_retries: {remaining_retries}, {e}")
                        remaining_retries -= 1
                        self.event_tracker.add_event(
                            event_type=EventType.ERROR,
                            description=f"Error in day action: {e}",
                            round_number=self._round_number,
                            phase=self._current_phase.value,
                            participants=[player.name],
                        )
                        return None
                    else:
                        finsihed_action = True

            if end_day_early:
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
                game_state=self._get_enhanced_game_state_for_logging(),
                metadata={"executed_player": executed_player.name}
            )
            
            # Mark for Undertaker if they're alive
            if Townsfolk.UNDERTAKER in self._character_dict and self._character_dict[Townsfolk.UNDERTAKER].alive:
                self._reminder_tokens[Townsfolk.UNDERTAKER][ReminderTokens.UNDERTAKER_EXECUTED] = executed_player
            
            self._chopping_block = None
            self._kill_player(executed_player)

            if executed_player.character == Outsider.SAINT:
                self._broadcast_info("Storyteller", self._all_players(), f"{executed_player.name} was a Saint and has been executed. Evil has won.",
                                    EventType.SAINT_EXECUTED,
                                    metadata={"executed_player": executed_player.name})
                return Alignment.EVIL
            
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
        self.event_tracker.add_event(
            event_type=EventType.GAME_START,
            description=f"Blood on the Clocktower game started with {len(self._players)} players",
            round_number=self._round_number,
            phase=self._current_phase.value,
            participants=[p.name for p in self._players],
            game_state=self._get_enhanced_game_state_for_logging(),
            metadata={
                "max_rounds": max_rounds, 
                "players": [p.name for p in self._players],
                "player_count": len(self._players)
            }
        )
        
        logger.info("Initial game state:")
        self._print_status_summary()
        
        try:
            # Handle initial setup phase transition
            if self._current_phase == Phase.SETUP:
                self.event_tracker.add_event(
                    event_type=EventType.PHASE_CHANGE,
                    description=f"Setup phase complete, transitioning to Night phase",
                    round_number=self._round_number,
                    phase="NIGHT",
                    game_state=self._get_enhanced_game_state_for_logging()
                )
                self._current_phase = Phase.NIGHT
            
            while self._round_number <= max_rounds:
                # Only add night phase change event if we're not already in night phase
                if self._current_phase != Phase.NIGHT:
                    self.event_tracker.add_event(
                        event_type=EventType.PHASE_CHANGE,
                        description=f"Night phase begins",
                        round_number=self._round_number,
                        phase="NIGHT",
                        game_state=self._get_enhanced_game_state_for_logging()
                    )
                
                self._run_night_phase()

                for player in self._players:
                    thinking = player.summarize_history(self._get_public_game_state(), clear_history=self._round_number > 1)
                    
                    # Track the notes update event
                    self.event_tracker.add_event(
                        event_type=EventType.NOTES_UPDATE,
                        description=f"{player.name} updated their notes",
                        round_number=self._round_number,
                        phase=self._current_phase.value,
                        participants=[player.name],
                        game_state=self._get_enhanced_game_state_for_logging(),
                        metadata={
                            "player_name": player.name, 
                            "character": player.character.value, 
                            "notes": player.notes,
                            "thinking": thinking
                        }
                    )

                game_over = self._game_over()
                if game_over:
                    self._end_game(game_over)
                    return game_over
                    
                self.event_tracker.add_event(
                    event_type=EventType.PHASE_CHANGE,
                    description=f"Day phase begins",
                    round_number=self._round_number,
                    phase="DAY",
                    game_state=self._get_enhanced_game_state_for_logging()
                )
                
                game_over = self._run_day_phase()
                if game_over:
                    self._end_game(game_over)
                    return game_over

                game_over = self._game_over()
                if game_over:
                    self._end_game(game_over)
                    return game_over

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
            description = f"{winner.value} team wins!"
        else:
            description = "Maximum rounds reached, no winner"
        
        # Get API cost summary
        cost_tracker = get_cost_tracker()
        cost_summary = cost_tracker.get_summary()
        
        # Get comprehensive game statistics
        game_stats = self.event_tracker.get_game_statistics()
            
        self.event_tracker.add_event(
            event_type=EventType.GAME_END,
            description=description,
            round_number=self._round_number,
            phase=self._current_phase.value,
            game_state=self._get_enhanced_game_state_for_logging(),
            metadata={
                "winner": winner.value if winner else None,
                "api_cost_summary": cost_summary,
                "game_statistics": game_stats
            }
        )