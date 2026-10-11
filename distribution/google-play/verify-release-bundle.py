#!/usr/bin/env python3
"""Validate an existing signed AAB without rebuilding, installing, or publishing it.

Example, from the repository root:
  python3 distribution/google-play/verify-release-bundle.py \
    --bundle distribution/google-play/release/AgentAgenda-2.0.3+10.aab \
    --previous-bundle distribution/google-play/release/AgentAgenda-2.0.2+9.aab \
    --output distribution/google-play/verification/release-bundle-version-10.json

The previous bundle is used only for byte comparisons. Previous runtime results
are never presented as runtime verification of the new bundle.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


DEFAULT_BUNDLETOOL = (
    Path.home() / ".local/share/agentagenda/tools/bundletool-all-1.18.3.jar"
)
UPLOAD_CERTIFICATE_SHA256 = (
    "35e555ba23217ca7b9565e94b732e3974e6f77e15e9f32496d18d3a507dab69f"
)
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
PAGE_SIZE = 16384

# JarFile verifies signatures when each entry is read to EOF. This also avoids
# confusing a ZIP entry-order warning from JarInputStream with an unsigned AAB.
# Neither this helper nor jarsigner needs access to the private signing key.
JAR_VERIFIER = r"""
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.security.cert.*;
import java.util.*;
import java.util.jar.*;

class VerifyBundleSignatures {
  public static void main(String[] args) throws Exception {
    int payloads = 0, signed = 0, unsigned = 0;
    Set<String> fingerprints = new TreeSet<>();
    Set<String> expirationDates = new TreeSet<>();
    try (JarFile jar = new JarFile(args[0], true)) {
      if (jar.getManifest() == null) throw new SecurityException("Missing JAR manifest");
      Enumeration<JarEntry> entries = jar.entries();
      while (entries.hasMoreElements()) {
        JarEntry entry = entries.nextElement();
        if (entry.isDirectory()) continue;
        String name = entry.getName().toUpperCase(Locale.ROOT);
        if (name.startsWith("META-INF/")) {
          String tail = name.substring("META-INF/".length());
          if (!tail.contains("/") && (tail.equals("MANIFEST.MF") ||
              tail.endsWith(".SF") || tail.endsWith(".RSA") ||
              tail.endsWith(".DSA") || tail.endsWith(".EC") ||
              tail.startsWith("SIG-"))) continue;
        }
        try (InputStream stream = jar.getInputStream(entry)) {
          stream.transferTo(OutputStream.nullOutputStream());
        }
        payloads++;
        CodeSigner[] signers = entry.getCodeSigners();
        if (signers == null || signers.length == 0) { unsigned++; continue; }
        signed++;
        for (CodeSigner signer : signers) {
          X509Certificate certificate = (X509Certificate)
              signer.getSignerCertPath().getCertificates().get(0);
          certificate.checkValidity();
          fingerprints.add(HexFormat.of().formatHex(
              MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded())));
          expirationDates.add(certificate.getNotAfter().toInstant().toString());
        }
      }
    }
    System.out.println("{\"payloads\":" + payloads +
        ",\"signed_payloads\":" + signed + ",\"unsigned_payloads\":" + unsigned +
        ",\"certificate_sha256\":[\"" + String.join("\",\"", fingerprints) +
        "\"],\"certificate_valid_until\":[\"" + String.join("\",\"", expirationDates) + "\"]}");
  }
}
"""


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command):
    return subprocess.run(
        [str(part) for part in command],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def concise_diagnostics(result):
    # Recent JDKs emit one warning per ZIP payload for the known manifest-order
    # difference. Preserve the explanation once, not hundreds of duplicate lines.
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    omitted = sum(line.startswith("- Entry ") for line in lines)
    return {
        "exit_code": result.returncode,
        "diagnostics": "\n".join(
            line for line in lines if not line.startswith("- Entry ")
        ).strip()[:12000],
        "entry_order_warning_lines_omitted": omitted,
    }


def zip_checks(bundle):
    entries = bundle.infolist()
    names = [entry.filename for entry in entries]
    return {
        "entries": len(entries),
        "duplicate_names": sorted(
            name for name, count in Counter(names).items() if count > 1
        ),
        "symlinks": [
            entry.filename
            for entry in entries
            if stat.S_ISLNK(entry.external_attr >> 16)
        ],
    }


def native_library_hashes(bundle):
    return {
        entry.filename: hashlib.sha256(bundle.read(entry)).hexdigest()
        for entry in bundle.infolist()
        if "/lib/" in entry.filename and entry.filename.endswith(".so")
    }


def elf_load_segments(data):
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise ValueError("Native library is not a complete ELF file")
    elf_class, encoding = data[4], data[5]
    if elf_class not in (1, 2) or encoding not in (1, 2):
        raise ValueError("Unsupported ELF class or byte order")
    endian = "<" if encoding == 1 else ">"
    if elf_class == 2:
        table_offset = struct.unpack_from(endian + "Q", data, 32)[0]
        entry_size, count = struct.unpack_from(endian + "HH", data, 54)
        layout = endian + "IIQQQQQQ"
    else:
        table_offset = struct.unpack_from(endian + "I", data, 28)[0]
        entry_size, count = struct.unpack_from(endian + "HH", data, 42)
        layout = endian + "IIIIIIII"
    if count == 0 or entry_size < struct.calcsize(layout):
        raise ValueError("ELF program header table is missing or invalid")
    if table_offset + entry_size * count > len(data):
        raise ValueError("ELF program header table exceeds file size")
    segments = []
    for index in range(count):
        fields = struct.unpack_from(layout, data, table_offset + index * entry_size)
        if fields[0] != 1:  # PT_LOAD
            continue
        offset, virtual_address = fields[2:4] if elf_class == 2 else fields[1:3]
        alignment = fields[7]
        segments.append({
            "offset": offset,
            "virtual_address": virtual_address,
            "alignment": alignment,
            "aligned_16kb": alignment >= PAGE_SIZE
            and alignment & (alignment - 1) == 0
            and offset % PAGE_SIZE == virtual_address % PAGE_SIZE,
        })
    if not segments:
        raise ValueError("ELF has no loadable segments")
    return {
        "elf_bits": 64 if elf_class == 2 else 32,
        "load_segments": segments,
        "passed_16kb": all(segment["aligned_16kb"] for segment in segments)
        if elf_class == 2 else None,
    }


def verify(args):
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "checks": {},
        "errors": [],
        "scope": {
            "built": False,
            "installed": False,
            "published": False,
            "apk_splits_generated": False,
            "runtime_tested_for_this_bundle": False,
            "limitations": [
                "ELF and bundle alignment checks are static checks, not a 16 KB runtime test.",
                "Byte-identical non-app libraries preserve comparison evidence only; previous runtime results do not verify this version.",
                "This validation does not establish Google Play acceptance or review status.",
            ],
        },
    }

    def check(name, passed):
        report["checks"][name] = bool(passed)

    def stage(name, operation):
        try:
            operation()
        except (OSError, ValueError, KeyError, struct.error, zipfile.BadZipFile,
                ET.ParseError, subprocess.SubprocessError) as error:
            check(name, False)
            report["errors"].append({"stage": name, "message": str(error)[:2000]})

    def inspect_artifacts():
        if args.bundle.resolve() == args.previous_bundle.resolve():
            raise ValueError("Current and previous bundle must be different files")
        report["artifact"] = {
            "path": str(args.bundle.resolve()),
            "bytes": args.bundle.stat().st_size,
            "sha256": sha256_file(args.bundle),
        }
        report["previous_artifact"] = {
            "path": str(args.previous_bundle.resolve()),
            "bytes": args.previous_bundle.stat().st_size,
            "sha256": sha256_file(args.previous_bundle),
        }
        with zipfile.ZipFile(args.bundle) as bundle, zipfile.ZipFile(args.previous_bundle) as previous:
            report["zip"] = zip_checks(bundle)
            report["previous_zip"] = zip_checks(previous)
            check("zip_unique_names_and_no_symlinks", not report["zip"]["duplicate_names"] and not report["zip"]["symlinks"])
            check("previous_zip_unique_names_and_no_symlinks", not report["previous_zip"]["duplicate_names"] and not report["previous_zip"]["symlinks"])
            current_hashes = native_library_hashes(bundle)
            previous_hashes = native_library_hashes(previous)
            native = []
            for name, digest in sorted(current_hashes.items()):
                native.append({"library": name, "sha256": digest, **elf_load_segments(bundle.read(name))})
            report["native_libraries"] = native
            native64 = [library for library in native if library["elf_bits"] == 64]
            check("elf_64_bit_load_segments_aligned_16kb", bool(native64) and all(library["passed_16kb"] for library in native64))
            current_non_app = {name: digest for name, digest in current_hashes.items() if Path(name).name != "libapp.so"}
            previous_non_app = {name: digest for name, digest in previous_hashes.items() if Path(name).name != "libapp.so"}
            shared = current_non_app.keys() & previous_non_app.keys()
            comparison = {
                "added": sorted(current_non_app.keys() - previous_non_app.keys()),
                "removed": sorted(previous_non_app.keys() - current_non_app.keys()),
                "changed": sorted(name for name in shared if current_non_app[name] != previous_non_app[name]),
                "unchanged": sorted(name for name in shared if current_non_app[name] == previous_non_app[name]),
                "current_sha256": current_non_app,
                "previous_sha256": previous_non_app,
                "previous_runtime_results_reused_as_current": False,
            }
            report["non_app_native_comparison"] = comparison
            check("non_app_native_libraries_unchanged", bool(current_non_app) and current_non_app == previous_non_app)

    def verify_signature():
        result = run(["jarsigner", "-J-Duser.language=en", "-J-Duser.country=US", "-verify", args.bundle])
        report["jarsigner"] = concise_diagnostics(result)
        check("jarsigner_verified", result.returncode == 0 and "jar verified." in result.stdout.lower())
        with tempfile.TemporaryDirectory(prefix="agentagenda-aab-signatures-") as temporary:
            helper = Path(temporary) / "VerifyBundleSignatures.java"
            helper.write_text(JAR_VERIFIER, encoding="utf-8")
            helper.chmod(0o600)
            verified = run(["java", helper, args.bundle.resolve()])
            if verified.returncode:
                report["jarfile"] = concise_diagnostics(verified)
                check("jarfile_all_payloads_signed_by_expected_certificate", False)
                return
            signature = json.loads(verified.stdout)
            signature["expected_certificate_sha256"] = args.expected_certificate_sha256.lower().replace(":", "")
            report["jarfile"] = signature
            check("jarfile_all_payloads_signed_by_expected_certificate",
                  signature["payloads"] > 0
                  and signature["signed_payloads"] == signature["payloads"]
                  and signature["unsigned_payloads"] == 0
                  and signature["certificate_sha256"] == [signature["expected_certificate_sha256"]])

    def verify_bundletool():
        report["bundletool"] = {"path": str(args.bundletool.resolve()), "sha256": sha256_file(args.bundletool)}
        command = ["java", "-jar", args.bundletool]
        result = run([*command, "validate", "--bundle=" + str(args.bundle)])
        report["bundletool"]["validate"] = concise_diagnostics(result)
        check("bundletool_validate", result.returncode == 0)
        manifest = run([*command, "dump", "manifest", "--bundle=" + str(args.bundle)])
        if manifest.returncode:
            raise ValueError("bundletool dump manifest failed: " + manifest.stderr[:2000])
        root = ET.fromstring(manifest.stdout)
        uses_sdk = root.find("uses-sdk")
        application = root.find("application")
        info = {
            "package": root.get("package"),
            "version_name": root.get(ANDROID_NS + "versionName"),
            "version_code": root.get(ANDROID_NS + "versionCode"),
            "min_sdk": uses_sdk.get(ANDROID_NS + "minSdkVersion") if uses_sdk is not None else None,
            "target_sdk": uses_sdk.get(ANDROID_NS + "targetSdkVersion") if uses_sdk is not None else None,
            "permissions": sorted(element.get(ANDROID_NS + "name") for element in root.findall("uses-permission")),
            "application": {
                name: application.get(ANDROID_NS + name)
                for name in ("debuggable", "allowBackup", "usesCleartextTraffic", "extractNativeLibs")
            } if application is not None else None,
        }
        report["manifest"] = info
        check("manifest_package", info["package"] == args.expected_package)
        check("manifest_version_name", info["version_name"] == args.expected_version_name)
        check("manifest_version_code", info["version_code"] == str(args.expected_version_code))
        config = run([*command, "dump", "config", "--bundle=" + str(args.bundle)])
        if config.returncode:
            raise ValueError("bundletool dump config failed: " + config.stderr[:2000])
        config_info = json.loads(config.stdout)
        report["bundle_config"] = config_info
        alignment = config_info.get("optimizations", {}).get("uncompressNativeLibraries", {})
        check("bundle_native_alignment_16kb", alignment.get("enabled") is True and alignment.get("alignment") == "PAGE_ALIGNMENT_16K")

    stage("artifact_and_native_inspection", inspect_artifacts)
    stage("signature_verification", verify_signature)
    stage("bundletool_inspection", verify_bundletool)
    report["passed"] = bool(report["checks"]) and all(report["checks"].values()) and not report["errors"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-bundle", type=Path, required=True)
    parser.add_argument("--bundletool", type=Path, default=DEFAULT_BUNDLETOOL)
    parser.add_argument("--expected-package", default="com.agentagenda.agent_agenda")
    parser.add_argument("--expected-version-name", default="2.0.3")
    parser.add_argument("--expected-version-code", type=int, default=10)
    parser.add_argument("--expected-certificate-sha256", default=UPLOAD_CERTIFICATE_SHA256)
    args = parser.parse_args()
    if args.output.resolve() in {args.bundle.resolve(), args.previous_bundle.resolve(), args.bundletool.resolve(), Path(__file__).resolve()}:
        parser.error("Output must not overwrite an input artifact or this script")
    report = verify(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.output.parent, prefix=".bundle-validation-", delete=False) as destination:
        temporary_path = Path(destination.name)
        json.dump(report, destination, indent=2, ensure_ascii=False)
        destination.write("\n")
    try:
        os.replace(temporary_path, args.output)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(json.dumps({
        "passed": report["passed"],
        "output": str(args.output.resolve()),
        "failed_checks": [name for name, passed in report["checks"].items() if not passed],
        "errors": report["errors"],
    }, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
