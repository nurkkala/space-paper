"""Display selectors.

Resolution is where a mistake is expensive: guessing wrong repaints a screen the
user did not name. So ambiguity is an error rather than a best guess, and that is
what most of these assert.
"""

import pytest

from space_paper import displays as dsp

from .conftest import make_display


class TestByRole:
    def test_main(self, two_screens, external):
        assert dsp.resolve("main", two_screens) is external

    def test_primary_is_an_alias_for_main(self, two_screens, external):
        assert dsp.resolve("primary", two_screens) is external

    @pytest.mark.parametrize("selector", ["builtin", "built-in", "internal", "laptop", "mac"])
    def test_builtin_aliases(self, two_screens, builtin, selector):
        assert dsp.resolve(selector, two_screens) is builtin

    def test_external(self, two_screens, external):
        assert dsp.resolve("external", two_screens) is external

    def test_selectors_are_case_insensitive(self, two_screens, builtin):
        assert dsp.resolve("BuiltIn".lower(), two_screens) is builtin
        assert dsp.resolve("MAIN", two_screens) is dsp.resolve("main", two_screens)

    def test_surrounding_whitespace_is_tolerated(self, two_screens, external):
        assert dsp.resolve("  main  ", two_screens) is external


class TestByIdentity:
    def test_index_is_one_based(self, two_screens, external, builtin):
        assert dsp.resolve("1", two_screens) is external
        assert dsp.resolve("2", two_screens) is builtin

    def test_name_substring_matches(self, two_screens, external):
        assert dsp.resolve("acme", two_screens) is external

    def test_uuid_prefix_matches(self, two_screens, external):
        assert dsp.resolve(external.uuid[:6].lower(), two_screens) is external

    def test_full_uuid_matches(self, two_screens, external):
        assert dsp.resolve(external.uuid, two_screens) is external


class TestFailures:
    def test_no_match_is_an_error(self, two_screens):
        with pytest.raises(dsp.DisplayError, match="no display matches"):
            dsp.resolve("projector", two_screens)

    def test_the_error_lists_what_is_available(self, two_screens):
        with pytest.raises(dsp.DisplayError, match="ACME 27"):
            dsp.resolve("projector", two_screens)

    def test_empty_display_list_is_an_error(self):
        with pytest.raises(dsp.DisplayError, match="no active displays"):
            dsp.resolve("main", [])

    def test_two_externals_make_external_ambiguous(self):
        """Never guess: picking the wrong one repaints the wrong screen."""
        screens = [
            make_display(cg_id=3, name="ACME 27", builtin=False, main=True),
            make_display(cg_id=4, name="Globex 32", builtin=False, main=False),
        ]
        with pytest.raises(dsp.DisplayError, match="ambiguous"):
            dsp.resolve("external", screens)

    def test_a_substring_matching_two_names_is_ambiguous(self):
        screens = [
            make_display(cg_id=3, name="ACME 27", builtin=False, main=True),
            make_display(cg_id=4, name="ACME 32", builtin=False, main=False),
        ]
        with pytest.raises(dsp.DisplayError, match="ambiguous"):
            dsp.resolve("acme", screens)

    def test_ambiguity_error_names_the_candidates(self):
        screens = [
            make_display(cg_id=3, name="ACME 27", builtin=False, main=True),
            make_display(cg_id=4, name="ACME 32", builtin=False, main=False),
        ]
        with pytest.raises(dsp.DisplayError, match="ACME 32"):
            dsp.resolve("acme", screens)

    def test_out_of_range_index_is_not_silently_clamped(self, two_screens):
        with pytest.raises(dsp.DisplayError):
            dsp.resolve("9", two_screens)


class TestDisplayProperties:
    def test_kind_reports_builtin_or_external(self, external, builtin):
        assert external.kind == "external"
        assert builtin.kind == "built-in"

    def test_label_mentions_main_only_when_main(self, external, builtin):
        assert "main" in external.label
        assert "main" not in builtin.label

    def test_current_space_reports_the_active_one(self, external):
        assert external.current_space == 1

    def test_current_space_is_zero_when_unknown(self):
        screen = make_display(spaces=0)
        assert screen.current_space == 0

    def test_center_is_the_middle_of_the_bounds(self):
        screen = make_display(width=3840, height=2160)  # bounds are half, in points
        assert screen.center == (960.0, 540.0)


class TestPictureExtraction:
    """Reading each Space's wallpaper out of the store's nested plist nodes."""

    def image_node(self, url: str) -> dict:
        import plistlib

        config = plistlib.dumps({"type": "imageFile", "url": {"relative": url}}, fmt=plistlib.FMT_BINARY)
        return {"Desktop": {"Content": {"Choices": [
            {"Provider": "com.apple.wallpaper.choice.image", "Configuration": config}
        ]}}}

    def test_reads_the_path_from_an_image_choice(self):
        node = self.image_node("file:///Users/x/Pictures/Wallpapers/main-sky.png")
        assert dsp._picture_of(node) == dsp.Path("/Users/x/Pictures/Wallpapers/main-sky.png")

    def test_percent_escapes_are_decoded(self):
        node = self.image_node("file:///Users/x/My%20Wallpapers/a%20b.png")
        assert dsp._picture_of(node) == dsp.Path("/Users/x/My Wallpapers/a b.png")

    def test_a_linked_space_has_no_picture_of_its_own(self):
        """`Linked` means it follows the global wallpaper, not that it is broken."""
        assert dsp._picture_of({"Type": "individual", "Linked": {}}) is None

    def test_non_image_providers_are_ignored(self):
        node = {"Desktop": {"Content": {"Choices": [{"Provider": "com.apple.wallpaper.choice.aerials"}]}}}
        assert dsp._picture_of(node) is None

    def test_malformed_nodes_do_not_raise(self):
        for node in [{}, {"Desktop": {}}, {"Desktop": {"Content": {"Choices": []}}}]:
            assert dsp._picture_of(node) is None
