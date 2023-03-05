# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import sys
from os.path import abspath
from os.path import dirname
from os.path import join

appdir = abspath(join(dirname(abspath(__file__)), "..", ".."))
sys.path.insert(0, appdir)

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "mmdb"
copyright = "2023, Leon Rendel"
author = "Leon Rendel"

version = "0.1.0"
release = "2023"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx-pydantic",
    "sphinx_rtd_theme",
    "sphinx.ext.autosummary",
]

templates_path = ["_templates"]
exclude_patterns = [".*.bak", ".*.tmp"]

language = "en"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# -- Options for todo extension ----------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/todo.html#configuration

todo_include_todos = True
