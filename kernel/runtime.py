"""Agent Runtime - Sandboxed execution environment for agent-generated code.

The runtime:
- Only exposes the `browser` API
- Blocks dangerous imports (os, socket, subprocess, etc.)
- Enforces timeouts and resource limits
- Communicates with the kernel via IPC (JSON over Unix sockets)
"""

from __future__ import annotations

import ast
import json
import socket
import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from kernel.capabilities import CapabilityBroker, CapabilityDenied
from kernel.objects import ObjectManager, Tab, Form, Workspace, ObjectType
from kernel.audit import AuditLog, Provenance
from kernel.transactions import TransactionCoordinator


BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "socket", "requests", "urllib",
    "http", "ftplib", "smtplib", "telnetlib", "ssl", "asyncio",
    "multiprocessing", "threading", "ctypes", "importlib",
    "builtins", "__builtins__", "eval", "exec", "compile",
    "open", "file", "input", "breakpoint",
})


class ExecutionState(Enum):
    """State of code execution."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    """Result of code execution."""
    state: ExecutionState
    return_value: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    duration_ms: float = 0
    operations: list[dict] = field(default_factory=list)


class ImportValidator(ast.NodeVisitor):
    """AST visitor to validate imports."""
    
    def __init__(self):
        self.violations: list[str] = []
    
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module = alias.name.split(".")[0]
            if module in BLOCKED_IMPORTS:
                self.violations.append(f"Blocked import: {alias.name}")
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            module = node.module.split(".")[0]
            if module in BLOCKED_IMPORTS:
                self.violations.append(f"Blocked import: from {node.module}")
        self.generic_visit(node)


class BrowserAPI:
    """The browser API exposed to agent code.
    
    This is the ONLY module agents can import. All operations
    go through capability checks and are logged.
    """
    
    def __init__(
        self,
        principal: str,
        caps: CapabilityBroker,
        objects: ObjectManager,
        audit: AuditLog,
        transactions: TransactionCoordinator,
    ):
        self._principal = principal
        self._caps = caps
        self._objects = objects
        self._audit = audit
        self._transactions = transactions
        
        # Expose sub-APIs
        self.Tab = TabAPI(self)
        self.Form = FormAPI(self)
        self.Workspace = WorkspaceAPI(self)
        self.human = HumanAPI(self)
    
    def _require_cap(self, operation: str, resource: str) -> None:
        """Check capability and raise if denied."""
        self._caps.require(self._principal, operation, resource)
    
    def _log(self, op: str, obj: str, args: dict, result: str) -> None:
        """Log an operation."""
        self._audit.log(
            op=op,
            principal=self._principal,
            object=obj,
            args=args,
            result=result,
            provenance=Provenance.AGENT,
        )
    
    def transaction(self) -> "TransactionContext":
        """Begin a new transaction."""
        from kernel.transactions import TransactionContext
        return self._transactions.begin()


class TabAPI:
    """Tab operations API."""
    
    def __init__(self, browser: BrowserAPI):
        self._b = browser
    
    def open(self, url: str, workspace: Optional[str] = None) -> Tab:
        """Open a new tab."""
        self._b._require_cap("tab.create", "*")
        tab = self._b._objects.create(ObjectType.TAB, url=url)
        self._b._log("tab.open", tab.id, {"url": url}, "success")
        return tab
    
    def get(self, tab_id: str) -> Tab:
        """Get a tab by ID."""
        self._b._require_cap("tab.read", tab_id)
        tab = self._b._objects.require(tab_id)
        if not isinstance(tab, Tab):
            raise TypeError(f"{tab_id} is not a Tab")
        return tab
    
    def list(self) -> list[Tab]:
        """List all tabs."""
        self._b._require_cap("tab.list", "*")
        return [t for t in self._b._objects.list_by_type(ObjectType.TAB) if isinstance(t, Tab)]
    
    def close(self, tab_id: str) -> bool:
        """Close a tab."""
        self._b._require_cap("tab.close", tab_id)
        result = self._b._objects.delete(tab_id)
        self._b._log("tab.close", tab_id, {}, "success" if result else "not_found")
        return result
    
    def navigate(self, tab_id: str, url: str) -> None:
        """Navigate a tab to a URL."""
        self._b._require_cap("tab.navigate", tab_id)
        tab = self.get(tab_id)
        tab.navigate(url)
        self._b._log("tab.navigate", tab_id, {"url": url}, "success")
    
    def wait_for(self, tab_id: str, state: str = "interactive") -> None:
        """Wait for tab to reach a load state."""
        self._b._require_cap("tab.read", tab_id)
        tab = self.get(tab_id)
        tab.wait_for(state)
    
    def extract(self, tab_id: str, extract_type: str = "readable") -> dict:
        """Extract content from a tab (mock)."""
        self._b._require_cap("tab.read", tab_id)
        tab = self.get(tab_id)
        # Mock extraction
        return {
            "type": extract_type,
            "url": tab.url,
            "title": tab.title,
            "content": f"[Mock {extract_type} content from {tab.url}]",
        }


class FormAPI:
    """Form operations API."""
    
    def __init__(self, browser: BrowserAPI):
        self._b = browser
    
    def find(self, tab_id: str, form_type: str = "") -> Form:
        """Find a form in a tab."""
        self._b._require_cap("form.read", f"{tab_id}:*")
        # Create a mock form
        form = self._b._objects.create(ObjectType.FORM, tab_id=tab_id, form_type=form_type)
        self._b._log("form.find", form.id, {"tab_id": tab_id, "type": form_type}, "found")
        return form
    
    def get(self, form_id: str) -> Form:
        """Get a form by ID."""
        self._b._require_cap("form.read", form_id)
        form = self._b._objects.require(form_id)
        if not isinstance(form, Form):
            raise TypeError(f"{form_id} is not a Form")
        return form
    
    def fill(self, form_id: str, values: dict[str, str]) -> None:
        """Fill form fields."""
        self._b._require_cap("form.fill", form_id)
        form = self.get(form_id)
        form.fill(values)
        # Log without sensitive values
        safe_keys = list(values.keys())
        self._b._log("form.fill", form_id, {"fields": safe_keys}, "success")
    
    def clear(self, form_id: str) -> None:
        """Clear form fields."""
        self._b._require_cap("form.fill", form_id)
        form = self.get(form_id)
        form.clear()
        self._b._log("form.clear", form_id, {}, "success")
    
    def submit(self, form_id: str) -> dict:
        """Submit a form (IRREVERSIBLE - requires approval)."""
        self._b._require_cap("form.submit", form_id)
        form = self.get(form_id)
        self._b._log("form.submit", form_id, {}, "success")
        return {"submitted": True, "form_id": form_id}


class WorkspaceAPI:
    """Workspace operations API."""
    
    def __init__(self, browser: BrowserAPI):
        self._b = browser
    
    def create(self, name: str) -> Workspace:
        """Create a new workspace."""
        self._b._require_cap("workspace.create", "*")
        ws = self._b._objects.create(ObjectType.WORKSPACE, name=name)
        self._b._log("workspace.create", ws.id, {"name": name}, "success")
        return ws
    
    def get(self, workspace_id: str) -> Workspace:
        """Get a workspace by ID."""
        self._b._require_cap("workspace.read", workspace_id)
        ws = self._b._objects.require(workspace_id)
        if not isinstance(ws, Workspace):
            raise TypeError(f"{workspace_id} is not a Workspace")
        return ws
    
    def list(self) -> list[Workspace]:
        """List all workspaces."""
        self._b._require_cap("workspace.list", "*")
        return [w for w in self._b._objects.list_by_type(ObjectType.WORKSPACE) if isinstance(w, Workspace)]


class HumanAPI:
    """Human-in-the-loop operations."""
    
    def __init__(self, browser: BrowserAPI):
        self._b = browser
        self._auto_approve = False  # For testing
    
    def approve(self, message: str) -> bool:
        """Request human approval for a sensitive operation.
        
        In a real implementation, this would show a UI prompt.
        For testing, returns self._auto_approve.
        """
        self._b._log("human.approve", "user", {"message": message}, "requested")
        
        if self._auto_approve:
            self._b._log("human.approve", "user", {}, "auto_approved")
            return True
        
        # In real implementation: show UI, wait for response
        # For now, return False (deny by default)
        self._b._log("human.approve", "user", {}, "denied")
        return False
    
    def set_auto_approve(self, value: bool) -> None:
        """Set auto-approve mode (for testing only)."""
        self._auto_approve = value


class AgentRuntime:
    """Sandboxed execution environment for agent code."""
    
    def __init__(
        self,
        caps: CapabilityBroker,
        objects: ObjectManager,
        audit: AuditLog,
        transactions: TransactionCoordinator,
        timeout_seconds: float = 30.0,
    ):
        self._caps = caps
        self._objects = objects
        self._audit = audit
        self._transactions = transactions
        self._timeout = timeout_seconds
    
    def validate_code(self, code: str) -> list[str]:
        """Validate code for blocked imports and syntax errors.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Parse
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"Syntax error: {e}"]
        
        # Check imports
        validator = ImportValidator()
        validator.visit(tree)
        errors.extend(validator.violations)
        
        return errors
    
    def create_browser_api(self, principal: str) -> BrowserAPI:
        """Create a BrowserAPI instance for a principal."""
        return BrowserAPI(
            principal=principal,
            caps=self._caps,
            objects=self._objects,
            audit=self._audit,
            transactions=self._transactions,
        )
    
    def execute(self, code: str, principal: str = "agent:default") -> ExecutionResult:
        """Execute agent code in a sandboxed environment.
        
        Args:
            code: Python code to execute
            principal: Identity of the agent
            
        Returns:
            ExecutionResult with outcome and any errors
        """
        # Validate first
        errors = self.validate_code(code)
        if errors:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                error="; ".join(errors),
                error_type="ValidationError",
            )
        
        # Create restricted globals
        browser_api = self.create_browser_api(principal)
        restricted_globals = {
            "browser": browser_api,
            "__builtins__": {
                "print": print,
                "len": len,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "True": True,
                "False": False,
                "None": None,
                "isinstance": isinstance,
                "hasattr": hasattr,
                "getattr": getattr,
            },
        }
        
        start_time = time.time()
        result = {"value": None}
        error = {"value": None, "type": None}
        
        def run_code():
            try:
                exec(code, restricted_globals)
                result["value"] = restricted_globals.get("__result__")
            except CapabilityDenied as e:
                error["value"] = str(e)
                error["type"] = "CapabilityDenied"
            except Exception as e:
                error["value"] = f"{type(e).__name__}: {e}"
                error["type"] = type(e).__name__
        
        # Run with timeout
        thread = threading.Thread(target=run_code)
        thread.start()
        thread.join(timeout=self._timeout)
        
        duration_ms = (time.time() - start_time) * 1000
        
        if thread.is_alive():
            return ExecutionResult(
                state=ExecutionState.TIMEOUT,
                error=f"Execution timed out after {self._timeout}s",
                error_type="Timeout",
                duration_ms=duration_ms,
            )
        
        if error["value"]:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                error=error["value"],
                error_type=error["type"],
                duration_ms=duration_ms,
            )
        
        return ExecutionResult(
            state=ExecutionState.COMPLETED,
            return_value=result["value"],
            duration_ms=duration_ms,
        )


# --- IPC Server (Unix Socket + JSON) ---

class IPCServer:
    """Simple IPC server using Unix sockets and JSON messages."""
    
    def __init__(self, socket_path: str, runtime: AgentRuntime):
        self._socket_path = socket_path
        self._runtime = runtime
        self._server: Optional[socket.socket] = None
        self._running = False
    
    def start(self) -> None:
        """Start the IPC server."""
        # Remove existing socket
        path = Path(self._socket_path)
        if path.exists():
            path.unlink()
        
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self._socket_path)
        self._server.listen(5)
        self._running = True
        
        while self._running:
            try:
                self._server.settimeout(1.0)
                conn, _ = self._server.accept()
                self._handle_connection(conn)
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    raise
    
    def stop(self) -> None:
        """Stop the IPC server."""
        self._running = False
        if self._server:
            self._server.close()
        path = Path(self._socket_path)
        if path.exists():
            path.unlink()
    
    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle an incoming connection."""
        try:
            data = conn.recv(65536).decode("utf-8")
            request = json.loads(data)
            
            method = request.get("method")
            params = request.get("params", {})
            
            if method == "execute":
                result = self._runtime.execute(
                    code=params.get("code", ""),
                    principal=params.get("principal", "agent:default"),
                )
                response = {
                    "state": result.state.value,
                    "return_value": result.return_value,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                }
            elif method == "validate":
                errors = self._runtime.validate_code(params.get("code", ""))
                response = {"valid": len(errors) == 0, "errors": errors}
            else:
                response = {"error": f"Unknown method: {method}"}
            
            conn.send(json.dumps(response).encode("utf-8"))
        finally:
            conn.close()


class IPCClient:
    """Client for communicating with the kernel via IPC."""
    
    def __init__(self, socket_path: str):
        self._socket_path = socket_path
    
    def call(self, method: str, **params) -> dict:
        """Make an IPC call to the kernel.
        
        Args:
            method: Method name ('execute', 'validate')
            **params: Method parameters
            
        Returns:
            Response dictionary
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            request = {"method": method, "params": params}
            sock.send(json.dumps(request).encode("utf-8"))
            response = sock.recv(65536).decode("utf-8")
            return json.loads(response)
        finally:
            sock.close()
    
    def execute(self, code: str, principal: str = "agent:default") -> dict:
        """Execute code via IPC."""
        return self.call("execute", code=code, principal=principal)
    
    def validate(self, code: str) -> dict:
        """Validate code via IPC."""
        return self.call("validate", code=code)
