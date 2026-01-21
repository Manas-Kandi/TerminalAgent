"""Terminal UI - Primary interface for human governance.

Provides:
- Code review before execution
- Capability preview (dry-run)
- Edit/run/step controls
- Transaction checkpoint display
- Audit log viewer
- Approval prompts for high-risk operations
"""

from __future__ import annotations

import ast
import readline
import shutil
import sys
import textwrap
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from kernel.capabilities import CapabilityBroker, CapabilityRisk, CapabilityDenied
from kernel.objects import ObjectManager, ObjectType
from kernel.audit import AuditLog, Provenance
from kernel.transactions import TransactionCoordinator
from kernel.runtime import AgentRuntime, ExecutionState, ImportValidator


class Color:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"


def colored(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""
    return f"{color}{text}{Color.RESET}"


def bold(text: str) -> str:
    return colored(text, Color.BOLD)


def dim(text: str) -> str:
    return colored(text, Color.DIM)


class RiskDisplay:
    """Maps risk levels to display properties."""
    COLORS = {
        CapabilityRisk.READ: Color.GREEN,
        CapabilityRisk.STATEFUL: Color.YELLOW,
        CapabilityRisk.IRREVERSIBLE: Color.RED,
    }
    LABELS = {
        CapabilityRisk.READ: "READ",
        CapabilityRisk.STATEFUL: "STATEFUL",
        CapabilityRisk.IRREVERSIBLE: "IRREVERSIBLE",
    }
    
    @classmethod
    def format(cls, risk: CapabilityRisk) -> str:
        color = cls.COLORS.get(risk, Color.WHITE)
        label = cls.LABELS.get(risk, str(risk))
        return colored(f"[{label}]", color)


@dataclass
class CodeBuffer:
    """Holds code being reviewed/edited."""
    source: str
    principal: str = "agent:interactive"
    validated: bool = False
    validation_errors: list[str] = None
    required_caps: list[dict] = None
    
    def __post_init__(self):
        if self.validation_errors is None:
            self.validation_errors = []
        if self.required_caps is None:
            self.required_caps = []


class TerminalUI:
    """Terminal-based UI for human governance of agent execution.
    
    Commands:
        load <file>     Load code from file
        paste           Enter multiline code (end with blank line)
        show            Display current code with line numbers
        edit <line>     Edit a specific line
        validate        Check code for errors and blocked imports
        caps            Preview required capabilities (dry-run)
        run             Execute the code
        step            Step through execution (not yet implemented)
        
        audit [n]       Show last n audit entries (default 20)
        audit tx <id>   Show entries for a transaction
        objects         List all managed objects
        tx              Show transaction state
        
        approve         Pre-approve pending high-risk operation
        deny            Deny pending high-risk operation
        rollback [cp]   Rollback to checkpoint (or initial)
        
        help            Show this help
        quit            Exit
    """
    
    PROMPT = colored("agent> ", Color.CYAN)
    
    def __init__(
        self,
        caps: CapabilityBroker,
        objects: ObjectManager,
        audit: AuditLog,
        transactions: TransactionCoordinator,
        runtime: AgentRuntime,
    ):
        self._caps = caps
        self._objects = objects
        self._audit = audit
        self._transactions = transactions
        self._runtime = runtime
        
        self._code_buffer: Optional[CodeBuffer] = None
        self._pending_approval: Optional[dict] = None
        self._running = False
        
        self._term_width = shutil.get_terminal_size().columns
        
        self._commands = {
            "load": self._cmd_load,
            "paste": self._cmd_paste,
            "show": self._cmd_show,
            "edit": self._cmd_edit,
            "validate": self._cmd_validate,
            "caps": self._cmd_caps,
            "run": self._cmd_run,
            "audit": self._cmd_audit,
            "objects": self._cmd_objects,
            "tx": self._cmd_tx,
            "approve": self._cmd_approve,
            "deny": self._cmd_deny,
            "rollback": self._cmd_rollback,
            "grant": self._cmd_grant,
            "help": self._cmd_help,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }
    
    def _print_header(self, title: str) -> None:
        """Print a section header."""
        print(f"\n{bold(f'═══ {title} ')}" + "═" * (self._term_width - len(title) - 5))
    
    def _print_divider(self) -> None:
        """Print a divider line."""
        print(dim("─" * self._term_width))
    
    def _print_code(self, code: str, highlight_line: Optional[int] = None) -> None:
        """Print code with line numbers."""
        lines = code.split("\n")
        width = len(str(len(lines)))
        for i, line in enumerate(lines, 1):
            num = f"{i:>{width}}"
            if highlight_line and i == highlight_line:
                print(colored(f" {num} │ ", Color.YELLOW) + colored(line, Color.YELLOW))
            else:
                print(dim(f" {num} │ ") + line)
    
    def _cmd_load(self, args: list[str]) -> None:
        """Load code from a file."""
        if not args:
            print(colored("Usage: load <filename>", Color.RED))
            return
        
        filepath = args[0]
        try:
            with open(filepath, "r") as f:
                code = f.read()
            self._code_buffer = CodeBuffer(source=code)
            print(colored(f"Loaded {len(code)} bytes from {filepath}", Color.GREEN))
            self._cmd_show([])
        except FileNotFoundError:
            print(colored(f"File not found: {filepath}", Color.RED))
        except Exception as e:
            print(colored(f"Error loading file: {e}", Color.RED))
    
    def _cmd_paste(self, args: list[str]) -> None:
        """Enter multiline code (end with blank line or Ctrl+D)."""
        print(dim("Enter code (blank line or Ctrl+D to finish):"))
        lines = []
        try:
            while True:
                line = input(dim("... "))
                if line == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        
        if lines:
            code = "\n".join(lines)
            self._code_buffer = CodeBuffer(source=code)
            print(colored(f"Captured {len(lines)} lines", Color.GREEN))
        else:
            print(colored("No code entered", Color.YELLOW))
    
    def _cmd_show(self, args: list[str]) -> None:
        """Display current code with line numbers."""
        if not self._code_buffer:
            print(colored("No code loaded. Use 'load' or 'paste'", Color.YELLOW))
            return
        
        self._print_header("Code Buffer")
        self._print_code(self._code_buffer.source)
        
        if self._code_buffer.validation_errors:
            self._print_header("Validation Errors")
            for err in self._code_buffer.validation_errors:
                print(colored(f"  ✗ {err}", Color.RED))
        elif self._code_buffer.validated:
            print(colored("\n  ✓ Code validated successfully", Color.GREEN))
    
    def _cmd_edit(self, args: list[str]) -> None:
        """Edit a specific line of code."""
        if not self._code_buffer:
            print(colored("No code loaded", Color.YELLOW))
            return
        
        if not args:
            print(colored("Usage: edit <line_number>", Color.RED))
            return
        
        try:
            line_num = int(args[0])
        except ValueError:
            print(colored("Invalid line number", Color.RED))
            return
        
        lines = self._code_buffer.source.split("\n")
        if line_num < 1 or line_num > len(lines):
            print(colored(f"Line {line_num} out of range (1-{len(lines)})", Color.RED))
            return
        
        print(f"Current line {line_num}: {lines[line_num - 1]}")
        new_line = input("New content: ")
        lines[line_num - 1] = new_line
        self._code_buffer.source = "\n".join(lines)
        self._code_buffer.validated = False
        print(colored("Line updated", Color.GREEN))
    
    def _cmd_validate(self, args: list[str]) -> None:
        """Validate code for syntax errors and blocked imports."""
        if not self._code_buffer:
            print(colored("No code loaded", Color.YELLOW))
            return
        
        errors = self._runtime.validate_code(self._code_buffer.source)
        self._code_buffer.validation_errors = errors
        self._code_buffer.validated = len(errors) == 0
        
        self._print_header("Validation")
        if errors:
            for err in errors:
                print(colored(f"  ✗ {err}", Color.RED))
        else:
            print(colored("  ✓ Code is valid", Color.GREEN))
    
    def _cmd_caps(self, args: list[str]) -> None:
        """Preview required capabilities (dry-run analysis)."""
        if not self._code_buffer:
            print(colored("No code loaded", Color.YELLOW))
            return
        
        # Static analysis to find API calls
        required = self._analyze_required_caps(self._code_buffer.source)
        self._code_buffer.required_caps = required
        
        self._print_header("Required Capabilities")
        if not required:
            print(dim("  No privileged operations detected"))
            return
        
        principal = self._code_buffer.principal
        print(f"  Principal: {bold(principal)}\n")
        
        for cap in required:
            op = cap["operation"]
            resource = cap["resource"]
            risk = cap.get("risk", CapabilityRisk.READ)
            
            # Check if granted
            has_cap = self._caps.check(principal, op, resource)
            status = colored("✓ GRANTED", Color.GREEN) if has_cap else colored("✗ MISSING", Color.RED)
            
            risk_display = RiskDisplay.format(risk)
            print(f"  {risk_display} {op} on {resource} ... {status}")
        
        missing = [c for c in required if not self._caps.check(principal, c["operation"], c["resource"])]
        if missing:
            print(colored(f"\n  ⚠ {len(missing)} capabilities missing. Use 'grant' to add.", Color.YELLOW))
    
    def _analyze_required_caps(self, code: str) -> list[dict]:
        """Static analysis to determine required capabilities."""
        required = []
        
        # Parse and walk AST
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                cap = self._infer_cap_from_call(node)
                if cap and cap not in required:
                    required.append(cap)
        
        return required
    
    def _infer_cap_from_call(self, node: ast.Call) -> Optional[dict]:
        """Infer capability requirement from an AST Call node."""
        func = node.func
        
        # Handle browser.Tab.open(...), browser.Form.fill(...), etc.
        if isinstance(func, ast.Attribute):
            parts = []
            current = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            
            parts.reverse()
            
            if len(parts) >= 3 and parts[0] == "browser":
                obj_type = parts[1].lower()
                method = parts[2]
                
                op = f"{obj_type}.{method}"
                resource = "*"  # Static analysis can't know the resource
                
                # Classify risk
                risk = CapabilityRisk.READ
                if method in ("navigate", "fill", "clear", "create", "open", "close"):
                    risk = CapabilityRisk.STATEFUL
                if method in ("submit", "delete", "send"):
                    risk = CapabilityRisk.IRREVERSIBLE
                
                return {"operation": op, "resource": resource, "risk": risk}
        
        return None
    
    def _cmd_run(self, args: list[str]) -> None:
        """Execute the code."""
        if not self._code_buffer:
            print(colored("No code loaded", Color.YELLOW))
            return
        
        if not self._code_buffer.validated:
            print(colored("Code not validated. Running 'validate' first...", Color.YELLOW))
            self._cmd_validate([])
            if self._code_buffer.validation_errors:
                print(colored("Fix errors before running", Color.RED))
                return
        
        # Check capabilities
        self._cmd_caps([])
        required = self._code_buffer.required_caps
        principal = self._code_buffer.principal
        
        missing = [c for c in required if not self._caps.check(principal, c["operation"], c["resource"])]
        if missing:
            print(colored("\n⚠ Cannot run: missing capabilities", Color.RED))
            return
        
        # Check for irreversible operations
        irreversible = [c for c in required if c.get("risk") == CapabilityRisk.IRREVERSIBLE]
        if irreversible:
            self._print_header("⚠ IRREVERSIBLE OPERATIONS DETECTED")
            for cap in irreversible:
                print(colored(f"  • {cap['operation']} on {cap['resource']}", Color.RED))
            
            confirm = input(colored("\nProceed? [y/N]: ", Color.YELLOW))
            if confirm.lower() != "y":
                print("Execution cancelled")
                return
        
        self._print_header("Execution")
        print(dim(f"Principal: {principal}"))
        print(dim(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}"))
        self._print_divider()
        
        result = self._runtime.execute(self._code_buffer.source, principal=principal)
        
        self._print_divider()
        
        if result.state == ExecutionState.COMPLETED:
            print(colored(f"\n✓ Completed in {result.duration_ms:.1f}ms", Color.GREEN))
        elif result.state == ExecutionState.FAILED:
            print(colored(f"\n✗ Failed: {result.error}", Color.RED))
        elif result.state == ExecutionState.TIMEOUT:
            print(colored(f"\n✗ Timeout: {result.error}", Color.RED))
    
    def _cmd_audit(self, args: list[str]) -> None:
        """Show audit log entries."""
        limit = 20
        tx_id = None
        principal = None
        
        # Parse args
        i = 0
        while i < len(args):
            if args[i] == "tx" and i + 1 < len(args):
                tx_id = args[i + 1]
                i += 2
            elif args[i] == "principal" and i + 1 < len(args):
                principal = args[i + 1]
                i += 2
            elif args[i].isdigit():
                limit = int(args[i])
                i += 1
            else:
                i += 1
        
        entries = self._audit.query(tx_id=tx_id, principal=principal, limit=limit)
        
        self._print_header(f"Audit Log (last {limit})")
        
        if not entries:
            print(dim("  No entries found"))
            return
        
        for entry in entries:
            ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            prov = entry.provenance.value[:1].upper()
            
            # Color by provenance
            prov_color = {
                Provenance.HUMAN: Color.GREEN,
                Provenance.AGENT: Color.CYAN,
                Provenance.WEB_CONTENT: Color.YELLOW,
                Provenance.SYSTEM: Color.DIM,
            }.get(entry.provenance, Color.WHITE)
            
            result_color = Color.GREEN if entry.result == "success" else Color.RED if "denied" in entry.result else Color.WHITE
            
            print(
                f"  {dim(ts)} "
                f"{colored(f'[{prov}]', prov_color)} "
                f"{entry.principal:15} "
                f"{entry.op:25} "
                f"{entry.object:15} "
                f"{colored(entry.result, result_color)}"
            )
    
    def _cmd_objects(self, args: list[str]) -> None:
        """List all managed objects."""
        self._print_header("Managed Objects")
        
        for obj_type in ObjectType:
            objects = self._objects.list_by_type(obj_type)
            if objects:
                print(f"\n  {bold(obj_type.value.upper())}S:")
                for obj in objects:
                    data_preview = str(obj._data)[:60] + "..." if len(str(obj._data)) > 60 else str(obj._data)
                    print(f"    {obj.id}: {dim(data_preview)}")
        
        if not any(self._objects.list_by_type(t) for t in ObjectType):
            print(dim("  No objects"))
    
    def _cmd_tx(self, args: list[str]) -> None:
        """Show transaction state."""
        self._print_header("Transaction State")
        
        active = self._transactions.get_active_transaction()
        if not active:
            print(dim("  No active transaction"))
            return
        
        print(f"  ID: {bold(active.id)}")
        print(f"  State: {active.state.value}")
        print(f"  Started: {time.strftime('%H:%M:%S', time.localtime(active.started_at))}")
        
        checkpoints = [name for name in active.checkpoints.keys() if name != "__initial__"]
        if checkpoints:
            print(f"\n  Checkpoints:")
            for cp_name in checkpoints:
                cp = active.checkpoints[cp_name]
                print(f"    • {cp_name} ({len(cp.state)} objects)")
    
    def _cmd_approve(self, args: list[str]) -> None:
        """Approve a pending high-risk operation."""
        if not self._pending_approval:
            print(colored("No pending approval", Color.YELLOW))
            return
        # TODO: Integrate with runtime approval flow
        print(colored("Approved", Color.GREEN))
        self._pending_approval = None
    
    def _cmd_deny(self, args: list[str]) -> None:
        """Deny a pending high-risk operation."""
        if not self._pending_approval:
            print(colored("No pending denial", Color.YELLOW))
            return
        print(colored("Denied", Color.RED))
        self._pending_approval = None
    
    def _cmd_rollback(self, args: list[str]) -> None:
        """Rollback to a checkpoint."""
        active = self._transactions.get_active_transaction()
        if not active:
            print(colored("No active transaction", Color.YELLOW))
            return
        
        checkpoint = args[0] if args else "__initial__"
        try:
            self._transactions.rollback(checkpoint)
            print(colored(f"Rolled back to checkpoint: {checkpoint}", Color.GREEN))
        except Exception as e:
            print(colored(f"Rollback failed: {e}", Color.RED))
    
    def _cmd_grant(self, args: list[str]) -> None:
        """Grant a capability to the current principal."""
        if len(args) < 2:
            print(colored("Usage: grant <operation> <resource> [risk]", Color.RED))
            print(dim("  Example: grant tab.* * READ"))
            print(dim("  Example: grant form.submit form:* IRREVERSIBLE"))
            return
        
        operation = args[0]
        resource = args[1]
        risk_str = args[2].upper() if len(args) > 2 else "READ"
        
        try:
            risk = CapabilityRisk[risk_str]
        except KeyError:
            print(colored(f"Invalid risk level: {risk_str}. Use READ, STATEFUL, or IRREVERSIBLE", Color.RED))
            return
        
        principal = self._code_buffer.principal if self._code_buffer else "agent:interactive"
        
        cap = self._caps.grant(
            principal=principal,
            operation=operation,
            resource=resource,
            risk=risk,
        )
        
        print(colored(f"Granted: {principal} can {operation} on {resource} {RiskDisplay.format(risk)}", Color.GREEN))
    
    def _cmd_help(self, args: list[str]) -> None:
        """Show help."""
        self._print_header("Commands")
        print(textwrap.dedent("""
        Code Management:
          load <file>     Load code from file
          paste           Enter multiline code
          show            Display current code
          edit <line>     Edit a specific line
          validate        Check for errors
          caps            Preview required capabilities
          run             Execute the code
        
        Monitoring:
          audit [n]       Show last n audit entries
          audit tx <id>   Show entries for transaction
          objects         List managed objects
          tx              Show transaction state
        
        Governance:
          grant <op> <res> [risk]   Grant capability
          approve         Approve pending operation
          deny            Deny pending operation
          rollback [cp]   Rollback to checkpoint
        
        Other:
          help            Show this help
          quit            Exit
        """))
    
    def _cmd_quit(self, args: list[str]) -> None:
        """Exit the UI."""
        self._running = False
    
    def run(self) -> None:
        """Start the interactive terminal UI."""
        self._running = True
        
        print(bold("\n╔═══════════════════════════════════════════════════════════╗"))
        print(bold("║         Agentic Browser Kernel - Terminal UI              ║"))
        print(bold("╚═══════════════════════════════════════════════════════════╝"))
        print(dim("Type 'help' for commands, 'quit' to exit\n"))
        
        while self._running:
            try:
                line = input(self.PROMPT).strip()
                if not line:
                    continue
                
                parts = line.split()
                cmd = parts[0].lower()
                args = parts[1:]
                
                if cmd in self._commands:
                    self._commands[cmd](args)
                else:
                    print(colored(f"Unknown command: {cmd}. Type 'help' for commands.", Color.RED))
                    
            except KeyboardInterrupt:
                print("\n" + colored("Use 'quit' to exit", Color.YELLOW))
            except EOFError:
                break
        
        print(dim("\nGoodbye."))


def create_terminal_ui() -> TerminalUI:
    """Factory to create a fully-wired TerminalUI."""
    audit = AuditLog()
    caps = CapabilityBroker(audit_log=audit)
    objects = ObjectManager(audit_log=audit)
    transactions = TransactionCoordinator(objects, audit)
    runtime = AgentRuntime(
        caps=caps,
        objects=objects,
        audit=audit,
        transactions=transactions,
    )
    
    return TerminalUI(
        caps=caps,
        objects=objects,
        audit=audit,
        transactions=transactions,
        runtime=runtime,
    )


def main():
    """Entry point for terminal UI."""
    ui = create_terminal_ui()
    ui.run()


if __name__ == "__main__":
    main()
