#Sale schemas for request validation and response serialization.

from marshmallow import (
    Schema, fields, validate, ValidationError, post_load, EXCLUDE,
)


class SaleItemSchema(Schema):
    """Output schema for a single sale line item."""
    id = fields.Int()
    product_id = fields.Int()
    product_name = fields.Str()
    quantity = fields.Int()
    selling_price = fields.Decimal(places=2)
    subtotal = fields.Decimal(places=2)
    created_at = fields.DateTime()


class SaleItemCreateSchema(Schema):
    """
    Input schema for a single sale line item.

    `selling_price` is accepted for backward compatibility but
    IGNORED. The server determines the actual price from the
    products table to prevent price spoofing.

    `unknown = EXCLUDE` means extra fields (like selling_price)
    are silently dropped instead of causing a validation error.
    """
    class Meta:
        unknown = EXCLUDE

    product_id = fields.Int(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))


class SaleSchema(Schema):
    """Output schema for a complete sale."""
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
    """
    Input schema for creating a sale.

    Price validation is deferred to the route, which computes
    totals from server-side product prices (not client input).

    `unknown = EXCLUDE` means extra fields are dropped silently.
    """
    class Meta:
        unknown = EXCLUDE

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
        """Validate input that does NOT depend on server-side prices."""
        discount = data.get('discount', 0)
        if discount < 0:
            raise ValidationError("Discount cannot be negative")

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
            data['payment_reference'] = None

        return data
