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


def _write_minimal_pdf(path: Path) -> None:
    # We only need a file with .pdf extension for Section 4 validation (no parsing yet).
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

    def test_missing_required_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "beta_pack"
            create_company_pack_skeleton(root, "beta", "Beta LLC")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            (root / "plugins.yaml").unlink()
            with self.assertRaises(CompanyPackValidationError):
                load_company_pack(root)

    def test_company_id_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mismatch_pack"
            create_company_pack_skeleton(root, "id1", "Mismatch Co.")
            _write_minimal_pdf(root / "docs" / "a.pdf")

            # Break metadata.yaml company_id
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

            # set allow_empty_docs = True in manifest.json
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

            # cleanup extracted temp
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

            # Create a zip with a traversal entry
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("../pwned.txt", "owned")

            with self.assertRaises(CompanyPackExtractionError):
                load_company_pack(zip_path)

    def test_nonexistent_pack_path_fails(self) -> None:
        with self.assertRaises(CompanyPackNotFoundError):
            load_company_pack("/this/path/does/not/exist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
