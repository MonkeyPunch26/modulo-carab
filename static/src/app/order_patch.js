/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { carabineroBlock, carabineroStatus, restrictedLines } from "./carabinero_status";

patch(Order.prototype, {
    /** Primera barrera: no se puede ir a pagar si el cliente no está activo. */
    async pay() {
        if (this.get_total_with_tax() > 0) {
            const block = carabineroBlock(this.pos, this);
            if (block) {
                await this.env.services.popup.add(ErrorPopup, block);
                return;
            }
        }
        return super.pay(...arguments);
    },

    /** Avisa al elegir un cliente no activo, solo si la venta ya tiene productos restringidos. */
    set_partner(partner) {
        super.set_partner(...arguments);
        if (partner && this.pos.config.carabinero_required && restrictedLines(this.pos, this).length) {
            const status = carabineroStatus(partner);
            if (!status.active) {
                this.env.services.pos_notification?.add(`${partner.name}: ${status.label}`, 5000);
            }
        }
    },
});

patch(PaymentScreen.prototype, {
    /** Segunda barrera: aunque se llegue a la pantalla de pago por otro camino, no se valida. */
    async _isOrderValid(isForceValidate) {
        const order = this.currentOrder;
        if (order.get_total_with_tax() > 0) {
            const block = carabineroBlock(this.pos, order);
            if (block) {
                await this.popup.add(ErrorPopup, block);
                return false;
            }
        }
        return super._isOrderValid(...arguments);
    },
});
