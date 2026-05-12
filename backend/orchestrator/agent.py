"""LLM-backed recommendation agent (not yet implemented).

This module will own the reasoning loop that drives each conversation turn:
prompting the language model, parsing its response, and deciding the next
step_type (show / ask / stop).

All LLM calls must go through ``backend.llm_harness`` — never instantiate a
model client directly here.
"""
