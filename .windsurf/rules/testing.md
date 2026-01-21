# Testing Standards

## Required Tests
- Unit test per API function
- Integration test per workflow
- Security test for capability enforcement
- Replay test: log → replay → verify

## Test Structure
```python
def test_tab_navigation_with_capability():
    # Given: capability granted
    caps.grant('cap.tab.navigate:42')
    
    # When: navigate
    result = tab.navigate('https://example.com')
    
    # Then: success + audit logged
    assert result.success
    assert audit.last_entry.operation == 'tab.navigate'
```

## Coverage Requirements
- Success paths
- Failure paths (missing caps, network errors)
- Edge cases (empty data, timeouts)
