"""Agentic Browser Kernel - Capability-secure browser kernel for LLM code generation."""

from kernel.capabilities import CapabilityBroker
from kernel.objects import ObjectManager
from kernel.audit import AuditLog
from kernel.transactions import TransactionCoordinator

__all__ = ["CapabilityBroker", "ObjectManager", "AuditLog", "TransactionCoordinator"]
__version__ = "0.1.0"
