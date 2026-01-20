from pathlib import Path
import tempfile

from company_pack import PLATFORM_VERSION
from company_pack.scaffold import create_company_pack_skeleton
from company_pack.loader import load_company_pack

from company_pack.pluginsystem import PluginRegistry, PluginCallContext
from company_pack.pluginsystem.builtins import BUILTIN_PLUGIN_CLASSES

def write_minimal_pdf(path: Path) -> None:
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "acme_pack"
    create_company_pack_skeleton(root, "acme", "ACME Inc.", sector="retail", primary_language="en")
    write_minimal_pdf(root / "docs" / "policy.pdf")

    # Enable two plugins via plugins.yaml (per-company allow-list)
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

    pack, _ = load_company_pack(root, platform_version=PLATFORM_VERSION)

    reg = PluginRegistry(platform_version=PLATFORM_VERSION)
    reg.register_many(BUILTIN_PLUGIN_CLASSES)

    bound = reg.bind_company(pack)

    ctx = PluginCallContext(
        company_id=pack.manifest.company_id,
        pack_root=pack.root,
        conversation_id="conv_demo",
        trace_id="trace_demo",
        tags=["policy"],
    )

    # Tool plugin
    r1 = bound.invoke("tool.ticket.mock_v1", ctx, {"subject": "Refund", "message": "I need help"})
    print("Ticket result:", r1.status, r1.result)
    print("Ticket metadata keys:", sorted(list(r1.metadata.keys())))

    # Postprocessor plugin
    text = "Contact me at test@example.com or +34 600 123 456."
    r2 = bound.invoke("post.redaction.basic_v1", ctx, {"text": text})
    print("Redacted text:", r2.result["text"])
