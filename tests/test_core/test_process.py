import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import setup_malcolm_paths

from collections import OrderedDict
# import logging
# logging.basicConfig(level=logging.DEBUG)

import unittest
from mock import MagicMock, call

# module imports
from malcolm.core.process import \
    Process, BlockChanged, BlockNotify, PROCESS_STOP, BlockAdd, BlockRespond, \
    BlockList
from malcolm.core.syncfactory import SyncFactory
from malcolm.core.request import Subscribe, Post, Get
from malcolm.core.response import Return, Update, Delta
from malcolm.core.attribute import Attribute
from malcolm.vmetas import StringArrayMeta


class TestProcess(unittest.TestCase):

    def test_init(self):
        s = MagicMock()
        p = Process("proc", s)
        s.create_queue.assert_called_once_with()
        self.assertEqual(p.q, s.create_queue.return_value)

    def test_add_block(self):
        p = Process("proc", MagicMock())
        b = MagicMock()
        p.add_block("myblock", b)
        b.set_parent.assert_called_once_with(p, "myblock")
        req = p.q.put.call_args[0][0]
        self.assertEqual(req.block, b)

    def test_add_block_calls_handle(self):
        s = SyncFactory("sched")
        p = Process("proc", s)
        b = MagicMock()
        b.name = "myblock"
        p.add_block("myblock", b)
        p.start()
        p.stop()
        b.set_parent.assert_called_once_with(p, "myblock")
        self.assertEqual(len(p._blocks), 2)
        self.assertEqual(p._blocks, dict(myblock=b, proc=p.process_block))

    def test_starting_process(self):
        s = SyncFactory("sched")
        p = Process("proc", s)
        b = MagicMock()
        b.name = "myblock"
        p._handle_block_add(BlockAdd(b))
        self.assertEqual(p._blocks, dict(myblock=b))
        p.start()
        request = Post(MagicMock(), MagicMock(), ["myblock", "foo"])
        p.q.put(request)
        # wait for spawns to have done their job
        p.stop()
        b.handle_request.assert_called_once_with(request)

    def test_error(self):
        s = SyncFactory("sched")
        p = Process("proc", s)
        p.log_exception = MagicMock()
        p.start()
        request = MagicMock()
        request.endpoint = ["anything"]
        p.q.put(request)
        p.stop()
        p.log_exception.assert_called_once_with("Exception while handling %s",
                                                request)

    def test_spawned_adds_to_other_spawned(self):
        s = MagicMock()
        p = Process("proc", s)
        spawned = p.spawn(callable, "fred", a=4)
        self.assertEqual(spawned, s.spawn.return_value)
        self.assertEqual(p._other_spawned, [spawned])
        s.spawn.assert_called_once_with(callable, "fred", a=4)

    def test_get(self):
        p = Process("proc", MagicMock())
        block = MagicMock()
        block.name = "myblock"
        block.to_dict = MagicMock(
            return_value={"path_1": {"path_2": {"attr": "value"}}})
        request = Get(MagicMock(), MagicMock(), ["myblock", "path_1", "path_2"])
        p._handle_block_add(BlockAdd(block))
        p.q.get = MagicMock(side_effect=[request, PROCESS_STOP])

        p.recv_loop()

        response = request.response_queue.put.call_args[0][0]
        self.assertIsInstance(response, Return)
        self.assertEquals({"attr": "value"}, response.value)

    def test_block_respond(self):
        p = Process("proc", MagicMock())
        p.q.put = MagicMock()
        response = MagicMock()
        response_queue = MagicMock()
        p.block_respond(response, response_queue)
        block_response = p.q.put.call_args[0][0]
        self.assertEquals(block_response.response, response)
        self.assertEquals(block_response.response_queue, response_queue)

    def test_block_respond_triggers_response(self):
        p = Process("proc", MagicMock())
        response = MagicMock()
        response_queue = MagicMock()
        p.q.get = MagicMock(
            side_effect=[BlockRespond(response, response_queue), PROCESS_STOP])

        p.recv_loop()

        response_queue.put.assert_called_once_with(response)

    def test_make_process_block(self):
        p = Process("proc", MagicMock())
        p_block = p.process_block
        self.assertEquals(p.name, p_block.name)
        self.assertEquals(Attribute, type(p_block.blocks))
        self.assertEquals(StringArrayMeta, type(p_block.blocks.meta))
        self.assertEquals("blocks", p_block.blocks.name)
        self.assertEquals("meta", p_block.blocks.meta.name)
        self.assertEquals("Blocks hosted by this Process",
                          p_block.blocks.meta.description)

    def test_update_block_list(self):
        p = Process("proc", MagicMock())
        p.q.reset_mock()
        p.update_block_list("cc", ["myblock"])
        request = BlockList(client_comms="cc", blocks=["myblock"])
        p.q.put.assert_called_once_with(request)
        self.assertEqual(p._client_comms, {})
        p._handle_block_list(request)
        self.assertEqual(p._client_comms, dict(cc=["myblock"]))
        self.assertEqual(p.process_block.remoteBlocks.value, ["myblock"])
        self.assertEqual(p.get_client_comms("myblock"), "cc")


class TestSubscriptions(unittest.TestCase):

    def test_on_changed(self):
        change = [["path"], "value"]
        s = MagicMock()
        p = Process("proc", s)
        s.reset_mock()
        p.on_changed(change, notify=False)
        p.q.put.assert_called_once_with(BlockChanged(change=change))

    def test_on_changed_with_notify(self):
        change = [["path"], "value"]
        s = MagicMock()
        p = Process("proc", s)
        s.reset_mock()
        p.on_changed(change)
        p.q.put.assert_has_calls([
            call(BlockChanged(change=change)),
            call(BlockNotify(name="path"))])

    def test_notify(self):
        s = MagicMock()
        p = Process("proc", s)
        s.reset_mock()
        p.notify_subscribers("block")
        p.q.put.assert_called_once_with(BlockNotify(name="block"))

    def test_subscribe(self):
        block = MagicMock(
            to_dict=MagicMock(
                return_value={"attr": "value", "inner": {"attr2": "other"}}))
        block.name = "block"
        p = Process("proc", MagicMock())
        sub_1 = Subscribe(
            MagicMock(), MagicMock(), ["block"], False)
        sub_2 = Subscribe(
            MagicMock(), MagicMock(), ["block", "inner"], True)
        p.q.get = MagicMock(side_effect=[sub_1, sub_2, PROCESS_STOP])

        p._handle_block_add(BlockAdd(block))
        p.recv_loop()

        self.assertEquals(OrderedDict(block=[sub_1, sub_2]),
                          p._subscriptions)
        response_1 = sub_1.response_queue.put.call_args[0][0]
        response_2 = sub_2.response_queue.put.call_args[0][0]
        self.assertEquals({"attr": "value", "inner": {"attr2": "other"}},
                          response_1.value)
        self.assertEquals([[[], {"attr2": "other"}]], response_2.changes)

    def test_deletions(self):
        block = MagicMock(
            to_dict=MagicMock(return_value={"attr": "value", "attr2": "other"}))
        block.name = "block"
        sub_1 = MagicMock()
        sub_1.endpoint = ["block"]
        sub_1.delta = False
        sub_2 = MagicMock()
        sub_2.endpoint = ["block"]
        sub_2.delta = True
        changes_1 = [["block", "attr"]]
        request_1 = BlockChanged(changes_1)
        request_2 = BlockNotify(block.name)
        s = MagicMock()
        p = Process("proc", s)
        p._subscriptions["block"] = [sub_1, sub_2]
        p.q.get = MagicMock(
            side_effect=[request_1, request_2, PROCESS_STOP])

        p._handle_block_add(BlockAdd(block))
        p.recv_loop()

        self.assertEqual(sub_1.response_queue.put.call_count, 1)
        self.assertEqual(sub_2.response_queue.put.call_count, 1)
        response_1 = sub_1.response_queue.put.call_args[0][0]
        response_2 = sub_2.response_queue.put.call_args[0][0]
        self.assertEquals({"attr2": "other"}, response_1.value)
        self.assertEquals([[["attr"]]], response_2.changes)

    def test_overlapped_changes(self):
        block = MagicMock(
            to_dict=MagicMock(return_value={"attr": "value", "attr2": "other"}))
        block.name = "block"
        sub_1 = MagicMock()
        sub_1.endpoint = ["block"]
        sub_1.delta = False
        sub_2 = MagicMock()
        sub_2.endpoint = ["block"]
        sub_2.delta = True
        changes_1 = [["block", "attr"], "changing_value"]
        changes_2 = [["block", "attr"], "final_value"]
        request_1 = BlockChanged(changes_1)
        request_2 = BlockChanged(changes_2)
        request_3 = BlockNotify(block.name)
        s = MagicMock()
        p = Process("proc", s)
        p._subscriptions["block"] = [sub_1, sub_2]
        p.q.get = MagicMock(
            side_effect=[request_1, request_2, request_3, PROCESS_STOP])

        p._handle_block_add(BlockAdd(block))
        p.recv_loop()

        self.assertEqual(sub_1.response_queue.put.call_count, 1)
        self.assertEqual(sub_2.response_queue.put.call_count, 1)
        response_1 = sub_1.response_queue.put.call_args[0][0]
        response_2 = sub_2.response_queue.put.call_args[0][0]
        self.assertEquals({"attr": "final_value", "attr2": "other"},
                          response_1.value)
        self.assertEquals(
            [[["attr"], "changing_value"], [["attr"], "final_value"]],
            response_2.changes)

    def test_partial_structure_subscriptions(self):
        block_1 = MagicMock(
            to_dict=MagicMock(
                return_value={"attr": "value", "inner": {"attr2": "value"}}))
        block_1.name = "block_1"
        block_2 = MagicMock(
            to_dict=MagicMock(return_value={"attr": "value"}))
        block_2.name = "block_2"

        sub_1 = MagicMock()
        sub_1.endpoint = ["block_1", "inner"]
        sub_1.delta = False
        sub_2 = MagicMock()
        sub_2.endpoint = ["block_1", "inner"]
        sub_2.delta = True

        changes_1 = [["block_1", "inner", "attr2"], "new_value"]
        changes_2 = [["block_1", "attr"], "new_value"]
        changes_3 = [["block_2", "attr"], "block_2_value"]
        request_1 = BlockChanged(changes_1)
        request_2 = BlockChanged(changes_2)
        request_3 = BlockChanged(changes_3)
        request_4 = BlockNotify(block_1.name)
        request_5 = BlockNotify(block_2.name)
        p = Process("proc", MagicMock())
        p.q.get = MagicMock(side_effect=[
            request_1, request_2, request_3, request_4, request_5,
            PROCESS_STOP])
        p._subscriptions["block_1"] = [sub_1, sub_2]

        p._handle_block_add(BlockAdd(block_1))
        p._handle_block_add(BlockAdd(block_2))
        p.recv_loop()

        response_1 = sub_1.response_queue.put.call_args[0][0]
        response_2 = sub_2.response_queue.put.call_args[0][0]
        self.assertEquals({"attr2": "new_value"}, response_1.value)
        self.assertEquals([[["attr2"], "new_value"]], response_2.changes)

    def test_multiple_notifies_single_change(self):
        block_1 = MagicMock(
            to_dict=MagicMock(return_value={"attr": "initial_value"}))
        block_1.name = "block_1"
        block_2 = MagicMock(
            to_dict=MagicMock(return_value={"attr2": "initial_value"}))
        block_2.name = "block_2"
        sub_1 = MagicMock()
        sub_1.endpoint = ["block_1"]
        sub_1.delta = False
        sub_2 = MagicMock()
        sub_2.endpoint = ["block_1"]
        sub_2.delta = True
        sub_3 = MagicMock()
        sub_3.endpoint = ["block_2"]
        sub_3.delta = False
        sub_4 = MagicMock()
        sub_4.endpoint = ["block_2"]
        sub_4.delta = True
        change_1 = [["block_1", "attr"], "final_value"]
        change_2 = [["block_2", "attr2"], "final_value"]
        request_1 = BlockNotify("block_1")
        request_2 = BlockChanged(change_1)
        request_3 = BlockChanged(change_2)
        request_4 = BlockNotify("block_1")
        request_5 = BlockNotify("block_1")
        request_6 = BlockNotify("block_2")
        p = Process("proc", MagicMock())
        p.q.get = MagicMock(side_effect=[request_1, request_2, request_3,
                                         request_4, request_5, request_6,
                                         PROCESS_STOP])
        p.q.put = MagicMock(side_effect=p.q.put)
        p._subscriptions["block_1"] = [sub_1, sub_2]
        p._subscriptions["block_2"] = [sub_3, sub_4]
        p._handle_block_add(BlockAdd(block_1))
        p._handle_block_add(BlockAdd(block_2))

        p.recv_loop()

        call_list = sub_1.response_queue.put.call_args_list
        self.assertEquals(1, len(call_list))
        self.assertIsInstance(call_list[0][0][0], Update)
        self.assertEquals({"attr": "final_value"}, call_list[0][0][0].value)

        call_list = sub_2.response_queue.put.call_args_list
        self.assertEquals(1, len(call_list))
        self.assertIsInstance(call_list[0][0][0], Delta)
        self.assertEquals([[["attr"], "final_value"]],
                          call_list[0][0][0].changes)

        call_list = sub_3.response_queue.put.call_args_list
        self.assertEquals(1, len(call_list))
        self.assertIsInstance(call_list[0][0][0], Update)
        self.assertEquals({"attr2": "final_value"}, call_list[0][0][0].value)

        call_list = sub_4.response_queue.put.call_args_list
        self.assertEquals(1, len(call_list))
        self.assertIsInstance(call_list[0][0][0], Delta)
        self.assertEquals([[["attr2"], "final_value"]],
                          call_list[0][0][0].changes)

if __name__ == "__main__":
    unittest.main(verbosity=2)
