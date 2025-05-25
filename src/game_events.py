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
    GAME_SETUP = "game_setup"
    ROUND_START = "round_start"
    PHASE_CHANGE = "phase_change"
    PLAYER_DEATH = "player_death"
    CHARACTER_POWER = "character_power"  # Keep for backwards compatibility and generic use
    NOMINATION = "nomination"
    NOMINATION_RESULT = "nomination_result"
    VOTING = "voting"
    EXECUTION = "execution"
    MESSAGE = "message"
    GAME_END = "game_end"
    INFO_BROADCAST = "info_broadcast"
    NOTES_UPDATE = "notes_update"
    PLAYER_PASS = "player_pass"
    PLAYER_SETUP = "player_setup"
    STORYTELLER_INFO = "storyteller_info"
    
    # Specific character power events
    WASHERWOMAN_POWER = "washerwoman_power"
    LIBRARIAN_POWER = "librarian_power"
    INVESTIGATOR_POWER = "investigator_power"
    CHEF_POWER = "chef_power"
    EMPATH_POWER = "empath_power"
    FORTUNETELLER_POWER = "fortuneteller_power"
    POISONER_POWER = "poisoner_power"
    SPY_POWER = "spy_power"
    MONK_POWER = "monk_power"
    IMP_POWER = "imp_power"
    RAVENKEEPER_POWER = "ravenkeeper_power"
    UNDERTAKER_POWER = "undertaker_power"
    BUTLER_POWER = "butler_power"
    SLAYER_POWER = "slayer_power"
    VIRGIN_POWER = "virgin_power"
    
    # Special character events
    SCARLET_WOMAN_TRANSFORM = "scarlet_woman_transform"
    MAYOR_WIN = "mayor_win"

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
    public_game_state: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.participants is None:
            self.participants = []
        if self.metadata is None:
            self.metadata = {}
        if self.public_game_state is None:
            self.public_game_state = {}

class GameEventTracker:
    """Tracks and manages all events during a Blood on the Clocktower game"""
    
    def __init__(self, log_filename: Optional[str] = None):
        self.events: List[GameEvent] = []
        self._game_start_time = datetime.now()
        
        # Set up JSONL file for streaming events
        if log_filename is None:
            timestamp = self._game_start_time.strftime("%Y%m%d_%H%M%S")
            log_filename = f"game_log_{timestamp}.jsonl"
        
        # Ensure the logs directory exists
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        self._log_file_path = logs_dir / log_filename
        
        # Open file for writing
        self._log_file = open(self._log_file_path, 'w', encoding='utf-8')
        logger.info(f"Game event log will be written to: {self._log_file_path}")
        print(f"\033[1;32m📁 Game events will be logged to: {self._log_file_path}\033[0m")
        
    def __del__(self):
        """Ensure the log file is closed when the tracker is destroyed"""
        if hasattr(self, '_log_file') and self._log_file and not self._log_file.closed:
            self._log_file.close()
        
    def add_event(self, 
                  event_type: EventType,
                  description: str,
                  round_number: int,
                  phase: str,
                  participants: Optional[List[str]] = None,
                  metadata: Optional[Dict[str, Any]] = None,
                  public_game_state: Optional[Dict[str, Any]] = None) -> None:
        """Add a new event to the tracker and write it immediately to JSONL file"""
        event = GameEvent(
            timestamp=datetime.now().isoformat(),
            round_number=round_number,
            phase=phase,
            event_type=event_type,
            description=description,
            participants=participants or [],
            metadata=metadata or {},
            public_game_state=public_game_state or {}
        )
        self.events.append(event)
        self._print_event(event)
        self._write_event_to_jsonl(event)
        
    def _write_event_to_jsonl(self, event: GameEvent) -> None:
        """Write a single event to the JSONL file"""
        try:
            # Convert event to dictionary for JSON serialization
            event_dict = asdict(event)
            # Convert enum to string
            event_dict['event_type'] = event.event_type.value
            
            # Write as single line JSON
            json_line = json.dumps(event_dict, ensure_ascii=False)
            self._log_file.write(json_line + '\n')
            self._log_file.flush()  # Ensure immediate write to disk
        except Exception as e:
            logger.error(f"Failed to write event to JSONL file: {e}")
        
    def _print_event(self, event: GameEvent) -> None:
        """Print an event in an elegant format"""
        # Color codes for different event types
        colors = {
            EventType.GAME_START: "\033[1;32m",      # Bold green
            EventType.GAME_SETUP: "\033[1;92m",      # Bright green
            EventType.ROUND_START: "\033[1;34m",     # Bold blue
            EventType.PHASE_CHANGE: "\033[1;36m",    # Bold cyan
            EventType.PLAYER_DEATH: "\033[1;31m",    # Bold red
            EventType.CHARACTER_POWER: "\033[1;35m", # Bold magenta
            EventType.NOMINATION: "\033[1;33m",      # Bold yellow
            EventType.NOMINATION_RESULT: "\033[1;93m", # Bright yellow
            EventType.VOTING: "\033[0;33m",          # Yellow
            EventType.EXECUTION: "\033[1;31m",       # Bold red
            EventType.MESSAGE: "\033[0;37m",         # White
            EventType.GAME_END: "\033[1;32m",        # Bold green
            EventType.INFO_BROADCAST: "\033[0;37m",  # White
            EventType.NOTES_UPDATE: "\033[1;94m",    # Light blue
            EventType.PLAYER_PASS: "\033[0;90m",     # Dark gray
            EventType.PLAYER_SETUP: "\033[1;96m",    # Bright cyan
            EventType.STORYTELLER_INFO: "\033[1;97m", # Bright white
            
            # Specific character power colors (all use same color)
            EventType.WASHERWOMAN_POWER: "\033[1;35m",    # Bold magenta
            EventType.LIBRARIAN_POWER: "\033[1;35m",      # Bold magenta
            EventType.INVESTIGATOR_POWER: "\033[1;35m",   # Bold magenta
            EventType.CHEF_POWER: "\033[1;35m",           # Bold magenta
            EventType.EMPATH_POWER: "\033[1;35m",         # Bold magenta
            EventType.FORTUNETELLER_POWER: "\033[1;35m",  # Bold magenta
            EventType.POISONER_POWER: "\033[1;35m",       # Bold magenta
            EventType.SPY_POWER: "\033[1;35m",            # Bold magenta
            EventType.MONK_POWER: "\033[1;35m",           # Bold magenta
            EventType.IMP_POWER: "\033[1;35m",            # Bold magenta
            EventType.RAVENKEEPER_POWER: "\033[1;35m",    # Bold magenta
            EventType.UNDERTAKER_POWER: "\033[1;35m",     # Bold magenta
            EventType.BUTLER_POWER: "\033[1;35m",         # Bold magenta
            EventType.SLAYER_POWER: "\033[1;35m",         # Bold magenta
            EventType.VIRGIN_POWER: "\033[1;35m",         # Bold magenta
            # Special character events
            EventType.SCARLET_WOMAN_TRANSFORM: "\033[1;95m", # Bright magenta
            EventType.MAYOR_WIN: "\033[1;32m",                # Bold green
        }
        
        reset = "\033[0m"
        color = colors.get(event.event_type, "\033[0;37m")
        
        # Format timestamp
        time_str = datetime.fromisoformat(event.timestamp).strftime("%H:%M:%S")
        
        # Create prefix based on event type
        prefix_map = {
            EventType.GAME_START: "🎮 GAME",
            EventType.GAME_SETUP: "⚙️  SETUP",
            EventType.ROUND_START: "🌅 ROUND",
            EventType.PHASE_CHANGE: "🌙 PHASE",
            EventType.PLAYER_DEATH: "💀 DEATH",
            EventType.CHARACTER_POWER: "✨ POWER",
            EventType.NOMINATION: "⚖️ NOMINATION",
            EventType.NOMINATION_RESULT: "✅ VOTE RESULT",
            EventType.VOTING: "🗳️ VOTE",
            EventType.EXECUTION: "⚔️ EXECUTION",
            EventType.MESSAGE: "💬 MESSAGE",
            EventType.GAME_END: "🏁 GAME END",
            EventType.INFO_BROADCAST: "📢 INFO",
            EventType.NOTES_UPDATE: "📝 NOTES",
            EventType.PLAYER_PASS: "⏭️  PASS",
            EventType.PLAYER_SETUP: "🔧 SETUP",
            EventType.STORYTELLER_INFO: "🎭 STORYTELLER",
            
            # Specific character power prefixes
            EventType.WASHERWOMAN_POWER: "🧺 WASHERWOMAN",
            EventType.LIBRARIAN_POWER: "📚 LIBRARIAN", 
            EventType.INVESTIGATOR_POWER: "🔍 INVESTIGATOR",
            EventType.CHEF_POWER: "👨‍🍳 CHEF",
            EventType.EMPATH_POWER: "💝 EMPATH",
            EventType.FORTUNETELLER_POWER: "🔮 FORTUNETELLER",
            EventType.POISONER_POWER: "🧪 POISONER",
            EventType.SPY_POWER: "🕵️ SPY",
            EventType.MONK_POWER: "🙏 MONK",
            EventType.IMP_POWER: "😈 IMP",
            EventType.RAVENKEEPER_POWER: "🐦 RAVENKEEPER",
            EventType.UNDERTAKER_POWER: "⚰️ UNDERTAKER",
            EventType.BUTLER_POWER: "🤵 BUTLER",
            EventType.SLAYER_POWER: "⚔️ SLAYER",
            EventType.VIRGIN_POWER: "👰 VIRGIN",
            # Special character events
            EventType.SCARLET_WOMAN_TRANSFORM: "🔄 SCARLET WOMAN",
            EventType.MAYOR_WIN: "🏛️ MAYOR WIN",
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
                # Fallback to original format if parsing fails - removed participant list
                print(f"{color}[{time_str}] {prefix}: {event.description}{reset}")
        # Special formatting for notes updates
        elif event.event_type == EventType.NOTES_UPDATE:
            # Removed participant list from notes updates
            print(f"{color}[{time_str}] {prefix}: {event.description}{reset}")
            
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
            # Format the output - removed participant list
            print(f"{color}[{time_str}] {prefix}: {event.description}{reset}")
        
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
        
    def close(self) -> str:
        """Close the JSONL file and return the file path"""
        if hasattr(self, '_log_file') and self._log_file and not self._log_file.closed:
            self._log_file.close()
            print(f"\033[1;32m📁 Game log completed: {self._log_file_path}\033[0m")
        return str(self._log_file_path)
        
    def save_to_jsonl(self, filename: Optional[str] = None) -> str:
        """Save all events to a JSONL file (for compatibility, since events are already being written)"""
        if filename is None:
            # Events are already being written to the current file
            return str(self._log_file_path)
        
        # If a different filename is requested, create a copy
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        filepath = logs_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                for event in self.events:
                    event_dict = asdict(event)
                    event_dict['event_type'] = event.event_type.value
                    json_line = json.dumps(event_dict, ensure_ascii=False)
                    f.write(json_line + '\n')
            
            logger.info(f"Game events saved to {filepath}")
            print(f"\033[1;32m📁 Game log saved to: {filepath}\033[0m")
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to save game events to JSONL: {e}")
            raise
    
    def save_to_json(self, filename: Optional[str] = None) -> str:
        """Save all events to a JSON file (legacy format)"""
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
        
def load_events_from_jsonl(filepath: str) -> List[GameEvent]:
    """Load events from a JSONL file"""
    events = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    event_dict = json.loads(line)
                    # Convert event_type string back to enum
                    event_dict['event_type'] = EventType(event_dict['event_type'])
                    
                    # Create GameEvent from dict (need to handle optional fields)
                    event = GameEvent(
                        timestamp=event_dict['timestamp'],
                        round_number=event_dict['round_number'],
                        phase=event_dict['phase'],
                        event_type=event_dict['event_type'],
                        description=event_dict['description'],
                        participants=event_dict.get('participants', []),
                        metadata=event_dict.get('metadata', {}),
                        public_game_state=event_dict.get('public_game_state', {})
                    )
                    events.append(event)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON on line {line_num} in {filepath}: {e}")
                except (KeyError, ValueError) as e:
                    logger.error(f"Invalid event data on line {line_num} in {filepath}: {e}")
                    
    except FileNotFoundError:
        logger.error(f"JSONL file not found: {filepath}")
    except Exception as e:
        logger.error(f"Error reading JSONL file {filepath}: {e}")
        
    return events

def get_game_statistics_from_jsonl(filepath: str) -> Dict[str, Any]:
    """Generate game statistics directly from a JSONL file without loading all events into memory"""
    stats: Dict[str, Any] = {
        "total_events": 0,
        "total_rounds": 0,
        "events_by_type": {},
        "deaths": [],
        "executions": [],
        "nominations": [],
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    event_dict = json.loads(line)
                    stats["total_events"] += 1
                    stats["total_rounds"] = max(stats["total_rounds"], event_dict.get('round_number', 0))
                    
                    event_type = event_dict.get('event_type', 'unknown')
                    stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
                    
                    participants = event_dict.get('participants', [])
                    if event_type == 'player_death' and participants:
                        stats["deaths"].append(participants[0])
                    elif event_type == 'execution' and participants:
                        stats["executions"].append(participants[0])
                    elif event_type == 'nomination' and len(participants) >= 2:
                        stats["nominations"].append(f"{participants[0]} → {participants[1]}")
                        
                except json.JSONDecodeError:
                    continue  # Skip invalid lines
                    
    except Exception as e:
        logger.error(f"Error analyzing JSONL file {filepath}: {e}")
        
    return stats 