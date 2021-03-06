import functools
from collections import OrderedDict

from malcolm.core import Controller,  Post, Subscribe, Return, Method, takes, \
    Serializable


@takes()
class ClientController(Controller):
    """Sync a local block with a given remote block"""
    REMOTE_BLOCKS_ID = 0
    BLOCK_ID = 1

    def __init__(self, process, block, block_name):
        """
        Args:
            process (Process): The process this should run under
            block (Block): The local block we should be controlling
            block_name (str): The local block's name
        """
        super(ClientController, self).__init__(block=block, process=process,
                                               block_name=block_name)
        request = Subscribe(
            None, self, [self.process.name, "remoteBlocks", "value"])
        request.set_id(self.REMOTE_BLOCKS_ID)
        self.process.q.put(request)

    def put(self, response):
        """We don't have a queue as no thread to service, but act like one"""
        if response.id_ == self.REMOTE_BLOCKS_ID:
            if response.value and self.block.name in response.value:
                # process knows how to get to a block
                self._subscribe_to_block(self.block.name)
        elif response.id_ == self.BLOCK_ID:
            with self.block.lock:
                self.log_debug(response)
                for change in response.changes:
                    if change[0] == []:
                        # update root
                        self._regenerate_block(change[1])
                    else:
                        # just pass it to the block to handle
                        self.block.update(change)

    def _regenerate_block(self, d):
        children = OrderedDict()
        for k, v in d.items():
            if k == "typeid":
                continue
            child = Serializable.from_dict(v)
            children[k] = child
            if isinstance(child, Method):
                # calling method forwards to server
                child.set_function(
                    functools.partial(self.call_server_method, k))
        self.block.replace_children(children)

    def _subscribe_to_block(self, block_name):
        self.client_comms = self.process.get_client_comms(block_name)
        assert self.client_comms, \
            "Process doesn't know about block %s" % block_name
        request = Subscribe(None, self, [block_name], delta=True)
        request.set_id(self.BLOCK_ID)
        self.client_comms.q.put(request)

    def call_server_method(self, method_name, parameters, returns):
        """Call method_name on the server

        Args:
            method_name (str): Name of the method
            parameters (Map): Map of arguments to be called with
            returns (Map): Returns map to fill and return
        """
        self.log_debug(dict(parameters))
        q = self.process.create_queue()
        request = Post(None, q,
                               [self.block.name, method_name], parameters)
        self.client_comms.q.put(request)
        response = q.get()
        assert isinstance(response, Return), \
            "Expected Return, got %s" % response.typeid
        if "typeid" in response.value:
            response.value.pop("typeid")
        returns.update(response.value)
        return returns
