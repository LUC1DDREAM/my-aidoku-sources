#!/usr/bin/env python3
import json

with open('config/source_policy.json') as f:
    policy = json.load(f)

# Remove from quarantine
if 'en.asurascans' in policy.get('quarantinedSources', {}):
    del policy['quarantinedSources']['en.asurascans']

# Add local override
policy['localPackageOverrides'] = policy.get('localPackageOverrides', {})
policy['localPackageOverrides']['en.asurascans'] = {
    'path': 'overrides/en.asurascans-v20.aix',
    'provenanceURL': 'https://github.com/LUC1DDREAM/my-aidoku-sources/blob/main/overrides/en.asurascans-v20.aix'
}

with open('config/source_policy.json', 'w') as f:
    json.dump(policy, f, indent=2)

print("✓ Policy updated: Asura Scans v19 override added, quarantine removed")
