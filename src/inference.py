from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from typing import Optional, Dict, Any, List, Union, TypedDict, cast
import logging
import os
import copy
from datetime import datetime

# Model pricing per 1M tokens (input, output)
# Prices as of December 2024 - update as needed
MODEL_PRICING = {
    # Claude 3 Family
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    
    # Claude 3.5 Family  
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-sonnet-20240620": (3.00, 15.00),  # Earlier version
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    
    # Claude 4 Family
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
}

class CostTracker:
    """Tracks cumulative API costs across a game session"""
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self.api_calls = 0
        self.model_usage = {}  # Track usage by model
        
    def add_usage(self, model: str, input_tokens: int, output_tokens: int, 
                  cache_creation: int = 0, cache_read: int = 0):
        """Add token usage for an API call"""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_creation_tokens += cache_creation
        self.total_cache_read_tokens += cache_read
        self.api_calls += 1
        
        # Track by model
        if model not in self.model_usage:
            self.model_usage[model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
                "calls": 0
            }
        
        usage = self.model_usage[model]
        usage["input_tokens"] += input_tokens
        usage["output_tokens"] += output_tokens
        usage["cache_creation_tokens"] += cache_creation
        usage["cache_read_tokens"] += cache_read
        usage["calls"] += 1
    
    def calculate_cost(self, model: Optional[str] = None) -> float:
        """Calculate total cost in USD"""
        total_cost = 0.0
        
        models_to_calculate = [model] if model else self.model_usage.keys()
        
        for model_name in models_to_calculate:
            if model_name not in self.model_usage:
                continue
                
            usage = self.model_usage[model_name]
            
            if model_name in MODEL_PRICING:
                input_price, output_price = MODEL_PRICING[model_name]
                
                # Regular input tokens (full price) - input_tokens already excludes cached tokens
                input_cost = (usage["input_tokens"] / 1_000_000) * input_price
                
                # Cache creation tokens (25% more than regular price)
                cache_creation_cost = (usage["cache_creation_tokens"] / 1_000_000) * input_price * 1.25
                
                # Cache read tokens (90% savings, so 10% of regular price)
                cache_read_cost = (usage["cache_read_tokens"] / 1_000_000) * input_price * 0.1
                
                # Output tokens (always full price)
                output_cost = (usage["output_tokens"] / 1_000_000) * output_price
                
                total_cost += input_cost + cache_creation_cost + cache_read_cost + output_cost
            else:
                # Log warning for unknown model pricing
                log_cache_info(f"WARNING: No pricing data for model '{model_name}' - cost calculation incomplete")
        
        return total_cost
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive cost and usage summary"""
        total_cost = self.calculate_cost()
        
        # Check for models with unknown pricing
        unknown_models = [model for model in self.model_usage.keys() if model not in MODEL_PRICING]
        
        summary = {
            "total_cost_usd": round(total_cost, 4),
            "total_api_calls": self.api_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "cache_savings_tokens": self.total_cache_read_tokens,
            "cache_savings_usd": 0.0,
            "models_used": {},
            "unknown_models": unknown_models,  # Track models without pricing
            "cost_incomplete": len(unknown_models) > 0  # Flag if cost calculation is incomplete
        }
        
        # Calculate cache savings in USD (accounting for cache write costs)
        for model_name, usage in self.model_usage.items():
            if model_name in MODEL_PRICING and (usage["cache_read_tokens"] > 0 or usage["cache_creation_tokens"] > 0):
                input_price = MODEL_PRICING[model_name][0]
                
                # Cost WITH caching: cache_writes * 1.25 + cache_reads * 0.1
                cache_cost = (usage["cache_creation_tokens"] / 1_000_000) * input_price * 1.25 + \
                           (usage["cache_read_tokens"] / 1_000_000) * input_price * 0.1
                
                # Cost WITHOUT caching: all tokens at full price
                no_cache_cost = ((usage["cache_creation_tokens"] + usage["cache_read_tokens"]) / 1_000_000) * input_price
                
                # Net savings (can be negative if caching costs more)
                net_savings = no_cache_cost - cache_cost
                summary["cache_savings_usd"] += net_savings
        
        summary["cache_savings_usd"] = round(summary["cache_savings_usd"], 4)
        
        # Add per-model breakdown
        for model_name, usage in self.model_usage.items():
            model_cost = self.calculate_cost(model_name)
            summary["models_used"][model_name] = {
                "cost_usd": round(model_cost, 4) if model_name in MODEL_PRICING else "unknown",
                "calls": usage["calls"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "cache_read_tokens": usage["cache_read_tokens"],
                "pricing_available": model_name in MODEL_PRICING
            }
        
        return summary

# Global cost tracker instance
_cost_tracker = CostTracker()

def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker instance"""
    return _cost_tracker

def reset_cost_tracker():
    """Reset the cost tracker for a new game session"""
    global _cost_tracker
    _cost_tracker = CostTracker()

# Simple cache logging
def log_cache_info(message: str):
    """Write cache info to log file."""
    os.makedirs("logs", exist_ok=True)
    with open("logs/cache_metrics.log", "a") as f:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{timestamp} - {message}\n")

def log_full_request(args: Dict[str, Any], user_message: str):
    """Log the full request in a readable format."""
    os.makedirs("logs", exist_ok=True)
    with open("logs/full_requests.log", "a") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"\n{'='*80}\n")
        f.write(f"REQUEST AT {timestamp}\n")
        f.write(f"{'='*80}\n")
        
        # Log model and basic parameters
        f.write(f"MODEL: {args.get('model', 'unknown')}\n")
        f.write(f"MAX_TOKENS: {args.get('max_tokens', 'unknown')}\n")
        
        # Log system prompts
        if 'system' in args and args['system']:
            f.write(f"\nSYSTEM PROMPTS:\n")
            f.write(f"{'-'*40}\n")
            for i, block in enumerate(args['system']):
                cache_info = ""
                if 'cache_control' in block:
                    cache_info = " [CACHED]"
                f.write(f"System Block {i+1}{cache_info}:\n")
                f.write(f"{block.get('text', 'No text')}\n")
                f.write(f"{'-'*40}\n")
        
        # Log user message
        f.write(f"\nUSER MESSAGE:\n")
        f.write(f"{'-'*40}\n")
        f.write(f"{user_message}\n")
        f.write(f"{'-'*40}\n")
        
        # Log tools if present
        if 'tools' in args and args['tools']:
            f.write(f"\nTOOLS:\n")
            f.write(f"{'-'*40}\n")
            for i, tool in enumerate(args['tools']):
                cache_info = ""
                if 'cache_control' in tool:
                    cache_info = " [CACHED]"
                f.write(f"Tool {i+1}{cache_info}: {tool.get('name', 'unknown')}\n")
                f.write(f"Description: {tool.get('description', 'No description')}\n")
                if 'input_schema' in tool:
                    f.write(f"Input Schema: {tool['input_schema']}\n")
                f.write(f"{'-'*20}\n")
        
        # Log tool choice if present
        if 'tool_choice' in args:
            f.write(f"\nTOOL CHOICE: {args['tool_choice']}\n")
        
        f.write(f"\n{'='*80}\n\n")

def log_full_response(response_content: Any, model: str):
    """Log the full response in a readable format."""
    os.makedirs("logs", exist_ok=True)
    with open("logs/full_requests.log", "a") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESPONSE AT {timestamp} (Model: {model}):\n")
        f.write(f"{'-'*80}\n")
        
        if isinstance(response_content, str):
            f.write(f"TEXT RESPONSE:\n{response_content}\n")
        elif isinstance(response_content, dict):
            if "function_name" in response_content:
                f.write(f"TOOL RESPONSE:\n")
                f.write(f"Function: {response_content.get('function_name', 'unknown')}\n")
                f.write(f"Arguments: {response_content.get('arguments', {})}\n")
            else:
                f.write(f"DICT RESPONSE:\n{response_content}\n")
        else:
            f.write(f"OTHER RESPONSE TYPE ({type(response_content)}): {response_content}\n")
        
        f.write(f"{'-'*80}\n\n")

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

def log_cache_metrics(usage: Any, cache_enabled: bool, model: str) -> CacheMetrics:
    """Log cache usage metrics and track costs."""
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
    
    # Add to cost tracker
    _cost_tracker.add_usage(model, input_tokens, output_tokens, cache_creation, cache_read)
    
    # Log detailed usage metrics for every response
    log_message = f"RESPONSE [{model}] - "
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
    cache_tools: bool = True,
    return_metrics: bool = False,
    cached_system_prompt_strs: List[str] = [],
    non_cached_system_prompt_strs: List[str] = []
) -> Union[str, Dict[str, Any]]:
    """
    Send a request to the LLM and return the response.
    
    Args:
        user_message: User message content
        model: Model to use
        max_tokens: Maximum tokens in response
        tools: Optional list of tools to use
        cache_tools: Whether to cache the tool definitions
        return_metrics: Whether to return cache metrics along with response
        cached_system_prompt_strs: List of system prompt strings to cache (up to 4 blocks)
        non_cached_system_prompt_strs: List of system prompt strings that won't be cached
        
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
        
        system_blocks: List[SystemContentBlock] = []
        
        # Add cached system prompts first (up to 4 blocks can be cached)
        for system_prompt_str in cached_system_prompt_strs[:4]:
            system_blocks.append({
                "type": "text",
                "text": system_prompt_str,
                "cache_control": {"type": "ephemeral"}
            })
        
        # Add non-cached system prompts
        for system_prompt_str in non_cached_system_prompt_strs:
            system_blocks.append({
                "type": "text",
                "text": system_prompt_str
            })
            
        if system_blocks:
            args["system"] = system_blocks
        
        # Add tools if provided
        if tools:
            args["tools"] = tools
            args["tool_choice"] = {"type": "any"}
        
        # Log the full request for debugging
        log_full_request(cast(Dict[str, Any], args), user_message)
        
        # Make API call
        client = get_client()
        message = client.messages.create(**cast(Dict[str, Any], args))
        
        # Log cache metrics
        cache_enabled = len(cached_system_prompt_strs) > 0 or (cache_tools and tools is not None)
        cache_metrics = log_cache_metrics(message.usage, cache_enabled, model)
        
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
                    log_full_response(tool_response, model)
                    if return_metrics:
                        return {"response": tool_response, "metrics": cache_metrics}
                    return tool_response
            # No tool was used, return text response if available
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "text":
                    text_response = content_block.text
                    log_full_response(text_response, model)
                    if return_metrics:
                        return {"response": text_response, "metrics": cache_metrics}
                    return text_response
            empty_response = ""
            log_full_response(empty_response, model)
            if return_metrics:
                return {"response": empty_response, "metrics": cache_metrics}
            return empty_response
        else:
            # Just return the text response
            for content_block in message.content:
                if hasattr(content_block, 'type') and content_block.type == "text":
                    text_response = content_block.text
                    log_full_response(text_response, model)
                    if return_metrics:
                        return {"response": text_response, "metrics": cache_metrics}
                    return text_response
            empty_response = ""
            log_full_response(empty_response, model)
            if return_metrics:
                return {"response": empty_response, "metrics": cache_metrics}
            return empty_response
            
    except Exception as e:
        print(f"Error making API request: {e}")
        if return_metrics:
            return {"response": "" if not tools else {}, "metrics": {}}
        return "" if not tools else {}



