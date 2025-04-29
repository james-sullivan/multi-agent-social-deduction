from game import Alignment, Vote

class Player:
    def __init__(self, name: str, alignment: Alignment) -> None:
        self.name: str = name
        self.alive: bool = True
        self.history: list[str] = []
        self.notes: str = ""
        self._alignment: Alignment = alignment      

    def get_alignment(self) -> Alignment:
        return self._alignment

    def give_info(self, info: str) -> None:
        self.history.append(info)

    def vote(self, 
             public_game_state: dict, 
             previous_votes: list[tuple[str, Vote]], 
             bulter_player_choice: str | None = None) -> Vote:
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

        return Vote.YES