#!/usr/bin/env python3
"""Read R8 results and DEX sizes from an existing AAB without rebuilding it."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def inspect_bundle(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    with zipfile.ZipFile(path) as bundle:
        metadata_path = "BUNDLE-METADATA/com.android.tools/r8.json"
        metadata = json.loads(bundle.read(metadata_path))
        dex_files = [
            {"path": entry.filename, "uncompressed_bytes": entry.file_size}
            for entry in bundle.infolist()
            if entry.filename.endswith(".dex")
        ]
        options = metadata["options"]
        stats = metadata["stats"]
        percentages = {}
        for label, field in (
            ("optimization", "noOptimizationPercentage"),
            ("obfuscation", "noObfuscationPercentage"),
            ("shrinking", "noShrinkingPercentage"),
        ):
            unoptimized = float(stats[field])
            if not 0 <= unoptimized <= 100:
                raise ValueError(f"Unexpected R8 percentage: {field}")
            percentages[label] = round(100 - unoptimized, 2)

        return {
            "artifact": path.name,
            "sha256": digest.hexdigest(),
            "metadata_path": metadata_path,
            "r8_version": metadata["version"],
            "dex_files": dex_files,
            "uncompressed_dex_bytes": sum(
                entry["uncompressed_bytes"] for entry in dex_files
            ),
            "optimization_enabled": options["isOptimizationsEnabled"],
            "obfuscation_enabled": options["isObfuscationEnabled"],
            "shrinking_enabled": options["isShrinkingEnabled"],
            "full_mode": not options["isProGuardCompatibilityModeEnabled"],
            "optimized_resource_shrinking": metadata["resourceOptimization"][
                "isOptimizedShrinkingEnabled"
            ],
            "percentages": percentages,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aab", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_bundle(args.aab), indent=2, ensure_ascii=False))
