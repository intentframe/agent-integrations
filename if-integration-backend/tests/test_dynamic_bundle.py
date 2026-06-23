#!/usr/bin/env python3
"""Unit tests for GenericDynamicBundle and manifest parsing."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "if-integration-backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


class TestManifestParsing(unittest.TestCase):
    def test_parse_comma_separated_ids(self) -> None:
        from if_security_backend.bundles.dynamic import parse_manifest_ids

        self.assertEqual(
            parse_manifest_ids("HERMES_CRONJOB, HERMES_WEB_EXTRACT"),
            frozenset({"HERMES_CRONJOB", "HERMES_WEB_EXTRACT"}),
        )

    def test_parse_tolerates_trailing_comma_and_whitespace(self) -> None:
        from if_security_backend.bundles.dynamic import parse_manifest_ids

        self.assertEqual(
            parse_manifest_ids(" HERMES_CRONJOB , \n"),
            frozenset({"HERMES_CRONJOB"}),
        )

    def test_parse_empty_raises(self) -> None:
        from if_security_backend.bundles.dynamic import parse_manifest_ids

        with self.assertRaises(ValueError):
            parse_manifest_ids("  ,  ")


class TestGenericDynamicBundle(unittest.TestCase):
    def test_rejects_native_action_overlap(self) -> None:
        from if_security_backend.bundles.dynamic import GenericDynamicBundle

        with self.assertRaises(ValueError):
            GenericDynamicBundle(frozenset({"RUN_COMMAND", "HERMES_CRONJOB"}))

    def test_rejects_constraints_at_boot_validation(self) -> None:
        from if_security_backend.bundles.dynamic import GenericDynamicBundle
        from intentframe_bundle_sdk.types import ActionPermission, BundleConfigError

        bundle = GenericDynamicBundle(frozenset({"HERMES_CRONJOB"}))
        permission = ActionPermission(
            safe=False,
            constraints={"blocked_patterns": ["sudo"]},
        )
        with self.assertRaises(BundleConfigError):
            bundle.validate_constraints(permission)

    def test_register_bundles_noop_without_env(self) -> None:
        from if_security_backend.bundles import dynamic as dynamic_module
        import intentframe_bundle_sdk.registry as registry

        previous = os.environ.pop("IF_DYNAMIC_BUNDLE_MANIFEST", None)
        saved_actions = dict(registry._ACTION_BY_ID)
        saved_instances = list(registry._ACTION_INSTANCES)
        registry._ACTION_BY_ID.clear()
        registry._ACTION_INSTANCES.clear()
        try:
            dynamic_module.register_bundles(registry)
            self.assertEqual(len(registry._ACTION_INSTANCES), 0)
        finally:
            registry._ACTION_BY_ID.clear()
            registry._ACTION_INSTANCES.clear()
            registry._ACTION_BY_ID.update(saved_actions)
            registry._ACTION_INSTANCES.extend(saved_instances)
            if previous is not None:
                os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = previous

    def test_register_bundles_reads_manifest_from_env(self) -> None:
        from if_security_backend.bundles import dynamic as dynamic_module
        from intentframe_bundle_sdk.registry import action_bundle_for
        import intentframe_bundle_sdk.registry as registry

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "generic_actions.manifest"
            manifest.write_text("HERMES_CRONJOB", encoding="utf-8")
            previous = os.environ.get("IF_DYNAMIC_BUNDLE_MANIFEST")
            os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = str(manifest)
            saved_actions = dict(registry._ACTION_BY_ID)
            saved_instances = list(registry._ACTION_INSTANCES)
            registry._ACTION_BY_ID.clear()
            registry._ACTION_INSTANCES.clear()
            try:
                dynamic_module.register_bundles(registry)
                bundle = action_bundle_for("HERMES_CRONJOB")
                self.assertIsNotNone(bundle)
                assert bundle is not None
                self.assertEqual(bundle.bundle_id, "dynamic")
            finally:
                registry._ACTION_BY_ID.clear()
                registry._ACTION_INSTANCES.clear()
                registry._ACTION_BY_ID.update(saved_actions)
                registry._ACTION_INSTANCES.extend(saved_instances)
                if previous is None:
                    os.environ.pop("IF_DYNAMIC_BUNDLE_MANIFEST", None)
                else:
                    os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = previous


class TestCoreBundlePackages(unittest.TestCase):
    def test_load_core_bundle_packages(self) -> None:
        from if_security_backend.runtime.bundles import load_core_bundle_packages

        packages = load_core_bundle_packages()
        self.assertIn("native", packages)
        self.assertIn("dynamic", packages)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
