import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import setup_malcolm_paths

from collections import OrderedDict

import unittest
from mock import MagicMock, patch, call

from malcolm.wscomms.wsclientcomms import WSClientComms


class TestWSClientComms(unittest.TestCase):

    def setUp(self):
        self.p = MagicMock()

    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_init(self, ioloop_mock, connect_mock):
        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")

        self.assertEqual(self.p, self.WS.process)
        self.assertEqual("test/url", self.WS.url)
        self.assertEqual(ioloop_mock.current(), self.WS.loop)
        connect_mock.assert_called_once_with(self.WS.url, callback=self.WS.subscribe_server_blocks, on_message_callback=self.WS.on_message)
        self.assertEqual(connect_mock(), self.WS.conn)

    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_subscribe_initial(self, _, _2):
        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")
        self.WS.subscribe_server_blocks("conn")
        self.assertEqual(self.WS.loop.add_callback.call_count, 1)
        request = self.WS.loop.add_callback.call_args[0][1]
        self.assertEqual(request.id_, 0)
        self.assertEqual(request.typeid, "malcolm:core/Subscribe:1.0")
        self.assertEqual(request.endpoint, [".", "blocks", "value"])
        self.assertEqual(request.delta, False)

    @patch('malcolm.wscomms.wsclientcomms.Serializable')
    @patch('malcolm.wscomms.wsclientcomms.json')
    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_on_message(self, _, _1, json_mock, serializable_mock):
        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")

        message_dict = dict(name="TestMessage")
        json_mock.loads.return_value = message_dict

        response = MagicMock()
        response.id_ = 1
        serializable_mock.from_dict.return_value = response
        request_mock = MagicMock()
        self.WS.requests[1] = request_mock

        self.WS.on_message("TestMessage")

        json_mock.loads.assert_called_once_with("TestMessage",
                                                object_pairs_hook=OrderedDict)
        serializable_mock.from_dict.assert_called_once_with(message_dict)
        request_mock.response_queue.put.assert_called_once_with(response)

    @patch('malcolm.wscomms.wsclientcomms.json')
    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_on_message_logs_exception(self, _, _1, json_mock):
        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")
        self.WS.log_exception = MagicMock()
        exception = Exception()
        json_mock.loads.side_effect = exception

        self.WS.on_message("test")

        self.WS.log_exception.assert_called_once_with(exception)

    @patch('malcolm.wscomms.wsclientcomms.json')
    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_send_to_server(self, _, connect_mock, json_mock):
        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")
        json_mock.reset_mock()
        result_mock = MagicMock()
        connect_mock().result.return_value = result_mock
        dumps_mock = MagicMock()
        json_mock.dumps.return_value = dumps_mock

        request_mock = MagicMock()
        self.WS.send_to_server(request_mock)

        json_mock.dumps.assert_called_once_with(request_mock.to_dict())
        result_mock.write_message.assert_called_once_with(dumps_mock)

    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_start(self, ioloop_mock, _):
        loop_mock = MagicMock()
        ioloop_mock.current.return_value = loop_mock
        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")
        self.WS.process.spawn = MagicMock()
        self.WS.start()

        self.assertEqual([call(self.WS.send_loop), call(self.WS.loop.start)],
                         self.WS.process.spawn.call_args_list)

    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_stop(self, ioloop_mock, _):
        loop_mock = MagicMock()
        ioloop_mock.current.return_value = loop_mock

        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")
        self.WS.start()
        self.WS.stop()

        loop_mock.add_callback.assert_called_once_with(
            ioloop_mock.current().stop)
        self.WS.process.spawn.return_value.assert_not_called()

    @patch('malcolm.wscomms.wsclientcomms.websocket_connect')
    @patch('malcolm.wscomms.wsclientcomms.IOLoop')
    def test_wait(self, _, _2):
        spawnable_mocks = [MagicMock(), MagicMock()]
        timeout = MagicMock()

        self.WS = WSClientComms("TestWebSocket", self.p, "test/url")
        self.WS.process.spawn = MagicMock(side_effect=spawnable_mocks)
        self.WS.start()
        self.WS.wait(timeout)

        spawnable_mocks[0].wait.assert_called_once_with(timeout=timeout)
        spawnable_mocks[1].wait.assert_called_once_with(timeout=timeout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
