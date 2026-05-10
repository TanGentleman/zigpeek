"""Prefetched docs bundle consumed by zigpeek's offline extra.

Layout: ``zigpeek_offline/<zig_version>/{sources.tar,langref.html}``.
Files are populated at wheel-build time by ``hatch_build.py``; importing
this module is just a way for ``importlib.resources`` to locate them.
"""
