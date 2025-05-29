from __future__ import annotations
from game_enums import Alignment, Vote
from characters import Character
from typing import Optional, List, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from game import PublicGameState
import json
from anthropic.types import ToolParam
from player_tools import get_message_tool, get_slayer_tool, PASS_TOOL, VOTE_TOOL, get_nomination_tool, get_night_choice_tool
from enum import Enum
from prompts import BOTC_RULES
from scripts import TROUBLE_BREWING_CHARACTERS
from dataclasses import dataclass
from inference import request_llm_response
import re

logger = logging.getLogger(__name__)

class DayActions(Enum):
    MESSAGE = "message"
    NOMINATION = "nomination"
    SLAYER_POWER = "slayer_power"
    VOTE = "vote"
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
    nominator: str
    private_reasoning: str
    public_reasoning: str
    
    def __init__(self, nominee: str, nominator: str, private_reasoning: str, public_reasoning: str):
        super().__init__(DayActions.NOMINATION, private_reasoning)  # Use private reasoning as the internal reason
        self.nominee = nominee
        self.nominator = nominator
        self.private_reasoning = private_reasoning
        self.public_reasoning = public_reasoning

@dataclass
class SlayerPowerAction(DayAction):
    target: str
    private_reasoning: str
    public_reasoning: str
    
    def __init__(self, target: str, private_reasoning: str, public_reasoning: str):
        super().__init__(DayActions.SLAYER_POWER, private_reasoning)  # Use private reasoning as internal reason
        self.target = target
        self.private_reasoning = private_reasoning
        self.public_reasoning = public_reasoning

@dataclass
class VoteAction(DayAction):
    vote: Vote
    private_reasoning: str
    public_reasoning: str
    
    def __init__(self, vote: Vote, private_reasoning: str, public_reasoning: str):
        super().__init__(DayActions.VOTE, private_reasoning)  # Use private reasoning as internal reason
        self.vote = vote
        self.private_reasoning = private_reasoning
        self.public_reasoning = public_reasoning

@dataclass
class NoAction(DayAction):
    private_reasoning: str
    
    def __init__(self, private_reasoning: str = "No action taken"):
        super().__init__(DayActions.NO_ACTION, private_reasoning)
        self.private_reasoning = private_reasoning


class Player:
    def __init__(self, name: str, alignment: Alignment, character: Character, drunk_character: Character | None = None, model: str = "claude-3-5-haiku-20241022") -> None:
        self.name: str = name
        self.alive: bool = True
        self.history: list[str] = []
        self.notes: str = "No notes so far."
        self.alignment: Alignment = alignment
        self.character: Character = character
        self.used_once_per_game: dict[DayActions, bool] = {action: False for action in ONCE_PER_GAME_ACTIONS}
        self.used_nomination: bool = False
        self.nominated_today: bool = False
        self.used_dead_vote: bool = False
        self.drunk_character: Character | None = None
        self.model: str = model

    def start_of_day(self) -> None:
        self.used_nomination = False
        self.nominated_today = False

    def give_info(self, info: str) -> None:
        self.history.append(info)

    def _get_cached_system_prompt(self, public_game_state: PublicGameState) -> list[str]:
        """Get the cached system prompt (rules, characters, and identity) - cacheable."""
        rules_and_chars = f"""<rules>
{BOTC_RULES}
</rules>
<characters>
{public_game_state.character_str}
</characters>
<role_counts>
This game was set up with {public_game_state.original_role_counts['townsfolk']} Townsfolk, {public_game_state.original_role_counts['outsider']} Outsider(s), {public_game_state.original_role_counts['minion']} Minion(s), and {public_game_state.original_role_counts['demon']} Demon (before any Baron modifications).
</role_counts>"""

        seating_explanation = f"The seating order is important for several game mechanics such as voting order and character abilities. The seat adjacency wraps from the first to the last. For example, {public_game_state.player_state[0]['name']} is adjacent to {public_game_state.player_state[-1]['name']} and {public_game_state.player_state[1]['name']}."

        player_info = f"""{seating_explanation}

You are a player in Blood on the Clocktower.
Your name is {self.name}.
Your character is {self.character.value if self.drunk_character is None else self.drunk_character.value}.
Your primary identity is a player. Your character only tells you what ability you have and it does not define how you need to act.
You are on the {self.alignment.name} team.
Remember to always act with your team's win condition in mind. Analyze the current game state carefully before making decisions.

IMPORTANT:
- Ghost players can still receive and send messages
- Do not exclude ghost players from messages just because they are ghosts
- Information you receive is potentially false because of drunkenness, poisioning, and players lying
- You will never have perfect information, do not wait for perfect information to take action or to vote YES on a nomination
- The day will be played in cycles where each player gets one chance to act per cycle. The order that players act in is randomized at the start of each cycle. 
"""

        return [rules_and_chars, player_info]

    def _get_dynamic_system_prompt(self, public_game_state: PublicGameState) -> str:
        """Get the dynamic system prompt (current state, chopping block, nominations, player state) - changes frequently."""
        # Add player state information
        player_state = "Here is the publicly available player state in the order they are sitting in:" + ", ".join([json.dumps(player) for player in public_game_state.player_state])
        
        # Add chopping block information
        chopping_block_info = ""
        if public_game_state.chopping_block is not None:
            chopping_block_info = f"Current execution nominee: {public_game_state.chopping_block.nominee} with {public_game_state.chopping_block.votes} votes. They will be executed at the end of the day unless someone else gets more votes."
        else:
            chopping_block_info = "No one is currently nominated for execution."

        # Add nominatable players information
        nomination_info = ""
        if public_game_state.nominatable_players:
            nomination_info = f"Players who can currently be nominated: {', '.join(public_game_state.nominatable_players)}"
        else:
            nomination_info = "No players can currently be nominated."

        return f"""<player_order>
{player_state}
</player_order>

<current_state>
It is round {public_game_state.round_number} and the current phase is {public_game_state.current_phase}.
You are {'alive' if self.alive else f'a ghost and you have {'not' if not self.used_dead_vote else ''} used your ghost vote'}. 
You have {"not" if self.used_nomination else ""} nominated today.
</current_state>

<game_state>
{chopping_block_info}
{nomination_info}
</game_state>

<notes>
{self.notes}
</notes>"""

    def _get_history_prompt(self) -> str:
        """Get the history prompt - not cached since it changes frequently."""
        return f"""<history>
{"\n".join(self.history)}
</history>"""


    def summarize_history(self, public_game_state: PublicGameState, clear_history: bool = True) -> None:
        """Summarize the player's history into their notes using AI."""
        if not self.history:
            self.notes = "No notes so far."
            return
        
        # Use prefix caching for better performance (no redundancy)
        user_message = "It's time to update your notes. This first half of your notes should be a summary of your history. After this update your history will be cleared so make sure that all of the important information is included in your notes. The second half of your notes should be five bullet points of actionable strategy advice that you want to follow to help your team win. If there are already five bullet points, update them based on the new information. Only give me your updated notes, no other text and use bullet points. You only need to note information that is not in the rest of your system prompt. Do not make this longer than 20 lines."
        
        response = request_llm_response(
            user_message=user_message,
            model=self.model,
            cached_system_prompt_strs=self._get_cached_system_prompt(public_game_state),
            non_cached_system_prompt_strs=[
                self._get_dynamic_system_prompt(public_game_state),
                self._get_history_prompt()
            ]
        )
        
        if isinstance(response, str):
            self.notes = response
        else:
            logger.error(f"{self.name} failed to summarize history: {response}")
            self.notes = "No notes so far."

        if clear_history:
            self.history = []

    def vote(self,
             nominee: str,
             public_game_state: PublicGameState,
             current_tally: int,
             required_to_tie: int | None,
             required_to_nominate: int,
             previous_votes: list[tuple[str, Vote, str, str]],  # Now includes private and public reasoning
             nomination_action: NominationAction,
                            butler_player_choice: str | None = None) -> tuple[Vote, str, str]:
        """
        Use the voting tool to get the player's vote and reasoning.
        Returns a tuple of (Vote, private_reasoning, public_reasoning).
        """
        
        if not self.alive and self.used_dead_vote:
            return Vote.CANT_VOTE, "Cannot vote - already used ghost vote", "Cannot vote - already used ghost vote"

        # The butler cannot vote if the player they chose didn't vote yes
        if butler_player_choice:
            found_player = False
            # Find the butler's player choice in previous votes
            for player_name, vote, _, _ in previous_votes:
                if player_name == butler_player_choice:
                    # If the butler's choice didn't vote yes, we vote no
                    if vote != Vote.YES:
                        return Vote.NO, "Butler restriction - master didn't vote yes", "Butler restriction - master didn't vote yes"
                    found_player = True
                    break
            if not found_player:
                return Vote.NO, "Butler restriction - master hasn't voted yet", "Butler restriction - master hasn't voted yet"

        # Nominator context
        if nomination_action.nominator == self.name:
            nominator_context = f"You are the player who nominated {nominee} and you should STRONGLY consider voting YES since you initiated this nomination. Your private reasoning for nominating them is:\n{nomination_action.private_reasoning}\n\nRemember: If you don't vote YES on your own nomination, it sends a confusing signal to other players and makes the nomination much less likely to succeed."
        else:
            nominator_context = f"The player who nominated {nominee} is {nomination_action.nominator} and their reason for nominating them is:\n{nomination_action.public_reasoning}"

        # Get the player's vote based on the game state and previous votes
        if nominee == self.name:
            nominee_context = "You are the nominee for execution."
            question = "Should you vote YES or NO on this nomination? As the nominee, you typically want to vote NO unless you have a strategic reason to vote YES (like proving your innocence through death)."
        else:
            nominee_context = f"The nominee for execution is {nominee}."
            # Add context about current game state
            alive_count = sum(1 for p in public_game_state.player_state if p['alive'])
            if alive_count <= 3:
                urgency_context = "WARNING: With only a few players left alive, this decision is CRITICAL. The Evil team wins if only 2 players remain alive."
            else:
                urgency_context = "Consider whether this execution will help your team gather information or eliminate a threat."
            question = f"Should you vote YES or NO on this nomination? {urgency_context} Consider all relevant information."

        if required_to_tie:
            required_votes_context = f"{required_to_nominate} votes are required to execute the nominee. {required_to_tie} votes are required to tie the previous nominee."
        else:
            required_votes_context = f"{required_to_nominate} votes are required to execute the nominee."

        # Format previous votes for context, including public reasoning only
        votes_context = "Previous votes in this nomination:\n"
        for voter_name, vote, _, public_reasoning in previous_votes:
            votes_context += f"- {voter_name}: {vote.value} (Reasoning: {public_reasoning})\n"
        
        user_message = f"""
You need to vote on the current nomination.
{nominator_context}
{nominee_context}
{current_tally} votes have been cast so far.
{required_votes_context}
{votes_context}

{question}

Use the vote tool to cast your vote and provide your reasoning. Your reasoning will be shared with all players who vote after you.

IMPORTANT: You do not need perfect information to vote YES on a nomination. Both good and evil players need to vote YES to kill the other team and get closer to winning. Voting YES to kill the other team is an important part of the game.
"""
        
        response = request_llm_response(
            user_message=user_message,
            model=self.model,
            cached_system_prompt_strs=self._get_cached_system_prompt(public_game_state),
            non_cached_system_prompt_strs=[
                self._get_dynamic_system_prompt(public_game_state),
                self._get_history_prompt()
            ],
            tools=[VOTE_TOOL]
        )
        
        # Handle the response
        if isinstance(response, dict) and "function_name" in response:
            function_name = response["function_name"]
            arguments = response.get("arguments", {})
            
            if function_name == "vote":
                vote_str = arguments.get("vote", "NO").upper()
                private_reasoning = arguments.get("private_reasoning", "No private reasoning provided")
                public_reasoning = arguments.get("public_reasoning", "No public reasoning provided")
                
                if vote_str == "YES":
                    if not self.alive:
                        self.used_dead_vote = True
                    return Vote.YES, private_reasoning, public_reasoning
                elif vote_str == "NO":
                    return Vote.NO, private_reasoning, public_reasoning
                else:
                    logger.error(f"{self.name} voted with invalid vote: {vote_str}")
                    return Vote.NO, f"Invalid vote response: {vote_str}", f"Invalid vote response: {vote_str}"
        
        logger.error(f"{self.name} failed to use voting tool properly: {response}")
        return Vote.NO, "Failed to vote properly", "Failed to vote properly"

    def day_action(self, public_game_state: PublicGameState, nominations_open: bool = False, remaining_action_rounds: int = 0) -> Optional[DayAction]:
        available_tools: List[ToolParam] = []

        if nominations_open and not self.used_nomination and self.alive:
            available_tools.append(get_nomination_tool(public_game_state.nominatable_players))

        action_to_tool = { 
            DayActions.SLAYER_POWER: get_slayer_tool([player['name'] for player in public_game_state.player_state]),
        }
        
        # Add any once-per-game tools that haven't been used yet
        if self.alive:
            for action, used in self.used_once_per_game.items():
                if not used and action in action_to_tool:
                    available_tools.append(action_to_tool[action])

        # Always allow messaging
        available_tools.append(get_message_tool([player['name'] for player in public_game_state.player_state]))


        # Always add the pass tool as an option when other tools are available
        available_tools.append(PASS_TOOL)

        # Add information about remaining action rounds
        rounds_info = ""
        if remaining_action_rounds > 0:
            rounds_info = f" After this round, there will be {remaining_action_rounds} more chances to act before the day ends."
        elif remaining_action_rounds == 0:
            rounds_info = " This is the final round of day actions before the day ends."

        user_message = f"It is your turn to either take an action or pass.{rounds_info} Consider things like your notes, what team you are on, and what has happened so far. Be a little hesistant to nominate someone. What do you want to do?"
        
        response = request_llm_response(
            user_message=user_message,
            model=self.model,
            cached_system_prompt_strs=self._get_cached_system_prompt(public_game_state),
            non_cached_system_prompt_strs=[
                self._get_dynamic_system_prompt(public_game_state),
                self._get_history_prompt()
            ],
            tools=available_tools
        )
        
        # Handle the response based on whether it's a tool response or not
        if isinstance(response, dict) and "function_name" in response:
            function_name = response["function_name"]
            arguments = response.get("arguments", {})
            
            if function_name == "send_message":
                recipients = arguments.get("recipients", [])
                message_text = arguments.get("message", "")
                return MessageAction(recipients, message_text)
                
            elif function_name == "nominate":
                player = arguments.get("player", "")
                private_reasoning = arguments.get("private_reasoning", "No private reasoning provided")
                public_reasoning = arguments.get("public_reasoning", "No public reasoning provided")
                return NominationAction(player, self.name, private_reasoning, public_reasoning)
                
            elif function_name == "slayer_power":
                target = arguments.get("target", "")
                private_reasoning = arguments.get("private_reasoning", "No private reasoning provided")
                public_reasoning = arguments.get("public_reasoning", "No public reasoning provided")
                self.used_once_per_game[DayActions.SLAYER_POWER] = True
                return SlayerPowerAction(target, private_reasoning, public_reasoning)
                
            elif function_name == "pass":
                private_reasoning = arguments.get("private_reasoning", "No private reasoning provided")
                return NoAction(private_reasoning)
        else:
            logger.error(f"{self.name} chose an invalid action: {response}")
                
        # Default if no action was taken or there was an error
        return NoAction("Did not choose a valid action")
     
    def night_player_choice(self, public_game_state: PublicGameState, prompt: str) -> tuple[list[str], str]:        
        user_message = "Use the night_choice tool to make your selection and provide your reasoning."

        response = request_llm_response(
            user_message=user_message,
            model=self.model,
            cached_system_prompt_strs=self._get_cached_system_prompt(public_game_state),
            non_cached_system_prompt_strs=[
                self._get_dynamic_system_prompt(public_game_state),
                self._get_history_prompt()
            ],
            tools=[get_night_choice_tool(prompt, [player['name'] for player in public_game_state.player_state])]
        )

        # Handle the response
        if isinstance(response, dict) and "function_name" in response:
            function_name = response["function_name"]
            arguments = response.get("arguments", {})
            
            if function_name == "night_choice":
                player_choice = arguments.get("player_choice", [])
                private_reasoning = arguments.get("private_reasoning", "")
                
                if player_choice and isinstance(player_choice, list) and len(player_choice) > 0:
                    # Log the private reasoning for debugging/analysis
                    logger.info(f"{self.name} night choice reasoning: {private_reasoning}")
                    return player_choice, private_reasoning
                else:
                    logger.error(f"{self.name} provided empty or invalid player choice: {player_choice}")
            else:
                logger.error(f"{self.name} used wrong tool: {function_name}")
        else:
            logger.error(f"{self.name} failed to use night choice tool: {response}")

        # Return empty list if there was an error
        return [], ""
        