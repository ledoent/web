# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import time

from odoo.addons.base.tests.common import BaseCommon


class TestProvenance(BaseCommon):
    """Provenance stamping + `_user_set` + `_provenance_for` coverage.

    Uses `res.partner.comment` as the probe field because it's
    universally available and not driven by any compute, so we control
    its provenance exclusively from these tests.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.field_comment = cls.env["ir.model.fields"]._get("res.partner", "comment")
        # Base fields (state='base') are protected from `.write()`; flip the
        # opt-in flag via SQL. Production UX exposes the same operation
        # via a custom wizard (Technical → Field Provenance Setup) — that
        # wizard will use the same SQL path. The `clear_cache` ensures the
        # ormcache on `_field_track_set` picks it up.
        cls._set_track_provenance(cls.field_comment, True)

    @classmethod
    def _set_track_provenance(cls, field, enabled):
        cls.env.cr.execute(
            "UPDATE ir_model_fields SET track_provenance = %s WHERE id = %s",
            [enabled, field.id],
        )
        cls.env.cache.invalidate()
        cls.env.registry.clear_cache()

    # ------------------------------------------------------------------
    # Stamping on user paths
    # ------------------------------------------------------------------
    def test_create_with_value_stamps_user(self):
        partner = self.env["res.partner"].create(
            {"name": "Created With Comment", "comment": "manual note"}
        )
        entry = (partner._provenance or {}).get("comment")
        self.assertIsInstance(entry, dict, "Provenance entries are dicts now")
        self.assertEqual(entry["s"], "u")
        self.assertEqual(entry["b"], self.env.user.login)
        self.assertIsInstance(entry["t"], int)
        self.assertTrue(partner._user_set("comment"))

    def test_create_without_value_does_not_stamp(self):
        """Implicit default — absence of an entry means the field is
        still at its default. We never stamp the default state; it
        keeps the JSON column compact."""
        partner = self.env["res.partner"].create({"name": "No Comment"})
        self.assertNotIn(
            "comment",
            (partner._provenance or {}),
            "Default state must be implicit (no entry).",
        )
        self.assertFalse(partner._user_set("comment"))

    def test_write_stamps_user(self):
        partner = self.env["res.partner"].create({"name": "Late Writer"})
        partner.write({"comment": "user-typed"})
        entry = (partner._provenance or {}).get("comment")
        self.assertEqual(entry["s"], "u")
        self.assertEqual(entry["b"], self.env.user.login)

    # ------------------------------------------------------------------
    # Rule / cascade stamping (public API)
    # ------------------------------------------------------------------
    def test_stamp_provenance_rule(self):
        partner = self.env["res.partner"].create({"name": "Cascade Target"})
        partner._stamp_provenance(
            ["comment"],
            source="r",
            by="sot.cascade",
            rule="Sale Order Type cascade",
        )
        entry = (partner._provenance or {}).get("comment")
        self.assertEqual(entry["s"], "r")
        self.assertEqual(entry["b"], "sot.cascade")
        self.assertEqual(entry["r"], "Sale Order Type cascade")
        # `_user_set` returns False for rule-stamped entries — that's the
        # whole point: cascade values stay re-computable on next change.
        self.assertFalse(partner._user_set("comment"))

    def test_stamp_provenance_user_via_public_api(self):
        partner = self.env["res.partner"].create({"name": "Anchored"})
        partner._stamp_provenance(["comment"], source="u", by="dkendall")
        self.assertTrue(partner._user_set("comment"))

    def test_stamp_provenance_rejects_unknown_source(self):
        partner = self.env["res.partner"].create({"name": "Reject Source"})
        with self.assertRaises(ValueError):
            partner._stamp_provenance(["comment"], source="d", by="anything")
        with self.assertRaises(ValueError):
            partner._stamp_provenance(["comment"], source="s", by="anything")

    def test_stamp_provenance_requires_by(self):
        partner = self.env["res.partner"].create({"name": "Reject By"})
        with self.assertRaises(ValueError):
            partner._stamp_provenance(["comment"], source="r", by="")
        with self.assertRaises(ValueError):
            partner._stamp_provenance(["comment"], source="r", by=None)

    def test_stamp_provenance_skips_untracked_keys(self):
        partner = self.env["res.partner"].create({"name": "Mixed"})
        partner._stamp_provenance(["comment", "name"], source="r", by="sot.cascade")
        prov = partner._provenance or {}
        self.assertIn("comment", prov)
        self.assertNotIn("name", prov, "Untracked keys must not be stamped")

    def test_user_write_flips_rule_to_user(self):
        partner = self.env["res.partner"].create({"name": "Override Path"})
        partner._stamp_provenance(["comment"], source="r", by="sot.cascade")
        self.assertFalse(partner._user_set("comment"))
        partner.write({"comment": "I override the rule"})
        self.assertTrue(partner._user_set("comment"))
        self.assertEqual((partner._provenance or {})["comment"]["s"], "u")

    # ------------------------------------------------------------------
    # `_provenance_for` — badge tooltip
    # ------------------------------------------------------------------
    def test_provenance_for_default(self):
        partner = self.env["res.partner"].create({"name": "Default Only"})
        info = partner._provenance_for("comment")
        self.assertEqual(info["state"], "default")
        self.assertIn("Default", info["label"])
        # The "when" for a default state is the record's create_date,
        # serving as the proxy for "this default has been in effect
        # since X" without storing any extra data.
        self.assertIsNotNone(info["when"])

    def test_provenance_for_user(self):
        partner = self.env["res.partner"].create({"name": "User State", "comment": "x"})
        info = partner._provenance_for("comment")
        self.assertEqual(info["state"], "user")
        self.assertEqual(info["by"], self.env.user.login)
        self.assertIn(self.env.user.login, info["label"])

    def test_provenance_for_rule(self):
        partner = self.env["res.partner"].create({"name": "Rule State"})
        partner._stamp_provenance(
            ["comment"],
            source="r",
            by="sot.cascade",
            rule="Sale Order Type cascade",
        )
        info = partner._provenance_for("comment")
        self.assertEqual(info["state"], "rule")
        self.assertEqual(info["by"], "sot.cascade")
        self.assertEqual(info["rule"], "Sale Order Type cascade")
        self.assertIn("Sale Order Type cascade", info["label"])

    def test_provenance_for_legacy_string_entry(self):
        """Backward-compat: read a v0.1 bare-string entry."""
        partner = self.env["res.partner"].create({"name": "Legacy"})
        # Bypass the public API to inject the legacy shape directly.
        partner.with_context(_prov_skip=True).write({"_provenance": {"comment": "u"}})
        self.assertTrue(partner._user_set("comment"))
        info = partner._provenance_for("comment")
        self.assertEqual(info["state"], "user")
        # No `by` was stored in the legacy form; tooltip degrades to
        # "Set by user system".
        self.assertEqual(info["by"], "system")

    # ------------------------------------------------------------------
    # Track-set caching and untracked-field hygiene
    # ------------------------------------------------------------------
    def test_untracked_field_not_stamped(self):
        partner = self.env["res.partner"].create({"name": "Tracked Only"})
        self.assertNotIn("name", partner._provenance or {})

    def test_cache_invalidated_on_flag_toggle(self):
        self._set_track_provenance(self.field_comment, False)
        partner = self.env["res.partner"].create(
            {"name": "Post-Toggle", "comment": "no longer tracked"}
        )
        self.assertNotIn("comment", partner._provenance or {})
        self._set_track_provenance(self.field_comment, True)

    # ------------------------------------------------------------------
    # Web client integration
    # ------------------------------------------------------------------
    def test_web_read_emits_provenance(self):
        partner = self.env["res.partner"].create(
            {"name": "WebRead Probe", "comment": "anchored"}
        )
        rows = partner.web_read({"comment": {}, "name": {}})
        self.assertEqual(len(rows), 1)
        self.assertIn("_provenance", rows[0])
        self.assertEqual(rows[0]["_provenance"]["comment"]["s"], "u")

    # ------------------------------------------------------------------
    # Timestamp determinism
    # ------------------------------------------------------------------
    def test_explicit_when_is_persisted(self):
        partner = self.env["res.partner"].create({"name": "Frozen Time"})
        frozen = int(time.time()) - 3600  # one hour ago
        partner._stamp_provenance(
            ["comment"], source="r", by="cron.recompute", when=frozen
        )
        self.assertEqual((partner._provenance or {})["comment"]["t"], frozen)
        info = partner._provenance_for("comment")
        # The ISO timestamp serializes the frozen-in-the-past time.
        self.assertIn("T", info["when"])
