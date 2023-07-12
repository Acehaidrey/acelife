import yaml


class TransactionRecord:
    TRANSACTION_ID = 'transaction_id'
    PROVIDER = 'provider'
    STORE = 'store'
    ORDER_DATE = 'order_date'
    PAYMENT_TYPE = 'payment_type'
    SUBTOTAL = 'subtotal'  # not including any other fees - before all of them
    TIP = 'tip'
    TAX = 'tax'
    DELIVERY_CHARGE = 'delivery_fee'
    TOTAL_BEFORE_FEES = 'total_before_fees'
    SERVICE_FEE = 'service_fee'
    MARKETING_FEE = 'marketing_fee'
    ADJUSTMENT_FEE = 'adjustment_fee'
    MERCHANT_PROCESSING_FEE = 'merchant_processing_fee'
    COMMISSION_FEE = 'commission_fee'
    TOTAL_AFTER_FEES = 'total_after_fees'
    NOTES = 'notes'

    COLUMN_TYPE_MAPPING = {
        PROVIDER: 'string',
        STORE: 'string',
        TRANSACTION_ID: 'string',
        ORDER_DATE: 'timestamp',
        PAYMENT_TYPE: 'string',
        SUBTOTAL: 'float',
        TIP: 'float',
        TAX: 'float',
        DELIVERY_CHARGE: 'float',
        SERVICE_FEE: 'float',
        MARKETING_FEE: 'float',
        ADJUSTMENT_FEE: 'float',
        MERCHANT_PROCESSING_FEE: 'float',
        COMMISSION_FEE: 'float',
        TOTAL_BEFORE_FEES: 'float',
        TOTAL_AFTER_FEES: 'float',
        NOTES: 'string',
    }

    @classmethod
    def get_column_names(cls):
        return list(cls.COLUMN_TYPE_MAPPING.keys())

    @classmethod
    def generate_yaml_config(cls, provider_name, version_tuples=None):
        config = {
            provider_name: {
                'column_mapping': [],
                'version_mappings': []
            }
        }

        # Add column mappings for the current column_type_mapping
        for column_name, column_type in cls.COLUMN_TYPE_MAPPING.items():
            config[provider_name]['column_mapping'].append({
                'provider_column': 'PLACEHOLDER',
                'mapped_column': column_name
            })

        # Add version mappings if needed
        if version_tuples: # (date, col_name, mapped_col)
            for version_tup in version_tuples:
                config[provider_name]['version_mappings'].append({
                    'version': version_tup[0],
                    'column_mapping': {
                        'provider_column': version_tup[1],
                        'mapped_column': version_tup[2]
                    }
                })

        # Convert the config to YAML string
        yaml_str = yaml.safe_dump(config, default_flow_style=False)
        return yaml_str
