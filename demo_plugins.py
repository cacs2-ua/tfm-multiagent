from pathlib import Path
import tempfile

from company_pack import PLATFORM_VERSION, load_company_pack
from company_pack.scaffold import create_company_pack_skeleton
from company_pack.pluginsystem import PluginRegistry, PluginCallContext, PluginNotEnabledError
from company_pack.pluginsystem.builtins import BUILTIN_PLUGIN_CLASSES


def write_minimal_pdf(path: Path) -> None:
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


reg = PluginRegistry(platform_version=PLATFORM_VERSION)
reg.register_many(BUILTIN_PLUGIN_CLASSES)

# --------- 1) Pack REAL: ./packs/acme ----------
pack_path = Path("./packs/acme").expanduser().resolve()
pack_disk, _ = load_company_pack(pack_path, platform_version=PLATFORM_VERSION)

print("DISK pack.root =", pack_disk.root)
print("DISK enabled =", pack_disk.plugins.enabled)
print("DISK plugins.yaml:\n", (pack_disk.root / "plugins.yaml").read_text(encoding="utf-8"))

bound_disk = reg.bind_company(pack_disk)

ctx_disk = PluginCallContext(
    company_id=pack_disk.manifest.company_id,
    pack_root=pack_disk.root,
    conversation_id="conv_disk",
    trace_id="trace_disk",
    tags=["policy"],
)

print("\n--- tool.ticket.mock_v1 on DISK pack ---")
if bound_disk.is_enabled("tool.ticket.mock_v1"):
    r = bound_disk.invoke("tool.ticket.mock_v1", ctx_disk, {"subject": "Refund", "message": "I need help"})
    print("Expected success:", r.status, r.result)
else:
    try:
        r = bound_disk.invoke("tool.ticket.mock_v1", ctx_disk, {"subject": "Refund", "message": "I need help"})
        print("Unexpected success (should be disabled):", r.status, r.result)
    except PluginNotEnabledError as e:
        print("Expected error:", e)

# --------- 2) Pack TEMPORAL: explicit enablement ----------
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "acme_pack"
    create_company_pack_skeleton(root, "acme", "ACME Inc.", sector="retail", primary_language="en")
    write_minimal_pdf(root / "docs" / "policy.pdf")

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

    pack_tmp, _ = load_company_pack(root, platform_version=PLATFORM_VERSION)
    bound_tmp = reg.bind_company(pack_tmp)

    ctx_tmp = PluginCallContext(
        company_id=pack_tmp.manifest.company_id,
        pack_root=pack_tmp.root,
        conversation_id="conv_tmp",
        trace_id="trace_tmp",
        tags=["policy"],
    )

    print("\n--- tool.ticket.mock_v1 on TEMP pack (should succeed) ---")
    r1 = bound_tmp.invoke("tool.ticket.mock_v1", ctx_tmp, {"subject": "Refund", "message": "I need help"})
    print("Ticket result:", r1.status, r1.result)
