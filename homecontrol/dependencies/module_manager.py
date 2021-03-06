"""ModuleManager module"""

import sys
import importlib
import importlib.util
import os
import logging

import pkg_resources
import voluptuous as vol

import homecontrol
from homecontrol.dependencies.yaml_loader import YAMLLoader
from homecontrol.dependencies.entity_types import Module
from homecontrol.dependencies.ensure_pip_requirements import (
    ensure_pip_requirements
)
from homecontrol.exceptions import PipInstallError

LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Required("folders", default=[]): [str],
    vol.Required("blacklist", default=[]): [str],
    vol.Required("whitelist", default=[]): [str],
    vol.Required("install-pip-requirements", default=True): bool,
    vol.Required("load-internal-modules", default=True): bool
})


# pylint: disable=too-few-public-methods
class ModuleFolder:
    """
    module folder representation to create
    a dummy package in sys.modules
    """
    def __init__(self, name: str) -> None:
        self.__name__ = name


class ModuleManager:
    """Manages your modules"""

    cfg: dict

    def __init__(self, core):
        self.core = core
        self.loaded_modules = {}

    async def init(self) -> None:
        """Initialise the modules"""
        self.cfg = await self.core.cfg.register_domain(
            "module-manager",
            schema=CONFIG_SCHEMA,
            allow_reload=False)

        for folder in self.cfg["folders"]:
            await self.load_folder(folder)

        if self.cfg["load-internal-modules"]:
            internal_module_folder = pkg_resources.resource_filename(
                homecontrol.__name__, "modules")
            await self.load_folder(internal_module_folder)

    async def load_folder(self, path: str) -> [object]:
        """Load every module in a folder"""
        out = []
        blacklist = self.cfg["blacklist"]
        whitelist = self.cfg["whitelist"]

        package_name = f"homecontrol_{os.path.basename(path)}"
        sys.modules[package_name] = ModuleFolder(package_name)

        for node in os.listdir(path):
            if node == "__pycache__":
                continue
            mod_path = os.path.join(path, node)
            mod_name = node if os.path.isdir(
                node) else ".".join(os.path.splitext(node)[:-1])

            if ((mod_name not in blacklist)
                    and (not whitelist or mod_name in whitelist)):
                if os.path.isdir(mod_path):
                    out.append(
                        await self.load_folder_module(mod_path, mod_name))

                elif os.path.isfile(mod_path) and node.endswith(".py"):
                    out.append(
                        await self.load_file_module(mod_path, mod_name))

        return out

    async def load_file_module(self,
                               mod_path: str,
                               name: str) -> (Module, Exception):
        """
        Loads a module from a file and initialises it

        Returns a Module object
        """
        try:
            assert os.path.isfile(mod_path)
        except AssertionError as error:
            LOGGER.warning(
                "Module could not be loaded: %s at %s", name, mod_path)
            self.core.event_engine.broadcast(
                "module_not_loaded", exception=error)
            return error

        mod_spec = importlib.util.spec_from_file_location(name, mod_path)
        mod = importlib.util.module_from_spec(mod_spec)
        mod.resource_folder = None
        mod.event = self.core.event_engine.register
        mod.tick = self.core.tick_engine.tick
        mod_spec.loader.exec_module(mod)
        if not hasattr(mod, "Module"):
            mod.Module = type("Module_" + name, (Module,), {})
        else:
            mod.Module = type("Module_" + name, (mod.Module, Module), {})

        spec = (mod.SPEC if isinstance(mod.SPEC, dict) else YAMLLoader.load(
            mod.SPEC)) if hasattr(mod, "SPEC") else {}

        return await self._load_module_object(spec, name, mod_path, mod)

    async def load_folder_module(self,
                                 path: str,
                                 name: str) -> (Module, Exception):
        """
        Loads a module from a folder and initialises it

        It also takes care of pip requirements

        Returns a Module object
        """
        mod_path = os.path.join(path, "module.py")
        spec_path = os.path.join(path, "module.yaml")
        parent_path = os.path.dirname(path)

        try:
            assert os.path.isdir(path)
            assert os.path.isfile(mod_path)
            assert os.path.isfile(spec_path)
        except AssertionError as error:
            LOGGER.warning("Module could not be loaded: %s at %s", name, path)
            self.core.event_engine.broadcast(
                "module_not_loaded", exception=error, name=name)
            return error

        spec = YAMLLoader.load(open(spec_path))

        try:
            ensure_pip_requirements(spec.get("pip-requirements", []))
        except PipInstallError as e:
            LOGGER.warning(
                "Module could not be loaded: %s at %s", name, path)
            self.core.event_engine.broadcast(
                "module_not_loaded",
                exception=e,
                name=name)
            return

        mod_name = f"homecontrol_{os.path.basename(parent_path)}.{name}"
        mod_spec = importlib.util.spec_from_file_location(
            name, mod_path, submodule_search_locations=[path])
        mod = importlib.util.module_from_spec(mod_spec)
        mod.__package__ = mod_name
        sys.modules[mod_name] = mod
        mod.SPEC = spec
        mod.resource_folder = path
        mod_spec.loader.exec_module(mod)
        return await self._load_module_object(spec, name, path, mod)

    async def _load_module_object(self,
                                  spec: dict,
                                  name: str,
                                  path: str,
                                  mod) -> Module:
        """
        Initialises a module object
        This method should only be invoked by ModuleManager
        """
        if not hasattr(mod, "Module"):
            mod.Module = type("Module_" + name, (Module,), {})
        else:
            mod.Module = type("Module_" + name, (mod.Module, Module), {})

        mod_obj = mod.Module.__new__(mod.Module)

        mod_obj.core = self.core
        mod_obj.meta = spec.get("meta", {})
        mod_obj.resource_folder = mod.resource_folder
        mod_obj.name = name
        mod_obj.path = path
        mod_obj.items = {}
        mod_obj.item_specs = {}
        mod_obj.mod = mod
        mod_obj.spec = spec
        mod_obj.__init__()

        self.loaded_modules[name] = mod_obj
        await self.core.item_manager.add_from_module(mod_obj)
        if hasattr(mod_obj, "init"):
            await mod_obj.init()
        self.core.event_engine.broadcast("module_loaded", module=mod_obj)
        return mod_obj

    async def unload_module(self, name: str) -> None:
        """
        First removes all the items the module offers.
        Then it triggers the stop-coro and fully removes it.
        """
        for identifier in self.loaded_modules[name].items.keys():
            await self.core.item_manager.remove_item(identifier)
        if hasattr(self.loaded_modules[name], "stop"):
            await self.loaded_modules[name].stop()
        del self.loaded_modules[name]

    async def stop(self) -> None:
        """Unloads all modules to prepare for a shutdown"""
        for module in list(self.loaded_modules.keys()):
            await self.unload_module(module)

    # pylint: disable=no-self-use
    def resource_path(self, module: Module, path: str = "") -> str:
        """
        Returns the path for a module's resource folder
        Note that only folder modules can have a resource path
        """
        path = os.path.join(module.resource_folder, path)
        if os.path.exists(path):
            return path
        raise FileNotFoundError(f"Resource path {path} does not exist")
