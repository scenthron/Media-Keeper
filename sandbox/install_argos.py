import argostranslate.package
import argostranslate.translate

# Download and install Argos Translate package
argostranslate.package.update_package_index()
available_packages = argostranslate.package.get_available_packages()
package_to_install = next(
    filter(
        lambda x: x.from_code == 'ru' and x.to_code == 'en', available_packages
    )
)
print("Downloading and installing", package_to_install)
argostranslate.package.install_from_path(package_to_install.download())
print("Installed!")
