# -*- coding: utf-8 -*-
import re

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import format_date

APPROVER_GROUP = 'dros_carabineros.group_carabinero_aprobador'
DEFAULT_TZ = 'America/Santiago'
DEFAULT_VALIDITY_MONTHS = 12

# Estos campos solo se cambian con los botones del flujo (que escriben como superusuario).
# Así un vendedor no puede dejarse a sí mismo "Activo" escribiendo el campo por RPC.
PROTECTED_FIELDS = frozenset({
    'carabinero_state',
    'carabinero_valid_until',
    'carabinero_requested_by',
    'carabinero_requested_on',
    'carabinero_resolved_by',
    'carabinero_resolved_on',
    'carabinero_reject_reason',
})


def rut_key(value):
    """'12.345.678-5', ' 12345678-5 ' o 'CL123456785' -> '123456785' (cuerpo + DV en mayúscula)."""
    if not value:
        return ''
    return re.sub(r'[^0-9K]', '', value.upper())


def rut_is_valid(key):
    """Valida cuerpo (7-8 dígitos) y dígito verificador (módulo 11) de una clave de RUT."""
    if not re.fullmatch(r'\d{7,8}[0-9K]', key or ''):
        return False
    body, dv = key[:-1], key[-1]
    total, factor = 0, 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    expected = 11 - total % 11
    expected = '0' if expected == 11 else 'K' if expected == 10 else str(expected)
    return dv == expected


class ResPartner(models.Model):
    _inherit = 'res.partner'

    carabinero_state = fields.Selection(
        [
            ('none', 'No inscrito'),
            ('pending', 'Pendiente de aprobación'),
            ('active', 'Activo'),
            ('expired', 'Inactivo (vencido)'),
            ('rejected', 'Rechazado'),
        ],
        string='Estado Carabineros', default='none', copy=False, tracking=True, index=True,
    )
    carabinero_valid_until = fields.Date('Vigente hasta', copy=False, tracking=True)
    carabinero_is_active = fields.Boolean(
        'Activo hoy', compute='_compute_carabinero_is_active', search='_search_carabinero_is_active')
    carabinero_rut_key = fields.Char(compute='_compute_carabinero_rut_key', store=True, index=True)

    carabinero_email = fields.Char('Correo institucional', copy=False)
    carabinero_rank = fields.Char('Grado')
    carabinero_unit = fields.Char('Unidad / destacamento')

    carabinero_requested_by = fields.Many2one('res.users', 'Solicitado por', copy=False, readonly=True)
    carabinero_requested_on = fields.Datetime('Solicitado el', copy=False, readonly=True)
    carabinero_resolved_by = fields.Many2one('res.users', 'Resuelto por', copy=False, readonly=True)
    carabinero_resolved_on = fields.Datetime('Resuelto el', copy=False, readonly=True)
    carabinero_reject_reason = fields.Char('Motivo del rechazo', copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Campos calculados y restricciones
    # ------------------------------------------------------------------
    @api.depends('vat')
    def _compute_carabinero_rut_key(self):
        for partner in self:
            partner.carabinero_rut_key = rut_key(partner.vat)

    @api.depends('carabinero_state', 'carabinero_valid_until')
    def _compute_carabinero_is_active(self):
        today = self._carabinero_today()
        for partner in self:
            partner.carabinero_is_active = bool(
                partner.carabinero_state == 'active'
                and partner.carabinero_valid_until
                and partner.carabinero_valid_until >= today
            )

    def _search_carabinero_is_active(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_("Operador no soportado para 'Activo hoy'."))
        today = self._carabinero_today()
        positive = (operator == '=') == bool(value)
        if positive:
            return [('carabinero_state', '=', 'active'), ('carabinero_valid_until', '>=', today)]
        return ['|', ('carabinero_state', '!=', 'active'),
                '|', ('carabinero_valid_until', '=', False), ('carabinero_valid_until', '<', today)]

    @api.constrains('carabinero_rut_key', 'carabinero_state')
    def _check_carabinero_rut_unique(self):
        for partner in self:
            if partner.carabinero_state == 'none' or not partner.carabinero_rut_key:
                continue
            other = self.sudo().with_context(active_test=False).search([
                ('id', '!=', partner.id),
                ('carabinero_rut_key', '=', partner.carabinero_rut_key),
                ('carabinero_state', '!=', 'none'),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    "El RUT %(rut)s ya está inscrito en otro cliente: %(name)s.",
                    rut=partner.vat, name=other.display_name))

    # ------------------------------------------------------------------
    # Seguridad: los campos del flujo no se escriben a mano
    # ------------------------------------------------------------------
    def _carabinero_check_protected(self, vals, creating=False):
        if self.env.su:
            return
        for name in PROTECTED_FIELDS.intersection(vals):
            value = vals[name]
            # Al crear, los valores en blanco son los de fábrica: Odoo los pasa solo, por ejemplo
            # cuando se crea un usuario (que crea su contacto). Un valor real sí se bloquea.
            if creating and (not value or (name == 'carabinero_state' and value == 'none')):
                continue
            raise AccessError(_(
                "El estado y la vigencia de Carabineros solo se cambian con los botones "
                "de solicitar, aprobar o rechazar."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._carabinero_check_protected(vals, creating=True)
        return super().create(vals_list)

    def write(self, vals):
        self._carabinero_check_protected(vals)
        return super().write(vals)

    def _carabinero_check_approver(self):
        if not (self.env.su or self.env.user.has_group(APPROVER_GROUP)):
            raise AccessError(_("Solo un Aprobador de Carabineros puede aprobar o rechazar inscripciones."))

    # ------------------------------------------------------------------
    # Fechas
    # ------------------------------------------------------------------
    def _carabinero_tz(self):
        return self.env.context.get('tz') or self.env.user.tz or DEFAULT_TZ

    def _carabinero_today(self):
        return fields.Date.context_today(self.with_context(tz=self._carabinero_tz()))

    def _carabinero_validity_months(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'dros_carabineros.validity_months', DEFAULT_VALIDITY_MONTHS)
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return DEFAULT_VALIDITY_MONTHS

    def _carabinero_valid_on(self, date):
        """¿Estaba vigente el cliente en esa fecha? (se usa al sincronizar ventas hechas sin conexión)."""
        self.ensure_one()
        return bool(
            self.carabinero_state != 'rejected'
            and self.carabinero_valid_until
            and self.carabinero_valid_until >= date
        )

    @api.model
    def _carabinero_local_date(self, utc_string):
        """Convierte 'YYYY-MM-DD HH:MM:SS' (UTC) a la fecha local del negocio."""
        try:
            naive = fields.Datetime.to_datetime(str(utc_string).replace('T', ' ')[:19])
            aware = pytz.utc.localize(naive).astimezone(pytz.timezone(self._carabinero_tz()))
            return aware.date()
        except (TypeError, ValueError, pytz.UnknownTimeZoneError):
            return self._carabinero_today()

    # ------------------------------------------------------------------
    # Flujo
    # ------------------------------------------------------------------
    @api.model
    def _carabinero_approvers(self):
        group = self.env.ref(APPROVER_GROUP)
        return group.sudo().users.filtered(lambda u: u.active and not u.share)

    def _carabinero_validate_rut(self):
        for partner in self:
            if not partner.vat:
                raise UserError(_("%s no tiene RUT. Anótalo en el campo RUT / Tax ID antes de continuar.",
                                  partner.display_name))
            if not rut_is_valid(partner.carabinero_rut_key):
                raise UserError(_(
                    "El RUT '%(vat)s' de %(name)s no es válido. Revisa el número y el dígito verificador.",
                    vat=partner.vat, name=partner.display_name))

    def _carabinero_close_activities(self):
        self.sudo().activity_feedback(['dros_carabineros.mail_activity_type_approval'])

    def action_carabinero_request(self):
        """El vendedor pide que el aprobador inscriba (o renueve) al cliente."""
        approvers = self._carabinero_approvers()
        if not approvers:
            raise UserError(_(
                "No hay ningún Aprobador de Carabineros configurado. Pide al administrador que "
                "agregue ese grupo al usuario que aprueba (Ajustes > Usuarios)."))
        for partner in self:
            if partner.carabinero_state == 'pending':
                raise UserError(_("%s ya tiene una solicitud pendiente de aprobación.", partner.display_name))
            if partner.carabinero_state == 'active':
                raise UserError(_("%s ya está activo.", partner.display_name))
            partner._carabinero_validate_rut()
            partner.sudo().write({
                'carabinero_state': 'pending',
                'carabinero_requested_by': self.env.user.id,
                'carabinero_requested_on': fields.Datetime.now(),
                'carabinero_reject_reason': False,
            })
            partner.sudo().message_post(body=_(
                "%s solicitó la inscripción de este cliente. Queda pendiente de aprobación.",
                self.env.user.name))
            for approver in approvers:
                partner.sudo().activity_schedule(
                    'dros_carabineros.mail_activity_type_approval',
                    user_id=approver.id,
                    summary=_("Aprobar inscripción: %s", partner.display_name),
                )
        return True

    def action_carabinero_approve(self):
        """El aprobador activa al cliente por 12 meses (también sirve para renovar)."""
        self._carabinero_check_approver()
        today = self._carabinero_today()
        until = today + relativedelta(months=self._carabinero_validity_months())
        for partner in self:
            partner._carabinero_validate_rut()
            partner.sudo().write({
                'carabinero_state': 'active',
                'carabinero_valid_until': until,
                'carabinero_resolved_by': self.env.user.id,
                'carabinero_resolved_on': fields.Datetime.now(),
                'carabinero_reject_reason': False,
            })
            partner._carabinero_close_activities()
            partner.sudo().message_post(body=_(
                "%(user)s aprobó la inscripción. Vigente hasta el %(date)s.",
                user=self.env.user.name, date=format_date(self.sudo().env, until)))
        return True

    def action_carabinero_reject(self, reason=None):
        """El aprobador rechaza una solicitud o revoca a un cliente activo."""
        self._carabinero_check_approver()
        for partner in self:
            if partner.carabinero_state not in ('pending', 'active', 'expired'):
                raise UserError(_("%s no tiene nada que rechazar.", partner.display_name))
            partner.sudo().write({
                'carabinero_state': 'rejected',
                'carabinero_valid_until': False,
                'carabinero_resolved_by': self.env.user.id,
                'carabinero_resolved_on': fields.Datetime.now(),
                'carabinero_reject_reason': reason or False,
            })
            partner._carabinero_close_activities()
            partner.sudo().message_post(body=_(
                "%(user)s rechazó la inscripción.%(reason)s",
                user=self.env.user.name,
                reason=_(" Motivo: %s", reason) if reason else ''))
        return True

    def action_carabinero_open_reject_wizard(self):
        self._carabinero_check_approver()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Rechazar o revocar inscripción"),
            'res_model': 'dros.carabinero.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_ids': self.ids},
        }

    @api.model
    def _cron_carabinero_expire(self):
        """Todas las noches: los clientes cuya vigencia terminó pasan a 'Inactivo (vencido)'."""
        today = self._carabinero_today()
        expired = self.sudo().search([
            ('carabinero_state', '=', 'active'),
            ('carabinero_valid_until', '<', today),
        ])
        for partner in expired:
            partner.write({'carabinero_state': 'expired'})
            partner.message_post(body=_(
                "La vigencia terminó el %s. El cliente quedó inactivo y hay que volver a activarlo para venderle.",
                format_date(self.sudo().env, partner.carabinero_valid_until)))
        return len(expired)

    # ------------------------------------------------------------------
    # POS: crear/editar cliente desde la caja, con solicitud opcional
    # ------------------------------------------------------------------
    @api.model
    def create_from_ui(self, partner):
        partner = dict(partner)
        request = partner.pop('carabinero_request', False)
        partner_id = super().create_from_ui(partner)
        if request:
            self.browse(partner_id).action_carabinero_request()
        return partner_id
