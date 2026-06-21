"""One Actor session per registered bridge agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from intentframe_actor import Actor
from intentframe_core.types import AgentCapabilities, ExecutionResult, RuntimeContext

from if_security_backend.bridge.config import BridgeAgentConfig


class HandshakeRequiredError(RuntimeError):
    """Raised when submit is called before handshake on this agent session."""


@dataclass
class BridgeActorPool:
    core_socket: str
    _actors: dict[str, Actor] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _handshaken: set[str] = field(default_factory=set)

    def _lock_for(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self._locks:
            self._locks[agent_id] = asyncio.Lock()
        return self._locks[agent_id]

    def is_handshaken(self, agent_id: str) -> bool:
        return agent_id in self._handshaken

    @staticmethod
    def default_capabilities(agent_cfg: BridgeAgentConfig) -> AgentCapabilities:
        return AgentCapabilities(
            agent_type=agent_cfg.agent_type,
            description=f"Bridge agent {agent_cfg.agent_id}",
            action_types=list(agent_cfg.action_types),
        )

    async def _actor_for(self, agent_cfg: BridgeAgentConfig) -> Actor:
        actor = self._actors.get(agent_cfg.agent_id)
        if actor is None:
            actor = Actor(
                agent_id=agent_cfg.agent_id,
                user_id=agent_cfg.user_id,
                socket_path=self.core_socket,
            )
            self._actors[agent_cfg.agent_id] = actor
        return actor

    async def handshake(
        self,
        agent_cfg: BridgeAgentConfig,
        capabilities: AgentCapabilities | None = None,
    ) -> RuntimeContext:
        caps = capabilities or self.default_capabilities(agent_cfg)
        async with self._lock_for(agent_cfg.agent_id):
            actor = await self._actor_for(agent_cfg)
            ctx = await actor.handshake(caps)
            self._handshaken.add(agent_cfg.agent_id)
            return ctx

    async def submit(
        self,
        agent_cfg: BridgeAgentConfig,
        request: dict,
    ) -> ExecutionResult:
        async with self._lock_for(agent_cfg.agent_id):
            if agent_cfg.agent_id not in self._handshaken:
                raise HandshakeRequiredError(
                    "POST /handshake must be called before POST /validate"
                )
            actor = await self._actor_for(agent_cfg)
            return await actor.submit(request)

    async def close(self) -> None:
        for actor in self._actors.values():
            await actor.close()
        self._actors.clear()
        self._handshaken.clear()
