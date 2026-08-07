"""The screenshot sense: PNG encoding, the wire round trip, and the one
tool whose MCP result is an image block instead of JSON text.

The instrument sends raw RGBA8 (libultraship vendors no image encoder and
this lane adds no dependencies), so everything between "bytes on the wire"
and "pixels the model can see" is ours to be right about — and the failure
mode that matters is the quiet one: a short or misaligned buffer encoded
into a picture that merely LOOKS plausible. Hence the ramp fixtures, whose
every pixel is checkable, and the length assertions on both sides.
"""

import base64
import json
import struct
import zlib

from ocarina.screenshot import PNG_SIGNATURE, encode_png

from .stubgame import canned_frame, frame_bytes
from .test_server import ServerCase


def png_chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    """Walk a PNG's chunk list, verifying every CRC on the way."""
    assert png[:8] == PNG_SIGNATURE, "bad signature"
    out, i = [], 8
    while i < len(png):
        (length,) = struct.unpack(">I", png[i:i + 4])
        kind = png[i + 4:i + 8]
        data = png[i + 8:i + 8 + length]
        (crc,) = struct.unpack(">I", png[i + 8 + length:i + 12 + length])
        assert crc == zlib.crc32(kind + data) & 0xFFFFFFFF, f"bad CRC on {kind!r}"
        out.append((kind, data))
        i += 12 + length
    return out


class TestPngEncoder(ServerCase):
    """ServerCase only for its setUp discipline; these are pure-function
    tests of the encoder."""

    def test_output_is_a_valid_png(self):
        png = encode_png(frame_bytes(4, 3), 4, 3)
        chunks = png_chunks(png)
        self.assertEqual([k for k, _ in chunks], [b"IHDR", b"IDAT", b"IEND"])

        width, height, depth, color, comp, filt, interlace = struct.unpack(
            ">IIBBBBB", chunks[0][1])
        self.assertEqual((width, height), (4, 3))
        self.assertEqual((depth, color), (8, 6))   # 8-bit truecolour + alpha
        self.assertEqual((comp, filt, interlace), (0, 0, 0))

    def test_idat_decompresses_to_the_exact_scanlines(self):
        rgba = frame_bytes(4, 3)
        idat = dict(png_chunks(encode_png(rgba, 4, 3)))[b"IDAT"]
        raw = zlib.decompress(idat)
        # One filter byte + one row of pixels, per scanline, in order.
        self.assertEqual(len(raw), 3 * (1 + 4 * 4))
        for y in range(3):
            row = raw[y * 17:(y + 1) * 17]
            self.assertEqual(row[0], 0, "filter type 0 (None) on every scanline")
            self.assertEqual(row[1:], rgba[y * 16:(y + 1) * 16],
                             "pixels survive the round trip unpermuted")

    def test_a_short_buffer_is_refused_not_encoded(self):
        # The quiet lie this whole module exists to prevent.
        with self.assertRaises(ValueError) as caught:
            encode_png(frame_bytes(4, 3)[:-4], 4, 3)
        self.assertIn("48 bytes", str(caught.exception))

    def test_zero_dimensions_are_refused(self):
        with self.assertRaises(ValueError):
            encode_png(b"", 0, 0)


class TestGameScreenshot(ServerCase):
    def test_decodes_the_wire_frame(self):
        shot = self.game.screenshot()
        self.assertTrue(shot["ok"], shot)
        self.assertEqual((shot["width"], shot["height"]), (4, 3))
        self.assertEqual(shot["rgba"], frame_bytes(4, 3))

    def test_max_width_rides_to_the_instrument(self):
        # Downscaling is the instrument's job — the wire carries raw RGBA,
        # so shrinking mind-side would save nothing where it costs.
        self.game.screenshot(max_width=320)
        sent = [r for r in self.link.requests if r.get("op") == "screenshot"]
        self.assertEqual(sent[-1]["max_width"], 320)

    def test_reports_the_native_size_it_was_reduced_from(self):
        self.link.screenshot_script = [canned_frame(4, 3, full=(16, 12))]
        shot = self.game.screenshot()
        self.assertEqual((shot["full_width"], shot["full_height"]), (16, 12))

    def test_an_old_instrument_names_the_build_it_wants(self):
        self.link.screenshot_script = [
            {"status": "failure", "error": "unknown agent op: screenshot"}]
        shot = self.game.screenshot()
        self.assertFalse(shot["ok"])
        self.assertIn("2026-08-07", shot["error"])
        self.assertIn("rebuild SoH", shot["error"])

    def test_a_named_backend_refusal_passes_through(self):
        self.link.screenshot_script = [
            {"status": "failure",
             "error": "this rendering backend cannot capture frames "
                      "(screenshot supports Metal and OpenGL)"}]
        shot = self.game.screenshot()
        self.assertFalse(shot["ok"])
        self.assertIn("cannot capture frames", shot["error"])

    def test_a_short_payload_is_refused_by_length(self):
        bad = canned_frame(4, 3)
        bad["pixels"] = base64.b64encode(frame_bytes(4, 3)[:-8]).decode()
        self.link.screenshot_script = [bad]
        shot = self.game.screenshot()
        self.assertFalse(shot["ok"])
        self.assertIn("40 bytes, not the 48", shot["error"])

    def test_an_unknown_format_is_refused(self):
        odd = canned_frame(4, 3)
        odd["format"] = "bgra8"
        self.link.screenshot_script = [odd]
        shot = self.game.screenshot()
        self.assertFalse(shot["ok"])
        self.assertIn("bgra8", shot["error"])


class TestScreenshotTool(ServerCase):
    def test_it_is_no_longer_a_not_yet_stub(self):
        from ocarina.server import NOT_YET
        self.assertNotIn("screenshot", NOT_YET)

    def test_returns_an_image_block_the_model_can_see(self):
        result = self.call_tool("screenshot")
        self.assertFalse(result["isError"], result)
        image, note = result["content"]

        self.assertEqual(image["type"], "image")
        self.assertEqual(image["mimeType"], "image/png")
        png = base64.b64decode(image["data"])
        self.assertEqual([k for k, _ in png_chunks(png)],
                         [b"IHDR", b"IDAT", b"IEND"])
        width, height = struct.unpack(">II", dict(png_chunks(png))[b"IHDR"][:8])
        self.assertEqual((width, height), (4, 3))

        # The text block alongside: size, when, and the boundary.
        self.assertEqual(note["type"], "text")
        body = json.loads(note["text"])
        self.assertEqual((body["width"], body["height"]), (4, 3))
        self.assertGreater(body["captured_at"], 0)
        self.assertTrue(body["captured_at_utc"].endswith("Z"))
        self.assertEqual(body["png_bytes"], len(png))
        # The design ruling: the debug overlay's labels stay IN the shot,
        # and the note says so rather than leaving it to be discovered.
        self.assertTrue(body["includes_debug_overlay"])

    def test_a_downscaled_frame_says_what_it_was_reduced_from(self):
        # 0.6.0's flight lesson: a debug layer shows the BOUNDARY of what
        # it received, never only the contents.
        self.link.screenshot_script = [canned_frame(4, 3, full=(1280, 960))]
        body = json.loads(self.call_tool("screenshot")["content"][1]["text"])
        self.assertEqual(body["downscaled_from"], "1280x960")

    def test_a_native_frame_claims_no_downscale(self):
        body = json.loads(self.call_tool("screenshot")["content"][1]["text"])
        self.assertNotIn("downscaled_from", body)

    def test_max_width_argument_reaches_the_wire(self):
        self.call_tool("screenshot", {"max_width": 0})
        sent = [r for r in self.link.requests if r.get("op") == "screenshot"]
        self.assertEqual(sent[-1]["max_width"], 0)

    def test_no_game_is_a_clean_error(self):
        self.link._connected = False
        result = self.call_tool("screenshot")
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], "game not connected")

    def test_an_old_instrument_is_a_loud_diagnostic_not_a_silence(self):
        self.link.screenshot_script = [
            {"status": "failure", "error": "unknown agent op: screenshot"}]
        result = self.call_tool("screenshot")
        self.assertTrue(result["isError"])
        self.assertIn("2026-08-07", result["content"][0]["text"])
