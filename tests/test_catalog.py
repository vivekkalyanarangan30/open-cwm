from pathlib import Path

from orchestrator.catalog import RepoCatalog


def test_catalog_loads_json_yaml_subset(tmp_path: Path) -> None:
    catalog_path = tmp_path / "repos.yaml"
    catalog_path.write_text(
        """
{
  \"version\": 1,
  \"repos\": [
    {\"id\": \"demo_repo\", \"url\": \"https://example.com/demo.git\", \"commit\": \"main\"}
  ]
}
"""
    )
    catalog = RepoCatalog.from_file(catalog_path)
    spec = catalog.get("demo_repo")
    assert spec.id == "demo_repo"
    assert spec.url == "https://example.com/demo.git"
    assert spec.commit == "main"
