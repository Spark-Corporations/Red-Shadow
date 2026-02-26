"""
RedClaw V3.1 Router — LLM Reliability Layer + Model Alloy + OpenRouter

Components:
  - LLMClient: Enterprise LLM client with retry, fallback, compaction, cost tracking
  - OpenRouterClient: API client for OpenRouter (gpt-oss-120B + qwen3-coder:free)
  - ModelAlloyRouter: Strategic model selection with 60/40 balance enforcement
"""

from .llm_client import (
    LLMClient,
    ProviderConfig,
    CostTracker,
    LLMCallMetrics,
    BudgetExceededError,
    AllProvidersFailedError,
    fix_message_list,
    auto_compact_messages,
)
from .openrouter_client import OpenRouterClient
from .model_alloy import ModelAlloyRouter, ModelSelector, BalancedRouter

__all__ = [
    "LLMClient",
    "ProviderConfig",
    "CostTracker",
    "LLMCallMetrics",
    "BudgetExceededError",
    "AllProvidersFailedError",
    "fix_message_list",
    "auto_compact_messages",
    "OpenRouterClient",
    "ModelAlloyRouter",
    "ModelSelector",
    "BalancedRouter",
]
