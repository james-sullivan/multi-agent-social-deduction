from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union, cast
import logging
from abc import ABC, abstractmethod

from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, AIMessage, SystemMessage

logger = logging.getLogger(__name__)

class Agent:
    def __init__(self, name: str, role: Role, model: Optional[ChatAnthropic] = None, debug: bool = False):
        self.name = name
        self.role = role
        self.alive = True
        self.debug = debug
        
        # Configure the model with appropriate verbosity
        if model:
            self.model = model
        else:
            # Initialize the ChatAnthropic model
            # Note: We're not setting timeout or stop as we'll use the defaults
            # Setting those explicitly would require the extra imports from langchain_core
            self.model = ChatAnthropic(
                model_name="claude-3-5-haiku-20241022",
                verbose=debug
            )
            
        self.known_werewolves: List[str] = []
        self.investigation_results: Dict[str, bool] = {}
        self.game_history: List[str] = []
        
        # Set up role-specific system prompt
        if role == Role.VILLAGER:
            self.system_prompt = self._create_villager_prompt()
        elif role == Role.WEREWOLF:
            self.system_prompt = self._create_werewolf_prompt()
        elif role == Role.SEER:
            self.system_prompt = self._create_seer_prompt()
            
        if debug:
            logger.debug(f"Created {role.name} agent '{name}' with debug mode enabled")
    
    
    def set_known_werewolves(self, werewolves: List[str]) -> None:
        if self.role == Role.WEREWOLF:
            self.known_werewolves = werewolves
    
    def receive_investigation_result(self, player: str, is_werewolf: bool) -> None:
        if self.role == Role.SEER:
            self.investigation_results[player] = is_werewolf
    
    def update_game_state(self, game_state: Any) -> None:
        """Update agent with latest game state"""
        # Record the most recent event
        if game_state.history:
            latest_events = game_state.history[-3:] if len(game_state.history) > 3 else game_state.history
            for event in latest_events:
                if event not in self.game_history:
                    self.game_history.append(event)
    
    def night_action(self, alive_players: List[str], alive_werewolves: List[str]) -> Optional[str]:
        """Perform night action based on role"""
        if not self.alive or not alive_players:
            return None
        
        # Remove self from potential targets
        potential_targets = [p for p in alive_players if p != self.name]
        if not potential_targets:
            return None
            
        if self.role == Role.WEREWOLF:
            # Werewolves decide who to eliminate
            # Format the information about known werewolves
            werewolf_info = f"Known werewolves: {', '.join(self.known_werewolves)}"
            # Format the list of potential targets
            targets_info = f"Potential targets: {', '.join(potential_targets)}"
            # Format game history
            history_info = "\n".join(self.game_history[-10:]) if self.game_history else "No history yet"
            
            prompt = f"""You are {self.name}, a werewolf deciding which villager to eliminate during the night phase.

{werewolf_info}

{targets_info}

Recent game history:
{history_info}

Choose ONE player to eliminate. Your choice should be strategic to help werewolves win.
Respond with just the name of the player you wish to eliminate."""
            
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ]
            
            response = self.model.invoke(messages).content
            # Make sure we're working with a string
            response_text = cast(str, response)
            # Extract just the player name from response
            for player in potential_targets:
                if player.lower() in response_text.lower():
                    return player
            
            # If no valid target found in response, pick randomly from potential_targets
            import random
            return random.choice(potential_targets)
            
        elif self.role == Role.SEER:
            # Format the list of potential investigation targets
            targets_info = f"Potential investigation targets: {', '.join(potential_targets)}"
            # Format previous investigation results
            investigation_results_info = "Previous investigation results:\n"
            for player, is_werewolf in self.investigation_results.items():
                result = "IS a werewolf" if is_werewolf else "is NOT a werewolf"
                investigation_results_info += f"- {player}: {result}\n"
            
            # Format game history
            history_info = "\n".join(self.game_history[-10:]) if self.game_history else "No history yet"
            
            prompt = f"""You are {self.name}, the Seer deciding which player to investigate during the night phase.

{targets_info}

{investigation_results_info}

Recent game history:
{history_info}

Choose ONE player to investigate. Your choice should be strategic to help identify werewolves.
Respond with just the name of the player you wish to investigate."""
            
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt)
            ]
            
            response = self.model.invoke(messages).content
            # Make sure we're working with a string
            response_text = cast(str, response)
            # Extract just the player name from response
            for player in potential_targets:
                if player.lower() in response_text.lower():
                    return player
            
            # If no valid target found in response, pick randomly from potential_targets
            import random
            return random.choice(potential_targets)
        
        return None
    
    def discuss(self, discussion: List[Tuple[str, str]]) -> str:
        """Participate in day phase discussion"""
        if not self.alive:
            return ""
        
        # Format the current discussion
        discussion_text = ""
        for speaker, message in discussion:
            discussion_text += f"{speaker}: {message}\n"
        
        # Format game history
        history_info = "\n".join(self.game_history[-10:]) if self.game_history else "No history yet"
        
        # Role-specific information
        role_info = ""
        if self.role == Role.WEREWOLF:
            role_info = f"Known werewolves: {', '.join(self.known_werewolves)}\n"
            role_info += "Remember to hide your identity as a werewolf!"
        elif self.role == Role.SEER:
            role_info = "Investigation results:\n"
            for player, is_werewolf in self.investigation_results.items():
                result = "IS a werewolf" if is_werewolf else "is NOT a werewolf"
                role_info += f"- {player}: {result}\n"
            
        prompt = f"""You are {self.name}, participating in the day discussion of Werewolf.

Current discussion:
{discussion_text}

Recent game history:
{history_info}

{role_info}

Contribute to the discussion by sharing your thoughts, suspicions, or defending yourself.
Keep your response brief (1-3 sentences) and in-character."""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt)
        ]
        
        response = self.model.invoke(messages).content
        # Make sure we're working with a string
        return cast(str, response)
    
    def vote(self, alive_players: List[str], discussion: List[Tuple[str, str]]) -> Optional[str]:
        """Vote for a player to eliminate during day phase"""
        if not self.alive:
            return None
        
        # Remove self from potential targets
        potential_targets = [p for p in alive_players if p != self.name]
        if not potential_targets:
            return None
        
        # Format the current discussion
        discussion_text = ""
        for speaker, message in discussion:
            discussion_text += f"{speaker}: {message}\n"
        
        # Format game history
        history_info = "\n".join(self.game_history[-10:]) if self.game_history else "No history yet"
        
        # Role-specific information
        role_info = ""
        if self.role == Role.WEREWOLF:
            role_info = f"Known werewolves: {', '.join(self.known_werewolves)}\n"
            role_info += "Vote strategically to protect werewolves and eliminate villagers."
        elif self.role == Role.SEER:
            role_info = "Investigation results:\n"
            for player, is_werewolf in self.investigation_results.items():
                result = "IS a werewolf" if is_werewolf else "is NOT a werewolf"
                role_info += f"- {player}: {result}\n"
        
        prompt = f"""You are {self.name}, voting in the day phase of Werewolf.

Potential players to vote for: {', '.join(potential_targets)}

Discussion summary:
{discussion_text}

Recent game history:
{history_info}

{role_info}

Based on the discussion and your knowledge, vote for ONE player to eliminate.
Respond with just the name of the player you're voting for."""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt)
        ]
        
        response = self.model.invoke(messages).content
        # Make sure we're working with a string
        response_text = cast(str, response)
        # Extract just the player name from response
        for player in potential_targets:
            if player.lower() in response_text.lower():
                return player
        
        # If no valid target found in response, pick randomly from potential_targets
        import random
        return random.choice(potential_targets) 