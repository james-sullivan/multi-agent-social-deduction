from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from typing import Optional, Dict, Any, List, Union, TypedDict, cast

# Client will be initialized lazily
_client: Optional[Anthropic] = None

def get_client() -> Anthropic:
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        _client = Anthropic()
    return _client

class CreateMessageArgs(TypedDict, total=False):
    model: str
    max_tokens: int
    system: str
    messages: List[MessageParam]
    tools: List[ToolParam]
    tool_choice: Dict[str, str]


def request_llm_response(
    system_prompt: str,
    user_message: str,
    model: str = "claude-3-5-haiku-20241022",
    max_tokens: int = 1024,
    tools: Optional[List[ToolParam]] = None
) -> Union[str, Dict[str, Any]]:
    """
    Send a request to the LLM and return the response.
    
    Args:
        system_prompt: System prompt with context
        user_message: User message content
        model: Model to use
        max_tokens: Maximum tokens in response
        tools: Optional list of tools to use
        
    Returns:
        Either a string response (when no tools) or a dict with tool usage info
    """
    try:
        # Prepare message
        messages: List[MessageParam] = [
            {
                "role": "user",
                "content": user_message
            }
        ]
        
        # Create arguments for messages.create
        args: CreateMessageArgs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages
        }
        
        # Add tools if provided
        if tools:
            args["tools"] = tools
            args["tool_choice"] = {"type": "any"}
        
        # Make API call
        client = get_client()
        message = client.messages.create(**cast(Dict[str, Any], args))
        
        # Handle response based on whether tools were used
        if tools:
            # Check for tool usage
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "tool_use":
                    # Return tool usage information
                    return {
                        "function_name": content_block.name,
                        "arguments": content_block.input if hasattr(content_block, 'input') else {}
                    }
            # No tool was used, return text response if available
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "text":
                    return content_block.text
            return ""
        else:
            # Just return the text response
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "text":
                    return content_block.text
            return ""
            
    except Exception as e:
        print(f"Error making API request: {e}")
        return "" if not tools else {}
