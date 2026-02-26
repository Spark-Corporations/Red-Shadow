"""
RedClaw V3.1 Router — Model Alloy + OpenRouter Dual-Brain System

Components:
  - OpenRouterClient: API client for OpenRouter (gpt-oss-120B + qwen3-coder:free)
  - ModelAlloyRouter: Strategic model selection with 60/40 balance enforcement
  - RouterConfig: Configuration management
"""

from .openrouter_client import OpenRouterClient
from .model_alloy import ModelAlloyRouter, ModelSelector, BalancedRouter

__all__ = [
    "OpenRouterClient",
    "ModelAlloyRouter",
    "ModelSelector",
    "BalancedRouter",
]
