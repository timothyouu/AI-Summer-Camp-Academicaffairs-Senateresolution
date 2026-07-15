from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from infra.scripts.prepare_corpus import (
    CORPUS_SOURCES,
    DEFAULT_SOURCE_ROOT,
    MANAGED_CORPUS_PREFIXES,
    REPO_ROOT,
    _registry_item,
    build_staging_tree,
)


class PrepareCorpusTests(unittest.TestCase):
    def test_helper_prefixes_match_cdk_data_source_prefixes(self) -> None:
        stack_path = REPO_ROOT / "infra" / "stacks" / "policy_intelligence_stack.py"
        tree = ast.parse(stack_path.read_text(encoding="utf-8"))
        value = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "CORPUS_PREFIXES" for target in node.targets)
        )
        cdk_prefixes = {prefix.rstrip("/") for prefix in ast.literal_eval(value)}

        self.assertEqual(cdk_prefixes, MANAGED_CORPUS_PREFIXES | {"uploads", "raw"})
        self.assertEqual({source.prefix for source in CORPUS_SOURCES}, MANAGED_CORPUS_PREFIXES)

    def test_every_source_is_staged_under_a_kb_prefix_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            staging_root = Path(temporary)
            build_staging_tree(DEFAULT_SOURCE_ROOT, staging_root)

            for source in CORPUS_SOURCES:
                destination = staging_root / source.prefix / Path(source.relative_path).name
                self.assertTrue(destination.is_file())
                metadata = json.loads(
                    destination.with_name(destination.name + ".metadata.json").read_text(encoding="utf-8")
                )
                self.assertLessEqual(len(json.dumps(metadata).encode("utf-8")), 10 * 1024)
                attributes = metadata["metadataAttributes"]
                self.assertEqual(set(attributes), {"source", "section", "doc_type", "topic"})
                self.assertEqual(attributes["source"]["value"]["stringValue"], destination.stem)
                self.assertEqual(attributes["section"]["value"]["stringValue"], "Document")
                self.assertEqual(attributes["doc_type"]["value"]["stringValue"], source.doc_type)
                self.assertEqual(attributes["topic"]["value"]["stringValue"], source.topic)

            staged_sources = [
                path for path in staging_root.rglob("*")
                if path.is_file() and not path.name.endswith(".metadata.json")
            ]
            self.assertEqual(len(staged_sources), len(CORPUS_SOURCES))

    def test_registry_seed_items_match_bedrock_source_names(self) -> None:
        for source in CORPUS_SOURCES:
            item = _registry_item(source)
            filename = Path(source.relative_path).name
            self.assertEqual(item["id"]["S"], Path(filename).stem.lower())
            self.assertEqual(item["title"]["S"], Path(filename).stem)
            self.assertEqual(item["status"]["S"], "active")
            self.assertEqual(item["s3_key"]["S"], f"{source.prefix}/{filename}")


if __name__ == "__main__":
    unittest.main()
