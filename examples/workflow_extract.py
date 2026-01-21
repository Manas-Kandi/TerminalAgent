"""Example Workflow: Documentation extraction.

This demonstrates:
1. Navigate to documentation site
2. Extract readable content
3. Query audit trail for the session

Run with: python examples/workflow_extract.py
"""

from kernel.capabilities import CapabilityBroker, CapabilityRisk
from kernel.objects import ObjectManager, ObjectType
from kernel.audit import AuditLog
from kernel.transactions import TransactionCoordinator
from kernel.renderer.mock import MockRenderer


def main():
    print("=" * 60)
    print("Workflow: Documentation Extraction")
    print("=" * 60)
    
    # Initialize kernel components
    audit = AuditLog()
    caps = CapabilityBroker(audit_log=audit)
    objects = ObjectManager(audit_log=audit)
    transactions = TransactionCoordinator(objects, audit)
    renderer = MockRenderer(objects, audit)
    
    # Grant read-only capabilities
    caps.grant("workflow:docs", "tab.*", "*", risk=CapabilityRisk.READ)
    
    print("\n[1] Creating tab and navigating to docs...")
    tab = objects.create(ObjectType.TAB, url="about:blank")
    renderer.navigate(tab.id, "https://docs.example.com/")
    print(f"    Tab: {tab.id}")
    print(f"    URL: {tab.url}")
    print(f"    Title: {tab._data['title']}")
    
    print("\n[2] Extracting readable content...")
    content = renderer.extract(tab.id, "readable")
    print(f"    Word count: {content['word_count']}")
    print(f"    Content preview:")
    preview = content['content'][:200] + "..." if len(content['content']) > 200 else content['content']
    for line in preview.split('\n')[:5]:
        print(f"      {line}")
    
    print("\n[3] Extracting links...")
    links = renderer.extract(tab.id, "links")
    print(f"    Found {len(links['links'])} links:")
    for link in links['links']:
        print(f"      - {link['text']}: {link['href']}")
    
    print("\n[4] Checking audit trail...")
    entries = audit.query(op="renderer.*")
    print(f"    Renderer operations logged: {len(entries)}")
    for entry in entries:
        print(f"      [{entry.provenance.value}] {entry.op} on {entry.object}")
    
    print("\n" + "=" * 60)
    print("Extraction workflow completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
