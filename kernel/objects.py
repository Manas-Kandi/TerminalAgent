"""Object Manager - Canonical registry of browser resources with stable IDs.

All browser resources (tabs, forms, downloads, etc.) are registered here
with stable, human-readable IDs that persist across operations.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar


class ObjectType(Enum):
    """Types of managed browser objects."""
    TAB = "tab"
    DOCUMENT = "doc"
    FORM = "form"
    DOWNLOAD = "download"
    WORKSPACE = "workspace"
    TRANSACTION = "tx"
    CHECKPOINT = "cp"
    CREDENTIAL = "cred"


@dataclass
class ObjectState:
    """State snapshot for an object (used in transactions)."""
    id: str
    type: ObjectType
    data: dict
    timestamp: float = field(default_factory=time.time)


class ManagedObject:
    """Base class for all managed browser objects."""
    
    def __init__(self, obj_id: str, obj_type: ObjectType, manager: ObjectManager):
        self._id = obj_id
        self._type = obj_type
        self._manager = manager
        self._data: dict[str, Any] = {}
        self._created_at = time.time()
        self._updated_at = self._created_at
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def type(self) -> ObjectType:
        return self._type
    
    @property
    def created_at(self) -> float:
        return self._created_at
    
    @property
    def updated_at(self) -> float:
        return self._updated_at
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._updated_at = time.time()
        self._manager._notify_update(self)
    
    def update(self, **kwargs) -> None:
        self._data.update(kwargs)
        self._updated_at = time.time()
        self._manager._notify_update(self)
    
    def snapshot(self) -> ObjectState:
        """Capture current state for transaction checkpoints."""
        import copy
        return ObjectState(
            id=self._id,
            type=self._type,
            data=copy.deepcopy(self._data),
            timestamp=time.time(),
        )
    
    def restore(self, state: ObjectState) -> None:
        """Restore state from a snapshot."""
        import copy
        if state.id != self._id or state.type != self._type:
            raise ValueError(f"State mismatch: {state.id} vs {self._id}")
        self._data = copy.deepcopy(state.data)
        self._updated_at = time.time()
    
    def to_dict(self) -> dict:
        return {
            "id": self._id,
            "type": self._type.value,
            "data": dict(self._data),
            "created_at": self._created_at,
            "updated_at": self._updated_at,
        }


class Tab(ManagedObject):
    """Represents a browser tab."""
    
    def __init__(self, obj_id: str, manager: ObjectManager, url: str = "", title: str = ""):
        super().__init__(obj_id, ObjectType.TAB, manager)
        self._data = {
            "url": url,
            "title": title,
            "load_state": "idle",
            "workspace": None,
        }
    
    @property
    def url(self) -> str:
        return self._data["url"]
    
    @property
    def title(self) -> str:
        return self._data["title"]
    
    @property
    def load_state(self) -> str:
        return self._data["load_state"]
    
    def navigate(self, url: str) -> None:
        """Navigate to a URL (mock implementation)."""
        self._data["url"] = url
        self._data["load_state"] = "loading"
        self._updated_at = time.time()
        self._manager._notify_update(self)
    
    def wait_for(self, state: str = "interactive") -> None:
        """Wait for load state (mock: instant)."""
        self._data["load_state"] = state
        self._updated_at = time.time()


class Form(ManagedObject):
    """Represents a web form."""
    
    def __init__(self, obj_id: str, manager: ObjectManager, tab_id: str, form_type: str = ""):
        super().__init__(obj_id, ObjectType.FORM, manager)
        self._data = {
            "tab_id": tab_id,
            "form_type": form_type,
            "fields": {},
            "filled": {},
        }
    
    @property
    def tab_id(self) -> str:
        return self._data["tab_id"]
    
    @property
    def form_type(self) -> str:
        return self._data["form_type"]
    
    def fill(self, values: dict[str, str]) -> None:
        """Fill form fields."""
        self._data["filled"].update(values)
        self._updated_at = time.time()
        self._manager._notify_update(self)
    
    def clear(self) -> None:
        """Clear filled values."""
        self._data["filled"] = {}
        self._updated_at = time.time()
        self._manager._notify_update(self)


class Workspace(ManagedObject):
    """Represents a workspace grouping tabs, storage, and policies."""
    
    def __init__(self, obj_id: str, manager: ObjectManager, name: str = ""):
        super().__init__(obj_id, ObjectType.WORKSPACE, manager)
        self._data = {
            "name": name,
            "tabs": [],
            "storage": {},
            "policies": {},
        }
    
    @property
    def name(self) -> str:
        return self._data["name"]
    
    @property
    def tabs(self) -> list[str]:
        return list(self._data["tabs"])
    
    def add_tab(self, tab_id: str) -> None:
        if tab_id not in self._data["tabs"]:
            self._data["tabs"].append(tab_id)
            self._updated_at = time.time()
    
    def remove_tab(self, tab_id: str) -> None:
        if tab_id in self._data["tabs"]:
            self._data["tabs"].remove(tab_id)
            self._updated_at = time.time()


T = TypeVar("T", bound=ManagedObject)


class ObjectManager:
    """Canonical registry of browser resources with stable IDs."""
    
    _TYPE_CLASSES: dict[ObjectType, type] = {
        ObjectType.TAB: Tab,
        ObjectType.FORM: Form,
        ObjectType.WORKSPACE: Workspace,
    }
    
    def __init__(self, audit_log=None):
        self._objects: dict[str, ManagedObject] = {}
        self._counters: dict[ObjectType, int] = {t: 0 for t in ObjectType}
        self._lock = threading.Lock()
        self._listeners: list[Callable[[str, ManagedObject], None]] = []
        self._audit = audit_log
    
    def _next_id(self, obj_type: ObjectType) -> str:
        """Generate the next stable ID for an object type."""
        with self._lock:
            self._counters[obj_type] += 1
            return f"{obj_type.value}:{self._counters[obj_type]}"
    
    def create(self, obj_type: ObjectType | str, **kwargs) -> ManagedObject:
        """Create and register a new managed object.
        
        Args:
            obj_type: Type of object to create
            **kwargs: Type-specific initialization arguments
            
        Returns:
            The created object with a stable ID
        """
        if isinstance(obj_type, str):
            obj_type = ObjectType(obj_type)
        
        obj_id = self._next_id(obj_type)
        
        cls = self._TYPE_CLASSES.get(obj_type, ManagedObject)
        if cls == ManagedObject:
            obj = ManagedObject(obj_id, obj_type, self)
            obj.update(**kwargs)
        else:
            obj = cls(obj_id, self, **kwargs)
        
        self._objects[obj_id] = obj
        
        if self._audit:
            self._audit.log(
                op=f"{obj_type.value}.create",
                principal="system",
                object=obj_id,
                args=kwargs,
                result="created",
            )
        
        return obj
    
    def get(self, obj_id: str) -> Optional[ManagedObject]:
        """Get an object by its stable ID."""
        return self._objects.get(obj_id)
    
    def require(self, obj_id: str) -> ManagedObject:
        """Get an object by ID, raising if not found."""
        obj = self.get(obj_id)
        if obj is None:
            raise KeyError(f"Object not found: {obj_id}")
        return obj
    
    def delete(self, obj_id: str) -> bool:
        """Delete an object by its ID.
        
        Returns:
            True if deleted, False if not found
        """
        obj = self._objects.pop(obj_id, None)
        if obj is None:
            return False
        
        if self._audit:
            self._audit.log(
                op=f"{obj.type.value}.delete",
                principal="system",
                object=obj_id,
                args={},
                result="deleted",
            )
        
        return True
    
    def list_by_type(self, obj_type: ObjectType | str) -> list[ManagedObject]:
        """List all objects of a given type."""
        if isinstance(obj_type, str):
            obj_type = ObjectType(obj_type)
        return [o for o in self._objects.values() if o.type == obj_type]
    
    def query(self, obj_type: Optional[ObjectType] = None, **filters) -> list[ManagedObject]:
        """Query objects by type and data filters.
        
        Args:
            obj_type: Optional type filter
            **filters: Key-value filters on object data
            
        Returns:
            List of matching objects
        """
        results = []
        for obj in self._objects.values():
            if obj_type and obj.type != obj_type:
                continue
            match = all(obj.get(k) == v for k, v in filters.items())
            if match:
                results.append(obj)
        return results
    
    def snapshot_all(self) -> dict[str, ObjectState]:
        """Snapshot all objects (for transactions)."""
        return {obj_id: obj.snapshot() for obj_id, obj in self._objects.items()}
    
    def restore_snapshot(self, snapshot: dict[str, ObjectState]) -> None:
        """Restore all objects from snapshot."""
        for obj_id, state in snapshot.items():
            obj = self._objects.get(obj_id)
            if obj:
                obj.restore(state)
    
    def add_listener(self, callback: Callable[[str, ManagedObject], None]) -> None:
        """Add a listener for object updates."""
        self._listeners.append(callback)
    
    def _notify_update(self, obj: ManagedObject) -> None:
        """Notify listeners of an object update."""
        for listener in self._listeners:
            try:
                listener("update", obj)
            except Exception:
                pass
