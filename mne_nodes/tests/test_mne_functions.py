def test_adding_all_mne_nodes(qtbot, nodeviewer, subtests):
    for func_name in sorted(nodeviewer.ct.function_meta):
        with subtests.test(func_name=func_name):
            node = nodeviewer.add_function_node(func_name)
            qtbot.wait(10)  # Wait a bit to ensure the node is fully initialized
            nodeviewer.remove_node(node)
            qtbot.wait(10)  # Wait a bit after removing the node
