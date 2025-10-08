"""Sphinx configuration for xarray-ome documentation."""

project = "xarray-ome"
copyright = "2025, xarray-ome contributors"
author = "xarray-ome contributors"

extensions = [
    "myst_parser",
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

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_book_theme"
html_static_path: list[str] = []

html_theme_options = {
    "repository_url": "https://github.com/your-org/xarray-ome",
    "use_repository_button": True,
    "use_issues_button": True,
    "path_to_docs": "docs",
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "xarray": ("https://docs.xarray.dev/en/stable", None),
    "numpy": ("https://numpy.org/doc/stable", None),
}

myst_heading_anchors = 3
