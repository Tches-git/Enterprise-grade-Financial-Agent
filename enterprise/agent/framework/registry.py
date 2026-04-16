from __future__ import annotations

import logging
from typing import Any

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        if agent.agent_name in self._agents:
            logger.warning("Agent %s already registered, overwriting", agent.agent_name)
        self._agents[agent.agent_name] = agent
        logger.info("Registered agent: %s (capabilities: %s)", agent.agent_name, agent.capabilities)

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def find_by_capability(self, message_type: str) -> list[BaseAgent]:
        return [agent for agent in self._agents.values() if agent.can_handle(message_type)]

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "name": agent.agent_name,
                "description": agent.agent_description,
                "capabilities": agent.capabilities,
                "model_tier": agent.model_tier,
            }
            for agent in self._agents.values()
        ]

    def unregister(self, name: str) -> bool:
        if name in self._agents:
            del self._agents[name]
            return True
        return False


agent_registry = AgentRegistry()
