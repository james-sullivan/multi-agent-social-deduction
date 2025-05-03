from game import Alignment, Vote
from characters import Character
from typing import Optional, List, Dict, Any, cast, TypedDict
import json
import os
from anthropic import Anthropic, APIStatusError
from anthropic.types import Message, MessageParam, ToolParam, ToolChoiceParam
from player_tools import MESSAGE_TOOL, SLAYER_TOOL, NOMINATION_TOOL
from enum import Enum
from prompts import BOTC_RULES, TROUBLE_BREWING_SCRIPT
from dataclasses import dataclass

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
    player: str
    
    def __init__(self, player: str, reason: str):
        super().__init__(DayActions.NOMINATION, reason)
        self.player = player

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
    def __init__(self, name: str, alignment: Alignment, character: Optional[Character] = None) -> None:
        self.name: str = name
        self.alive: bool = True
        self.history: list[str] = []
        self.notes: str = "No notes so far."
        self.alignment: Alignment = alignment
        self.character: Optional[Character] = character
        self.used_once_per_game: dict[DayActions, bool] = {action: False for action in ONCE_PER_GAME_ACTIONS}
        self.messages_left: int = 3
        self.used_nomination: bool = False
        self.used_dead_vote: bool = False

    def end_of_day(self) -> None:
        self.used_nomination = False
        self.messages_left = 3

    def give_info(self, info: str) -> None:
        self.history.append(info)

    def vote(self,
             client: Anthropic,
             nominee: str,
             public_player_state: dict,
             current_tally: int,
             required_votes: int,
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
        system_prompt = self._get_player_system_prompt(public_player_state)
        
        if nominee == self.name:
            nominee_context = "You are the nominee for execution. "
        else:
            nominee_context = f"The nominee for execution is {nominee}. "

        required_votes_context = f"{required_votes} votes are required to execute the nominee."

        # Format previous votes for context
        votes_context = "Previous votes in this nomination:\n"
        for voter_name, vote in previous_votes:
            votes_context += f"- {voter_name}: {vote.name}\n"
        
        message = client.messages.create(
            model="claude-3-5-haiku-20240307",
            max_tokens=100,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"""
You need to vote on the current nomination.
{nominee_context}
{current_tally} have been cast so far.
{required_votes_context}
{votes_context}

Should you vote YES or NO on this nomination? Consider the game state, your character's abilities, and the previous votes.
Respond with only 'YES' or 'NO'.
"""
                }
            ]
        )
        
        response = message.content[0].text.strip().upper()
            
        # Return the appropriate vote
        if response == "YES":
            if not self.alive:
                self.used_dead_vote = True
            return Vote.YES
        else:
            return Vote.NO
    
    def _get_player_system_prompt(self, public_player_state: list[dict]) -> str:
        if self.character:
            character_prompt = f"Your character is {self.character.name}."
        else:
            character_prompt = ""

        game_state = "Here is the publicly available player state in the order they are sitting in:" + ", ".join([json.dumps(player) for player in public_player_state])
        seating_explanation = f"The seating order is important for several game mechanics such as voting order and character abilities. The seat adjacency wraps from the first to the last. For example, {public_player_state[0]['name']} is adjacent to {public_player_state[-1]['name']} and {public_player_state[1]['name']}."

        system_prompt = BOTC_RULES + "\n\n" + \
            TROUBLE_BREWING_SCRIPT + "\n\n" + \
            f"You are a player. Your name is {self.name}. You are on the {self.alignment.name} team. " + \
            character_prompt + "\n" + \
            f"You are {'alive' if self.alive else f'dead and you have {'not' if not self.used_dead_vote else ''} used your dead vote'}. " + \
            f"You have {"not" if self.used_nomination else ""} nominated today. " + \
            f"You have {self.messages_left} messages left that you can send today. " + "\n" + \
            game_state + "\n" + \
            seating_explanation + "\n" + \
            "Here are your notes summarizing the game state:" + "\n" + \
            self.notes + "\n" + \
            "Here's a complete history of the current day:" + "\n" + \
            "\n".join(self.history)

        return system_prompt
    
    def day_action(self, client: Anthropic, public_player_state: list[dict], nominations_open: bool = False) -> Optional[DayAction]:
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

        # This player has nothing left to do
        if not available_tools:
            return NoAction("No available actions left")        
      
        system_prompt = self._get_player_system_prompt(public_player_state)
        
        # Add history to provide context
        history_context = "\n".join(self.history) if self.history else "No prior information available."
        
        # Use ONLY the Anthropic SDK to make the call with the messages.create() method
        try:
            # Prepare message with correct types
            user_message: MessageParam = {
                "role": "user", 
                "content": "It is your turn to either take an action or pass. What do you want to do?"
            }
            
            # Use client.messages.create() directly
            message = client.messages.create(
                model="claude-3-5-haiku-20240307",
                max_tokens=1024,
                system=system_prompt,
                messages=[user_message],
                tools=available_tools,
                tool_choice={"type": "any"}
            )
            
            # Process the raw response for tools
            for content_block in message.content:
                # Check if we have a tool use block
                if hasattr(content_block, 'type') and content_block.type == "tool_use":
                    # For safely accessing tool properties
                    function_name = content_block.name
                    arguments_dict: Dict[str, Any] = {}
                    
                    # Extract input arguments safely
                    if hasattr(content_block, 'input'):
                        arguments_dict = cast(Dict[str, Any], content_block.input)
                    
                    # Process different tool types
                    if function_name == "send_message":
                        # Process message action - safely access dictionary values
                        recipients: List[str] = []
                        message_text: str = ""
                        
                        # Get recipients list
                        if isinstance(arguments_dict, dict) and "recipients" in arguments_dict:
                            recipients = cast(List[str], arguments_dict["recipients"])
                        
                        # Get message text
                        if isinstance(arguments_dict, dict) and "message" in arguments_dict:
                            message_text = cast(str, arguments_dict["message"])
                        
                        # Update state
                        self.messages_left -= 1
                        
                        # Create and return action object
                        return MessageAction(recipients, message_text)
                        
                    elif function_name == "nominate":
                        # Process nomination action - safely access dictionary values
                        player: str = ""
                        reason: str = "No reason provided"
                        
                        # Get player
                        if isinstance(arguments_dict, dict) and "player" in arguments_dict:
                            player = cast(str, arguments_dict["player"])
                        
                        # Get reason
                        if isinstance(arguments_dict, dict) and "reason" in arguments_dict:
                            reason = cast(str, arguments_dict["reason"])
                        
                        # Update state
                        self.used_nomination = True
                        
                        # Create and return action object
                        return NominationAction(player, reason)
                        
                    elif function_name == "slayer_power":
                        # Process slayer power action - safely access dictionary values
                        target: str = ""
                        
                        # Get target
                        if isinstance(arguments_dict, dict) and "target" in arguments_dict:
                            target = cast(str, arguments_dict["target"])
                        
                        # Update state
                        self.used_once_per_game[DayActions.SLAYER_POWER] = True
                        
                        # Create and return action object
                        return SlayerPowerAction(target)
                    elif function_name == "pass":
                        return NoAction(f"{self.name} passed on their turn")
                    else:
                        return NoAction(f"{self.name} did not choose a tool")
                       
            return NoAction("No action taken")
        except APIStatusError as e:
            error_msg = f"API Error: {e.status_code} - {e.message}"
            print(error_msg)
            return NoAction(f"No Action: API Error: {e.status_code}")
        except Exception as e:
            error_msg = f"Error making API request: {e}"
            print(error_msg)
            return NoAction(f"No Action: Exception: {str(e)[:50]}...")