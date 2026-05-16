/** @odoo-module **/

/*
 * Provenance Badge — SAP S/4HANA "green-arrow" pattern for Odoo.
 *
 * Reads `_provenance` (a JSON map of {field_name: 'u'|'s'}) from the active
 * record and renders a tiny icon next to fields that opted in via
 * `ir.model.fields.track_provenance`. Clicking the badge flips provenance
 * to "user" (anchoring the manual override) and reveals the original
 * computed value in a tooltip.
 *
 * Usage: <field name="payment_term_id" widget="provenance_m2o"/>
 *
 * MVP scope: many2one only. selection/char follow the same shape.
 */
import {registry} from "@web/core/registry";
import {useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {Many2OneField, many2OneField} from "@web/views/fields/many2one/many2one_field";

const SOURCE_USER = "u";
const SOURCE_SYSTEM = "s";

export class ProvenanceMany2OneField extends Many2OneField {
    static template = "web_field_provenance.ProvenanceMany2One";
    static components = {...Many2OneField.components};

    setup() {
        super.setup();
        this.badge = useState({visible: true});
    }

    get provenance() {
        const map = this.props.record.data._provenance || {};
        return map[this.props.name] || SOURCE_SYSTEM;
    }

    get badgeTitle() {
        if (this.provenance === SOURCE_USER) {
            return _t("Value set by user — will be preserved on recompute");
        }
        return _t(
            "Value derived from a default or computed rule — may change if upstream fields change"
        );
    }

    onBadgeClick(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        const current = {...(this.props.record.data._provenance || {})};
        current[this.props.name] = SOURCE_USER;
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
