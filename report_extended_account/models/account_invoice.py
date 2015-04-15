# -*- coding: utf-8 -*-
from openerp import models, fields, api


class account_invoice(models.Model):
    _inherit = 'account.invoice'

    splitter_invoice_id = fields.Many2one(
        'account.invoice', 'Splitter Invoice', copy=False,
        help='This field contain the invoice that was splitted, generating another invoice.')
    splitted_invoice_id = fields.Many2one(
        'account.invoice', 'Generated Invoice', copy=False,
        help='This field contain the invoice generated by splitting the current one.')

    @api.multi
    def invoice_print(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        assert len(self) == 1, 'This option should only be used for a single id at a time.'
        report_obj = self.env['ir.actions.report.xml']
        report_name = report_obj.get_report_name('account.invoice', self.ids)
        self.sent = True
        return self.env['report'].get_action(self, report_name)

    @api.multi
    def split_invoice(self, lines_to_split):
        '''
        Split the invoice when the lines exceed the maximum lines_to_split
        '''
        res = {}
        for line in self:
            new_invoice = False
            if not lines_to_split:
                return

            if line.type in ["out_invoice", "out_refund"]:

                if len(line.invoice_line) > lines_to_split:
                    lst = []
                    invoice = line.read(
                        ['name', 'type', 'number', 'reference', 'comment',
                         'date_due', 'partner_id', 'partner_contact',
                         'partner_insite', 'partner_ref', 'payment_term',
                         'account_id', 'currency_id', 'invoice_line',
                         'tax_line', 'journal_id', 'period_id',
                         'company_id', 'origin', 'user_id'])[0]
                    invoice.update({
                        'state': 'draft',
                        'number': False,
                        'invoice_line': [],
                        'tax_line': [],
                        'splitter_invoice_id': line.id,
                    })
                    # take the id part of the tuple returned for many2one
                    # fields
                    for field in ('partner_id', 'account_id', 'currency_id',
                                  'payment_term', 'journal_id', 'period_id',
                                  'company_id', 'user_id'):
                        invoice[field] = invoice[field] and invoice[field][0]

                    new_invoice = line.create(invoice)
                    lst = line.invoice_line
                    lst = lst[lines_to_split:]

                    for il in lst:
                        line.env['account.invoice.line'].browse(il.id).write(
                            {'invoice_id': new_invoice.id})

                    line.write(
                        {'splitted_invoice_id': new_invoice.id})

                    line.button_compute(set_total=True)
            res[line.id] = new_invoice

        return res

    # This is the first action on the invoice
    @api.multi
    def action_date_assign(self):
        report_obj = self.env['ir.actions.report.xml']
        report = report_obj.with_context(ignore_state=True).get_report(
            'account.invoice', self.ids)
        if report and report.account_invoice_split_invoice and report.account_invoice_lines_to_split:
            self.split_invoice(report.account_invoice_lines_to_split)
        return super(account_invoice, self).action_date_assign()

    def confirm_paid(self, cr, uid, ids, context=None):
        res = super(account_invoice, self).confirm_paid(
            cr, uid, ids, context=context)
        self.check_sale_order_paid(cr, uid, ids, context=context)
        return res

    def check_sale_order_paid(self, cr, uid, ids, context=None):
        '''Esta funcion la hacemos para verificar si toda la orden de venta fue pagada en el caso de
         'pago antes de la entrega' porque el problema es el siguiente, de manera original openerp
         genera una factura que queda vinculada por el subflow avisando cuando fue pagada a la orden de venta, 
         el problema es que en este caso tendriamos mas de una factura ligada, por eso el chequeo hay que hacerlo aparte
         '''
        sale_order_obj = self.pool.get('sale.order')
        so_ids = sale_order_obj.search(
            cr, uid, [('invoice_ids', 'in', ids)], context=context)
        for so in sale_order_obj.browse(cr, uid, so_ids, context=context):
            if so.order_policy == 'prepaid' and so.invoiced:
                so.signal_workflow('subflow.paid')
        return True
