"""Independent clipped-decoration controls for the opt-in Wayland test oracle."""
import copy
import unittest

from tests.cockpit_omarchy_smoke import visible_geometry


class WindowGeometryTests(unittest.TestCase):
    def setUp(self):
        self.parent = {"type": "workspace", "rect": {
            "x": 0, "y": 26, "width": 1280, "height": 774}}
        self.node = {
            "visible": True,
            "rect": {"x": 94, "y": 73, "width": 1092, "height": 682},
            "deco_rect": {"x": 94, "y": 21, "width": 1092, "height": 26},
        }

    def test_actual_fixture_geometry_fits(self):
        self.assertTrue(visible_geometry(self.node, self.parent))

    def test_decoration_coordinates_are_relative_to_workspace(self):
        # A zero relative y starts below the bar at the workspace origin.
        self.node["deco_rect"]["y"] = 0
        self.assertTrue(visible_geometry(self.node, self.parent))

    def test_clipped_header_and_decoration_edges_refuse(self):
        for key, value in (("x", -1), ("y", -1),
                           ("width", 1280), ("height", 800)):
            with self.subTest(key=key):
                node = copy.deepcopy(self.node)
                node["deco_rect"][key] = value
                self.assertFalse(visible_geometry(node, self.parent))

    def test_original_oversized_window_refuses(self):
        self.node["rect"] = {"x": -2, "y": 0, "width": 1284, "height": 802}
        self.node["deco_rect"] = {"x": -2, "y": -52, "width": 1284, "height": 26}
        self.assertFalse(visible_geometry(self.node, self.parent))

    def test_hidden_or_wrong_parent_refuses(self):
        self.assertFalse(visible_geometry(self.node, None))
        self.parent["type"] = "con"
        self.assertFalse(visible_geometry(self.node, self.parent))
        self.parent["type"] = "workspace"
        self.node["visible"] = False
        self.assertFalse(visible_geometry(self.node, self.parent))

    def test_invalid_or_outside_workspace_refuses(self):
        for key, value in (("width", 0), ("width", 1281), ("x", -1)):
            with self.subTest(key=key, value=value):
                parent = copy.deepcopy(self.parent)
                parent["rect"][key] = value
                self.assertFalse(visible_geometry(self.node, parent))
