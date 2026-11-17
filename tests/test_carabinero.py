# -*- coding: utf-8 -*-
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from odoo import fields
from odoo.addons.point_of_sale.tests.common import TestPoSCommon
from odoo.addons.dros_carabineros.models.res_partner import rut_is_valid, rut_key
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

VALID_RUT = '12.345.678-5'
OTHER_VALID_RUT = '11.111.111-1'


class CarabineroCommon:
    """Usuarios y utilidades compartidas."""

    def _make_users(self):
        Users = self.env['res.users'].with_context(no_reset_password=True)
        base_user = self.env.ref('base.group_user')
        pos_user = self.env.ref('point_of_sale.group_pos_user')
        # Vendedor típico: puede crear/editar clientes desde la caja (derecho estándar "Creación de contactos").
        self.cashier = Users.create({
            'name': 'Cajero Prueba', 'login': 'cajero_prueba', 'email': 'cajero@example.com',
            'groups_id': [(6, 0, [base_user.id, pos_user.id, self.env.ref('base.group_partner_manager').id])],
        })
        # Vendedor sin ese derecho: igual puede pedir la inscripción de un cliente que ya existe.
        self.cashier_basic = Users.create({
            'name': 'Cajero Básico', 'login': 'cajero_basico', 'email': 'basico@example.com',
            'groups_id': [(6, 0, [base_user.id, pos_user.id])],
        })
        self.approver = Users.create({
            'name': 'Papá Aprobador', 'login': 'aprobador_prueba', 'email': 'papa@example.com',
            'groups_id': [(6, 0, [self.env.ref('dros_carabineros.group_carabinero_aprobador').id])],
        })

    @contextmanager
    def _today(self, day):
        """Fija el 'hoy' del negocio. Vacía el caché: 'Activo hoy' depende de la fecha, no de campos guardados."""
        with patch.object(self.env.registry['res.partner'], '_carabinero_today', return_value=day):
            self.env.invalidate_all()
            yield
        self.env.invalidate_all()

    def _partner(self, name='Juan Pérez', vat=VALID_RUT, **kw):
        return self.env['res.partner'].create({'name': name, 'vat': vat, **kw})


@tagged('post_install', '-at_install')
class TestCarabineroFlow(CarabineroCommon, TransactionCase):

    def setUp(self):
        super().setUp()
        self._make_users()
        self.partner = self._partner()

    # ------------------------------------------------------------ RUT
    def test_rut_helpers(self):
        for rut in ('12.345.678-5', '11111111-1', 'CL761234560', ' 10.000.013-k ', '9.999.999-3', '7654321-6'):
            self.assertTrue(rut_is_valid(rut_key(rut)), rut)
        for rut in ('12.345.678-9', '', '123', 'abc', '1234567890-1', '12.345.678'):
            self.assertFalse(rut_is_valid(rut_key(rut)), rut)

    # ------------------------------------------------------------ solicitud
    def test_request_requires_a_valid_rut(self):
        no_rut = self.env['res.partner'].create({'name': 'Sin RUT'})
        with self.assertRaises(UserError):
            no_rut.with_user(self.cashier).action_carabinero_request()
        bad = self._partner('RUT malo', vat='12.345.678-9')
        with self.assertRaises(UserError):
            bad.with_user(self.cashier).action_carabinero_request()
        self.assertEqual(bad.carabinero_state, 'none')

    def test_request_creates_pending_and_notifies_the_approver(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        self.assertEqual(self.partner.carabinero_state, 'pending')
        self.assertEqual(self.partner.carabinero_requested_by, self.cashier)
        activities = self.partner.activity_ids.filtered(
            lambda a: a.activity_type_id == self.env.ref('dros_carabineros.mail_activity_type_approval'))
        self.assertEqual(activities.user_id, self.approver)
        self.assertFalse(self.partner.carabinero_is_active)

    def test_request_works_without_contact_edit_rights(self):
        """Pedir la inscripción no exige poder editar contactos: el cambio de estado lo hace el flujo."""
        with self.assertRaises(AccessError):
            self.partner.with_user(self.cashier_basic).write({'name': 'Cambio no permitido'})
        self.partner.with_user(self.cashier_basic).action_carabinero_request()
        self.assertEqual(self.partner.carabinero_state, 'pending')
        self.assertEqual(self.partner.carabinero_requested_by, self.cashier_basic)

    def test_request_twice_or_when_active_is_refused(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        with self.assertRaises(UserError):
            self.partner.with_user(self.cashier).action_carabinero_request()
        self.partner.with_user(self.approver).action_carabinero_approve()
        with self.assertRaises(UserError):
            self.partner.with_user(self.cashier).action_carabinero_request()

    def test_request_needs_an_approver_to_exist(self):
        self.env.ref('dros_carabineros.group_carabinero_aprobador').users = [(5, 0, 0)]
        with self.assertRaises(UserError):
            self.partner.with_user(self.cashier).action_carabinero_request()
        self.assertEqual(self.partner.carabinero_state, 'none')

    def test_rut_is_unique_among_enrolled_customers(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        twin = self._partner('Otro Juan', vat='12345678-5')  # mismo RUT escrito distinto
        with self.assertRaises(ValidationError):
            twin.with_user(self.cashier).action_carabinero_request()

    # ------------------------------------------------------------ seguridad
    def test_only_the_approver_can_approve_or_reject(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        with self.assertRaises(AccessError):
            self.partner.with_user(self.cashier).action_carabinero_approve()
        with self.assertRaises(AccessError):
            self.partner.with_user(self.cashier).action_carabinero_reject('no')
        self.assertEqual(self.partner.carabinero_state, 'pending')

    def test_cashier_cannot_write_the_protected_fields(self):
        partner = self.partner.with_user(self.cashier)
        for vals in ({'carabinero_state': 'active'},
                     {'carabinero_valid_until': date(2099, 1, 1)},
                     {'carabinero_resolved_by': self.cashier.id}):
            with self.assertRaises(AccessError, msg=str(vals)):
                partner.write(vals)
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.cashier).create(
                {'name': 'Tramposo', 'vat': OTHER_VALID_RUT, 'carabinero_state': 'active'})
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.cashier).create_from_ui(
                {'name': 'Tramposo POS', 'vat': OTHER_VALID_RUT, 'carabinero_state': 'active'})
        # lo que sí puede editar el vendedor:
        partner.write({'carabinero_rank': 'Sargento', 'carabinero_unit': '1a Comisaría', 'carabinero_email': 'x@y.cl'})
        self.assertEqual(self.partner.carabinero_rank, 'Sargento')
        self.assertEqual(self.partner.carabinero_state, 'none')

    def test_creating_a_user_still_works(self):
        """Regresión: crear un usuario crea su contacto con valores de fábrica; no debe bloquearse."""
        admin = self.env.ref('base.user_admin')
        user = self.env['res.users'].with_user(admin).with_context(no_reset_password=True).create(
            {'name': 'Usuario Nuevo', 'login': 'usuario_nuevo', 'email': 'nuevo@example.com'})
        self.assertEqual(user.partner_id.carabinero_state, 'none')

    # ------------------------------------------------------------ aprobación y vigencia
    def test_approval_grants_12_months(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        with self._today(date(2026, 11, 17)):
            self.partner.with_user(self.approver).action_carabinero_approve()
            self.assertEqual(self.partner.carabinero_state, 'active')
            self.assertEqual(self.partner.carabinero_valid_until, date(2027, 11, 17))
            self.assertEqual(self.partner.carabinero_resolved_by, self.approver)
            self.assertTrue(self.partner.carabinero_is_active)
        self.assertFalse(self.partner.activity_ids.filtered(
            lambda a: a.activity_type_id == self.env.ref('dros_carabineros.mail_activity_type_approval')))
        with self._today(date(2027, 11, 17)):  # el último día todavía vale
            self.assertTrue(self.partner.carabinero_is_active)
        with self._today(date(2027, 11, 18)):  # al día siguiente ya no, aunque el cron no haya corrido
            self.assertFalse(self.partner.carabinero_is_active)
            self.assertEqual(self.partner.carabinero_state, 'active')
            self.assertFalse(self.env['res.partner'].search([('carabinero_is_active', '=', True)]))
            self.assertIn(self.partner, self.env['res.partner'].search([('carabinero_is_active', '=', False)]))

    def test_validity_months_can_be_configured(self):
        self.env['ir.config_parameter'].sudo().set_param('dros_carabineros.validity_months', '6')
        with self._today(date(2026, 11, 17)):
            self.partner.with_user(self.approver).action_carabinero_approve()
        self.assertEqual(self.partner.carabinero_valid_until, date(2027, 5, 17))

    def test_cron_marks_expired_and_renewal_needs_a_new_approval(self):
        with self._today(date(2026, 11, 17)):
            self.partner.with_user(self.approver).action_carabinero_approve()
            self.env['res.partner']._cron_carabinero_expire()
            self.assertEqual(self.partner.carabinero_state, 'active')  # sigue vigente
        with self._today(date(2027, 11, 18)):
            self.assertEqual(self.env['res.partner']._cron_carabinero_expire(), 1)
            self.assertEqual(self.partner.carabinero_state, 'expired')
            self.assertFalse(self.partner.carabinero_is_active)
            # el vendedor pide renovar; mientras no se apruebe sigue inactivo
            self.partner.with_user(self.cashier).action_carabinero_request()
            self.assertEqual(self.partner.carabinero_state, 'pending')
            self.assertFalse(self.partner.carabinero_is_active)
            self.partner.with_user(self.approver).action_carabinero_approve()
            self.assertEqual(self.partner.carabinero_valid_until, date(2028, 11, 18))
            self.assertTrue(self.partner.carabinero_is_active)

    def test_approver_can_activate_directly_and_renew_early(self):
        with self._today(date(2026, 11, 17)):
            self.partner.with_user(self.approver).action_carabinero_approve()
        with self._today(date(2027, 10, 20)):
            self.partner.with_user(self.approver).action_carabinero_approve()
        self.assertEqual(self.partner.carabinero_valid_until, date(2028, 10, 20))

    def test_reject_and_revoke(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        self.partner.with_user(self.approver).action_carabinero_reject('No es funcionario')
        self.assertEqual(self.partner.carabinero_state, 'rejected')
        self.assertEqual(self.partner.carabinero_reject_reason, 'No es funcionario')
        self.assertFalse(self.partner.carabinero_valid_until)
        # puede volver a solicitar, y luego revocarse estando activo
        self.partner.with_user(self.cashier).action_carabinero_request()
        self.partner.with_user(self.approver).action_carabinero_approve()
        self.assertTrue(self.partner.carabinero_is_active)
        self.partner.with_user(self.approver).action_carabinero_reject('Ya no pertenece')
        self.assertFalse(self.partner.carabinero_is_active)
        self.assertFalse(self.partner.carabinero_valid_until)

    def test_reject_wizard(self):
        self.partner.with_user(self.cashier).action_carabinero_request()
        action = self.partner.with_user(self.approver).action_carabinero_open_reject_wizard()
        wizard = self.env[action['res_model']].with_user(self.approver).with_context(**action['context']).create(
            {'reason': 'Datos falsos'})
        wizard.action_confirm()
        self.assertEqual(self.partner.carabinero_state, 'rejected')

    # ------------------------------------------------------------ POS: crear desde la caja
    def test_create_from_ui_can_request_in_one_step(self):
        partner_id = self.env['res.partner'].with_user(self.cashier).create_from_ui({
            'name': 'Cliente Caja', 'vat': OTHER_VALID_RUT, 'carabinero_rank': 'Cabo',
            'carabinero_email': 'cabo@carabineros.cl', 'carabinero_request': True,
        })
        partner = self.env['res.partner'].browse(partner_id)
        self.assertEqual(partner.carabinero_state, 'pending')
        self.assertEqual(partner.carabinero_rank, 'Cabo')

    def test_create_from_ui_with_bad_rut_saves_nothing(self):
        before = self.env['res.partner'].search_count([])
        with self.assertRaises(UserError):
            self.env['res.partner'].with_user(self.cashier).create_from_ui(
                {'name': 'RUT roto', 'vat': '1-9', 'carabinero_request': True})
        self.assertEqual(self.env['res.partner'].search_count([]), before)

    def test_create_from_ui_without_request_does_not_enroll(self):
        partner_id = self.env['res.partner'].with_user(self.cashier).create_from_ui(
            {'name': 'Solo guardar', 'vat': OTHER_VALID_RUT, 'carabinero_request': False})
        self.assertEqual(self.env['res.partner'].browse(partner_id).carabinero_state, 'none')


@tagged('post_install', '-at_install')
class TestCarabineroPosOrders(CarabineroCommon, TestPoSCommon):
    """El servidor rechaza ventas a clientes que no estaban activos."""

    def setUp(self):
        super().setUp()
        self._make_users()
        self.config = self.basic_config
        self.product = self.create_product('Polera', self.categ_basic, 10.0, 5)
        self.public_product = self.create_product('Calcetines', self.categ_basic, 3.0, 2)
        self.public_product.product_tmpl_id.carabinero_public_sale = True
        self.open_new_session()
        self.partner = self._partner()

    def _sell(self, customer, qty=1):
        order = self.create_ui_order_data([(self.product, qty)], customer=customer)
        return self.env['pos.order'].create_from_ui([order])

    def _approve(self, partner=None):
        (partner or self.partner).with_user(self.approver).action_carabinero_approve()

    def test_config_requires_active_carabinero_by_default(self):
        self.assertTrue(self.config.carabinero_required)

    def test_sale_to_active_customer_goes_through(self):
        self._approve()
        res = self._sell(self.partner)
        self.assertEqual(len(res), 1)
        self.assertEqual(self.env['pos.order'].browse(res[0]['id']).partner_id, self.partner)

    def test_sale_is_refused_for_every_non_active_state(self):
        for label in ('none', 'pending', 'expired', 'rejected'):
            partner = self._partner('Cliente %s' % label, vat={
                'none': '7.654.321-6', 'pending': '9.999.999-3', 'expired': '10.000.013-K', 'rejected': '76.123.456-0',
            }[label])
            if label == 'pending':
                partner.with_user(self.cashier).action_carabinero_request()
            elif label == 'expired':
                with self._today(date(2020, 1, 1)):
                    partner.with_user(self.approver).action_carabinero_approve()
                self.env['res.partner']._cron_carabinero_expire()
            elif label == 'rejected':
                partner.with_user(self.cashier).action_carabinero_request()
                partner.with_user(self.approver).action_carabinero_reject('no')
            self.assertEqual(partner.carabinero_state, label)
            with self.assertRaises(UserError, msg=label):
                self._sell(partner)

    def test_sale_without_customer_is_refused(self):
        with self.assertRaises(UserError):
            self._sell(False)

    def test_refund_is_not_blocked(self):
        res = self._sell(False, qty=-1)  # total negativo: devolución, sin cliente y sin bloqueo
        self.assertEqual(len(res), 1)

    def test_switching_the_requirement_off_allows_everything(self):
        self.config.carabinero_required = False
        self.assertEqual(len(self._sell(False)), 1)
        self.assertEqual(len(self._sell(self.partner)), 1)

    def test_offline_sale_made_while_active_still_syncs_after_expiry(self):
        with self._today(date(2026, 11, 17)):
            self._approve()
        with self._today(date(2027, 11, 20)):
            self.env['res.partner']._cron_carabinero_expire()
        self.assertEqual(self.partner.carabinero_state, 'expired')
        order = self.create_ui_order_data([(self.product, 1)], customer=self.partner)
        order['data']['date_order'] = '2027-11-10 15:00:00'   # venta hecha cuando todavía estaba vigente
        self.assertEqual(len(self.env['pos.order'].create_from_ui([order])), 1)
        late = self.create_ui_order_data([(self.product, 1)], customer=self.partner)
        late['data']['date_order'] = '2027-11-19 15:00:00'    # venta hecha ya vencido
        with self.assertRaises(UserError):
            self.env['pos.order'].create_from_ui([late])

    def test_pos_loads_the_carabinero_fields(self):
        self._approve()
        fields_loaded = self.pos_session._loader_params_res_partner()['search_params']['fields']
        for name in ('carabinero_state', 'carabinero_valid_until', 'carabinero_email', 'carabinero_rank', 'carabinero_unit'):
            self.assertIn(name, fields_loaded)
        data = self.pos_session.get_pos_ui_res_partner_by_params({'domain': [('id', '=', self.partner.id)]})
        self.assertEqual(data[0]['carabinero_state'], 'active')
        self.assertTrue(fields.Date.to_string(data[0]['carabinero_valid_until']))

    # --- regla por producto: aptos para público general vs. solo Carabineros ---

    def _sell_products(self, products, customer):
        order = self.create_ui_order_data([(p, 1) for p in products], customer=customer)
        return self.env['pos.order'].create_from_ui([order])

    def test_products_are_carabineros_only_by_default(self):
        new = self.create_product('Gorra', self.categ_basic, 5.0, 2)
        self.assertFalse(new.carabinero_public_sale)
        self.assertFalse(new.product_tmpl_id.carabinero_public_sale)

    def test_public_products_sell_to_anyone_even_without_customer(self):
        self.assertEqual(len(self._sell_products([self.public_product], False)), 1)
        self.assertEqual(len(self._sell_products([self.public_product], self.partner)), 1)  # cliente no inscrito

    def test_mixed_order_needs_an_active_carabinero(self):
        with self.assertRaises(UserError):
            self._sell_products([self.public_product, self.product], False)
        with self.assertRaises(UserError):
            self._sell_products([self.public_product, self.product], self.partner)  # no inscrito
        self._approve()
        self.assertEqual(len(self._sell_products([self.public_product, self.product], self.partner)), 1)

    def test_error_names_only_the_restricted_products(self):
        with self.assertRaises(UserError) as cm:
            self._sell_products([self.public_product, self.product], self.partner)
        self.assertIn('Polera', str(cm.exception))
        self.assertNotIn('Calcetines', str(cm.exception))

    def test_tip_and_discount_lines_do_not_make_a_public_sale_restricted(self):
        tip = self.config.tip_product_id
        if tip:
            order = self.create_ui_order_data([(self.public_product, 1), (tip, 1)], customer=False)
            self.assertEqual(len(self.env['pos.order'].create_from_ui([order])), 1)
        order = self.create_ui_order_data([(self.public_product, 2)], customer=False)
        discount = self.create_product('Descuento', self.categ_basic, -1.0, 0)
        order['data']['lines'].append([0, 0, dict(order['data']['lines'][0][2], product_id=discount.id, price_unit=-1.0, qty=1)])
        self.assertEqual(len(self.env['pos.order'].create_from_ui([order])), 1)

    def test_requirement_off_ignores_product_flags(self):
        self.config.carabinero_required = False
        self.assertEqual(len(self._sell_products([self.product], False)), 1)

    def test_pos_loads_the_product_flag(self):
        self.assertIn('carabinero_public_sale', self.pos_session._loader_params_product_product()['search_params']['fields'])
        data = self.pos_session.get_pos_ui_product_product_by_params({'domain': [('id', 'in', (self.product + self.public_product).ids)]})
        flags = {d['id']: d['carabinero_public_sale'] for d in data}
        self.assertEqual(flags, {self.product.id: False, self.public_product.id: True})

    def test_bulk_server_actions_flip_the_flag(self):
        templates = self.product.product_tmpl_id + self.public_product.product_tmpl_id
        self.env.ref('dros_carabineros.action_product_mark_public').with_context(
            active_model='product.template', active_ids=templates.ids).run()
        self.assertTrue(all(templates.mapped('carabinero_public_sale')))
        self.env.ref('dros_carabineros.action_product_mark_carabinero_only').with_context(
            active_model='product.template', active_ids=templates.ids).run()
        self.assertFalse(any(templates.mapped('carabinero_public_sale')))
