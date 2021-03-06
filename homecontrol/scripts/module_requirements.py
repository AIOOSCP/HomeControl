"""Helper to find the pip requirements for a builtin module"""
import os
import pkg_resources

import homecontrol
from homecontrol.dependencies.yaml_loader import YAMLLoader


MODULE_FOLDER = pkg_resources.resource_filename(
    homecontrol.__name__, "modules")

def get_requirements() -> list:
    """
    Lists the pip requirements for the builtin folder modules
    """
    output = []

    for node in os.listdir(MODULE_FOLDER):
        if node == "__pycache__":
            continue
        mod_path = os.path.join(MODULE_FOLDER, node)

        if os.path.isdir(mod_path):
            cfg_path = os.path.join(mod_path, "module.yaml")
            cfg = YAMLLoader.load(open(cfg_path))
            output.extend(cfg.get("pip-requirements", []))

    return output

if __name__ == "__main__":
    print(" ".join(get_requirements()))
