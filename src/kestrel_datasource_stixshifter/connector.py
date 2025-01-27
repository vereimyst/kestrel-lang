import logging
import sys
import importlib
import subprocess
import requests
import pkg_resources
from lxml import html

from kestrel.exceptions import DataSourceError


_logger = logging.getLogger(__name__)


XPATH_PYPI_PKG_HOME = "/html/body/main/div[4]/div/div/div[1]/div[2]/ul/li[1]/a/@href"
XPATH_PYPI_PKG_SOURCE = "/html/body/main/div[4]/div/div/div[1]/div[2]/ul/li[2]/a/@href"
STIX_SHIFTER_HOMEPAGE = "https://github.com/opencybersecurityalliance/stix-shifter"


def get_package_name(connector_name):
    return "stix-shifter-modules-" + connector_name.replace("_", "-")


def verify_package_origin(connector_name):
    _logger.debug("go to PyPI to verify package genuineness from STIX-shifter project")
    package_name = get_package_name(connector_name)

    try:
        pypi_response = requests.get(f"https://pypi.org/project/{package_name}")
        pypi_etree = html.fromstring(pypi_response.content)
    except:
        raise DataSourceError(
            f'STIX-shifter connector for "{connector_name}" is not installed '
            f'and Kestrel guessed Python package name "{package_name}" but failed to locate it at PyPI',
            "please manually install the correct STIX-shifter connector Python package.",
        )

    try:
        p_homepage = pypi_etree.xpath(XPATH_PYPI_PKG_HOME)[0]
        p_source = pypi_etree.xpath(XPATH_PYPI_PKG_SOURCE)[0]
    except:
        raise DataSourceError(
            f'STIX-shifter connector for "{connector_name}" is not installed '
            f'and Kestrel guessed Python package name "{package_name}" but could not verify its genuineness due to PyPI design change',
            "please find the correct STIX-shifter connector Python package to install. "
            "And report to Kestrel developers about this package verification failure",
        )

    if p_homepage != STIX_SHIFTER_HOMEPAGE or p_source != STIX_SHIFTER_HOMEPAGE:
        raise DataSourceError(
            f'STIX-shifter connector for "{connector_name}" is not installed '
            f'and Kestrel found Python package "{package_name}" is not a genuine STIX-shifter package',
            "please find the correct STIX-shifter connector Python package to install. "
            "And report to Kestrel developers about this malicious package",
        )

    _logger.info(f'"{package_name}" verified as a STIX-shifter package.')


def check_module_availability(connector_name):
    try:
        importlib.import_module(
            "stix_shifter_modules." + connector_name + ".entry_point"
        )
    except:
        _logger.info(f'miss STIX-shifter connector "{connector_name}"')

        package_name = get_package_name(connector_name)
        _logger.debug(f"guess the connector package name: {package_name}")

        verify_package_origin(connector_name)

        stixshifter_version = pkg_resources.get_distribution("stix_shifter").version

        package_w_ver = package_name + "==" + stixshifter_version

        _logger.info(f'install Python package "{package_w_ver}".')
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package_w_ver]
            )
        except:
            _logger.info("package installation with 'pip' failed.")

        try:
            importlib.import_module(
                "stix_shifter_modules." + connector_name + ".entry_point"
            )
        except:
            raise DataSourceError(
                f'STIX-shifter connector for "{connector_name}" is not installed '
                f'and Kestrel failed to install the possible Python package "{package_name}"',
                "please manually install the corresponding STIX-shifter connector Python package.",
            )
