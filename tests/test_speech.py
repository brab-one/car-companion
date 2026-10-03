import base64
import unittest

from companion import font, speech


class SpeechTest(unittest.TestCase):
    def test_wraps_at_spaces(self):
        self.assertEqual(speech.wrap("Easy, the oil is still cold."), ["Easy, the oil is", "still cold."])

    def test_long_text_ends_with_dots(self):
        lines = speech.wrap("word " * 30)
        self.assertEqual(len(lines), speech.MAX_LINES)
        self.assertTrue(lines[-1].endswith("..."))
        self.assertTrue(all(len(line) <= speech.MAX_CHARS for line in lines))

    def test_long_word_is_cut(self):
        n = speech.MAX_CHARS
        self.assertEqual(speech.wrap("a" * (n + 6)), ["a" * n, "a" * 6])

    def test_unknown_characters_become_question_marks(self):
        self.assertEqual(speech.wrap("Grüß dich ☀ – gut"), ["Grüß dich ? - gut"])

    def test_bubble_fits_the_display_and_carries_the_text(self):
        b = speech.bubble("There's the Schlern.")
        self.assertTrue(0 <= b["x"] - b["w"] / 2 and b["x"] + b["w"] / 2 <= 128)
        self.assertLessEqual(b["y"] + b["h"] / 2, 128 - speech.MARGIN)
        self.assertLess(b["tail"][1], b["y"] - b["h"] / 2)  # the tail points up
        text = b["text"]
        bits = base64.b64decode(text["bits"])
        self.assertEqual(len(bits), (text["w"] + 7) // 8 * text["h"])
        lit = sum(bin(byte).count("1") for byte in bits)
        self.assertEqual(lit, len(list(font.pixels("There's the Schlern."))))
        self.assertLess(speech.lift(b), 0)

    def test_longer_lines_stay_longer(self):
        self.assertLess(speech.seconds("Hi", 2.5, 0.06), speech.seconds("Easy, the oil is still cold.", 2.5, 0.06))
        self.assertEqual(speech.seconds("x" * 1000, 2.5, 0.06), 10.0)


if __name__ == "__main__":
    unittest.main()
