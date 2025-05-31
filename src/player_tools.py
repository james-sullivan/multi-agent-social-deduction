from anthropic.types import ToolParam

# Function to generate message tool with current player names
def get_message_tool(player_names: list[str]) -> ToolParam:
    """Generate a message tool with the current list of player names as enum options."""
    return ToolParam(
        name="send_message",
        description="Send a message to one or more players. Saying that you nominate someone will not actually nominate them, it will just send a message to the other players. You need to use the nominate tool to actually nominate someone.",
        input_schema={
            "type": "object",
            "properties": {
                "recipients": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": player_names
                    },
                    "description": "An array of players (or player) you want to send the message to. IMPORTANT: GHOST PLAYERS ARE STILL PLAYING THE GAME, THEY CAN STILL RECEIVE MESSAGES AND PLAY AN IMPORTANT ROLE IN THE GAME. DO NOT EXCLUDE GHOST PLAYERS JUST BECAUSE THEY ARE GHOSTS."
                },
                "message": {
                    "type": "string",
                    "description": "The message content to send to the recipients. The message should be no more than 3 sentences."
                }
            },
            "required": ["recipients", "message"]
        }
    )

# Vote tool for players to vote on nominations
VOTE_TOOL = ToolParam(
    name="vote",
    description="Cast your vote on the current nomination. You must vote either YES or NO and provide both private and public reasoning for your vote. Only your public reasoning will be shared with other players. Think carefully about who you are voting to execute and how that will affect the game.",
    input_schema={
        "type": "object",
        "properties": {
            "vote": {
                "type": "string",
                "enum": ["YES", "NO"],
                "description": "Your vote on the nomination. YES means you want to execute the nominee, NO means you don't want to execute them."
            },
            "private_reasoning": {
                "type": "string",
                "description": "Your private strategic reasoning for this vote. This will NOT be shared with other players and can include your true thoughts, team strategy, etc. Limit to one short sentence."
            },
            "public_reasoning": {
                "type": "string",
                "description": "Your public reasoning for this vote. This will be shared with all players who vote after you. Limit to one short sentence."
            }
        },
        "required": ["vote", "private_reasoning", "public_reasoning"]
    }
)

# Function to generate slayer tool with current player names
def get_slayer_tool(player_names: list[str]) -> ToolParam:
    """Generate a slayer tool with the current list of player names as enum options."""
    return ToolParam(
        name="slayer_power",
        description="Pick a player, if they are a Demon they will die. This power can only be used once per game and will only work if you are the Slayer. It only makes sense to use this tool if you are claiming to be the Slayer.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "enum": player_names,
                    "description": "The name of the player to use the slayer power on. For example, if you want to use the power on Jace, you would put 'Jace' here."
                },
                "private_reasoning": {
                    "type": "string",
                    "description": "Your private strategic reasoning for using the slayer power on this target. This will NOT be shared with other players and can include your true thoughts, team strategy, etc. Limit to 1 sentence."
                },
                "public_reasoning": {
                    "type": "string",
                    "description": "Your public reasoning for using the slayer power on this target. This will be shared with all players. Limit to 1 sentence."
                }
            },
            "required": ["target", "private_reasoning", "public_reasoning"]
        }
    )

def get_nomination_tool(nominatable_players: list[str]) -> ToolParam:
    """Generate a nomination tool with the current list of nominatable players."""
    return ToolParam(
        name="nominate",
        description="Nominate a player for execution. This will start a vote to execute the nominated player. You can only nominate once per day and each player can only be nominated once per day. You must provide both private reasoning (for your own strategic thinking) and public reasoning (what others will hear).",
        input_schema={
            "type": "object",
            "properties": {
                "player": {
                    "type": "string",
                    "enum": nominatable_players,
                    "description": "The name of the player to nominate for execution. This should only be one of the players that are still nominatable today which are listed in the enum"
                },
                "private_reasoning": {
                    "type": "string",
                    "description": "Your private strategic reasoning for this nomination. This will NOT be shared with other players and can include your true thoughts, team strategy, etc. Limit of 2 sentences."
                },
                "public_reasoning": {
                    "type": "string", 
                    "description": "The public reasoning you want to share with all other players. Limit of 2 sentences."
                }
            },
            "required": ["player", "private_reasoning", "public_reasoning"]
        }
    )

PASS_TOOL = ToolParam(
    name="pass",
    description="Choose not to take an action at this time. You may only pass once per day so be hesitant to use this tool.",
    input_schema={
        "type": "object",
        "properties": {
            "private_reasoning": {
                "type": "string",
                "description": "Your private reasoning for passing on your turn. This will NOT be shared with other players and can include your true thoughts, team strategy, etc. Limit to one sentence."
            }
        },
        "required": ["private_reasoning"]
    }
)

def get_night_choice_tool(prompt: str, available_players: list[str]) -> ToolParam:
    """Generate a night choice tool with the given prompt as the description and available players as enum options."""
    return ToolParam(
        name="night_choice",
        description=prompt,
        input_schema={
            "type": "object",
            "properties": {
                "player_choice": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": available_players
                    },
                    "description": "The player name(s) you are choosing from the available options. For abilities that require multiple players, include all required players in this array."
                },
                "private_reasoning": {
                    "type": "string",
                    "description": "Your private reasoning for this choice. This will not be shared with other and can include your true thoughts, team strategy, etc. Limit of 2 sentences."
                }
            },
            "required": ["player_choice", "private_reasoning"]
        }
    )
