from anthropic.types import ToolParam

# Message tool for players to send messages to others
MESSAGE_TOOL = ToolParam(
    name="send_message",
    description="Send a message to one or more players. The message should be no more than 3 sentences. Send a message to everyone if you want to talk publicly or send a message to only one or a few players if you want to talk privately. Dead players are still in the game and can make decisions.",
    input_schema={
        "type": "object",
        "properties": {
            "recipients": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of player names to send the message to. For example, if you want to send a message to Susan and John, you would put ['Susan', 'John'] here."
            },
            "message": {
                "type": "string",
                "description": "The message content to send to the recipients."
            }
        },
        "required": ["recipients", "message"]
    }
)

# Vote tool for players to vote on nominations
VOTE_TOOL = ToolParam(
    name="vote",
    description="Cast your vote on the current nomination. You must vote either YES or NO and provide both private and public reasoning for your vote. Only your public reasoning will be shared with other players.",
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

# Slayer tool for using the one-time special ability
SLAYER_TOOL = ToolParam(
    name="slayer_power",
    description="Pick a player, if they are a Demon they will die. This power can only be used once per game and will only work if you are the Slayer. It only makes sense to use this tool if you are claiming to be the Slayer.",
    input_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "The name of the player to use the slayer power on. If you want to use the power on Jace, you would put 'Jace' here."
            }
        },
        "required": ["target"]
    }
)

def get_nomination_tool(nominatable_players: list[str]) -> ToolParam:
    """Generate a nomination tool with the current list of nominatable players."""
    players_list = ", ".join(nominatable_players)
    
    return ToolParam(
        name="nominate",
        description="Nominate a player for execution. This will start a vote to execute the nominated player. You can only nominate once per day and each player can only be nominated once per day. You must provide both private reasoning (for your own strategic thinking) and public reasoning (what others will hear).",
        input_schema={
            "type": "object",
            "properties": {
                "player": {
                    "type": "string",
                    "description": f"The player to nominate for execution. Must be one of: {players_list}"
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

# Static nomination tool for backwards compatibility (will be replaced by dynamic version)
NOMINATION_TOOL = get_nomination_tool([])

PASS_TOOL = ToolParam(
    name="pass",
    description="Choose not to take an action at this time. You may or may not have a chance to act again today.",
    input_schema={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "The reasoning for passing on your turn. This will be shared with the other players."
            }
        },
        "required": ["reason"]
    }
)

TROUBLE_BREWING_TOOLS = [SLAYER_TOOL]