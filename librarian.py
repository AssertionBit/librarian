from __future__ import annotations

from abc import abstractmethod, abstractstaticmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import singledispatch
from json import dumps
from os import getcwd, listdir, mkdir, walk
from os.path import abspath, expanduser, join
from pickle import dump as pickle_dump
from pickle import load as pickle_load
from typing import Callable, List, Union, final, overload

from click import Context, argument, command, group, option, pass_context
from flask import Flask, render_template
from flask_cors import CORS
from requests import Request
from rich import print
from rich.prompt import Confirm
from toml import dump as toml_dump
from toml import load as toml_load
from typing_extensions import override

# ================================= CONSTANTS =============================== #

CACHE_FOLDERS = [
    # Python
    ".tox",
    ".mypy_cache",
    ".egg-info",
    ".pytest_cache",
]


# =================================== RUNTIME =============================== #


@dataclass
class AppConfig:
    """Configurations for single run of CLI. Or the program itself when all is
    provided.

    Args:
        home_dir (str): Path where all resources will exist, recommended to
            place all here.
        force_install (bool): Ignore warnings and errors and attempt to install
            something anyway.
        ignore_compromised (bool): Disable sanity checks and run librarian in
            unsafe mode.
        always_yes (bool): Ignore all prompts and just run application.
    """

    home_dir: str = field()
    force_install: bool = field()
    ignore_compromised: bool = field()
    always_yes: bool = field()
    verbose: bool = field()

    def __post_init__(self):
        if self.ignore_compromised:
            print("[yellow bold blink][!] Enabled unsecure methods!")

        if self.ignore_compromised and self.verbose:
            print("[dim][VERBOSE][bold yellow] Recommendation:")
            for line in [
                "We not recommend to turn off all security checks during runtime!",
                "Run with this mode only if You really checked all dependencies and",
                "really sure that all is ok!",
            ]:
                print(f"[dim][VERBOSE]\t{line}")


APP_CONFIG: AppConfig


class AppResources:
    """Resources of application that available at runtime.

    Provides all languages, plugins and styling options that needed to runtime,
        plugins and etc. Class is functional wrap for all of them, including
        the list of plugins itself.

    Attributes:
        languages (List[LanguageSpecs]): All languages that supported at start
        plugin_vendor (List[Vendor]): Vendors that provide plugins for styling
            and etc.

    Methods:
        is_language_exists (bool): Check if language added to resources
        get_all_languages (List[str]): Return list of all languages
        get_all_file_extensions (List[str]): Return list of all file extensions
            that might be found.
        get_all_project_files (List[str]): Return all files, that marks as
            project

    Version: 0.0.1
    """

    _languages: List[LanguageSpecs] = []
    _plugin_vendor: List[Vendor] = []

    def __init__(self, data: dict) -> None:
        global APP_CONFIG

        if len(data["plugins"]) == 0:
            return

        # Plugin loaded from existing resources
        for plugin in data["plugins"]:
            try:
                if APP_CONFIG.verbose:
                    print(f"[dim][VERBOSE] Loading plugin {plugin['name']}")
                    print(f"[dim][VERBOSE]\t Version: {plugin['version']}")
                    print(f"[dim][VERBOSE]\t Vendor: {plugin['vendor']}")
                    print(f"[dim][VERBOSE]\t Timestamp: {plugin['timestamp']}")

                with open(join(APP_CONFIG.home_dir, "plugins", plugin["name"] + ".obj"), "rb") as file:
                    object: LanguageSpecs = pickle_load(file)
                    self._languages.append(object)

            except FileNotFoundError:
                data.pop(plugin)
                print(f"[bold red]Damaged plugin: {plugin['name']}")
                print(f"[bold red blink] PLUGIN IS DAMAGED!")

                if APP_CONFIG.always_yes:
                    install(f"{plugin['vendor']}:{plugin['name']}")
                    continue

                if Confirm.ask("Reinstall plugin?"):
                    install(f"{plugin['vendor']}:{plugin['name']}")
                    continue

                print("[bold red blink] PLUGIN DELETED AND NOT LOADED! CONTINUE!")

    def is_language_exists(self, lang: str) -> bool:
        """Check if language exists and returns this status

        Arguments:
            lang (str): Language name lowercase

        Return:
            status (bool): Found or not
        """

        return lang in self.get_all_languages()

    def get_all_languages(self) -> List[str]:
        """Get all languages that registered in root folder.

        Return:
            languages (List[str]): List of all languages in lowercase.
        """

        return [lang.language_name.lower() for lang in self._languages]

    def get_all_file_extensions(self) -> List[str]:
        """Return all file extensions that were added during runtime.

        Return:
            extensions (List(str)): List of all file extensions after period
        """

        result: List[str] = []
        for lang in self._languages:
            result.extend(lang.file_extensions)

        return result

    def get_all_project_files(self) -> List[str]:
        """Get files, that marks that directory is a project.

        Return:
            files (List[str]): All files that related to the project.
        """

        result: List[str] = []
        for lang in self._languages:
            result.extend(lang.project_files)

        return result


APP_RESOURCES: AppResources

# ============================= EXACT DATA TYPES ============================ #


_documentCellTypeRaw = ["paragraph", "link_text", "link_external", "table", "code", "image", "field"]
_documentCellTypeRaw.extend([f"header_{x}" for x in range(1, 11)])
DocumentCellType = Enum("DocumentCellType", _documentCellTypeRaw)


_ID_COUNTER: int = 0


def _id_generator() -> int:
    global _ID_COUNTER
    _ID_COUNTER += 1
    return _ID_COUNTER


@dataclass
class DocumentCell:
    raw_content: str = field()
    additional_content: dict = field(default_factory=lambda: {})
    id: int = field(default_factory=_id_generator)
    type: DocumentCellType = field(default=DocumentCellType.paragraph)  # This will make it more adaptive

    def __post_init__(self) -> None:  # Adaptation goes here
        global APP_CONFIG

        if self.type == DocumentCellType.field:
            if "name" not in self.additional_content.keys() or "label" not in self.additional_content.keys():
                raise ValueError(self.additional_content, self.id, "Fields must contain name and text label")

        if self.type in [DocumentCellType.link_text, DocumentCellType.link_external]:
            if "target" not in self.additional_content.keys():
                raise ValueError(self.additional_content, self.id, "Links must contain target information!")

        if self.type == DocumentCellType.link_external:
            if not self.additional_content["target"].startswith("https") and not APP_CONFIG.force_install:
                raise ValueError(self.additional_content, self.id, "External links must contain https schema")

        if self.type == DocumentCellType.code:
            if "lang" not in self.additional_content.keys():
                raise ValueError(
                    self.additional_content, self.id, "Code sections must contain language, at least empty key"
                )

        if self.type == DocumentCellType.image:
            if "src" not in self.additional_content.keys():
                raise ValueError(
                    self.additional_content, self.id, "Images must contain link to source, at least network"
                )

    @staticmethod
    def create_paragraph(text: str, centralized: bool = False) -> DocumentCell:
        return DocumentCell(text, additional_content={"centralize": centralized})

    @staticmethod
    def create_text_link(text: str, to: str, as_class: bool = False, as_text: bool = False) -> DocumentCell:
        return DocumentCell(
            text,
            additional_content={"to": to, "as_class": as_class, "as_text": as_text},
            type=DocumentCellType.link_text,
        )

    @staticmethod
    def create_external_link(
        text: str,
        to: str,
        as_class: bool = False,
        as_text: bool = False,
        to_twitter: bool = False,
        to_meta: bool = False,
        to_github: bool = False,
        to_gitlab: bool = False,
        to_vk: bool = False,
        to_email: bool = False,
        to_slack: bool = False,
    ) -> DocumentCell:
        global APP_CONFIG

        if not APP_CONFIG.ignore_compromised:
            ...  # TODO: check

        return DocumentCell(
            raw_content=text,
            additional_content={
                "to": to,
                "as_class": as_class,
                "as_text": as_text,
                "to_twitter": to_twitter,
                "to_meta": to_meta,
                "to_github": to_github,
                "to_gitlab": to_gitlab,
                "to_vk": to_vk,
                "to_email": to_email,
                "to_slack": to_slack,
            },
            type=DocumentCellType.link_external,
        )


@dataclass
class Module:
    name: str
    language: str
    language_specs: LanguageSpecs = field()
    project_files: List[str] = field(default_factory=lambda: [])
    dependencies: List[dict] = field(default_factory=lambda: [])


# ============================= FS FUNCTIONALITY ============================ #


def init_librarian():
    """
    Load plugins, data and configurations for librarian.
    """
    global CACHE_FOLDERS
    global APP_CONFIG

    # Creating home directory
    try:
        mkdir(APP_CONFIG.home_dir)

    except FileExistsError:
        ...

    # Creating plugin directory
    try:
        mkdir(join(APP_CONFIG.home_dir, "plugins"))

    except FileExistsError:
        ...

    # Loading data from configs
    data: dict = {}
    try:
        with open(join(APP_CONFIG.home_dir, "resources.toml"), "r") as file:
            data = toml_load(file)

    except FileNotFoundError:
        with open(join(APP_CONFIG.home_dir, "resources.toml"), "x") as file:
            data = {"plugins": [], "translations": {"enabled": False}}
            toml_dump(data, file)

    return data


def load_module(path: str) -> Module:
    return Module(path, path, None)


def load_project(path: str = getcwd()):
    """
    Loads all project from the provided path or from the current working
    directory.
    """
    global CACHE_FOLDERS

    # Avoiding all problems with README md files
    if "README.md" not in listdir(path):
        raise ValueError(path, "Path no containing README.md")

    positions: List[str] = []  # Will contain all pos where README/ProjectStart found
    for dirpath, dirname, files in walk(path):

        skip = False
        for cache_folder in CACHE_FOLDERS:
            if cache_folder in dirpath:
                skip = True

        if skip:
            continue

        if "README.md" in files:
            positions.append(dirpath)

    result: List[Module] = []
    for module in positions:
        result.append(load_module(module))

    return result


# =================================== RUNTIME =============================== #


class Vendor(object):
    _name: str
    _version: str
    _is_secure: str
    _login_method: str
    _credentials: dict = {"login": "", "password": "", "token": ""}

    @overload
    @abstractmethod
    def find(self, request: Request, name: str) -> Union[Dependency, None]:
        """Find dependency by it's name from the vendor.

        Make a request to the vendor API of any type and receive answer in
            dependency format. Used when parsers are required in network vendor
            and ensures, that requests are safe.

        Request done with custom headers and emulating human-requests model.
            But in headers there is a mark, that request done by the librarian:

            http {
                headers {
                    X-Request-Provider: librarian-vX.X.X
                }
            }

        Arguments:
            request (Request): Prepared for You human-like request function.
            name (str): Name of required package to look for.

        Returns:
            None: In case if not found anything.
            Dependency: If project found and dependency ready to go.
        """

        ...

    @overload
    @abstractmethod
    def find(self, request: Request, name: str, version: str) -> Union[Dependency, None]:
        """Find dependency by it's name from the vendor.

        Make a request to the vendor API of any type and receive answer in
            dependency format. Used when parsers are required in network vendor
            and ensures, that requests are safe.

        Request done with custom headers and emulating human-requests model.
            But in headers there is a mark, that request done by the librarian:

            http {
                headers {
                    X-Request-Provider: librarian-vX.X.X
                }
            }

        Arguments:
            request (Request): Prepared for You human-like request function.
            name (str): Name of required package to look for.
            version (str): Unified version of version representation based on
                math

        Returns:
            None: In case if not found anything.
            Dependency: If project found and dependency ready to go.
        """
        ...


class LocalVendor(Vendor):
    """Local vendors controller

    Controls dependency reading from local machine (non-network provider) and
        reads them, as configurator.

    Arguments:
        _locations (List[str]): All path where to look dependencies

    Version:
        0.0.1
    """

    _locations: List[str] = []

    @final
    @overload
    def register_path(self, path: str):
        """Add path to look at

        Arguments:
            path (str): Path to look
        """

        self._locations.append(path)

    @final
    @overload
    def register_path(self, path: List[str]):
        """Add paths to look at

        Arguments:
            path (List[str]): Paths to look
        """

        self._locations.extend(path)

    @override
    @overload
    @abstractmethod
    def find(self, name: str) -> Union[Dependency, None]:
        """Find dependency by it's name from the vendor.

        Look at local libraries and collect information from them as vendors.
            Method must collect data ONLY from files, never from internet. If
            information requires checks from local files.

        Arguments:
            name (str): Name of required package to look for.

        Returns:
            None: In case if not found anything.
            Dependency: If project found and dependency ready to go.
        """

        ...

    @override
    @overload
    @abstractmethod
    def find(self, name: str, version: str) -> Union[Dependency, None]:
        """Find dependency by it's name from the vendor.

        Look at local libraries and collect information from them as vendors.
            Method must collect data ONLY from files, never from internet. If
            information requires checks from local files.

        Arguments:
            name (str): Name of required package to look for.
            version (str): Unified version of version representation based on
                math

        Returns:
            None: In case if not found anything.
            Dependency: If project found and dependency ready to go.
        """

        ...

    @abstractmethod
    def scan(self) -> List[Dependency]:
        """Scans directory for possible libs and returns list of ready to use
            dependencies.

        Returns:
            List[Dependency]: All dependencies ready to be used
        """
        ...


@dataclass
class Dependency:
    """Dependencies used by project.

    Provides tooling for working with single dependency unit. Used for marking
        responsibilities and creating plugins based on it. Use for plugins
        only.

    Arguments:
        name (str): Name of package, human-like
        version (str): Version
        vendor (Vendor): Place from where were package taken
        license (str): License short code, will be transformed lately
        machine_name (str): Machine name that used with imports
        description (str): Description of package

    Version:
        1.0.0
    """

    name: str
    version: str
    vendor: Vendor
    license: str
    machine_name: str
    description: str = field(default="")

    @final
    def to_json(self) -> str:
        """Dump object to JSON-like string.

        Returns:
            str: ready to dump json string from object
        """

        return dumps({"name": self.name, "version": self.vendor, "vendor": self.vendor._name, "license": self.license})

    def __post_init__(self):
        # TODO: Verify license
        # TODO: Default vendor
        # TODO: Get description

        ...


@dataclass
class LanguageSpecs:

    # Data
    language_name: str = field()
    file_extensions: List[str] = field()
    comments: List[str] = field(default_factory=lambda: [])
    is_docs_after_func: bool = field(default=False)
    project_files: List[str] = field(default_factory=lambda: [])
    vendors_API: List[Vendor] = field(default_factory=lambda: [])

    # Requirement to run
    on_start: Callable[[str], None] = field(default_factory=lambda: None)
    is_language: Callable[[List[str]], bool] = field(default_factory=lambda: False)
    project_files_loaders: List[Callable[[str], Module]] = field(default_factory=lambda: None)
    project_loader: Callable[[List[str]], Module] = field(default_factory=lambda: None)

    # Callbacks
    parse_documentation: List[Callable[[str], str]] = field(default_factory=lambda: [])
    additional_files_loaded: List[Callable[[str], List[str]]] = field(default_factory=lambda: [])
    project_files_data_loaders: List[Callable[[str], List[str]]] = field(default=lambda: [])
    advanced_documentation_loaded: List[Callable[[Request], int]] = field(default=lambda: [])

    def __post_init__(self):
        # TODO: Emit file names
        # TODO: Append default docs parser
        # TODO: Verify amount of vendors API
        # TODO: Load defaults for every category
        ...

    def get_loader(self, project_file: str) -> Union[Callable[[str], Module], None]:
        if project_file not in self.project_files:
            return None

        return self.project_files_loaders[self.project_files.index(project_file)]

    def parse_project(self, project_files: List[str]) -> Union[Module, None]:
        if not self.is_language(project_files):
            return None
        return self.project_loader(project_files)


@singledispatch
def add_plugin(plugin, verbose=False):
    raise TypeError(type(plugin), "not supported")


@add_plugin.register
def _(plugin: str, verbose=False):
    ...


@add_plugin.register
def _(plugin: LanguageSpecs, verbose=False):
    ...


# ===================================== CLI ================================= #
@group
@option("--verbose", help="Print help options", is_flag=True, default=False)
@option("--home", help="Home of librarian, where all things", default=join(expanduser("~"), ".librarian"))
@option("-y", "--yes", is_flag=True, help="Agree to all prompts", default=False)
@option("-f", "--force", is_flag=True, help="Force run of program even if something is not here", default=False)
@option("--not-secure", is_flag=True, help="Ignore all security checks", default=False)
def cli(verbose, home, yes, force, not_secure):
    global APP_CONFIG
    global APP_RESOURCES

    APP_CONFIG = AppConfig(
        home_dir=home, force_install=force, ignore_compromised=not_secure, always_yes=yes, verbose=verbose
    )

    raw_data = init_librarian()

    APP_RESOURCES = AppResources(raw_data)

    init_librarian()


@cli.group
@argument("plugin", type=str)
@pass_context
def plugin(ctx: Context, plugin: str):
    ...


@command
@option("--source", type=str, help="From where to look plugin. Could be url or path")
def install(source: str):
    print("[green]Install!")


@cli.group
@option(
    "--rootless", default=False, type=bool, is_flag=True, help="Run the librarian without README.md scanning on top"
)
def doc(rootless: bool):
    """
    Work with documentation: compile, serve, etc.

    Manipulate the documentation around the project root and other things.
    Note, that command contains two sub-options: compile and serve. all of them
    requires from You to have plugins for languages, and be on top of source
    root.

    Sometimes, You may not have the README on top of the root then just run
    `--rootless` mode. Other things, like serving book and customizing the
    output is reserved to commands, that You want to use.
    """
    ...


@command
def compile():
    """
    Compile the documentation into raw html/css/js code and end program.

    Compile project documentation into useful documentation that could be used
    with any HTTP/HTTPS server, that could serve HTML. Librarian will build
    documentation in no-net-dependencies, so server will not add anything, that
    goes away from it's responsibility.

    If for, example, JQuery is requested for docs than librarian will dump
    it's build-in jquery document. To replace it, just configure it in
    top-level docs.
    """
    result = load_project()
    print(result)


@command
@option("--port", type=int, help="Port on which serve app", default=8080, show_default=True)
@option("--debug", type=bool, is_flag=True, help="Serve application in debug mode", default=False)
def serve(port: int, debug: bool):
    """
    Run local web-server based on Flask.

    Runs web server from current directory where docs folder found. To run the
    server You should have the WSGI container to serve application to outer
    world. Or just use build-in options.
    """

    server = Flask(__name__)
    CORS(server)

    @server.route("/")
    def index() -> str:
        return render_template(join("index.jinja"))

    server.run(debug=True)


# Plugin commands
plugin.add_command(install)


# Docs commands
doc.add_command(compile)
doc.add_command(serve)


if __name__ == "__main__":
    exit(cli())

init_librarian()
APP_CONFIG = AppConfig(expanduser("~"), False, False, False, False)
APP_RESOURCES = AppResources(APP_CONFIG)
