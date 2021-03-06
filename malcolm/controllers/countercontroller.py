from malcolm.core import Controller, Attribute, takes
from malcolm.vmetas import NumberMeta


@takes()
class CounterController(Controller):

    def create_attributes(self):
        self.counter = Attribute(NumberMeta(description="A counter"))
        self.counter.meta.set_dtype('uint32')
        self.counter.set_put_function(self.counter.set_value)
        self.counter.set_value(0)
        yield "counter", self.counter

    @Controller.Resetting
    def do_reset(self):
        self.counter.set_value(0, notify=False)
        # Transition will do the notify for us

    @takes()
    def increment(self):
        self.counter.set_value(self.counter.value + 1)
