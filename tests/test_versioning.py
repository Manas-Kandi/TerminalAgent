"""Tests for kernel versioning contract."""

import pytest
from kernel.version import (
    SemanticVersion, WorkflowMetadata, KernelVersionChecker,
    VersionCompatibility, KERNEL_VERSION, check_workflow_header,
    get_changelog,
)


class TestSemanticVersion:
    """Tests for semantic version parsing and comparison."""
    
    def test_parse_version(self):
        """Parse a version string."""
        ver = SemanticVersion.parse("1.2.3")
        
        assert ver.major == 1
        assert ver.minor == 2
        assert ver.patch == 3
    
    def test_parse_prerelease(self):
        """Parse a version with prerelease tag."""
        ver = SemanticVersion.parse("1.0.0-beta.1")
        
        assert ver.major == 1
        assert ver.prerelease == "beta.1"
    
    def test_invalid_version_raises(self):
        """Invalid version string raises ValueError."""
        with pytest.raises(ValueError):
            SemanticVersion.parse("not-a-version")
        
        with pytest.raises(ValueError):
            SemanticVersion.parse("1.2")  # Missing patch
    
    def test_version_comparison(self):
        """Version comparison works correctly."""
        v1 = SemanticVersion.parse("1.0.0")
        v2 = SemanticVersion.parse("1.0.1")
        v3 = SemanticVersion.parse("1.1.0")
        v4 = SemanticVersion.parse("2.0.0")
        
        assert v1 < v2 < v3 < v4
        assert v4 > v3 > v2 > v1
        assert v1 <= v1
        assert v1 >= v1
    
    def test_prerelease_less_than_release(self):
        """Prerelease version is less than release."""
        release = SemanticVersion.parse("1.0.0")
        prerelease = SemanticVersion.parse("1.0.0-beta.1")
        
        assert prerelease < release
    
    def test_version_to_string(self):
        """Version converts back to string."""
        ver = SemanticVersion.parse("1.2.3")
        assert str(ver) == "1.2.3"
        
        ver_pre = SemanticVersion.parse("1.0.0-alpha")
        assert str(ver_pre) == "1.0.0-alpha"
    
    def test_compatibility_same_major(self):
        """Same major version is compatible."""
        v1 = SemanticVersion.parse("1.0.0")
        v2 = SemanticVersion.parse("1.5.0")
        
        assert v1.is_compatible_with(v2)
        assert v2.is_compatible_with(v1)
    
    def test_compatibility_different_major(self):
        """Different major version is incompatible."""
        v1 = SemanticVersion.parse("1.0.0")
        v2 = SemanticVersion.parse("2.0.0")
        
        assert not v1.is_compatible_with(v2)


class TestWorkflowMetadata:
    """Tests for workflow version requirements."""
    
    def test_compatible_workflow(self):
        """Workflow is compatible with kernel."""
        workflow = WorkflowMetadata(
            name="test-workflow",
            version="1.0.0",
            min_kernel_version="0.1.0",
        )
        
        status, msg = workflow.check_compatibility("0.2.0")
        
        assert status == VersionCompatibility.COMPATIBLE
    
    def test_incompatible_min_version(self):
        """Workflow requires higher kernel version."""
        workflow = WorkflowMetadata(
            name="future-workflow",
            version="1.0.0",
            min_kernel_version="1.0.0",
        )
        
        status, msg = workflow.check_compatibility("0.2.0")
        
        assert status == VersionCompatibility.INCOMPATIBLE
        assert "requires kernel >= 1.0.0" in msg
    
    def test_incompatible_max_version(self):
        """Workflow has maximum kernel version."""
        workflow = WorkflowMetadata(
            name="legacy-workflow",
            version="1.0.0",
            min_kernel_version="0.1.0",
            max_kernel_version="0.1.5",
        )
        
        status, msg = workflow.check_compatibility("0.2.0")
        
        assert status == VersionCompatibility.INCOMPATIBLE
        assert "requires kernel <= 0.1.5" in msg
    
    def test_deprecated_workflow(self):
        """Workflow is deprecated in current kernel."""
        workflow = WorkflowMetadata(
            name="old-workflow",
            version="1.0.0",
            min_kernel_version="0.1.0",
            deprecated_in="0.2.0",
        )
        
        status, msg = workflow.check_compatibility("0.2.0")
        
        assert status == VersionCompatibility.DEPRECATED
        assert "deprecated" in msg.lower()


class TestKernelVersionChecker:
    """Tests for kernel version checker."""
    
    def test_current_version(self):
        """Can get current kernel version."""
        checker = KernelVersionChecker()
        
        assert checker.version == KERNEL_VERSION
    
    def test_check_min_version(self):
        """Check minimum version requirement."""
        checker = KernelVersionChecker("1.5.0")
        
        assert checker.check_min_version("1.0.0") is True
        assert checker.check_min_version("1.5.0") is True
        assert checker.check_min_version("2.0.0") is False
    
    def test_is_breaking_upgrade(self):
        """Detect breaking upgrades."""
        checker = KernelVersionChecker("2.0.0")
        
        assert checker.is_breaking_upgrade("1.0.0") is True
        assert checker.is_breaking_upgrade("2.5.0") is False


class TestWorkflowHeader:
    """Tests for extracting workflow metadata from code."""
    
    def test_extract_workflow_header(self):
        """Extract metadata from workflow code header."""
        code = '''
# @workflow name: login-automation
# @workflow version: 1.0.0
# @workflow min_kernel_version: 0.2.0

import browser

tab = browser.Tab.open("https://example.com")
'''
        
        metadata = check_workflow_header(code)
        
        assert metadata is not None
        assert metadata.name == "login-automation"
        assert metadata.version == "1.0.0"
        assert metadata.min_kernel_version == "0.2.0"
    
    def test_missing_header_returns_none(self):
        """Missing workflow header returns None."""
        code = '''
# Just a regular script
import browser
browser.Tab.open("https://example.com")
'''
        
        metadata = check_workflow_header(code)
        
        assert metadata is None
    
    def test_partial_header_returns_none(self):
        """Incomplete header returns None."""
        code = '''
# @workflow name: partial
# @workflow version: 1.0.0
# Missing min_kernel_version
'''
        
        metadata = check_workflow_header(code)
        
        assert metadata is None


class TestChangelog:
    """Tests for API changelog."""
    
    def test_get_changelog_between_versions(self):
        """Get changelog entries between versions."""
        entries = get_changelog("0.1.0", "0.2.0")
        
        # Should include 0.2.0 but not 0.1.0
        versions = [e["version"] for e in entries]
        assert "0.2.0" in versions
        assert "0.1.0" not in versions  # from_version is exclusive
    
    def test_changelog_sorted_by_version(self):
        """Changelog entries are sorted by version."""
        entries = get_changelog("0.0.0", "99.0.0")
        
        for i in range(len(entries) - 1):
            v1 = SemanticVersion.parse(entries[i]["version"])
            v2 = SemanticVersion.parse(entries[i + 1]["version"])
            assert v1 < v2
