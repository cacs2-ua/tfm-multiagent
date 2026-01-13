from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from company_pack import (
    PLATFORM_VERSION,
    CompanyPackExtractionError,
    CompanyPackNotFoundError,
    CompanyPackValidationError,
)
from company_pack.loader import load_company_pack
from company_pack.scaffold import create_company_pack_skeleton
from typing import Any

from company_pack.pluginsystem import (
    PluginRegistry,
    PluginCallContext,
    PluginStatus,
    PluginResult,
    PluginType,
    PluginMeta,
    FieldSpec,
    ConfigSchema,
    PluginBase,
    PluginValidationError,
    PluginCompatibilityError,
    PluginSettingsError,
    PluginNotEnabledError,
    PluginNotFoundError,
)
from company_pack.pluginsystem.builtins import BUILTIN_PLUGIN_CLASSES

def _write_minimal_pdf(path: Path) -> None:
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src_dir.rglob("*"):
            zf.write(p, p.relative_to(src_dir).as_posix())


class TestCompanyPack(unittest.TestCase):
    def test_valid_folder_pack_loads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "acme_pack"
            create_company_pack_skeleton(root, "acme", "ACME Inc.", sector="retail", primary_language="en")
            _write_minimal_pdf(root / "docs" / "policy.pdf")

            pack, tmp = load_company_pack(root, platform_version=PLATFORM_VERSION)
            self.assertIsNone(tmp)
            self.assertEqual(pack.manifest.company_id, "acme")
            self.assertEqual(pack.metadata.company_id, "acme")
            self.assertGreaterEqual(len(pack.list_pdfs()), 1)

            # Section 5 checks: prompts + retrieval resolved
            self.assertIn("agents", pack.prompts.raw)
            self.assertIn("care", pack.prompts.raw["agents"])
            self.assertIsInstance(pack.retrieval.chunk_size, int)
            self.assertGreater(pack.retrieval.top_k, 0)

    def test_missing_required_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "beta_pack"
            create_company_pack_skeleton(root, "beta", "Beta LLC")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            (root / "plugins.yaml").unlink()
            with self.assertRaises(CompanyPackValidationError):
                load_company_pack(root)

    def test_prompts_required_file_missing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "noprompts_pack"
            create_company_pack_skeleton(root, "np", "NoPrompts Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            (root / "prompts.yaml").unlink()
            with self.assertRaises(CompanyPackValidationError):
                load_company_pack(root)

    def test_prompts_validation_missing_agent_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "badprompts_pack"
            create_company_pack_skeleton(root, "bp", "BadPrompts Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            # Remove manager prompt from prompts.yaml
            prompts_path = root / "prompts.yaml"
            raw = prompts_path.read_text(encoding="utf-8")
            # quick-and-dirty: remove the manager block by rewriting minimal invalid YAML
            prompts_path.write_text(
                "schema_version: 1\nagents:\n  care:\n    system: 'x'\n  researcher:\n    system: 'y'\n",
                encoding="utf-8",
            )

            with self.assertRaises(CompanyPackValidationError):
                load_company_pack(root)

    def test_retrieval_defaults_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "noretrieval_pack"
            create_company_pack_skeleton(root, "nr", "NoRetrieval Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            # retrieval.yaml is optional; should fall back to defaults
            (root / "retrieval.yaml").unlink()

            pack, _ = load_company_pack(root)
            self.assertEqual(pack.retrieval.chunk_size, 800)
            self.assertEqual(pack.retrieval.chunk_overlap, 100)
            self.assertEqual(pack.retrieval.top_k, 5)

    def test_company_id_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mismatch_pack"
            create_company_pack_skeleton(root, "id1", "Mismatch Co.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            meta = (root / "metadata.yaml").read_text(encoding="utf-8")
            (root / "metadata.yaml").write_text(meta.replace("company_id: id1", "company_id: id2"), encoding="utf-8")

            with self.assertRaises(CompanyPackValidationError):
                load_company_pack(root)

    def test_empty_docs_not_allowed_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "nodocs_pack"
            create_company_pack_skeleton(root, "nodocs", "NoDocs Inc.")
            with self.assertRaises(CompanyPackValidationError):
                load_company_pack(root)

    def test_empty_docs_allowed_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "nodocs_ok_pack"
            create_company_pack_skeleton(root, "nodocs_ok", "NoDocs OK Inc.")

            manifest_path = root / "manifest.json"
            d = json.loads(manifest_path.read_text(encoding="utf-8"))
            d["allow_empty_docs"] = True
            manifest_path.write_text(json.dumps(d, indent=2), encoding="utf-8")

            pack, _ = load_company_pack(root)
            self.assertEqual(pack.manifest.company_id, "nodocs_ok")
            self.assertEqual(len(pack.list_pdfs()), 0)

    def test_zip_pack_loads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "zip_pack"
            create_company_pack_skeleton(root, "zipco", "Zip Co.")
            _write_minimal_pdf(root / "docs" / "policy.pdf")

            zip_path = td_path / "zip_pack.zip"
            _zip_dir(root, zip_path)

            pack, tmp = load_company_pack(zip_path, keep_temp=True)
            self.assertIsNotNone(tmp)
            self.assertEqual(pack.manifest.company_id, "zipco")
            self.assertGreaterEqual(len(pack.list_pdfs()), 1)

            if tmp is not None:
                shutil.rmtree(tmp, ignore_errors=True)

    def test_pack_root_detection_single_child_folder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td) / "outer"
            outer.mkdir()
            inner = outer / "inner_pack"
            create_company_pack_skeleton(inner, "nested", "Nested Co.")
            _write_minimal_pdf(inner / "docs" / "policy.pdf")

            pack, _ = load_company_pack(outer)
            self.assertEqual(pack.manifest.company_id, "nested")

    def test_zip_path_traversal_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            zip_path = td_path / "evil.zip"

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("../pwned.txt", "owned")

            with self.assertRaises(CompanyPackExtractionError):
                load_company_pack(zip_path)

    def test_nonexistent_pack_path_fails(self) -> None:
        with self.assertRaises(CompanyPackNotFoundError):
            load_company_pack("/this/path/does/not/exist")

class _ReqSettingPlugin(PluginBase):
    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="tool.reqsetting_v1",
            plugin_type=PluginType.TOOL,
            plugin_version="1.0.0",
            min_platform_version=PLATFORM_VERSION,
            max_platform_version=PLATFORM_VERSION,
            description="Plugin that requires a setting.",
        )

    @classmethod
    def schema(cls) -> ConfigSchema:
        return ConfigSchema(fields={"api_key": FieldSpec(str, required=True)})

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        return PluginResult(status=PluginStatus.OK, result={"ok": True})


class _IncompatiblePlugin(PluginBase):
    @classmethod
    def meta(cls) -> PluginMeta:
        return PluginMeta(
            plugin_id="tool.incompatible_v1",
            plugin_type=PluginType.TOOL,
            plugin_version="1.0.0",
            min_platform_version="9.9.9",
            max_platform_version="9.9.9",
            description="Incompatible plugin for tests.",
        )

    def run(self, ctx: PluginCallContext, payload: Any) -> PluginResult:
        return PluginResult(status=PluginStatus.OK, result={"ok": True})


class TestPluginSystem(unittest.TestCase):
    def test_registry_rejects_duplicate_plugin_id(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION)
        reg.register_many(BUILTIN_PLUGIN_CLASSES)

        with self.assertRaises(PluginValidationError):
            reg.register_plugin_class(BUILTIN_PLUGIN_CLASSES[0])

    def test_registry_rejects_incompatible_plugin(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION)
        with self.assertRaises(PluginCompatibilityError):
            reg.register_plugin_class(_IncompatiblePlugin)

    def test_settings_validation_missing_required_key_fails(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION, strict_settings=True)
        reg.register_plugin_class(_ReqSettingPlugin)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            create_company_pack_skeleton(root, "c1", "C1 Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            (root / "plugins.yaml").write_text(
                "enabled:\n  - tool.reqsetting_v1\nsettings:\n  tool.reqsetting_v1: {}\n",
                encoding="utf-8",
            )

            pack, _ = load_company_pack(root)
            with self.assertRaises(PluginSettingsError):
                reg.bind_company(pack)

    def test_allow_list_enforcement_disabled_plugin_cannot_run(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION)
        reg.register_many(BUILTIN_PLUGIN_CLASSES)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            create_company_pack_skeleton(root, "c2", "C2 Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            pack, _ = load_company_pack(root)
            bound = reg.bind_company(pack)

            ctx = PluginCallContext(
                company_id=pack.manifest.company_id,
                pack_root=pack.root,
                conversation_id="conv1",
                trace_id="trace1",
                tags=[],
            )

            with self.assertRaises(PluginNotEnabledError):
                bound.invoke("tool.ticket.mock_v1", ctx, {"subject": "Hi", "message": "Help"})

    def test_company_pack_enables_plugin_and_invocation_works(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION)
        reg.register_many(BUILTIN_PLUGIN_CLASSES)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            create_company_pack_skeleton(root, "acme", "ACME Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            (root / "plugins.yaml").write_text(
                "enabled:\n"
                "  - tool.ticket.mock_v1\n"
                "  - post.redaction.basic_v1\n"
                "settings:\n"
                "  tool.ticket.mock_v1:\n"
                "    default_priority: high\n"
                "  post.redaction.basic_v1:\n"
                "    replacement: '[X]'\n",
                encoding="utf-8",
            )

            pack, _ = load_company_pack(root)
            bound = reg.bind_company(pack)

            ctx = PluginCallContext(
                company_id=pack.manifest.company_id,
                pack_root=pack.root,
                conversation_id="conv2",
                trace_id="trace2",
                tags=[],
            )

            res = bound.invoke("tool.ticket.mock_v1", ctx, {"subject": "Refund", "message": "Need help"})
            self.assertEqual(res.status, PluginStatus.OK)
            self.assertIsInstance(res.result, dict)
            self.assertIn("ticket_id", res.result)
            self.assertEqual(res.result.get("priority"), "high")
            self.assertIn("duration_ms", res.metadata)

            text = "Contact me at test@example.com or +34 600 123 456."
            r2 = bound.invoke("post.redaction.basic_v1", ctx, {"text": text})
            self.assertEqual(r2.status, PluginStatus.OK)
            out_text = r2.result["text"]
            self.assertNotIn("test@example.com", out_text)
            self.assertIn("[X]", out_text)

    def test_company_pack_enabling_unknown_plugin_fails_fast(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION)
        reg.register_many(BUILTIN_PLUGIN_CLASSES)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            create_company_pack_skeleton(root, "c3", "C3 Inc.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            (root / "plugins.yaml").write_text(
                "enabled:\n  - tool.does_not_exist_v1\nsettings: {}\n",
                encoding="utf-8",
            )

            pack, _ = load_company_pack(root)
            with self.assertRaises(PluginNotFoundError):
                reg.bind_company(pack)

    def test_local_folder_discovery_works(self) -> None:
        reg = PluginRegistry(platform_version=PLATFORM_VERSION)

        with tempfile.TemporaryDirectory() as td:
            plugins_dir = Path(td) / "plugins"
            plugins_dir.mkdir()

            plugins_dir.joinpath("local_plugin.py").write_text(
                "from company_pack.pluginsystem import PluginBase, PluginMeta, PluginType, PluginResult, PluginStatus\n"
                "from company_pack.versioning import PLATFORM_VERSION\n\n"
                "class LocalTool(PluginBase):\n"
                "    @classmethod\n"
                "    def meta(cls):\n"
                "        return PluginMeta(\n"
                "            plugin_id='tool.local.demo_v1',\n"
                "            plugin_type=PluginType.TOOL,\n"
                "            plugin_version='1.0.0',\n"
                "            min_platform_version=PLATFORM_VERSION,\n"
                "            max_platform_version=PLATFORM_VERSION,\n"
                "            description='Local demo tool.'\n"
                "        )\n\n"
                "    def run(self, ctx, payload):\n"
                "        return PluginResult(status=PluginStatus.OK, result={'echo': payload})\n\n"
                "PLUGIN_CLASSES = [LocalTool]\n",
                encoding="utf-8",
            )

            n = reg.discover_local_dir(plugins_dir)
            self.assertEqual(n, 1)
            self.assertIn("tool.local.demo_v1", reg.list_plugin_ids())

if __name__ == "__main__":
    unittest.main(verbosity=2)
