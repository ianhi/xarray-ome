"""Sphinx configuration for xarray-ome documentation."""

project = "xarray-ome"
copyright = "2025, xarray-ome contributors"
author = "xarray-ome contributors"

extensions = [
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.mermaid",
    "sphinx_design",
]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]

nb_execution_mode = "cache"
nb_execution_timeout = 300
nb_execution_raise_on_error = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_logo = "_static/xarray-ome-logo.png"

html_theme_options = {
    "repository_url": "https://github.com/your-org/xarray-ome",
    "use_repository_button": True,
    "use_issues_button": True,
    "path_to_docs": "docs",
    "logo": {
        "image_light": "_static/xarray-ome-logo.png",
        "image_dark": "_static/xarray-ome-logo.png",
    },
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "xarray": ("https://docs.xarray.dev/en/stable", None),
    "numpy": ("https://numpy.org/doc/stable", None),
}

myst_heading_anchors = 3
