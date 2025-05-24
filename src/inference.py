from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from typing import Optional, Dict, Any, List, Union, TypedDict, cast
import logging
import os
from datetime import datetime

# Simple cache logging
def log_cache_info(message: str):
    """Write cache info to log file."""
    os.makedirs("logs", exist_ok=True)
    with open("logs/cache_metrics.log", "a") as f:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{timestamp} - {message}\n")

# Client will be initialized lazily
_client: Optional[Anthropic] = None

def get_client() -> Anthropic:
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        _client = Anthropic()
    return _client

class SystemContentBlock(TypedDict, total=False):
    type: str
    text: str
    cache_control: Dict[str, str]

class CreateMessageArgs(TypedDict, total=False):
    model: str
    max_tokens: int
    system: Union[str, List[SystemContentBlock]]
    messages: List[MessageParam]
    tools: List[ToolParam]
    tool_choice: Dict[str, str]

class CacheMetrics(TypedDict, total=False):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cache_hit: bool
    cache_savings_percent: float

def log_cache_metrics(usage: Any, cache_enabled: bool, is_prefix_cache: bool = False) -> CacheMetrics:
    """Log cache usage metrics."""
    if not cache_enabled:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_hit": False,
            "cache_savings_percent": 0.0
        }
    
    # Extract metrics
    input_tokens = getattr(usage, 'input_tokens', 0)
    output_tokens = getattr(usage, 'output_tokens', 0) 
    cache_creation = getattr(usage, 'cache_creation_input_tokens', 0)
    cache_read = getattr(usage, 'cache_read_input_tokens', 0)
    
    # Log detailed usage metrics for every response
    cache_type = "PREFIX" if is_prefix_cache else "FULL"
    
    # Create detailed log entry with all usage fields
    log_message = f"RESPONSE ({cache_type}) - "
    log_message += f"input_tokens: {input_tokens}, "
    log_message += f"output_tokens: {output_tokens}, "
    log_message += f"cache_creation_input_tokens: {cache_creation}, "
    log_message += f"cache_read_input_tokens: {cache_read}"
    
    log_cache_info(log_message)
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "cache_hit": cache_read > 0,
        "cache_savings_percent": 90.0 if cache_read > 0 else 0.0
    }


def request_llm_response(
    user_message: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
    tools: Optional[List[ToolParam]] = None,
    cache_system: bool = True,
    return_metrics: bool = False,
    static_system_prefix: Optional[str] = None,
    dynamic_system_content: Optional[str] = None
) -> Union[str, Dict[str, Any]]:
    """
    Send a request to the LLM and return the response.
    
    Args:
        user_message: User message content
        model: Model to use
        max_tokens: Maximum tokens in response
        tools: Optional list of tools to use
        cache_system: Whether to cache the system prompt
        return_metrics: Whether to return cache metrics along with response
        static_system_prefix: Static prefix to cache (rules, character info, etc.)
        dynamic_system_content: Dynamic content to append after cached prefix
        
    Returns:
        Either a string response (when no tools) or a dict with tool usage info
        If return_metrics=True, returns a dict with 'response' and 'metrics' keys
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
            "messages": messages
        }
        
        # Handle system prompt with prefix caching
        if static_system_prefix:
            # Create static block with optional caching
            static_block: SystemContentBlock = {
                "type": "text",
                "text": static_system_prefix
            }
            if cache_system:
                static_block["cache_control"] = {"type": "ephemeral"}
            
            system_blocks: List[SystemContentBlock] = [static_block]
            
            # Add dynamic content without caching if it exists
            if dynamic_system_content and dynamic_system_content.strip():
                system_blocks.append({
                    "type": "text", 
                    "text": dynamic_system_content
                })
                
            args["system"] = system_blocks
        
        # Add tools if provided
        if tools:
            args["tools"] = tools
            args["tool_choice"] = {"type": "any"}
        
        # Make API call
        client = get_client()
        message = client.messages.create(**cast(Dict[str, Any], args))
        
        # Log cache metrics
        is_prefix_cache = bool(static_system_prefix)
        cache_metrics = log_cache_metrics(message.usage, cache_system, is_prefix_cache)
        
        # Handle response based on whether tools were used
        if tools:
            # Check for tool usage
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "tool_use":
                    # Return tool usage information
                    tool_response = {
                        "function_name": content_block.name,
                        "arguments": content_block.input if hasattr(content_block, 'input') else {}
                    }
                    if return_metrics:
                        return {"response": tool_response, "metrics": cache_metrics}
                    return tool_response
            # No tool was used, return text response if available
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "text":
                    text_response = content_block.text
                    if return_metrics:
                        return {"response": text_response, "metrics": cache_metrics}
                    return text_response
            empty_response = ""
            if return_metrics:
                return {"response": empty_response, "metrics": cache_metrics}
            return empty_response
        else:
            # Just return the text response
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "text":
                    text_response = content_block.text
                    if return_metrics:
                        return {"response": text_response, "metrics": cache_metrics}
                    return text_response
            empty_response = ""
            if return_metrics:
                return {"response": empty_response, "metrics": cache_metrics}
            return empty_response
            
    except Exception as e:
        print(f"Error making API request: {e}")
        if return_metrics:
            return {"response": "" if not tools else {}, "metrics": {}}
        return "" if not tools else {}



