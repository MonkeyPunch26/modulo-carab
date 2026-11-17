/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { carabineroStatus } from "./carabinero_status";

patch(ActionpadWidget.prototype, {
    get carabinero() {
        if (!this.pos.config.carabinero_required || !this.props.partner) {
            return false;
        }
        return carabineroStatus(this.props.partner);
    },
});
