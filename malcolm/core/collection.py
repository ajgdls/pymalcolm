from collections import OrderedDict

from ruamel import yaml

import malcolm.parameters
import malcolm.controllers
import malcolm.parts
import malcolm.collections
from malcolm.core.method import takes, REQUIRED
from malcolm.vmetas import StringMeta
from malcolm.compat import base_string


def make_collection(text):
    """Make a collection function that will create a list of blocks

    Args:
        text (str): YAML text specifying parameters, controllers, parts and
            other collections to be instantiated

    Returns:
        function: A collection function decorated with @takes. This can be
            used in other collections or instantiated by the process. If the
            YAML text specified controllers or parts then a block instance
            with the given name will be instantiated. If there are any
            collections listed then they will be called. All created blocks by
            this or any sub collection will be returned
    """
    ds = yaml.load(text, Loader=yaml.RoundTripLoader)

    sections = split_into_sections(ds)

    # If we have parts then check we have a maximum of one controller
    if sections["controllers"] or sections["parts"]:
        num_controllers = len(sections["controllers"])
        assert num_controllers in (0, 1), \
            "Expected 0 or 1 controller with parts, got %s" % num_controllers
        # We will be creating a block here, so we need a name
        include_name = True
    else:
        # No name needed as just a collection of other collections
        include_name = False

    @with_takes_from(sections["parameters"], include_name)
    def collection(params, process):
        substitute_params(sections, params)
        ret = []

        # If told to make a block instance from controllers and parts
        if sections["controllers"] or sections["parts"]:
            ret.append(make_block_instance(
                params["name"], process,
                sections["controllers"], sections["parts"]))

        # It we have any other collections
        for name, d in sections["collections"].items():
            ret += call_with_map(malcolm.collections, name, d, process)

        return ret

    return collection


def split_into_sections(ds):
    """Split a dictionary into parameters, controllers, parts and collections

    Args:
        ds (dict): Dictionary of section: params. E.g.
            {
                "parameters.string": {"name": "something"},
                "controllers.ManagerController": None
             }

    Returns:
        dict: dictionary containing sections sub dictionaries. E.g.
            {
                "parameters": {
                    "string": {"name": "something"}
                },
                "controllers": {
                    "ManagerController": None
                }
            }
    """
    # First separate them into their relevant sections
    sections = dict(parameters={}, controllers={}, parts={}, collections={})
    for name, d in ds.items():
        section, subsection = name.split(".", 1)
        if section in sections:
            sections[section][subsection] = d
        else:
            raise ValueError("Unknown section name %s" % name)

    return sections


def with_takes_from(parameters, include_name):
    """Create an @takes decorator from parameters dict.

    Args:
        parameters (dict): Parameters sub dictionary. E.g.
            {"string": {"name": "something"}}
        include_name (bool): If True then put a "name" meta first

    Returns:
        function: Decorator that will set a "Method" attribute on the callable
            with the arguments it should take
    """
    # find all the Takes objects and create them
    if include_name:
        takes_arguments = [
            "name", StringMeta("Name of the created block"), REQUIRED]
    else:
        takes_arguments = []
    for name, d in parameters.items():
        takes_arguments += call_with_map(malcolm.parameters, name, d)
    return takes(*takes_arguments)


def substitute_params(d, params):
    """Substitute a dictionary in place with $(attr) macros in it with values
    from params

    Args:
        d (dict): Input dictionary {string key: any value}. E.g.
            {"name": "$(name):pos", "exposure": 1.0}
        params (Map or dict): Values to substitute. E.g. Map of
            {"name": "me"}

    After the call the dictionary will look like:
        {"name": "me:pos", "exposure": 1.0}
    """
    for p in params:
        for k, v in d.items():
            search = "$(%s)" % p
            if isinstance(v, base_string):
                d[k] = v.replace(search, params[p])
            elif isinstance(v, dict):
                substitute_params(v, params)


def make_block_instance(name, process, controllers_d, parts_d):
    """Make a block subclass from a series of parts.* and controllers.* dicts

    Args:
        name (str): The name of the resulting block instance
        process (Process): The process it should be attached to
        controllers_d (dict): Controllers sub dictionary. E.g.
            {"ManagerController": None}
        parts_d (dict): Parts sub dictionary. E.g.
            {"ca.CADoublePart": {"pv": "MY:PV:STRING"}}

    Returns:
        Block: The created block instance as managed by the controller with
            all the parts attached
    """
    parts = OrderedDict()
    for cls_name, d in parts_d.items():
        # Require all parts to have a name
        # TODO: make sure this is added from gui?
        name = d[name]
        parts[name] = call_with_map(malcolm.parts, cls_name, d)
    if controllers_d:
        cls_name, d = list(controllers_d.items())[0]
        controller = call_with_map(
            malcolm.controllers, cls_name, d, name, process, parts)
    else:
        controller = call_with_map(
            malcolm.core.controller, "Controller", d, name, process, parts)
    return controller.block


def call_with_map(ob, name, d, *args):
    """Keep recursing down from ob using dotted name, then call it with d, *args

    Args:
        ob (object): The starting object
        name (string): The dotted attribute path to follow
        d (dict): A dictionary of parameters that will be turned into a Map and
            passed to the found callable
        *args: Any other args to pass to the callable

    Returns:
        object: The found object called with (map_from_d, *args)

    E.g. if ob is malcolm.parts, and name is "ca.CADoublePart", then the object
    will be malcolm.parts.ca.CADoublePart
    """
    split = name.split(".")
    for n in split:
        ob = getattr(ob, n)

    # TODO: get params from method
    class Params(object):
        pass

    params = Params()
    for k, v in d.items():
        setattr(params, k, v)
    return ob(params, *args)
