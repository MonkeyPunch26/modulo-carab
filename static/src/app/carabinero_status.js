/** @odoo-module */

import { _t } from "@web/core/l10n/translation";

const pad = (n) => String(n).padStart(2, "0");

/** Fecha local del computador de la caja, como 'YYYY-MM-DD' (comparable como texto con la vigencia). */
export function todayISO(date = new Date()) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function displayDate(iso) {
    const [year, month, day] = iso.split("-");
    return `${day}/${month}/${year}`;
}

/**
 * Estado efectivo de un cliente frente al programa Carabineros.
 * No confía solo en el estado guardado: si la vigencia ya pasó, es inactivo aunque el
 * proceso nocturno del servidor todavía no lo haya marcado.
 */
export function carabineroStatus(partner) {
    if (!partner) {
        return { code: "no_customer", active: false, label: _t("Sin cliente"), cssClass: "text-bg-secondary" };
    }
    const state = partner.carabinero_state || "none";
    const until = partner.carabinero_valid_until || false;
    if (state === "active" && until && until >= todayISO()) {
        return {
            code: "active",
            active: true,
            label: _t("Activo hasta %s", displayDate(until)),
            cssClass: "text-bg-success",
        };
    }
    if (state === "active" || state === "expired") {
        return {
            code: "expired",
            active: false,
            label: until ? _t("Inactivo: venció el %s", displayDate(until)) : _t("Inactivo (vencido)"),
            cssClass: "text-bg-danger",
        };
    }
    if (state === "pending") {
        return { code: "pending", active: false, label: _t("Pendiente de aprobación"), cssClass: "text-bg-warning" };
    }
    if (state === "rejected") {
        return { code: "rejected", active: false, label: _t("Rechazado"), cssClass: "text-bg-danger" };
    }
    return { code: "none", active: false, label: _t("No inscrito"), cssClass: "text-bg-secondary" };
}

/** Líneas de la venta con productos que solo se venden a Carabineros activos (sin propinas ni descuentos). */
export function restrictedLines(pos, order) {
    const tip = pos.config.tip_product_id;
    const tipId = Array.isArray(tip) ? tip[0] : tip && typeof tip === "object" ? tip.id : tip;
    return order.get_orderlines().filter((line) => {
        const product = line.get_product();
        return (
            line.get_quantity() > 0 &&
            line.get_unit_price() > 0 &&
            product.id !== tipId &&
            !product.carabinero_public_sale
        );
    });
}

/**
 * Si la venta no se puede cobrar, devuelve { title, body } para mostrar; si se puede, null.
 * Solo importa si hay productos restringidos en la venta. Las ventas con total <= 0
 * (devoluciones) no se bloquean: eso lo decide quien llama.
 */
export function carabineroBlock(pos, order) {
    if (!pos.config.carabinero_required) {
        return null;
    }
    const restricted = restrictedLines(pos, order);
    if (!restricted.length) {
        return null;
    }
    const names = [...new Set(restricted.map((line) => line.get_full_product_name()))];
    const products = names.slice(0, 3).join(", ") + (names.length > 3 ? "…" : "");
    const partner = order.get_partner();
    if (!partner) {
        return {
            title: _t("Falta el cliente"),
            body: _t(
                "La venta incluye productos solo para Carabineros (%s). Selecciona un cliente Carabinero activo para continuar.",
                products
            ),
        };
    }
    const status = carabineroStatus(partner);
    if (status.active) {
        return null;
    }
    let hint;
    if (status.code === "pending") {
        hint = _t("Su inscripción espera la aprobación del encargado.");
    } else if (status.code === "none") {
        hint = _t("Entra a los detalles del cliente y usa 'Guardar y solicitar inscripción'.");
    } else if (status.code === "rejected") {
        hint = _t("El encargado rechazó su inscripción.");
    } else {
        hint = _t("Hay que renovar su inscripción: pide la renovación para que el encargado la apruebe.");
    }
    return {
        title: _t("Cliente no activo"),
        body: `${partner.name}: ${status.label}. ${_t("No se le pueden vender productos solo para Carabineros (%s).", products)} ${hint}`,
    };
}
