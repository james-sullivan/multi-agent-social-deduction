from anthropic.types import ToolParam

# Message tool for players to send messages to others
MESSAGE_TOOL = ToolParam(
    name="send_message",
    description="Send a message to one or more players. The message should be no more than 4 sentences. You have a limited number of messages you can send per day. Send a message to everyone if you want to talk publicly or send a message to only one or a few players if you want to talk privately.",
    input_schema={
        "type": "object",
        "properties": {
            "recipients": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of player names to send the message to."
            },
            "message": {
                "type": "string",
                "description": "The message content to send to the recipients."
            }
        },
        "required": ["recipients", "message"]
    }
)

# Slayer tool for using the one-time special ability
SLAYER_TOOL = ToolParam(
    name="slayer_power",
    description="Pick a player, if they are a Demon they will die. This power can only be used once per game.",
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

# Nomination tool for eliminating players
NOMINATION_TOOL = ToolParam(
    name="nominate",
    description="Nominate a player for execution. This will start a vote to execute the nominated player. You can only nominate once per day and each player can only be nominated once per day. The reason you provide will be shared with the other players and should convince them to vote with you.",
    input_schema={
        "type": "object",
        "properties": {
            "player": {
                "type": "string",
                "description": "The player to nominate for execution. If you want to nominate Susan, you would put 'Susan' here."
            },
            "reason": {
                "type": "string",
                "description": "The reasoning for nominating the player. This will be shared with the other players and should convince them to vote with you."
            }
        },
        "required": ["player", "reason"]
    }
)

PASS_TOOL = ToolParam(
    name="pass",
    description="Choose not to take an action at this time. You may or may not have a chance to act again today.",
    input_schema={
        "type": "object",

        "reason": {
            "type": "string",
            "description": "The reasoning for passing on your turn. This will be shared with the other players."
        }
    },
    "required": ["reason"],
    }
)

TROUBLE_BREWING_TOOLS = [SLAYER_TOOL]