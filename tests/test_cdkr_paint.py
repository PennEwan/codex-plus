import unittest

from cdkr import paint


class ColorTest(unittest.TestCase):
    def test_mix_endpoints_and_middle(self):
        a, b = (0, 0, 0), (100, 200, 50)
        self.assertEqual(paint.mix(a, b, 0), a)
        self.assertEqual(paint.mix(a, b, 1), b)
        self.assertEqual(paint.mix(a, b, 0.5), (50, 100, 25))

    def test_hexc(self):
        self.assertEqual(paint.hexc((237, 243, 248)), "#edf3f8")
        self.assertEqual(paint.hexc((0.4, 255.6, -3)), "#00ff00")  # rounded and clamped


class AuroraTest(unittest.TestCase):
    def rows(self, level="healthy", w=40, h=50):
        return paint.aurora_rows(level, w, h)

    def test_shape_and_valid_colors(self):
        rows = self.rows()
        self.assertEqual(len(rows), 50)
        self.assertTrue(all(len(r) == 40 for r in rows))
        for value in (rows[0][0], rows[-1][-1], rows[25][20]):
            self.assertRegex(value, r"^#[0-9a-f]{6}$")

    def test_varies_across_the_card(self):
        rows = self.rows()
        self.assertGreater(len({c for row in rows for c in row}, ), 20)

    def test_stays_in_the_light_range(self):
        for level in paint.PALETTES:
            for value in {c for row in self.rows(level) for c in row}:
                r, g, b = paint.unhex(value)
                self.assertGreater(min(r, g, b), 150, f"{level} {value}")

    def test_each_level_has_its_own_tint(self):
        seen = {level: self.rows(level)[-1][-1] for level in paint.PALETTES}
        self.assertEqual(len(set(seen.values())), len(seen), seen)


class RoundRectTest(unittest.TestCase):
    def test_polygon_stays_inside_the_box(self):
        points = paint.round_rect_points(10, 20, 110, 70, 12)
        xs, ys = points[0::2], points[1::2]
        self.assertGreaterEqual(min(xs), 10)
        self.assertLessEqual(max(xs), 110)
        self.assertGreaterEqual(min(ys), 20)
        self.assertLessEqual(max(ys), 70)
        self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (10, 110, 20, 70))

    def test_radius_is_clamped_to_half_the_shorter_side(self):
        pill = paint.round_rect_points(0, 0, 100, 20, 999)
        self.assertEqual(max(pill[1::2]), 20)
        self.assertEqual(min(pill[0::2]), 0)

    def test_zero_radius_is_a_rectangle(self):
        self.assertEqual(sorted(set(paint.round_rect_points(0, 0, 10, 4, 0))), [0, 4, 10])


if __name__ == "__main__":
    unittest.main()
