"""Diagnose one bounded normal-client broker-history response without sync writes."""
import hashlib
import json
import sys
from datetime import UTC,datetime
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from open_composer.adapters.broker.alpaca_paper import (
    _get_broker_orders,_normalize_broker_order,_trading_client,_validate_normalized_broker_order,
)
OUT=ROOT/'reports/research/program/paper-continuity-20261014/legacy-sync-readonly.json'
assert not OUT.exists()
from open_composer.cli import _load_env
_load_env()
client=_trading_client();start=datetime.now(UTC).isoformat()
orders=_get_broker_orders(client,include_closed=True)
invalid=[];valid=0
for ordinal,order in enumerate(orders):
    normalized=_normalize_broker_order(order)
    try:_validate_normalized_broker_order(normalized);valid+=1
    except Exception as exc:
        if len(invalid)<10:
            raw=order.model_dump()if hasattr(order,'model_dump')else vars(order)
            invalid.append({'response_ordinal':ordinal,'object_class':type(order).__name__,
                'order_id_sha256':hashlib.sha256(normalized['id'].encode()).hexdigest(),
                'client_order_id_sha256':hashlib.sha256(normalized['client_order_id'].encode()).hexdigest(),
                'error':str(exc),'normalized':{k:v for k,v in normalized.items()if k not in ['id','client_order_id']},
                'side_attribute_present':hasattr(order,'side'),'side_attribute_type':type(getattr(order,'side',None)).__name__,
                'SDK_field_names':sorted(raw),'SDK_side':str(raw.get('side')),'SDK_order_class':str(raw.get('order_class')),
                'SDK_legs_count':len(raw.get('legs')or[]),
            })
result={'started_UTC':start,'finished_UTC':datetime.now(UTC).isoformat(),'readonly':True,
        'broker_calls':['get_orders(status=ALL,limit=500,direction=DESC)'],
        'response_orders':len(orders),'valid_normalizations':valid,'invalid_count':len(orders)-valid,
        'invalid_first10':invalid,'sync_paper_orders_called':False,'production_writes':0,'broker_writes':0,
        'local_sleeve_fills_not_reconstructed':True}
OUT.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k!='invalid_first10'}))
