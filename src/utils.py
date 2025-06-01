import sys

# Use different import paths depending on how the file is being run
try:
    from game_enums import Vote
except ModuleNotFoundError:
    # Fall back to prefixed import when run from outside src directory
    from src.game_enums import Vote

def format_vote_history(votes) -> str:
    """Format the vote history as a comma-separated string"""
    if not votes:
        return "No votes cast yet."
        
    return ", ".join([f"{name}: {vote.value}" for name, vote, _, _ in votes])


