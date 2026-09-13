import re
from collections import defaultdict

from mne_nodes.logger import logger

OBJECT_SUFFIXES = {
    "epochs": "epo",
    "evokeds": "ave",
    "covariance": "cov",
    "forward": "fwd",
    "transform": "trans",
    "sourcespaces": "src",
}


class CodeGenerator:
    def __init__(self, controller, node_sequence):
        self.ct = controller
        self.node_sequence = node_sequence

        self.code = self.generate_code()

    @staticmethod
    def tab(num_tabs=1, tab_size=4):
        """Return a string of tabs for indentation."""
        return " " * (num_tabs * tab_size)

    @staticmethod
    def base_func_name(name):
        """Strip the disambiguating '-<N>' node-name suffix, e.g. for duplicate
        function nodes, to get the actual importable/callable function name."""
        return re.sub(r"-\d+$", "", name)

    @staticmethod
    def _suffix_for_ports(port_names):
        """Return the object suffix matching any of the given port names."""
        for port in port_names:
            if not port or not isinstance(port, str):
                continue
            stripped = port.rstrip("s")
            for key, suffix in OBJECT_SUFFIXES.items():
                if stripped == key.rstrip("s"):
                    return suffix
        return None

    @staticmethod
    def _match_port(meta, candidates):
        """Find the first matching value in a string or dict metadata mapping."""
        if isinstance(meta, str):
            return meta, candidates[0] if candidates else None
        if isinstance(meta, dict):
            for name in candidates:
                if not isinstance(name, str):
                    continue
                for variant in (name, name.rstrip("s"), name + "s"):
                    if variant in meta:
                        return meta[variant], variant
        return None, None

    def _resolve_read(self, func_name, input_name, node_info):
        """Resolve read function, suffix, and variable name for an input port."""
        input_meta = self.ct.get_input_meta(func_name, input_name)
        read_meta = input_meta.get("read")
        suffix_meta = input_meta.get("suffix")
        accepted_ports = input_meta.get("accepted_ports") or []
        connected_ports = node_info.get("input_ports", {}).get(input_name) or [
            cp
            for cp in node_info.get("inputs", {}).get(input_name, [])
            if isinstance(cp, str) and not cp.startswith("Input-")
        ]

        # Prioritize input port name and connected upstream port(s)
        if connected_ports:
            candidates = [input_name] + connected_ports
        else:
            candidates = [input_name] + accepted_ports

        read_func, matched_port = self._match_port(read_meta, candidates)
        load_name = matched_port or (
            connected_ports[0] if connected_ports else input_name
        )

        # Fallback to project-wide load metadata for candidates
        if read_func is None:
            for cand in candidates:
                alias_meta = self.ct.get_load_meta_for_port(cand)
                if alias_meta:
                    read_func, _ = self._match_port(alias_meta.get("read"), [cand])
                    if read_func:
                        load_name = cand
                        suffix_meta = suffix_meta or alias_meta.get("suffix")
                        break

        if read_func is None:
            logger.warning(
                f"No read function found for input '{input_name}' in "
                f"function '{func_name}' (connected: {connected_ports}). "
                "Connection is not valid."
            )
            return None, None, None

        suffix, _ = self._match_port(
            suffix_meta, [load_name, input_name] + connected_ports
        )
        suffix = (
            suffix
            or self._suffix_for_ports([load_name, input_name] + connected_ports)
            or load_name
        )
        return read_func, suffix, load_name

    def _resolve_write(self, func_name, output_name, node_info, func_inputs):
        """Resolve write function and suffix for an output port."""
        output_meta = self.ct.get_output_meta(func_name, output_name)
        write_meta = output_meta.get("write")
        if write_meta is None:
            return None, None

        suffix_meta = output_meta.get("suffix")
        accepted_ports = output_meta.get("accepted_ports") or []
        connected_ports = node_info.get("output_ports", {}).get(output_name) or []
        input_types = [v for v in func_inputs.values() if isinstance(v, str)]

        candidates = (
            [output_name] + input_types + connected_ports
            if input_types or connected_ports
            else [output_name] + accepted_ports
        )
        write_func, matched_port = self._match_port(write_meta, candidates)

        if write_func is None:
            logger.warning(
                f"No write function found for output '{output_name}' in "
                f"function '{func_name}'. Connection is not valid."
            )
            return None, None

        write_port = matched_port or output_name
        suffix, _ = self._match_port(suffix_meta, [write_port, output_name])
        suffix = (
            suffix or self._suffix_for_ports([write_port, output_name]) or output_name
        )
        return write_func, suffix

    def _indent(self, code, num_tabs=1):
        """Indent a code string by a given number of tabs."""
        indent_str = self.tab(num_tabs)
        # If line empty, don't indent
        indented_code = "\n".join(
            indent_str + line for line in code.splitlines() if line != ""
        )
        indented_code += "\n"
        return indented_code

    def _build_header(self, function_names, extra_modules=()):
        code = (
            "# This code was generated by mne-nodes\n\n"
            "import mne_nodes\n"
            "from mne_bids import get_bids_path_from_fname\n"
            "from mne_nodes.pipeline.controller import Controller\n\n"
            "# Disable gui-mode\n"
            "mne_nodes.gui_mode = False\n\n"
            "# Load controller\n"
            f"ct = Controller(config_path='{self.ct.ensure_config_path(interactive=False).as_posix()}')\n\n"
            "# Inject plugins into global namespace\n"
            "globals().update(ct.plugins)\n\n"
            "# Import plugins\n"
        )
        # Add plugin imports
        plugins_functions = defaultdict(list)
        seen_base_names = set()
        for function_name in function_names:
            base_name = self.base_func_name(function_name)
            if base_name in seen_base_names:
                continue
            seen_base_names.add(base_name)
            plugin_name = self.ct.get_plugin_from_function(function_name)
            plugins_functions[plugin_name].append(base_name)
        for plugin_name, functions in plugins_functions.items():
            if plugin_name == "mne_functions":
                module_functions_sorted = defaultdict(list)
                for func in functions:
                    module_name = self.ct.get_function_meta(func).get(
                        "module_name", None
                    )
                    if module_name is not None:
                        module_functions_sorted[module_name].append(func)
                for module, funcs in module_functions_sorted.items():
                    code += f"from {module} import {', '.join(funcs)}\n"
            else:
                code += f"from {plugin_name} import {', '.join(functions)}\n"

        # Import modules needed for reading/writing derivatives directly
        # (their functions are referenced module-qualified, not imported by name).
        for module in sorted(extra_modules):
            code += f"import {module}\n"

        code += "\n"

        return code

    def _qualified_call(self, func_name, required_modules):
        """Return a module-qualified call expression for a registered function.

        Records the function's module in ``required_modules`` so it can be
        imported in the header, unless the function is a class method (in
        which case it must be called on an instance instead).
        """
        func_meta = self.ct.get_function_meta(func_name)
        module_name = func_meta.get("module_name")
        if module_name:
            required_modules.add(module_name)
            return f"{module_name}.{func_name}"
        return func_name

    def generate_code(self):
        """Convert a list of instructions to a Python code string."""
        # Get available datatypes
        data_types = self.ct.get_datatypes()
        # Modules needed for module-qualified read/write function calls,
        # collected while building the body and imported in the header.
        import_function_names = set()
        required_modules = set()
        body = ""
        # Iterate nodes
        for target, nodes in self.node_sequence.items():
            if len(nodes) == 0:
                continue
            body += f"# Target: {target}\n"
            for selection_type in [
                key
                for key, items in self.ct.get("selected_inputs").items()
                if len(items) > 0
            ]:
                if (selection_type in self.ct.scopes and target == "file") or (
                    selection_type in data_types and target == "group"
                ):
                    continue
                loaded_data = set()
                body += f"# Selection-Type: {selection_type}\n"
                if target == "group":
                    body += f"group = ct.get_group_by('{selection_type}')\n"
                body += f"for item in ct.get('selected_inputs')['{selection_type}']:\n"
                # Prepare bids-paths
                if target == "file" and selection_type in data_types:
                    body += self._indent("bp = get_bids_path_from_fname(item)\n", 1)
                else:
                    # For group-data, load member bids-paths as a list
                    body += self._indent("members = group[item]\n", 1)
                for n in nodes:
                    name = n["name"]
                    func_meta = n["function_meta"]
                    # Only add functions that are not methods of a class
                    if func_meta["class_name"] is None:
                        import_function_names.add(name)
                    # Check which inputs are already satisfied (incl. via accepted_ports)
                    # before deciding what still needs to be loaded from disk.
                    func_inputs, loading_needed = self.ct.func_inputs(name, loaded_data)
                    # Only load inputs that are actually connected to something.
                    # Unconnected (optional) inputs are simply omitted from the call.
                    # A connected-but-unloaded input means the pipeline is being
                    # started from a subsequent node, so it must be read from disk.
                    inputs = [ip for ip in loading_needed if n["inputs"].get(ip)]
                    # Bids-path(s) to pass to the controller loading-methods
                    source = "bp" if target == "file" else "members"
                    for ip in inputs:
                        # Load selected data-types (if not already loaded)
                        if ip == "raw":
                            body += self._indent(
                                f"raw, event_id = ct.load_raw({source})\n", 1
                            )
                            loaded_data.update({"raw", "event_id"})
                        elif ip == "info":
                            raw_arg = "raw" if "raw" in loaded_data else "None"
                            body += self._indent(
                                f"info = ct.load_info({source}, raw={raw_arg})\n", 1
                            )
                            loaded_data.add("info")
                        elif ip == "subject":
                            # Load (freesurfer) subject if available
                            subject_source = "bp" if target == "file" else "members[0]"
                            body += self._indent(
                                f"subject = ct.load_subject({subject_source}.subject)\n",
                                1,
                            )
                            body += self._indent("if not subject:\n", 1)
                            body += self._indent("continue", 2)
                            loaded_data.add("subject")
                        else:
                            # Load data from derivatives
                            read_func, suffix, load_name = self._resolve_read(
                                name, ip, n
                            )
                            if read_func is None:
                                continue

                            read_call = self._qualified_call(
                                read_func, required_modules
                            )
                            # Load data from storage
                            body += self._indent(f"# Load {load_name}", 1)
                            # Read function's own parameters serve as its kwargs.
                            body += self._indent(
                                f"read_kwargs = {{k: v for k, v in ct.func_parameters('{read_func}').items() if k != 'fname'}}\n",
                                1,
                            )
                            if target == "file":
                                body += self._indent(
                                    f"data_path = bp.copy().update(suffix='{suffix}', root=ct.deriv_root, check=False).fpath\n",
                                    1,
                                )
                                # This assumes, that the file-path is always the first argument in a load-function
                                body += self._indent(
                                    f"{load_name} = {read_call}(data_path, **read_kwargs)\n",
                                    1,
                                )
                            else:
                                body += self._indent(
                                    f"{load_name} = [{read_call}(dp, **read_kwargs) for dp in [bp.copy().update(suffix='{suffix}', root=ct.deriv_root, check=False).fpath for bp in members]]\n",
                                    1,
                                )
                            loaded_data.add(load_name)
                            func_inputs[ip] = load_name
                        # A loaded port's variable is named after itself.
                        if ip in loaded_data:
                            func_inputs[ip] = ip
                    body += self._indent(f"# Execute function {name}\n", 1)
                    body += self._indent(
                        f"print(f'Executing {name} for {{item}} with the following parameters:')\n",
                        1,
                    )
                    outputs = ", ".join([op for op in n["outputs"]])
                    func_line = ""
                    if len(outputs) > 0:
                        func_line += f"{outputs} = "
                    # Inject (lowercase) class-name if the function is a method of a class
                    # This assumes, that instance references of a class always have the same name as the class but lowercase
                    base_name = self.base_func_name(name)
                    if func_meta["class_name"] is not None:
                        lower_class = func_meta["class_name"].lower()
                        func_line += f"{lower_class}."
                        func_name = base_name.split(".")[-1]
                        func_inputs.pop(lower_class, None)
                    else:
                        func_name = base_name
                    func_line += f"{func_name}("
                    if len(func_inputs) > 0:
                        inputs = ", ".join(
                            f"{param}={var}" for param, var in func_inputs.items()
                        )
                        func_line += f"{inputs}, **ct.func_parameters('{name}'))"
                    else:
                        func_line += f"**ct.func_parameters('{name}'))"
                    body += self._indent(func_line, 1)
                    # Save outputs (if enabled)
                    if n["checked"]:
                        for op in n["outputs"]:
                            write_func, suffix = self._resolve_write(
                                name, op, n, func_inputs
                            )
                            if write_func is None:
                                continue

                            # Save data to storage
                            body += self._indent(f"# Save {op}\n", 1)
                            if target == "file":
                                body += self._indent(
                                    f"data_path = bp.copy().update(suffix='{suffix}', root=ct.deriv_root, check=False).fpath\n",
                                    1,
                                )
                            else:
                                body += self._indent(
                                    f"data_path = members[0].copy().update(subject=item, suffix='{suffix}', root=ct.deriv_root, check=False)\n"
                                    "data_path.mkdir(exist_ok=True)\n",
                                    1,
                                )
                            # Write function's own parameters serve as its kwargs.
                            body += self._indent(
                                f"write_kwargs = {{k: v for k, v in ct.func_parameters('{write_func}').items() if k != 'fname'}}\n",
                                1,
                            )
                            write_func_meta = self.ct.get_function_meta(write_func)
                            if write_func_meta["class_name"] is not None:
                                # Called on the produced instance directly.
                                method_name = write_func.split(".")[-1]
                                body += self._indent(
                                    f"{op}.{method_name}(data_path, **write_kwargs)\n",
                                    1,
                                )
                            else:
                                write_call = self._qualified_call(
                                    write_func, required_modules
                                )
                                # This assumes, that the file-path is always the first argument in a save-function
                                body += self._indent(
                                    f"{write_call}(data_path, {op}, **write_kwargs)\n",
                                    1,
                                )
                    loaded_data.update(n["outputs"])

        # Create import header, including modules for read/write functions used above.
        header = self._build_header(import_function_names, required_modules)

        return header + body
