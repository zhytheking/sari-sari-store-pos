#Product schemas for request validation and response serialization.
from marshmallow import Schema, fields, validate, ValidationError, post_load


class ProductSchema(Schema):
    #Product response schema
    id = fields.Int()
    name = fields.Str()
    description = fields.Str(allow_none=True)
    barcode = fields.Str(allow_none=True)
    category_id = fields.Int(allow_none=True)
    category_name = fields.Str(allow_none=True)
    purchase_price = fields.Decimal(places=2)
    selling_price = fields.Decimal(places=2)
    stock_quantity = fields.Int()
    min_stock_level = fields.Int()
    unit = fields.Str()
    tax_rate = fields.Decimal(places=2)
    is_active = fields.Bool()
    is_low_stock = fields.Bool()
    stock_type = fields.Str()
    stock_icon = fields.Str()
    stock_color = fields.Str()
    stock_label = fields.Str()
    product_image = fields.Str(allow_none=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class ProductCreateSchema(Schema):
    #Product creation schema
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    description = fields.Str(required=False, allow_none=True)
    barcode = fields.Str(required=False, allow_none=True, validate=validate.Length(max=50))
    category_id = fields.Int(required=False, allow_none=True)
    purchase_price = fields.Decimal(required=True, validate=validate.Range(min=0))
    selling_price = fields.Decimal(required=True, validate=validate.Range(min=0))
    stock_quantity = fields.Int(required=False, missing=0, validate=validate.Range(min=0))
    min_stock_level = fields.Int(required=False, missing=10, validate=validate.Range(min=0))
    unit = fields.Str(required=False, missing='pc', validate=validate.Length(max=20))
    tax_rate = fields.Decimal(required=False, missing=0, validate=validate.Range(min=0, max=100))
    stock_type = fields.Str(required=False, missing='regular', 
                           validate=validate.OneOf(['regular', 'premium', 'discount', 'new_arrival', 'limited']))
    product_image = fields.Str(required=False, allow_none=True)
    
    @post_load
    def validate_prices(self, data, **kwargs):
        if data.get('selling_price', 0) < data.get('purchase_price', 0):
            raise ValidationError("Selling price must be greater than or equal to purchase price")
        return data


class ProductUpdateSchema(Schema):
    #Product update schema
    name = fields.Str(required=False, validate=validate.Length(min=1, max=100))
    description = fields.Str(required=False, allow_none=True)
    barcode = fields.Str(required=False, allow_none=True, validate=validate.Length(max=50))
    category_id = fields.Int(required=False, allow_none=True)
    purchase_price = fields.Decimal(required=False, validate=validate.Range(min=0))
    selling_price = fields.Decimal(required=False, validate=validate.Range(min=0))
    stock_quantity = fields.Int(required=False, validate=validate.Range(min=0))
    min_stock_level = fields.Int(required=False, validate=validate.Range(min=0))
    unit = fields.Str(required=False, validate=validate.Length(max=20))
    tax_rate = fields.Decimal(required=False, validate=validate.Range(min=0, max=100))
    is_active = fields.Bool(required=False)
    stock_type = fields.Str(required=False, validate=validate.OneOf(['regular', 'premium', 'discount', 'new_arrival', 'limited']))
    product_image = fields.Str(required=False, allow_none=True)


class CategorySchema(Schema):
    #Category response schema
    id = fields.Int()
    name = fields.Str()
    description = fields.Str(allow_none=True)
    product_count = fields.Int()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class CategoryCreateSchema(Schema):
    #Category creation schema
    name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    description = fields.Str(required=False, allow_none=True)


class InventoryAdjustmentSchema(Schema):
    #Inventory adjustment schema
    product_id = fields.Int(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))
    adjustment_type = fields.Str(required=True, validate=validate.OneOf(['add', 'subtract', 'set']))
    reason = fields.Str(required=True, validate=validate.Length(min=1))
    note = fields.Str(required=False, allow_none=True)


class StockTransferSchema(Schema):
    #Stock transfer schema
    from_product_id = fields.Int(required=True)
    to_product_id = fields.Int(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))
    reason = fields.Str(required=True, validate=validate.Length(min=1))
    note = fields.Str(required=False, allow_none=True)
