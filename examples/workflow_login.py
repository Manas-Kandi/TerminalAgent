"""Example Workflow: Login form with transaction rollback.

This demonstrates the full kernel working with the mock renderer:
1. Open login page
2. Find and fill login form
3. Use transaction checkpoint before fill
4. Rollback to checkpoint instead of submit

Run with: python examples/workflow_login.py
"""

from kernel.capabilities import CapabilityBroker, CapabilityRisk
from kernel.objects import ObjectManager, ObjectType
from kernel.audit import AuditLog
from kernel.transactions import TransactionCoordinator
from kernel.renderer.mock import MockRenderer


def main():
    print("=" * 60)
    print("Workflow: Login Form with Transaction Rollback")
    print("=" * 60)
    
    # Initialize kernel components
    audit = AuditLog()
    caps = CapabilityBroker(audit_log=audit)
    objects = ObjectManager(audit_log=audit)
    transactions = TransactionCoordinator(objects, audit)
    renderer = MockRenderer(objects, audit)
    
    # Grant capabilities (simulating what the UI would do)
    caps.grant("workflow:login", "tab.*", "*", risk=CapabilityRisk.STATEFUL)
    caps.grant("workflow:login", "form.*", "*", risk=CapabilityRisk.STATEFUL)
    
    print("\n[1] Creating tab and navigating to login page...")
    tab = objects.create(ObjectType.TAB, url="about:blank")
    print(f"    Created: {tab.id}")
    
    result = renderer.navigate(tab.id, "https://example.com/login")
    print(f"    Navigated to: {result['url']}")
    print(f"    Page title: {result['title']}")
    
    print("\n[2] Finding login form...")
    form_id = renderer.find_form(tab.id, "login")
    print(f"    Found form: {form_id}")
    
    print("\n[3] Starting transaction...")
    with transactions.begin() as tx:
        print(f"    Transaction ID: {tx.id}")
        
        print("\n[4] Creating checkpoint before form fill...")
        tx.checkpoint("before-fill")
        print("    Checkpoint: before-fill")
        
        form = objects.get(form_id)
        print(f"    Form state at checkpoint: {form._data['filled']}")
        
        print("\n[5] Filling login form...")
        renderer.fill_form(form_id, {
            "email": "test@example.com",
            "password": "supersecret123",
        })
        
        form = objects.get(form_id)
        print(f"    Filled email: {form._data['filled'].get('email')}")
        print(f"    Filled password: {'*' * len(form._data['filled'].get('password', ''))}")
        
        print("\n[6] Rolling back to checkpoint (simulating user cancellation)...")
        tx.rollback("before-fill")
        
        # Verify rollback
        form_after = objects.get(form_id)
        print(f"    Form filled data after rollback: {form_after._data['filled']}")
        
        print("\n[7] Committing transaction...")
        tx.commit()
        print("    Transaction committed")
    
    print("\n[8] Checking audit log...")
    entries = audit.query(limit=10)
    print(f"    Total audit entries: {len(entries)}")
    print("\n    Recent operations:")
    for entry in entries[-5:]:
        print(f"      - {entry.op}: {entry.object} ({entry.result})")
    
    print("\n" + "=" * 60)
    print("Workflow completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
