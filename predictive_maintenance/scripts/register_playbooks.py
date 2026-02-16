#!/usr/bin/env python3
"""
Register Example Playbooks

This script registers the example playbooks from the autopilot/playbooks directory
into the playbook registry. Run this after database migrations are complete.

Usage:
    python -m scripts.register_playbooks
    # or from predictive_maintenance directory:
    python scripts/register_playbooks.py
"""

import os
import sys
import logging
from pathlib import Path

# Add the predictive_maintenance directory to path
script_dir = Path(__file__).parent
pm_dir = script_dir.parent
if str(pm_dir) not in sys.path:
    sys.path.insert(0, str(pm_dir))

from predictive_maintenance.autopilot.playbook.parser import PlaybookParser
from predictive_maintenance.autopilot.playbook.schema import PlaybookDefinition

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_playbook_from_file(file_path: str) -> PlaybookDefinition:
    """Load and parse a playbook from a YAML file"""
    parser = PlaybookParser(strict=False)
    return parser.parse_file(file_path)


def register_playbooks_from_directory(playbooks_dir: str) -> dict:
    """
    Register all playbooks from a directory.
    
    Returns:
        dict: Summary of registered playbooks
    """
    results = {
        "registered": [],
        "failed": [],
        "skipped": [],
    }
    
    playbooks_path = Path(playbooks_dir)
    if not playbooks_path.exists():
        logger.error(f"Playbooks directory not found: {playbooks_dir}")
        return results
    
    yaml_files = list(playbooks_path.glob("*.yaml")) + list(playbooks_path.glob("*.yml"))
    
    logger.info(f"Found {len(yaml_files)} playbook files in {playbooks_dir}")
    
    for yaml_file in yaml_files:
        try:
            logger.info(f"Loading playbook: {yaml_file.name}")
            playbook = load_playbook_from_file(str(yaml_file))
            
            results["registered"].append({
                "id": playbook.id,
                "name": playbook.name,
                "version": playbook.version,
                "asset_class": playbook.asset_class,
                "fault_type": playbook.fault_type,
                "risk_tier": playbook.risk_tier,
                "steps": len(playbook.steps),
                "file": yaml_file.name,
            })
            
            logger.info(f"  ✓ Registered: {playbook.id} v{playbook.version} ({playbook.name})")
            
        except Exception as e:
            logger.error(f"  ✗ Failed to load {yaml_file.name}: {e}")
            results["failed"].append({
                "file": yaml_file.name,
                "error": str(e),
            })
    
    return results


def print_summary(results: dict):
    """Print registration summary"""
    print("\n" + "=" * 60)
    print("PLAYBOOK REGISTRATION SUMMARY")
    print("=" * 60)
    
    print(f"\n✓ Registered: {len(results['registered'])}")
    for pb in results["registered"]:
        print(f"  - {pb['id']} ({pb['name']}) - {pb['fault_type']} [{pb['risk_tier']}]")
    
    if results["failed"]:
        print(f"\n✗ Failed: {len(results['failed'])}")
        for fail in results["failed"]:
            print(f"  - {fail['file']}: {fail['error']}")
    
    if results["skipped"]:
        print(f"\n○ Skipped: {len(results['skipped'])}")
        for skip in results["skipped"]:
            print(f"  - {skip}")
    
    print("\n" + "=" * 60)


def main():
    """Main entry point"""
    # Determine playbooks directory
    script_dir = Path(__file__).parent
    playbooks_dir = script_dir.parent / "autopilot" / "playbooks"
    
    logger.info(f"Registering playbooks from: {playbooks_dir}")
    
    # Register playbooks
    results = register_playbooks_from_directory(str(playbooks_dir))
    
    # Print summary
    print_summary(results)
    
    # Return exit code based on results
    if results["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
