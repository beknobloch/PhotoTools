from pathlib import Path
import tempfile
import unittest

from lr2rt.parsers.dng import extract_xmp_packet_from_dng, parse_dng_file
from lr2rt.parsers.xmp import parse_xmp_file

CAMERA_RAW_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"
FIXTURE_XMP = Path(__file__).parent / "fixtures" / "sample_preset.xmp"


class ParserTests(unittest.TestCase):
    def test_parse_xmp_file_extracts_camera_raw_values(self) -> None:
        settings = parse_xmp_file(FIXTURE_XMP, CAMERA_RAW_NS)

        self.assertEqual(settings.values["Exposure2012"], 0.2)
        self.assertEqual(settings.values["Contrast2012"], 8)
        self.assertEqual(settings.values["Texture"], 8)
        self.assertEqual(settings.values["Dehaze"], 6)
        self.assertEqual(settings.values["SharpenRadius"], 0.8)

    def test_parse_dng_file_extracts_embedded_xmp(self) -> None:
        xmp_text = FIXTURE_XMP.read_text(encoding="utf-8")
        data = b"RANDOM_HEADER" + xmp_text.encode("utf-8") + b"RANDOM_TRAILER"

        with tempfile.TemporaryDirectory() as tmp_dir:
            dng_path = Path(tmp_dir) / "mobile_preset.dng"
            dng_path.write_bytes(data)

            settings = parse_dng_file(dng_path, CAMERA_RAW_NS)

        self.assertEqual(settings.source_format, "dng")
        self.assertEqual(settings.values["Temperature"], 5600)

    def test_extract_xmp_packet_from_dng_raises_without_packet(self) -> None:
        with self.assertRaises(ValueError):
            extract_xmp_packet_from_dng(b"NO_XMP_PACKET")

    def test_parse_xmp_extracts_rdf_seq_values(self) -> None:
        xmp_text = """<?xpacket begin='\\ufeff'?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/">
      <crs:ToneCurvePV2012>
        <rdf:Seq>
          <rdf:li>0, 0</rdf:li>
          <rdf:li>128, 140</rdf:li>
          <rdf:li>255, 255</rdf:li>
        </rdf:Seq>
      </crs:ToneCurvePV2012>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "curve.xmp"
            path.write_text(xmp_text, encoding="utf-8")
            settings = parse_xmp_file(path, CAMERA_RAW_NS)

        self.assertEqual(settings.values["ToneCurvePV2012"], ["0, 0", "128, 140", "255, 255"])


if __name__ == "__main__":
    unittest.main()
