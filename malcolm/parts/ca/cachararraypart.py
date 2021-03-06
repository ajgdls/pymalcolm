from cothread import catools

from malcolm.parts.ca.capart import CAPart, capart_takes
from malcolm.vmetas import StringMeta


@capart_takes()
class CACharArrayPart(CAPart):
    """Defines a part which connects to a pv via channel access DBR_CHAR_STR"""

    def create_meta(self, description):
        return StringMeta("meta", description)

    def get_datatype(self):
        return catools.DBR_CHAR_STR
