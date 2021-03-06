import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import setup_malcolm_paths

import unittest
from mock import Mock, patch

from malcolm.core.method import takes, REQUIRED
from malcolm.vmetas import StringMeta
from malcolm.core.collection import make_collection, split_into_sections, \
    with_takes_from, substitute_params, make_block_instance, call_with_map


class TestCollection(unittest.TestCase):

    @patch("malcolm.core.collection.make_block_instance")
    def test_make_collection(self, mock_make):
        yaml = """
parameters.string:
    name: something
    description: my description

parts.ca.CADoublePart:
    pv: $(something)
"""
        collection = make_collection(yaml)
        process = Mock()
        blocks = collection(dict(name="boo", something="mypv"), process)
        mock_make.assert_called_once_with(
            "boo", process, {}, {"ca.CADoublePart": {"pv": "mypv"}})
        self.assertEqual(blocks, [mock_make.return_value])

    def test_split_into_sections(self):
        ds = {"parameters.string": {"name": "something"},
              "controllers.ManagerController": None}
        expected = dict(
            parameters={"string": {"name": "something"}},
            controllers={"ManagerController": None},
            parts={},
            collections={})
        self.assertEqual(split_into_sections(ds), expected)

    def test_with_takes_from(self):
        parameters = {"string": {"name": "something", "description": ""}}
        @with_takes_from(parameters, include_name=True)
        def f():
            pass
        elements = f.Method.takes.elements
        self.assertEquals(len(elements), 2)
        self.assertEquals(list(elements), ["name", "something"])


    def test_with_takes_from_no_name(self):
        parameters = {"string": {"name": "something", "description": ""}}
        @with_takes_from(parameters, include_name=False)
        def f():
            pass
        elements = f.Method.takes.elements
        self.assertEquals(len(elements), 1)
        self.assertEquals(list(elements), ["something"])

    def test_substitute_params(self):
        d = {"name": "$(name):pos", "exposure": 1.0}
        params = {"name": "me"}
        substitute_params(d, params)
        expected = {"name": "me:pos", "exposure": 1.0}
        self.assertEqual(d, expected)

    def test_make_block_instance(self):
        # TODO: needs new controller and part stuff
        pass

    def test_call_with_map(self):
        @takes("desc", StringMeta("description"), REQUIRED)
        def f(params, *args):
            return 2

        d = dict(desc="my name")
        CAPart = Mock(wraps=f)
        ca = Mock(CAPart=CAPart)
        parts = Mock(ca=ca)

        result = call_with_map(parts, "ca.CAPart", d, 43)
        self.assertEqual(result, 2)
        self.assertEqual(CAPart.call_count, 1)
        call_args = CAPart.call_args_list[0][0]
        self.assertEqual(len(call_args), 2)
        self.assertEqual(call_args[1], 43)
        self.assertEqual(call_args[0].desc, "my name")

if __name__ == "__main__":
    unittest.main(verbosity=2)
