# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""Provenance machinery for computed-writable fields.

Two cooperating ideas:

1.  Per-field "did the user set this?" probe — `_user_set(fname)` — combining
    the persisted provenance map with an `_origin` transactional fallback.
    Available on every model.

2.  Per-field provenance map — a JSON column `_provenance` recording, for
    every opted-in field, *how* it got its current value:

      - **No entry**       → field still at its default. Implicit. We never
                             stamp the default state to keep the JSON small;
                             the badge falls back to `record.create_date`.
      - `{"s": "u", ...}`  → set by a user (login captured in `b`).
      - `{"s": "r", ...}`  → set by a rule / cascade / integration
                             (writer identifier in `b`, human-readable label
                             in `r`).

    Each entry also carries a unix timestamp `t`, surfaced to the OWL badge
    so the hover tooltip can say "Set by *dkendall* 12 minutes ago" or
    "Set by *Sale Order Type cascade* at 14:02".

Only fields opted-in via `ir.model.fields.track_provenance=True` are
stamped — keeps cost at zero for the typical record.

The OWL widget consumes `_provenance` from `web_read` and renders a small
icon next to the field; the `_provenance_for(fname)` method returns the
tooltip dict.
"""

import json
import time
from datetime import datetime, timezone

from odoo import api, fields, models, tools

# Source short-codes, kept terse so the JSON column stays compact when
# many fields opt in. Matches the convention in mail.tracking.value and
# sale.order.line.extra_tax_data.
_USER = "u"
_RULE = "r"
_VALID_SOURCES = (_USER, _RULE)


class Base(models.AbstractModel):
    _inherit = "base"

    _provenance = fields.Json(
        string="Field Provenance",
        help="Per-field provenance map.\n"
        "Absence of an entry means the field is still at its default. "
        "Entries are of the form {s, b, t, r?}: "
        "s=source ('u'=user, 'r'=rule/cascade), "
        "b=writer identifier (login or rule id), "
        "t=unix timestamp, "
        "r=optional human-readable rule label.",
        copy=False,
    )

    # ------------------------------------------------------------------
    # Public helper API
    # ------------------------------------------------------------------
    def _user_set(self, fname):
        """Return True if `fname` was set by the user, not by a default
        or a cascade.

        Resolution order:
          1. Persisted provenance map: entry with `s == 'u'` ⇒ True.
          2. `_origin` fallback: a NewId record whose current value
             differs from the persisted one and is non-falsy is treated
             as user-touched (in-form dirty bit before save).
        """
        self.ensure_one()
        entry = self._provenance_entry(fname)
        if entry.get("s") == _USER:
            return True
        origin = self._origin
        if (
            origin
            and origin is not self
            and self[fname]
            and origin[fname] != self[fname]
        ):
            return True
        return False

    def _stamp_provenance(self, keys, *, source, by, rule=None, when=None):
        """Public API for cascade methods and integrations.

        Use this when a rule, cascade, EDI inbound, import wizard, or any
        other non-user writer applies a value, so that the badge surface
        can attribute the value correctly.

        :param keys:  iterable of tracked field names to stamp.
        :param source: 'u' (user) or 'r' (rule/cascade). Do not stamp the
                       default state — its absence is informative.
        :param by: stable string identifier of the writer. Required and
                   non-empty. Examples:
                     - 'sot.cascade' for sale_order_type propagation
                     - 'edi:l10n_gr_edi' for Greek e-invoicing inbound
                     - 'import' for bulk loaders
                     - a user login for explicit attribution.
        :param rule: optional human-readable label rendered in the badge
                     tooltip ("Sale Order Type cascade").
        :param when: optional unix timestamp; defaults to `time.time()`.
        """
        if source not in _VALID_SOURCES:
            raise ValueError(
                "_stamp_provenance: source must be 'u' or 'r' "
                f"(absence of an entry already means default); got {source!r}"
            )
        if not by:
            raise ValueError(
                "_stamp_provenance: 'by' must be a non-empty string identifier"
            )
        tracked = self._field_track_set()
        keys = [k for k in keys if k in tracked]
        if not keys:
            return
        self._stamp_provenance_keys(
            keys,
            source=source,
            by=by,
            rule=rule,
            when=when,
        )

    def _provenance_for(self, fname):
        """Return the badge-tooltip dict for `fname`.

        Shape:
            {
                "state":  "default" | "user" | "rule",
                "label":  human-readable summary,
                "by":     writer identifier (omitted for default),
                "rule":   rule label (only for state=="rule" with `r`),
                "when":   ISO-8601 timestamp (None if unknown),
            }

        Consumed by the OWL widget; also useful in tests for golden
        assertions.
        """
        self.ensure_one()
        entry = self._provenance_entry(fname)
        if not entry or "s" not in entry:
            return {
                "state": "default",
                "label": "Default value",
                "when": (
                    self.create_date.replace(tzinfo=timezone.utc).isoformat()
                    if self.create_date
                    else None
                ),
            }
        source = entry.get("s")
        by = entry.get("b") or "system"
        when = entry.get("t")
        when_iso = (
            datetime.fromtimestamp(when, tz=timezone.utc).isoformat()
            if isinstance(when, int | float)
            else None
        )
        if source == _USER:
            return {
                "state": "user",
                "by": by,
                "label": f"Set by user {by}",
                "when": when_iso,
            }
        if source == _RULE:
            label_name = entry.get("r") or by
            return {
                "state": "rule",
                "by": by,
                "rule": entry.get("r"),
                "label": f"Set by {label_name}",
                "when": when_iso,
            }
        # Unknown source — degrade to default semantics rather than crash.
        return {
            "state": "default",
            "label": "Default value",
            "when": None,
        }

    # ------------------------------------------------------------------
    # ORM hooks — stamp provenance on user writes
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records._field_track_set():
            records._stamp_provenance_from_vals(vals_list, source=_USER)
        return records

    def write(self, vals):
        if self.env.context.get("_prov_skip"):
            return super().write(vals)
        # If the client supplied a `_provenance` payload (e.g. the OWL
        # badge's optimistic click-to-anchor update), sanitize it before
        # it hits the column. Untrusted callers must not be able to
        # forge `b` (writer identity) or `t` (timestamp), and must not
        # be able to claim rule provenance — only server-side cascade
        # code can do that via `_stamp_provenance`.
        if "_provenance" in vals and vals["_provenance"] is not None:
            vals = dict(vals)
            vals["_provenance"] = self._sanitize_client_provenance(vals["_provenance"])
        tracked = self._field_track_set()
        user_keys = [k for k in vals if k in tracked]
        res = super().write(vals)
        if user_keys:
            self._stamp_provenance_keys(user_keys, source=_USER)
        return res

    def _sanitize_client_provenance(self, payload):
        """Rewrite a client-supplied `_provenance` map so every entry is
        attributed to the currently-authenticated user with the current
        timestamp. Drops any `s='r'` (rule) entry — only server-side
        cascade callers may stamp rule provenance via `_stamp_provenance`.

        We keep the payload's *keys* (the field names the client wants
        anchored) but always replace the *values* with trusted ones.
        """
        if not isinstance(payload, dict):
            # Reject non-dict payloads outright rather than persist
            # something the badge can't interpret.
            return {}
        login = self.env.user.login
        now = int(time.time())
        sanitized = {}
        for fname, raw in payload.items():
            # Reject obvious junk: non-string keys, unknown sources, etc.
            if not isinstance(fname, str):
                continue
            if isinstance(raw, dict) and raw.get("s") == _RULE:
                # Client cannot claim rule provenance. Skip.
                continue
            sanitized[fname] = {"s": _USER, "b": login, "t": now}
        return sanitized

    # ------------------------------------------------------------------
    # Web client integration — surface _provenance alongside tracked
    # fields. Form views in 18.0+ call web_read; the legacy read()
    # override is kept thin for backwards compat.
    # ------------------------------------------------------------------
    def web_read(self, specification):
        result = super().web_read(specification)
        if not result or not self._field_track_set():
            return result
        if not any(name in self._field_track_set() for name in specification):
            return result
        prov_by_id = {r.id: (r._provenance or {}) for r in self}
        for row in result:
            row["_provenance"] = prov_by_id.get(row.get("id"), {})
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @api.model
    @tools.ormcache("self._name")
    def _field_track_set(self):
        """Cached set of opted-in field names on this model. Invalidated
        when `ir.model.fields.track_provenance` toggles (see
        ir_model_fields.py).
        """
        return frozenset(
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("model", "=", self._name),
                    ("track_provenance", "=", True),
                ]
            )
            .mapped("name")
        )

    def _provenance_entry(self, fname):
        """Return a dict-shaped entry for `fname`, normalizing the legacy
        bare-string form (`"u"` / `"s"`) into the dict shape. Callers
        outside this module should prefer `_provenance_for`.
        """
        self.ensure_one()
        raw = (self._provenance or {}).get(fname)
        if isinstance(raw, str):
            # Legacy v0.1 schema — keep readable while DBs migrate.
            return {"s": raw} if raw in _VALID_SOURCES else {}
        return dict(raw) if raw else {}

    def _stamp_provenance_from_vals(self, vals_list, source):
        tracked = self._field_track_set()
        for rec, vals in zip(self, vals_list, strict=False):
            keys = [k for k in (vals or {}) if k in tracked]
            if keys:
                rec._stamp_provenance_keys(keys, source=source)

    def _stamp_provenance_keys(self, keys, source, by=None, when=None, rule=None):
        """Persist the stamping. One UPDATE per persistent record.

        Skips records whose `id` is a `NewId` — i.e. unsaved records
        living inside an Odoo Form / onchange cycle. Stamping those
        would force `_provenance` into the onchange-diff result and
        break form views that don't declare the field (which is most
        of them — `_provenance` is consumed via `web_read` by the OWL
        badge, not via the view spec). On the eventual save the
        `create()` hook will stamp from `vals`, which includes the
        cascade-resolved value — so attribution is preserved with
        the caveat that NewId-time cascade stamps degrade to `s='u'`
        rather than `s='r'`. Acceptable for v1; a deferred-flush
        mechanism is the right long-term fix.

        We also bypass `write()` and use raw SQL: routing through the
        ORM would re-trigger compute chains and tracking machinery for
        what is conceptually a metadata side-effect.

        `by` defaults to `env.user.login` for user writes. For rule writes
        the public `_stamp_provenance` already enforced a non-empty `by`,
        so this private path shouldn't see `None`.
        """
        if not by:
            by = self.env.user.login if source == _USER else "system"
        if when is None:
            when = int(time.time())
        table = self._table
        # Only stamp persistent records. NewId records show up in two
        # paths: Form/onchange (stamping there leaks `_provenance` into
        # the diff and trips `KeyError: '_provenance'` in views that
        # don't declare the field — most of them) and `create()`
        # precomputes (no row to UPDATE yet). For new-record cascade
        # attribution, the badge degrades to the "default" state until
        # the next persistent-record write touches the field — at which
        # point this stamping path catches it correctly.
        persistent = self.filtered(lambda r: isinstance(r.id, int))
        for rec in persistent:
            current = dict(rec._provenance or {})
            for k in keys:
                entry = {"s": source, "b": by, "t": when}
                if rule:
                    entry["r"] = rule
                current[k] = entry
            self.env.cr.execute(
                f'UPDATE "{table}" SET "_provenance" = %s WHERE id = %s',
                [json.dumps(current), rec.id],
            )
            # Invalidate (don't set) so the new value isn't tracked as
            # an in-flight write — that's what makes `_provenance` show
            # up in onchange results and breaks Form tests with
            # `KeyError: '_provenance'`. Subsequent reads round-trip
            # to the DB, which is fine because the field is read-rare.
            rec.invalidate_recordset(["_provenance"])
