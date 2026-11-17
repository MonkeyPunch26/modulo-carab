/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { PartnerDetailsEdit } from "@point_of_sale/app/screens/partner_list/partner_editor/partner_editor";
import { carabineroStatus } from "./carabinero_status";

patch(PartnerDetailsEdit.prototype, {
    setup() {
        super.setup(...arguments);
        const partner = this.props.partner;
        Object.assign(this.changes, {
            carabinero_email: partner.carabinero_email || false,
            carabinero_rank: partner.carabinero_rank || false,
            carabinero_unit: partner.carabinero_unit || false,
            carabinero_request: false,
        });
    },

    get carabineroEnabled() {
        return Boolean(this.pos.config.carabinero_required);
    },

    /** Estado del cliente que se está editando (uno nuevo todavía no está inscrito). */
    get carabinero() {
        return carabineroStatus({ carabinero_state: "none", ...this.props.partner });
    },

    /** Se puede pedir inscripción si es nuevo, no está inscrito, venció o fue rechazado. */
    get canRequestCarabinero() {
        return ["none", "expired", "rejected"].includes(this.carabinero.code);
    },

    get requestCarabineroLabel() {
        return this.carabinero.code === "expired" ? _t("Guardar y solicitar renovación") : _t("Guardar y solicitar inscripción");
    },

    async requestCarabinero() {
        if (!this.changes.vat) {
            await this.popup.add(ErrorPopup, {
                title: _t("Falta el RUT"),
                body: _t("Escribe el RUT del cliente en el campo Tax ID antes de solicitar la inscripción."),
            });
            return;
        }
        this.changes.carabinero_request = true;
        this.saveChanges();
    },
});
