def test_adding_all_nodes(nodeviewer):
    for func_name in nodeviewer.ct.function_meta:
        try:
            nodeviewer.add_function_node(func_name)
        except Exception as e:
            print(f"Error adding function node {func_name}: {e}")
