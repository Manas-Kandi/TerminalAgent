"""Kernel Versioning Contract.

Defines:
- Semantic versioning for the kernel
- API compatibility rules
- min_kernel_version checking for workflows
- Breaking change detection
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


# Current kernel version
KERNEL_VERSION = "0.2.0"  # Tagged: Chromium-ready with COW snapshots

# Minimum supported workflow version (workflows below this won't run)
MIN_WORKFLOW_VERSION = "0.1.0"


class VersionCompatibility(Enum):
    """Compatibility status between versions."""
    COMPATIBLE = "compatible"
    DEPRECATED = "deprecated"  # Works but will break in future
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class SemanticVersion:
    """Semantic version (major.minor.patch)."""
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None
    
    @classmethod
    def parse(cls, version_str: str) -> "SemanticVersion":
        """Parse a version string like '1.2.3' or '1.2.3-beta.1'."""
        pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$"
        match = re.match(pattern, version_str)
        if not match:
            raise ValueError(f"Invalid version string: {version_str}")
        
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4),
        )
    
    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{self.prerelease}"
        return base
    
    def __lt__(self, other: "SemanticVersion") -> bool:
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        # Prerelease versions are less than release versions
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        return (self.prerelease or "") < (other.prerelease or "")
    
    def __le__(self, other: "SemanticVersion") -> bool:
        return self == other or self < other
    
    def __gt__(self, other: "SemanticVersion") -> bool:
        return not self <= other
    
    def __ge__(self, other: "SemanticVersion") -> bool:
        return not self < other
    
    def is_compatible_with(self, other: "SemanticVersion") -> bool:
        """Check if this version is API-compatible with another.
        
        Compatibility rules (semver):
        - Major version change = breaking, incompatible
        - Minor version change = new features, backwards compatible
        - Patch version change = bug fixes, backwards compatible
        """
        return self.major == other.major


@dataclass
class WorkflowMetadata:
    """Metadata for a workflow, including version requirements."""
    name: str
    version: str
    min_kernel_version: str
    max_kernel_version: Optional[str] = None
    deprecated_in: Optional[str] = None
    
    def check_compatibility(self, kernel_version: str) -> Tuple[VersionCompatibility, str]:
        """Check if this workflow is compatible with the given kernel version.
        
        Returns:
            Tuple of (compatibility_status, message)
        """
        kernel_ver = SemanticVersion.parse(kernel_version)
        min_ver = SemanticVersion.parse(self.min_kernel_version)
        
        # Check minimum version
        if kernel_ver < min_ver:
            return (
                VersionCompatibility.INCOMPATIBLE,
                f"Workflow requires kernel >= {self.min_kernel_version}, got {kernel_version}"
            )
        
        # Check maximum version if specified
        if self.max_kernel_version:
            max_ver = SemanticVersion.parse(self.max_kernel_version)
            if kernel_ver > max_ver:
                return (
                    VersionCompatibility.INCOMPATIBLE,
                    f"Workflow requires kernel <= {self.max_kernel_version}, got {kernel_version}"
                )
        
        # Check API compatibility (same major version)
        if not kernel_ver.is_compatible_with(min_ver):
            return (
                VersionCompatibility.INCOMPATIBLE,
                f"Workflow built for kernel {min_ver.major}.x, running on {kernel_ver.major}.x"
            )
        
        # Check deprecation
        if self.deprecated_in:
            deprecated_ver = SemanticVersion.parse(self.deprecated_in)
            if kernel_ver >= deprecated_ver:
                return (
                    VersionCompatibility.DEPRECATED,
                    f"Workflow is deprecated as of kernel {self.deprecated_in}"
                )
        
        return (VersionCompatibility.COMPATIBLE, "OK")


class KernelVersionChecker:
    """Checks workflow compatibility with current kernel."""
    
    def __init__(self, kernel_version: str = KERNEL_VERSION):
        self._kernel_version = kernel_version
        self._kernel_ver = SemanticVersion.parse(kernel_version)
    
    @property
    def version(self) -> str:
        return self._kernel_version
    
    @property
    def version_tuple(self) -> Tuple[int, int, int]:
        return (self._kernel_ver.major, self._kernel_ver.minor, self._kernel_ver.patch)
    
    def check_workflow(self, workflow: WorkflowMetadata) -> Tuple[VersionCompatibility, str]:
        """Check if a workflow is compatible with this kernel."""
        return workflow.check_compatibility(self._kernel_version)
    
    def check_min_version(self, min_version: str) -> bool:
        """Check if kernel meets minimum version requirement."""
        min_ver = SemanticVersion.parse(min_version)
        return self._kernel_ver >= min_ver
    
    def is_breaking_upgrade(self, from_version: str) -> bool:
        """Check if upgrading from a version would be breaking."""
        from_ver = SemanticVersion.parse(from_version)
        return self._kernel_ver.major != from_ver.major


# API Changelog for tracking breaking changes
API_CHANGELOG = {
    "0.1.0": {
        "description": "Initial release",
        "added": [
            "CapabilityBroker",
            "ObjectManager", 
            "AuditLog",
            "TransactionCoordinator",
            "AgentRuntime",
        ],
        "breaking": [],
    },
    "0.2.0": {
        "description": "Security hardening",
        "added": [
            "SessionManager",
            "PII field hashing",
            "CDP schema validation",
            "Chaos testing",
        ],
        "breaking": [],
        "deprecated": [],
    },
}


def get_changelog(from_version: str, to_version: str) -> list[dict]:
    """Get changelog entries between two versions."""
    from_ver = SemanticVersion.parse(from_version)
    to_ver = SemanticVersion.parse(to_version)
    
    entries = []
    for version_str, entry in API_CHANGELOG.items():
        ver = SemanticVersion.parse(version_str)
        if from_ver < ver <= to_ver:
            entries.append({"version": version_str, **entry})
    
    return sorted(entries, key=lambda e: SemanticVersion.parse(e["version"]))


def check_workflow_header(code: str) -> Optional[WorkflowMetadata]:
    """Extract workflow metadata from code header comment.
    
    Expected format:
    # @workflow name: my-workflow
    # @workflow version: 1.0.0
    # @workflow min_kernel_version: 0.2.0
    """
    metadata = {}
    
    for line in code.split("\n")[:20]:  # Only check first 20 lines
        line = line.strip()
        if not line.startswith("#"):
            continue
        
        if "@workflow" in line:
            match = re.match(r"#\s*@workflow\s+(\w+):\s*(.+)", line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                metadata[key] = value
    
    if "name" in metadata and "version" in metadata and "min_kernel_version" in metadata:
        return WorkflowMetadata(
            name=metadata["name"],
            version=metadata["version"],
            min_kernel_version=metadata["min_kernel_version"],
            max_kernel_version=metadata.get("max_kernel_version"),
            deprecated_in=metadata.get("deprecated_in"),
        )
    
    return None
