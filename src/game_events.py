from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class EventType(Enum):
    """Types of events that can occur in the game"""
    GAME_START = "game_start"
    ROUND_START = "round_start"
    PHASE_CHANGE = "phase_change"
    PLAYER_DEATH = "player_death"
    CHARACTER_POWER = "character_power"
    NOMINATION = "nomination"
    VOTING = "voting"
    EXECUTION = "execution"
    MESSAGE = "message"
    GAME_END = "game_end"
    INFO_BROADCAST = "info_broadcast"
    NOTES_UPDATE = "notes_update"
    PLAYER_PASS = "player_pass"
    PLAYER_SETUP = "player_setup"
    STORYTELLER_INFO = "storyteller_info"

@dataclass
class GameEvent:
    """Represents a single event in the game"""
    timestamp: str
    round_number: int
    phase: str
    event_type: EventType
    description: str
    participants: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.participants is None:
            self.participants = []
        if self.metadata is None:
            self.metadata = {}

class GameEventTracker:
    """Tracks and manages all events during a Blood on the Clocktower game"""
    
    def __init__(self):
        self.events: List[GameEvent] = []
        self._game_start_time = datetime.now()
        
    def add_event(self, 
                  event_type: EventType,
                  description: str,
                  round_number: int,
                  phase: str,
                  participants: Optional[List[str]] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a new event to the tracker"""
        event = GameEvent(
            timestamp=datetime.now().isoformat(),
            round_number=round_number,
            phase=phase,
            event_type=event_type,
            description=description,
            participants=participants or [],
            metadata=metadata or {}
        )
        self.events.append(event)
        self._print_event(event)
        
    def _print_event(self, event: GameEvent) -> None:
        """Print an event in an elegant format"""
        # Color codes for different event types
        colors = {
            EventType.GAME_START: "\033[1;32m",      # Bold green
            EventType.ROUND_START: "\033[1;34m",     # Bold blue
            EventType.PHASE_CHANGE: "\033[1;36m",    # Bold cyan
            EventType.PLAYER_DEATH: "\033[1;31m",    # Bold red
            EventType.CHARACTER_POWER: "\033[1;35m", # Bold magenta
            EventType.NOMINATION: "\033[1;33m",      # Bold yellow
            EventType.VOTING: "\033[0;33m",          # Yellow
            EventType.EXECUTION: "\033[1;31m",       # Bold red
            EventType.MESSAGE: "\033[0;37m",         # White
            EventType.GAME_END: "\033[1;32m",        # Bold green
            EventType.INFO_BROADCAST: "\033[0;37m",  # White
            EventType.NOTES_UPDATE: "\033[1;94m",    # Light blue
            EventType.PLAYER_PASS: "\033[0;90m",     # Dark gray
            EventType.PLAYER_SETUP: "\033[1;96m",    # Bright cyan
            EventType.STORYTELLER_INFO: "\033[1;97m", # Bright white
        }
        
        reset = "\033[0m"
        color = colors.get(event.event_type, "\033[0;37m")
        
        # Format timestamp
        time_str = datetime.fromisoformat(event.timestamp).strftime("%H:%M:%S")
        
        # Create prefix based on event type
        prefix_map = {
            EventType.GAME_START: "🎮 GAME",
            EventType.ROUND_START: "🌅 ROUND",
            EventType.PHASE_CHANGE: "🌙 PHASE",
            EventType.PLAYER_DEATH: "💀 DEATH",
            EventType.CHARACTER_POWER: "✨ POWER",
            EventType.NOMINATION: "⚖️  NOMINATION",
            EventType.VOTING: "🗳️  VOTE",
            EventType.EXECUTION: "⚔️  EXECUTION",
            EventType.MESSAGE: "💬 MESSAGE",
            EventType.GAME_END: "🏁 GAME END",
            EventType.INFO_BROADCAST: "📢 INFO",
            EventType.NOTES_UPDATE: "📝 NOTES",
            EventType.PLAYER_PASS: "⏭️  PASS",
            EventType.PLAYER_SETUP: "🔧 SETUP",
            EventType.STORYTELLER_INFO: "🎭 STORYTELLER",
        }
        
        prefix = prefix_map.get(event.event_type, "📝 EVENT")
        
        # Special formatting for messages
        if event.event_type == EventType.MESSAGE:
            # Extract sender and recipients from the description format: "sender → recipients: message"
            description = event.description
            if " → " in description and ": " in description:
                arrow_split = description.split(" → ", 1)
                sender = arrow_split[0]
                rest = arrow_split[1]
                colon_split = rest.split(": ", 1)
                recipients = colon_split[0]
                message = colon_split[1] if len(colon_split) > 1 else ""
                
                # Highlight sender in cyan and recipients in yellow
                sender_highlight = f"\033[1;36m{sender}\033[0m"  # Bold cyan
                recipients_highlight = f"\033[1;33m{recipients}\033[0m"  # Bold yellow
                
                formatted_description = f"{sender_highlight} → {recipients_highlight}: {message}"
                print(f"{color}[{time_str}] {prefix}: {formatted_description}{reset}")
            else:
                # Fallback to original format if parsing fails
                if event.participants:
                    participants_str = f" [{', '.join(event.participants)}]"
                else:
                    participants_str = ""
                print(f"{color}[{time_str}] {prefix}: {event.description}{participants_str}{reset}")
        # Special formatting for notes updates
        elif event.event_type == EventType.NOTES_UPDATE:
            participants_str = f" [{', '.join(event.participants)}]" if event.participants else ""
            print(f"{color}[{time_str}] {prefix}: {event.description}{participants_str}{reset}")
            
            # Display the notes content if available
            if event.metadata and "notes" in event.metadata:
                notes = event.metadata["notes"]
                character = event.metadata.get("character", "Unknown")
                
                # Format notes with indentation and character info
                print(f"{color}    Character: {character}{reset}")
                print(f"{color}    Notes:{reset}")
                
                # Split notes into lines and indent each line
                notes_lines = notes.split('\n')
                for line in notes_lines:
                    if line.strip():  # Only print non-empty lines
                        print(f"{color}      {line}{reset}")
                print()  # Add empty line after notes
        else:
            # Format the output
            if event.participants:
                participants_str = f" [{', '.join(event.participants)}]"
            else:
                participants_str = ""
            
            print(f"{color}[{time_str}] {prefix}: {event.description}{participants_str}{reset}")
        
    def print_round_summary(self, round_number: int) -> None:
        """Print a summary of events for a specific round"""
        round_events = [e for e in self.events if e.round_number == round_number]
        if not round_events:
            return
            
        print(f"\n\033[1;34m{'='*60}")
        print(f"               ROUND {round_number} SUMMARY")
        print(f"{'='*60}\033[0m")
        
        for event in round_events:
            if event.event_type not in [EventType.ROUND_START, EventType.PHASE_CHANGE]:
                time_str = datetime.fromisoformat(event.timestamp).strftime("%H:%M:%S")
                print(f"  [{time_str}] {event.description}")
        print()
        
    def save_to_json(self, filename: Optional[str] = None) -> str:
        """Save all events to a JSON file"""
        if filename is None:
            timestamp = self._game_start_time.strftime("%Y%m%d_%H%M%S")
            filename = f"game_log_{timestamp}.json"
            
        # Convert events to dictionaries for JSON serialization
        events_data = []
        for event in self.events:
            event_dict = asdict(event)
            # Convert enum to string
            event_dict['event_type'] = event.event_type.value
            events_data.append(event_dict)
            
        game_data = {
            "game_start_time": self._game_start_time.isoformat(),
            "total_events": len(self.events),
            "events": events_data
        }
        
        # Ensure the logs directory exists
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        filepath = logs_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(game_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Game events saved to {filepath}")
            print(f"\033[1;32m📁 Game log saved to: {filepath}\033[0m")
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to save game events to JSON: {e}")
            raise
            
    def get_events_by_type(self, event_type: EventType) -> List[GameEvent]:
        """Get all events of a specific type"""
        return [e for e in self.events if e.event_type == event_type]
        
    def get_events_by_round(self, round_number: int) -> List[GameEvent]:
        """Get all events from a specific round"""
        return [e for e in self.events if e.round_number == round_number]
        
    def get_game_statistics(self) -> Dict[str, Any]:
        """Generate game statistics from tracked events"""
        stats: Dict[str, Any] = {
            "total_events": len(self.events),
            "total_rounds": max((e.round_number for e in self.events), default=0),
            "events_by_type": {},
            "deaths": [],
            "executions": [],
            "nominations": [],
        }
        
        for event in self.events:
            event_type_str = event.event_type.value
            events_by_type = stats["events_by_type"]
            events_by_type[event_type_str] = events_by_type.get(event_type_str, 0) + 1
            
            if event.event_type == EventType.PLAYER_DEATH:
                stats["deaths"].append(event.participants[0] if event.participants else "Unknown")
            elif event.event_type == EventType.EXECUTION:
                stats["executions"].append(event.participants[0] if event.participants else "Unknown")
            elif event.event_type == EventType.NOMINATION:
                if event.participants and len(event.participants) >= 2:
                    stats["nominations"].append(f"{event.participants[0]} → {event.participants[1]}")
                    
        return stats 