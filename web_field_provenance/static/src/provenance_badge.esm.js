/** @odoo-module **/

/*
 * Provenance Badge — Salesforce/SAP-style "where did this value come
 * from?" indicator for Odoo.
 *
 * Reads `_provenance` (a JSON map of {field: {s, b, t, r?}}) from the
 * active record and renders a small icon next to fields that opted in
 * via `ir.model.fields.track_provenance`. Three visual states:
 *
 *   - default:  grey outline circle — field is still at its default
 *               (no entry in the map).
 *   - rule:     green cog — set by a rule / cascade / EDI integration.
 *   - user:     pencil — set by a user write.
 *
 * Hover reveals the writer and timestamp ("Set by user dkendall at
 * 2026-05-16T20:15Z", "Set by Sale Order Type cascade", etc.).
 * Clicking the badge promotes the value to user-anchored.
 *
 * Usage: <field name="payment_term_id" widget="provenance_m2o"/>
 *
 * MVP scope: many2one only. Selection / char follow the same shape.
 */
import {registry} from "@web/core/registry";
import {_t} from "@web/core/l10n/translation";
import {Many2OneField, many2OneField} from "@web/views/fields/many2one/many2one_field";

const SOURCE_USER = "u";
const SOURCE_RULE = "r";

export class ProvenanceMany2OneField extends Many2OneField {
    static template = "web_field_provenance.ProvenanceMany2One";
    static components = {...Many2OneField.components};

    get entry() {
        const map = this.props.record.data._provenance || {};
        const raw = map[this.props.name];
        if (!raw) {
            return null;
        }
        // Legacy bare-string schema: normalize to dict shape.
        if (typeof raw === "string") {
            return {s: raw};
        }
        return raw;
    }

    get state() {
        const e = this.entry;
        if (!e || !e.s) {
            return "default";
        }
        if (e.s === SOURCE_USER) {
            return "user";
        }
        if (e.s === SOURCE_RULE) {
            return "rule";
        }
        return "default";
    }

    get badgeIconClass() {
        if (this.state === "user") {
            return "fa fa-pencil";
        }
        if (this.state === "rule") {
            return "fa fa-cog text-success";
        }
        return "fa fa-circle-o text-muted";
    }

    get badgeTitle() {
        const e = this.entry;
        const when = e?.t ? new Date(e.t * 1000).toLocaleString() : null;
        if (this.state === "user") {
            return _t("Set by user %s%s", e.b || "?", when ? " at " + when : "");
        }
        if (this.state === "rule") {
            const label = e.r || e.b || _t("a rule");
            return _t("Set by %s%s", label, when ? " at " + when : "");
        }
        return _t("Default value — set when the record was created");
    }

    onBadgeClick(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        const current = {...(this.props.record.data._provenance || {})};
        // Promote to user-anchored. The `t` and `b` get filled in by the
        // server on save (ORM write() handles user stamping); we set a
        // sentinel here so the badge updates optimistically.
        current[this.props.name] = {
            s: SOURCE_USER,
            b: this.env.services.user?.login || "user",
            t: Math.floor(Date.now() / 1000),
        };
        this.props.record.update({_provenance: current});
    }
}

export const provenanceMany2OneField = {
    ...many2OneField,
    component: ProvenanceMany2OneField,
    displayName: ({string}) => string,
    supportedOptions: many2OneField.supportedOptions,
};

registry.category("fields").add("provenance_m2o", provenanceMany2OneField);
