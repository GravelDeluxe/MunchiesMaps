import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fetch_data import fetch_stale_overpass as stale


class FetchStaleOverpassTests(unittest.TestCase):
    def test_legacy_success_copies_expected_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            target_path = Path("resources/geojson/luxembourg/luxembourg/fuel.geojson")
            src = stale.ROOT / target_path
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            try:
                with patch.object(
                    stale.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
                ):
                    ok, err = stale.run_target_via_legacy_cli(
                        {
                            "country": "luxembourg",
                            "region": "luxembourg",
                            "category": "fuel",
                            "path": str(target_path),
                        },
                        out_dir,
                        debug=False,
                    )
                self.assertTrue(ok)
                self.assertEqual(err, "")
                self.assertTrue((out_dir / target_path).exists())
            finally:
                if src.exists():
                    src.unlink()


if __name__ == "__main__":
    unittest.main()
