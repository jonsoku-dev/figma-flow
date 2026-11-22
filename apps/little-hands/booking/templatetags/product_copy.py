"""Service copy for all Django render paths, including error pages without a request."""
import json
from pathlib import Path
from django import template

register = template.Library()
PRODUCT = json.loads((Path(__file__).resolve().parents[1] / 'product.json').read_bytes())


@register.simple_tag
def booking_brand():
    return PRODUCT['serviceName']


@register.simple_tag
def booking_payment():
    return PRODUCT['paymentDisclosure']
