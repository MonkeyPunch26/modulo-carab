/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { carabineroStatus } from "./carabinero_status";

patch(PartnerLine.prototype, {
    get carabinero() {
        if (!this.env.services.pos.config.carabinero_required) {
            return false;
        }
        return carabineroStatus(this.props.partner);
    },
});
