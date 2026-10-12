
#Sale schemas for request validation and response serialization.

from marshmallow import Schema, fields, validate, ValidationError, post_load

class SaleItemSchema(Schema):
    id = fields.Int()
    product_id = fields.Int()
    product_name = fields.Str()
    quantity = fields.Int()
    selling_price = fields.Decimal(places=2)
    subtotal = fields.Decimal(places=2)
    created_at = fields.DateTime()


class SaleItemCreateSchema(Schema):
    product_id = fields.Int(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))
    selling_price = fields.Decimal(required=True, validate=validate.Range(min=0))


class SaleSchema(Schema):
    id = fields.Int()
    invoice_number = fields.Str()
    customer_name = fields.Str(allow_none=True)
    user_id = fields.Int()
    username = fields.Str()
    total_amount = fields.Decimal(places=2)
    discount_amount = fields.Decimal(places=2)
    tax_amount = fields.Decimal(places=2)
    final_amount = fields.Decimal(places=2)
    payment_method = fields.Str()
    payment_amount = fields.Decimal(places=2)
    change_amount = fields.Decimal(places=2)
    payment_reference = fields.Str(allow_none=True)
    status = fields.Str()
    notes = fields.Str(allow_none=True)
    item_count = fields.Int()
    total_items = fields.Int()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
    items = fields.List(fields.Nested(SaleItemSchema), required=False)


class SaleCreateSchema(Schema):
    items = fields.List(
        fields.Nested(SaleItemCreateSchema),
        required=True,
        validate=validate.Length(min=1),
    )
    customer_name = fields.Str(required=False, allow_none=True)
    payment_method = fields.Str(
        required=True,
        validate=validate.OneOf(['cash', 'gcash']),
    )
    payment_amount = fields.Decimal(required=True, validate=validate.Range(min=0))
    discount = fields.Decimal(required=False, missing=0, validate=validate.Range(min=0))
    notes = fields.Str(required=False, allow_none=True)
    payment_reference = fields.Str(required=False, allow_none=True)

    @post_load
    def validate_payment(self, data, **kwargs):
        total = sum(item['quantity'] * item['selling_price'] for item in data['items'])
        discount = data.get('discount', 0)
        final_amount = total - discount
        if final_amount < 0:
            raise ValidationError("Discount cannot exceed total amount")
        if data['payment_amount'] < final_amount:
            raise ValidationError(
                f"Payment amount must be greater than or equal to total amount (₱{final_amount})"
            )

        #GCash requires a 3-digit reference number
        method = data.get('payment_method')
        ref = (data.get('payment_reference') or '').strip()

        if method == 'gcash':
            if not ref:
                raise ValidationError(
                    "GCash reference number (last 3 digits) is required"
                )
            if not ref.isdigit():
                raise ValidationError(
                    "GCash reference number must contain only digits"
                )
            if len(ref) != 3:
                raise ValidationError(
                    "GCash reference number must be exactly 3 digits"
                )
            data['payment_reference'] = ref
        else:
            #Cash: no reference
            data['payment_reference'] = None

        return data