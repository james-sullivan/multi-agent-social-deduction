from __future__ import annotations
from game_enums import Alignment, Vote
from characters import Character
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from game import PublicGameState
import json
from anthropic.types import ToolParam
from player_tools import MESSAGE_TOOL, SLAYER_TOOL, NOMINATION_TOOL, PASS_TOOL
from enum import Enum
from prompts import BOTC_RULES
from scripts import TROUBLE_BREWING_CHARACTERS
from dataclasses import dataclass
from inference import request_llm_response

class DayActions(Enum):
    MESSAGE = "message"
    NOMINATION = "nomination"
    SLAYER_POWER = "slayer_power"
    NO_ACTION = "no_action"

ONCE_PER_GAME_ACTIONS = [DayActions.SLAYER_POWER]

@dataclass
class DayAction:
    action: DayActions
    reason: str

@dataclass
class MessageAction(DayAction):
    recipients: List[str]
    message: str
    
    def __init__(self, recipients: List[str], message: str, reason: str = ""):
        super().__init__(DayActions.MESSAGE, reason)
        self.recipients = recipients
        self.message = message

@dataclass
class NominationAction(DayAction):
    nominee: str
    
    def __init__(self, nominee: str, reason: str):
        super().__init__(DayActions.NOMINATION, reason)
        self.nominee = nominee

@dataclass
class SlayerPowerAction(DayAction):
    target: str
    
    def __init__(self, target: str, reason: str = ""):
        super().__init__(DayActions.SLAYER_POWER, reason)
        self.target = target

@dataclass
class NoAction(DayAction):
    def __init__(self, reason: str = "No action taken"):
        super().__init__(DayActions.NO_ACTION, reason)


class Player:
    def __init__(self, name: str, alignment: Alignment, character: Character, drunk_character: Character | None = None) -> None:
        self.name: str = name
        self.alive: bool = True
        self.history: list[str] = []
        self.notes: str = "No notes so far."
        self.alignment: Alignment = alignment
        self.character: Character = character
        self.used_once_per_game: dict[DayActions, bool] = {action: False for action in ONCE_PER_GAME_ACTIONS}
        self.messages_left: int = 2
        self.used_nomination: bool = False
        self.nominated_today: bool = False
        self.used_dead_vote: bool = False
        self.drunk_character: Character | None = None

    def start_of_day(self) -> None:
        self.used_nomination = False
        self.messages_left = 2

    def give_info(self, info: str) -> None:
        self.history.append(info)

    def summarize_history(self, public_game_state: PublicGameState, event_tracker=None) -> None:
        """Summarize the player's history into their notes using AI."""
        if not self.history:
            self.notes = "No notes so far."
            return
        
        system_prompt = self._get_player_system_prompt(public_game_state)
        user_message = "It's time to update your notes using your history of events. You can find your notes in between <notes></notes> tags and history in between <history></history> tags. After this update your history will be cleared so make sure that all of the important information is included in your notes. Only give me your updated notes, no other text and use bullet points. You only need to note information that is not in the rest of your system prompt."
        
        response = request_llm_response(system_prompt, user_message)
        if isinstance(response, str):
            self.notes = response
        else:
            self.notes = "No notes so far."

        # Track the notes update event if tracker is provided
        if event_tracker:
            from game_events import EventType
            event_tracker.add_event(
                event_type=EventType.NOTES_UPDATE,
                description=f"{self.name} updated their notes",
                round_number=public_game_state.round_number,
                phase=public_game_state.current_phase.value,
                participants=[self.name],
                metadata={"character": self.character.value, "notes": self.notes}
            )

        self.history = []

    def vote(self,
             nominee: str,
             public_game_state: PublicGameState,
             current_tally: int,
             required_to_tie: int | None,
             required_to_nominate: int,
             previous_votes: list[tuple[str, Vote]], 
             bulter_player_choice: str | None = None) -> Vote:
        
        if not self.alive and self.used_dead_vote:
            return Vote.CANT_VOTE

        # The butler cannot vote if the player they chose didn't vote yes
        if bulter_player_choice:
            found_player = False
            # Find the butler's player choice in previous votes
            for player, vote in previous_votes:
                if player == bulter_player_choice:
                    # If the butler's choice didn't vote yes, we vote no
                    if vote != Vote.YES:
                        return Vote.NO
                    found_player = True
                    break
            if not found_player:
                return Vote.NO
            
        # Get the player's vote based on the game state and previous votes
        system_prompt = self._get_player_system_prompt(public_game_state)
        
        if nominee == self.name:
            nominee_context = "You are the nominee for execution. "
        else:
            nominee_context = f"The nominee for execution is {nominee}. "

        if required_to_tie:
            required_votes_context = f"{required_to_nominate} votes are required to execute the nominee. {required_to_tie} votes are required to tie the previous nominee. "
        else:
            required_votes_context = f"{required_to_nominate} votes are required to execute the nominee. "

        # Format previous votes for context
        votes_context = "Previous votes in this nomination:\n"
        for voter_name, vote in previous_votes:
            votes_context += f"- {voter_name}: {vote.name}\n"
        
        user_message = f"""
You need to vote on the current nomination.
{nominee_context}
{current_tally} votes have been cast so far.
{required_votes_context}
{votes_context}

Should you vote YES or NO on this nomination? Consider all relevant information.
Respond with only 'YES' or 'NO'.
"""
        
        response = request_llm_response(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=100
        )
        
        # Ensure response is a string and convert to uppercase
        if isinstance(response, str):
            vote_response = response.strip().upper()
            # Return the appropriate vote
            if vote_response == "YES":
                if not self.alive:
                    self.used_dead_vote = True
                return Vote.YES
            else:
                return Vote.NO
        else:
            # Default to NO if there was an issue with the response
            return Vote.NO
    
    def _get_player_system_prompt(self, public_game_state: PublicGameState, inlcude_history: bool = True) -> str:
        game_state = "Here is the publicly available player state in the order they are sitting in:" + ", ".join([json.dumps(player) for player in public_game_state.player_state])
        seating_explanation = f"The seating order is important for several game mechanics such as voting order and character abilities. The seat adjacency wraps from the first to the last. For example, {public_game_state.player_state[0]['name']} is adjacent to {public_game_state.player_state[-1]['name']} and {public_game_state.player_state[1]['name']}."
        
        # Add chopping block information
        chopping_block_info = ""
        if public_game_state.chopping_block is not None:
            chopping_block_info = f"\nCurrent execution nominee: {public_game_state.chopping_block.nominee} with {public_game_state.chopping_block.votes} votes. They will be executed at the end of the day unless someone else gets more votes."
        else:
            chopping_block_info = "\nNo one is currently nominated for execution."

        system_prompt = f"""<rules>
{BOTC_RULES}
</rules>

<characters>
{public_game_state.character_str}
</characters>

<player_state>
You are a player.
Your name is {self.name}.
Your character is {self.character.value if self.drunk_character is None else self.drunk_character.value}. 
You are on the {self.alignment.name} team. 
You are {'alive' if self.alive else f'dead and you have {'not' if not self.used_dead_vote else ''} used your dead vote'}. 
You have {"not" if self.used_nomination else ""} nominated today. 
You have {self.messages_left} messages left that you can send today. 
</player_state>

<game_state>
It is round {public_game_state.round_number} and the current phase is {public_game_state.current_phase}.
{game_state}
{seating_explanation}
{chopping_block_info}
</game_state>

Here are your notes summarizing the previous rounds:
<notes>
{self.notes}
</notes>

Here's your history of the current round from oldest to newest:
<history>
{"\n".join(self.history)}
</history>"""

        return system_prompt
    
    def day_action(self, public_game_state: PublicGameState, nominations_open: bool = False) -> Optional[DayAction]:
        available_tools: List[ToolParam] = []

        if nominations_open and not self.used_nomination and self.alive:
            available_tools.append(NOMINATION_TOOL)

        action_to_tool = { 
            DayActions.SLAYER_POWER: SLAYER_TOOL,
        }
        
        # Add any once-per-game tools that haven't been used yet
        for action, used in self.used_once_per_game.items():
            if not used and action in action_to_tool:
                available_tools.append(action_to_tool[action])

        if self.messages_left > 0:
            available_tools.append(MESSAGE_TOOL)

        # If no meaningful tools are available, just pass automatically
        if not available_tools:
            return NoAction(f"{self.name} has no actions available and passes")

        # Always add the pass tool as an option when other tools are available
        available_tools.append(PASS_TOOL)

        system_prompt = self._get_player_system_prompt(public_game_state)
        user_message = "It is your turn to either take an action or pass. What do you want to do?"
        
        response = request_llm_response(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=available_tools
        )
        
        # Handle the response based on whether it's a tool response or not
        if isinstance(response, dict) and "function_name" in response:
            function_name = response["function_name"]
            arguments = response.get("arguments", {})
            
            if function_name == "send_message":
                recipients = arguments.get("recipients", [])
                message_text = arguments.get("message", "")
                self.messages_left -= 1
                return MessageAction(recipients, message_text)
                
            elif function_name == "nominate":
                player = arguments.get("player", "")
                reason = arguments.get("reason", "No reason provided")
                return NominationAction(player, reason)
                
            elif function_name == "slayer_power":
                target = arguments.get("target", "")
                self.used_once_per_game[DayActions.SLAYER_POWER] = True
                return SlayerPowerAction(target)
                
            elif function_name == "pass":
                return NoAction(f"{self.name} passed on their turn")
                
        # Default if no action was taken or there was an error
        return NoAction(f"{self.name} did not choose a valid action")
    
    def night_player_choice(self, public_game_state: PublicGameState, prompt: str) -> list[str]:
        system_prompt = self._get_player_system_prompt(public_game_state)
        user_message = f"{prompt}\nProvide an explaination of your choice between <thinking> tags, then your choice or choices between <names> tags and seperated by commas. e.g. <names>Bruce, Jacob</names>"

        response = request_llm_response(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=[]
        )

        # Extract player names using regex
        import re
        if isinstance(response, str):
            name_match = re.search(r'<names>(.*?)</names>', response, re.DOTALL)
            if name_match:
                names_str = name_match.group(1)
                return [name.strip() for name in names_str.split(',')]
        
        return []
        