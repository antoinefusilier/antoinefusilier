import os
from pathlib import Path
import re
from typing import List, Optional, Any
from omegaconf import OmegaConf, DictConfig
import hvac
import shutil
import toml
from build import ProjectBuilder
import logging
from apollonai.core.config.logging_config import get_logger

from .repository_config_path_service import RepositoryConfigPathService
from omegaconf import OmegaConf
from dynaconf import Dynaconf

LOGGER = logging.getLogger(__name__)



class ConfigLoader:

    def __init__(
        self,
        package_name: Optional[str] = 'package_unknow',
        config_file_path: Optional[str] = None,
        logger=None,
    ):
        self.env = os.getenv("APOLLONAI_AIML_3EEFX8ZYE7DZPSU0VI8T4D1C_ENV", "local")
        self.project_path = os.getenv("APOLLONAI_AIML_3EEFX8ZYE7DZPSU0VI8T4D1C_REPO_PATH", f"~/projects/apollonai-aiml-3eefx8zye7dzpsu0vi8t4d1c")

        self.logger = logger or get_logger(
            config_file_path=config_file_path,
            package_name=package_name
        )
        
        print(f"Logger: {self.logger}")
        self.logger.info(f"ConfigLoader initialized for env: {self.env}")

        self.repository_paths = RepositoryConfigPathService( package_name
        )
        self.logger.info(f"Repository paths: {self.repository_paths}")

        self.vault_client = self._init_vault_client()
        self.config = self.load_all_configs()
        self.logger.info(f"Config loaded successfully for env: {self.env}")

    def _write_pyproject(self, package_path: str, meta: dict, requirements: List[str]) -> None:
        """
        Create a PEP 621 pyproject.toml in package_path
        using the provided metadata dict and requirements list.
        """
        # Normalize any OmegaConf license metadata
        lic = meta.get("license")
        if OmegaConf.is_config(lic):
            lic = OmegaConf.to_container(lic, resolve=True)

        # Determine PEP-compliant license field
        if isinstance(lic, str):
            # simple string license (must be valid SPDX)
            license_entry: Any = lic
        elif isinstance(lic, dict) and "file" in lic:
            license_entry = {"file": lic["file"]}
        elif isinstance(lic, dict) and "text" in lic:
            license_entry = {"text": lic["text"]}
        else:
            # fallback to pointing at LICENSE file
            license_entry = {"file": "LICENSE"}

        # Ensure URL has a scheme prefix
        raw_url = meta.get("url", "") or ""
        if raw_url and not re.match(r'^[a-zA-Z]+://', raw_url):
            raw_url = f"http://{raw_url}"
        homepage_url = raw_url

        LOGGER.info("______ REQUIREMENTS _______")
        self.logger.info(requirements)

        project_table = {
            "name":            meta.get("name"),
            "version":         meta.get("version"),
            "description":     meta.get("description", ""),
            "readme":          "README.md",
            "requires-python": ">=3.6",
            # PEP 621 license field (oneOf string|table)
            "license-files":    meta.get("license-files", []),
            "authors":         [{"name": meta.get("author", ""), "email": meta.get("author_email", "")}],
            "dependencies":    requirements,
            "classifiers": [
                "Programming Language :: Python :: 3",
                "Operating System :: OS Independent",
            ],
            # Use URL with scheme for maximum compatibility
            "urls":            {"Homepage": homepage_url},
            "scripts":         {f"{meta.get('name')}": f"{meta.get('name')}.main:cli"},
        }
        # Ensure that the apollonai/config directory is included in package data
        setuptools_config = {
            "package-data": {
                "apollonai": [
                    "config/*",
                    "docker/*",
                    
                    ]
                },
            "include-package-data": True,
        }

        # Merge with any existing tool.setuptools configuration

        pyproject = {
            "build-system": {
                "requires": ["setuptools>=61.0", "wheel"],
                "build-backend": "setuptools.build_meta",
            },
            "project": project_table,
        }
        pyproject.setdefault("tool", {}).setdefault("setuptools", {}).update(setuptools_config)

        toml_path = Path(package_path).parent / "pyproject.toml"
        with toml_path.open("w", encoding="utf-8") as f:
            toml.dump(pyproject, f)


    def _build_package(self, package_path: str, outdir: str = "dist") -> None:
        """
        Build sdist and wheel for the package at package_path into outdir.
        """
        package_path_parent = Path(package_path).parent
        print(f"Building package at {package_path_parent} into {outdir}")
        # builder = ProjectBuilder(Path(package_path).parent)
        builder = ProjectBuilder(package_path_parent)
        builder.build("sdist", outdir)
        builder.build("wheel", outdir)

    def _init_vault_client(self) -> Optional[hvac.Client]:
        vault_url = os.getenv("VAULT_ADDR")
        vault_token = os.getenv("VAULT_TOKEN")
        if vault_url and vault_token:
            try:
                client = hvac.Client(url=vault_url, token=vault_token)
                if client.is_authenticated():
                    self.logger.info("Connected to Vault successfully.")
                    return client
                else:
                    self.logger.error("Vault authentication failed.")
            except Exception as e:
                self.logger.error(f"Vault connection error: {e}")
        else:
            self.logger.warning("Vault environment variables not set; skipping Vault connection.")
        return None

    def load_yaml_config(self, path: str) -> DictConfig:
        if os.path.exists(path):
            return OmegaConf.load(path)
        else:
            self.logger.warning(f"Config path not found: {path}")
            return OmegaConf.create({})

    def resolve_vault_secrets(self, config: DictConfig) -> DictConfig:
        if not self.vault_client:
            self.logger.warning("Vault client unavailable; skipping secrets resolution.")
            return config

        pattern = re.compile(r'\${vault:([^#]+)#([^}]+)}')

        def _resolver(node: Any):
            if isinstance(node, DictConfig):
                for k, v in node.items():
                    node[k] = _resolver(v)
            elif isinstance(node, str):
                match = pattern.search(node)
                if match:
                    path, key = match.groups()
                    try:
                        secret = self.vault_client.secrets.kv.v2.read_secret_version(path=path)
                        return secret['data']['data'][key]
                    except Exception as e:
                        self.logger.error(f"Failed to resolve vault secret {path}:{key}: {e}")
            return node

        return _resolver(config)

    def load_all_configs(self) -> DictConfig:
        config_root = self.repository_paths.config_path
        env = self.env

        # 1. Project-level configuration
        project_config = self.safe_merge(
            os.path.join(config_root, "project", "base.yaml"),
            os.path.join(config_root, "project", f"{env}.yaml" )
        )

        # 2. Repository-level services configuration
        repository_services = {}
        services_root = os.path.join(config_root, "repository")
        if os.path.isdir(services_root):
            for service in os.listdir(services_root):
                service_path = os.path.join(services_root, service)
                if not os.path.isdir(service_path) or service in ["packages", "kube"]:
                    continue

                repository_services[service] = self.safe_merge(
                    os.path.join(service_path, "base.yaml"),
                    os.path.join(service_path, f"{env}.yaml" )
                )


        # 3. Repository-level packages configuration
        repository_packages = {}
        packages_root = os.path.join(services_root, "packages")
        if os.path.isdir(packages_root):
            for package_name in os.listdir(packages_root):
                package_path = os.path.join(packages_root, package_name)
                if not os.path.isdir(package_path):
                    continue

                stacks = {}
                for stack_name in os.listdir(package_path):
                    stack_path = os.path.join(package_path, stack_name)
                    if not os.path.isdir(stack_path):
                        continue

                    stack_entry = {
                        "meta": self.safe_merge(
                            os.path.join(stack_path, "base.yaml"),
                            os.path.join(stack_path, f"{env}.yaml")
                        )
                    }

                    # Load requirements (python/debian)
                    for req_section in ["requirements", "debian_requirements"]:
                        req_path = os.path.join(stack_path, req_section)
                        if os.path.isdir(req_path):
                            stack_entry[req_section] = self.safe_merge(
                                os.path.join(req_path, "base.yaml"),
                                os.path.join(req_path, f"{env}.yaml")
                            )

                    stacks[stack_name] = stack_entry

                repository_packages[package_name] = stacks

        # 4. Kubernetes manifests integration
        kube_manifests = {}
        kube_manifests_root = os.path.join(services_root, "kube", "manifests")
        if os.path.isdir(kube_manifests_root):
            for manifest_type in ["base", "apps", "system"]:
                manifest_path = os.path.join(kube_manifests_root, manifest_type)
                manifests = {}
                if os.path.isdir(manifest_path):
                    for root, _, files in os.walk(manifest_path):
                        for file in files:
                            if file.endswith(('.yaml', '.yml')):
                                file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(file_path, kube_manifests_root)
                                manifests[rel_path] = self.load_yaml_config(file_path)
                kube_manifests[manifest_type] = manifests

        # Compose final structured config
        final_config = OmegaConf.create({
            "project": project_config,
            "repository": {
                "services": repository_services,
                "packages": repository_packages,
                "kube_manifests": kube_manifests
            }
        })

        self.logger.info(f"Configuration successfully loaded for environment: {env}")
        return final_config

    def safe_merge(self, base_path: str, env_path: str) -> DictConfig:
        """
        Merge OmegaConf YAML files at base_path and env_path.
        """
        def try_load(path: str) -> Optional[DictConfig]:
            if path and os.path.isfile(path):
                return OmegaConf.load(path)
            return None

        base_cfg = try_load(base_path)
        env_cfg = try_load(env_path)

        if base_cfg is None and env_cfg is None:
            return OmegaConf.create({})
        if base_cfg is None:
            return env_cfg
        if env_cfg is None:
            return base_cfg
        if type(base_cfg) != type(env_cfg):
            self.logger.debug(
                f"Type mismatch during merge. Skipping merge:"
                f"base type: {type(base_cfg)}, env type: {type(env_cfg)}"
            )
            return env_cfg or base_cfg

        return OmegaConf.merge(base_cfg, env_cfg)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Safe wrapper around OmegaConf.select to avoid type errors.
        """
        if not isinstance(self.config, (dict, DictConfig)):
            return default

        try:
            return OmegaConf.select(self.config, key, default=default)
        except Exception as e:
            self.logger.debug(f"[Config.get] Failed to access '{key}': {e}")
            return default

    def display_library_startup(self) -> None:
        meta = self.get("metadata.project", {})
        startup_info = f"""
        {'='*60}
        {meta.get('name', 'Library')} v{meta.get('version', '0.0.0')}
        {meta.get('description', 'No description')}

        Author: {meta.get('author', 'Unknown')} <{meta.get('author_email', 'Unknown')}>
        Environment: {self.env}
        {'='*60}
        """
        self.logger.info(startup_info)

    def copy_library_configs(self, package_name: str, language: str, config_subfolder: str = "repository") -> None:
        """
        Copy configuration files from `/config/repository/packages/{package_name}/*` 
        to `/src/packages/{package_name}/{language}/{package_name}/config`.
        """
        self.logger.info(f"Copying library configs for package '{package_name}' and language '{language}'...")
        source_path = os.path.join(self.repository_paths.config_path, config_subfolder, 'packages', package_name, language)
        target_path = os.path.join(
            self.repository_paths.repository_path,
            "src",
            "packages",
            package_name,
            language,
            package_name,
            "config"
        )

        if not os.path.exists(source_path):
            self.logger.error(f"Source configuration folder does not exist: {source_path}")
            return

        self.delete_directories([target_path])
        os.makedirs(target_path, exist_ok=True)

        try:
            for item in os.listdir(source_path):
                item_path = os.path.join(source_path, item)
                if os.path.isfile(item_path):
                    shutil.copy(item_path, target_path)
                    self.logger.debug(f"Copied file: {item}")
                elif os.path.isdir(item_path):
                    target_subfolder = os.path.join(target_path, item)
                    shutil.copytree(item_path, target_subfolder, dirs_exist_ok=True)
                    self.logger.debug(f"Copied folder: {item}")
        except Exception as e:
            self.logger.error(f"Error copying configuration files: {e}")

        self.logger.info(f"Configuration files for '{package_name}' ({language}) successfully copied to {target_path}.")

    def _retrieve_package_data(self, package_name: str, config_sub_paths: Optional[List[str]] = None, file_extensions: Optional[List[str]] = None) -> dict:
        """
        Collects all non-Python files from the given paths relative to `base_path`.
        """
        self.logger.info(f"Retrieving package data for '{package_name}'...")
        base_path = self.repository_paths.repository_path
        if config_sub_paths is None:
            config_sub_paths = ['config/repository/packages']

        if file_extensions is None:
            file_extensions = ['.yaml', '.json', '.ini', '.cfg', '.txt', '.md']

        package_data = {}

        for sub_path in config_sub_paths:
            abs_path = os.path.join(base_path, sub_path)
            if not os.path.isdir(abs_path):
                self.logger.error(f"Skipping: {abs_path} (not a directory)")
                continue

            for root, _, files in os.walk(abs_path):
                for file in files:
                    if not any(file.endswith(ext) for ext in file_extensions):
                        continue

                    relative_path = os.path.relpath(os.path.join(root, file), abs_path)
                    package_key = package_name
                    if package_key not in package_data:
                        package_data[package_key] = []

                    replaced = relative_path.replace(f"{package_name}/", f"config/")
                    package_data[package_key].append(f"./{replaced}")

        return package_data

    def setup_packages(self) -> None:
        """
        For each python package:
          1) copy configs,
          2) write pyproject.toml,
          3) build sdist & wheel into /dist
        """
        base_src = os.path.join(self.repository_paths.repository_path, "_src", "packages")
        dist_dir = os.path.join(self.repository_paths.repository_path, "_build")
        os.makedirs(dist_dir, exist_ok=True)

        for pkg_name in os.listdir(base_src):
            pkg_root = os.path.join(base_src, pkg_name)
            python_pkg_path = os.path.join(pkg_root, "python", pkg_name)
            if not os.path.isdir(python_pkg_path):
                continue

            # ensure src-layout package has an __init__.py
            init_file = Path(python_pkg_path) / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")

            # 1) copy configuration files
            self.copy_library_configs(pkg_name, "python")

            # 2) extract metadata & requirements
            meta = {
                "name":         self.get(f"repository.packages.{pkg_name}.python.meta.name", pkg_name),
                "version":      self.get(f"repository.packages.{pkg_name}.python.meta.version", "0.1.0"),
                "description":  self.get(f"repository.packages.{pkg_name}.python.meta.description", "Description not provided"),
                "author":       self.get(f"repository.packages.{pkg_name}.python.meta.author", "Antoine Fusilier"),
                "author_email": self.get(f"repository.packages.{pkg_name}.python.meta.author_email", "antoine.fusilier@eurathos.eu"),
                "url":          self.get(f"repository.packages.{pkg_name}.python.meta.url", "https://apollonai.cloud"),
                # license may come as dict file/text; we normalize in _write_pyproject
                "license":      self.get(f"repository.packages.{pkg_name}.python.meta.license", {"file": "LICENSE"}),
                # optional SPDX string
                "license_spdx": self.get(f"repository.packages.{pkg_name}.python.meta.license_spdx", ""),
            }
            requirements = self.get(f"repository.packages.{pkg_name}.python.requirements", []) or []

            # 3) write PEP 621 pyproject.toml
            self._write_pyproject(python_pkg_path, meta, requirements)

            # 4) build artifacts
            self._build_package(python_pkg_path, outdir=dist_dir)

    def delete_directories(self, directory_paths: List[str]) -> None:
        """
        Deletes each directory and its contents from the provided list of paths.
        """
        self.logger.info("Deleting directories...")
        for path in directory_paths:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    self.logger.info(f"Successfully deleted: {path}")
                except Exception as e:
                    self.logger.error(f"Error deleting {path}: {e}")
            else:
                self.logger.error(f"Path does not exist: {path}")

class PythonConfigRetriever:
    def __init__(self, base_directory: str, logger=None):
        self.base_directory = base_directory
        self.logger = logger or get_logger()

    def load_yaml_config(self, file_path: str):
        if os.path.exists(file_path):
            return OmegaConf.load(file_path)
        else:
            self.logger.warning(f"Config file not found: {file_path}")
            return OmegaConf.create({})

    def retrieve_configs(self) -> "Dynaconf":

        # Step 1: Try to retrieve XDG package user configuration
        xdg_config_dir = os.path.join(os.path.expanduser("~/.config"), "apollonai")
        user_configs = {}
        if not os.path.isdir(xdg_config_dir):
            self.logger.warning(f"User XDG config directory does not exist: {xdg_config_dir}. Creating and preparing default configs.")
            os.makedirs(xdg_config_dir, exist_ok=True)
        else:
            for root, _, files in os.walk(xdg_config_dir):
                for file in files:
                    if file.endswith(('.yaml', '.yml')):
                        file_path = os.path.join(root, file)
                        # Remove extension from the relative path key
                        rel_path = os.path.splitext(os.path.relpath(file_path, xdg_config_dir))[0]
                        user_configs[rel_path] = self.load_yaml_config(file_path)
                        self.logger.info(f"Loaded user config: {rel_path}")

        # Step 2: Load default configurations from 'apollonai/config'
        config_dir = os.path.abspath(os.path.join(self.base_directory, "..", "..", "config"))
        default_configs = {}
        if not os.path.isdir(config_dir):
            self.logger.error(f"Default config directory does not exist: {config_dir}")
        else:
            for root, _, files in os.walk(config_dir):
                for file in files:
                    if file.endswith(('.yaml', '.yml')):
                        file_path = os.path.join(root, file)
                        # Remove extension from the relative path key
                        rel_path = os.path.splitext(os.path.relpath(file_path, config_dir))[0]
                        default_configs[rel_path] = self.load_yaml_config(file_path)
                        self.logger.info(f"Loaded default config: {rel_path}")

        # Step 3: Merge user config with default; if properties are missing in user config, copy/update with default values
        merged_configs = {}
        for key, default_cfg in default_configs.items():
            if key in user_configs:
                merged = OmegaConf.merge(default_cfg, user_configs[key])
                merged_configs[key] = merged
            else:
                merged_configs[key] = default_cfg
                # Write missing default config to user config directory, adding back the .yaml extension.
                target_file = os.path.join(xdg_config_dir, key + ".yaml")
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(OmegaConf.to_yaml(default_cfg))
                self.logger.info(f"Copied missing default config {key} to user config path")

        # Return a Dynaconf object initialized with the merged configurations
        settings = Dynaconf(environments=True, settings_dict=merged_configs)
        print("Settings:")
        config_dict = settings.as_dict()
        print(f"Config dict: {config_dict}")

        return settings