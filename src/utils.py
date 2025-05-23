from game_enums import Vote

def format_vote_history(votes: list[tuple[str, Vote]]) -> str:
    """Format a list of vote tuples into a single line string."""
    if not votes:
        return "No votes cast yet."
    return ", ".join(f"{name}: {vote.value}" for name, vote in votes)


